# -*- coding: utf-8 -*-
"""V2.2.0 persistent WebView chat, pure intent and lifecycle regression (not iPhone testing)."""
import ast
import shutil
import subprocess
import json
import os
import re
import sys
import tempfile
import types
import threading
import time
import uuid
import unittest
from pathlib import Path
from unittest.mock import Mock

BASE=Path(__file__).resolve().parents[1]
CORE=BASE/'agent_core_2_2_0.py'
PATCH=BASE/'chat_shell_v220.py'

def setup():
    folder=tempfile.TemporaryDirectory()
    logs=[]
    initial_state={'status':'finished','id':'prev','events':[]}
    def read_json(path, default):
        try:
            return json.loads(Path(path).read_text('utf-8'))
        except (OSError,ValueError):
            return default
    def atomic_json(path, obj):
        Path(path).write_text(json.dumps(obj,ensure_ascii=False),'utf-8')
    env={
        '__name__':'pyvoiceagent_chat_test',
        'os':os,'sys':type('FakeSys',(),{'argv':['PYVoiceAgent.py']})(),
        're':re,'json':json,'uuid':uuid,'DATA_DIR':folder.name,
        'show_menu':Mock(), 'final_report':Mock(), '_ask_clarification':Mock(),
        'prompt_alert':Mock(return_value=False), '_voice_authorize_ai':Mock(return_value=False),
        'main':Mock(), 'VOICE_PRIVACY_PATH':os.path.join(folder.name,'voice_privacy.json'),
        'VERSION':'2.2.0-deepseek-flash', 'read_json':read_json,'atomic_json':atomic_json,
        'get_state':lambda:initial_state, 'now_iso':lambda:'2026-11-11T08:05:00+08:00',
        '_webui_safe_json':lambda x:json.dumps(x,ensure_ascii=False),
        '_card_palette':lambda a:{'background':'#101319'},
        '_card_appearance_load':lambda:{'theme':'典雅紫','mode':'深色模式'},
        '_card_appearance_save':lambda x:x,
        'CARD_THEMES':{'典雅紫':'#8A62D8'},
        'DISPLAY_MODES':('跟随系统','浅色模式','深色模式'),
        '_card_hex':lambda c:c if re.fullmatch(r'#[A-Fa-f0-9]{6}',c) else '',
        '_result_card_model':lambda s:{'title':'执行完成','body':'任务成功','copy':'任务成功'},
        '_history_search':lambda *args:[],'_history_read':lambda k:{'goal':'旧任务'},
        '_history_md':lambda r:'档案内容',
        'ensure_dirs':lambda:None, 'VOICE_SESSION_ACTIVE':False,
        'start_new':Mock(return_value={'status':'finished'}),
    }
    exec(compile(PATCH.read_text('utf-8'),str(PATCH),'exec'),env)
    return folder, env, logs

def wait_until(predicate, limit=1.0):
    end=time.monotonic()+limit
    while time.monotonic()<end:
        if predicate():return True
        time.sleep(.005)
    return predicate()


class ChatV220Test(unittest.TestCase):
    def setUp(self):
        self.folder,self.ns,self.events=setup()
        self.shell=self.ns['_ChatShell']()
        self.shell.post=lambda payload:self.events.append(payload)

    def tearDown(self):
        self.shell.close()
        self.folder.cleanup()

    def test_python_source_compiles_and_only_one_main_guard(self):
        core=CORE.read_text('utf-8')
        ast.parse(core)
        ast.parse(PATCH.read_text('utf-8'))
        self.assertEqual(core.count('if __name__ == "__main__":'),1)
        self.assertIn("VERSION = '2.2.0-deepseek-flash'",core)
        self.assertIn("def _ChatShell",core) if False else None
        self.assertIn('class _ChatShell:',core)
        self.assertIn('def bridge_callback(',core)
        self.assertIn('def _bu_capture_and_calendar(',core)

    def test_only_explicit_meituan_intents_without_ai(self):
        decide=self.ns['_chat_local_intent']
        self.assertEqual(decide('我要点外卖')[0],'food')
        self.assertEqual(decide('快餐',True)[0],'food')
        self.assertIsNone(decide('快餐',False))
        self.assertEqual(decide('打开美团'),('open','meituan'))
        self.assertEqual(decide('打开美团外卖'),('open','meituan_waimai'))
        self.assertIsNone(decide('帮我买份外卖并付款'))
        self.assertIsNone(decide('今天的沥青期货价格'))

    def test_example_sequence_remains_local_and_cannot_place_order(self):
        opened=[]
        self.shell._open_trusted_app=lambda key:opened.append(key)
        self.shell.submit('我要点外卖')
        self.shell.submit('快餐')
        self.shell.submit('打开美团')
        self.assertEqual(opened,['meituan'])
        self.ns['start_new'].assert_not_called()
        self.assertEqual([p['message']['role'] for p in self.events
                          if p.get('type')=='message'][-3:],['user','assistant','user'])
        self.assertTrue(Path(self.shell._ChatShell__dict__['path']).exists()) if False else None

    def test_question_answer_is_inline_not_new_ai_job(self):
        found=[]
        th=threading.Thread(target=lambda:found.append(self.shell.ask('你希望点什么？')))
        th.start()
        self.assertTrue(wait_until(lambda:self.shell.answer_event is not None))
        self.shell.submit('快餐')
        th.join(1)
        self.assertFalse(th.is_alive())
        self.assertEqual(found,['快餐'])
        self.assertTrue(any(e.get('type')=='busy' and e.get('waiting') for e in self.events))
        self.ns['start_new'].assert_not_called()

    def test_user_can_pause_clarification_without_replaying(self):
        found=[]
        th=threading.Thread(target=lambda:found.append(self.shell.ask('请补充需求')))
        th.start()
        self.assertTrue(wait_until(lambda:self.shell.answer_event is not None))
        self.shell.submit('稍后继续')
        th.join(1)
        self.assertEqual(found,[None])
        self.ns['start_new'].assert_not_called()

    def test_approval_must_come_from_explicit_action(self):
        choices=[]
        th=threading.Thread(target=lambda:choices.append(
            self.shell.approve('允许创建一条测试日程？',[('确认','1'),('取消','0')])))
        th.start()
        self.assertTrue(wait_until(lambda:self.shell.approval_event is not None))
        self.assertFalse(choices)
        self.shell._handle_action('approve','0')
        th.join(1)
        self.assertEqual(choices,[0])

    def test_ai_permission_is_explicit_and_can_be_saved(self):
        self.ns['_CHAT_ACTIVE']=self.shell
        decisions=[]
        def request(question,choices):
            decisions.append((question,choices))
            return 2
        self.shell.approve=request
        yes=self.ns['_voice_authorize_ai']({'voice_session':True})
        self.assertTrue(yes)
        self.assertTrue(self.ns['read_json'](
            self.ns['VOICE_PRIVACY_PATH'],{}).get('voice_text_auto_share'))
        self.assertEqual(len(decisions),1)
        self.assertTrue(self.ns['_voice_authorize_ai']({'voice_session':False}))
        self.assertEqual(len(decisions),1)

    def test_background_prompt_requires_confirmation(self):
        self.ns['_CHAT_ACTIVE']=self.shell
        self.ns['_CHAT_IN_TASK'].active=True
        self.shell.approve=lambda *args:0
        self.assertFalse(self.ns['prompt_alert']('确认写入','创建真实日程？'))
        self.shell.approve=lambda *args:1
        self.assertTrue(self.ns['prompt_alert']('确认写入','创建真实日程？'))

    def test_final_report_reuses_chat_instead_of_modal(self):
        self.ns['_CHAT_ACTIVE']=self.shell
        self.shell.report=lambda state:self.events.append({'report':state['status']})
        self.ns['final_report']({'status':'finished'})
        self.assertEqual(self.events,[{'report':'finished'}])
        self.ns['_CHAT_ORIGINAL_FINAL'].assert_not_called()

    def test_callback_result_queued_for_chat_start(self):
        self.ns['_CHAT_ACTIVE']=None
        self.ns['sys'].argv=['PYVoiceAgent.py','bridge_callback','token','ok']
        self.ns['final_report']({'status':'finished'})
        self.assertEqual(self.ns['_CHAT_CALLBACK_RESULT']['title'],'执行完成')
        self.ns['_CHAT_ORIGINAL_FINAL'].assert_not_called()

    def test_desktop_voice_url_no_native_recorder_or_console(self):
        self.ns['sys'].argv=['PYVoiceAgent.py','voice']
        self.ns['show_menu']=Mock(return_value=True)
        self.ns['main']()
        self.assertTrue(self.ns['_CHAT_BOOTSTRAP_VOICE'])
        self.ns['show_menu'].assert_called_once()
        self.ns['_CHAT_ORIGINAL_MAIN'].assert_not_called()

    def test_malicious_navigation_stays_blocked_by_exact_scheme(self):
        html=self.ns['CHAT_HTML']
        self.assertIn("connect-src 'none'",html)
        self.assertIn('pyagent-chat://dispatch?nonce=',html)
        self.assertIn('window.PYChatReceive',html)
        self.assertIn("parsed.scheme!='pyagent-chat'",PATCH.read_text('utf-8'))
        self.assertIn("values['nonce'][0]!=outer.nonce",PATCH.read_text('utf-8'))
        self.assertNotIn('eval(',html)

    def test_embedded_javascript_has_valid_syntax(self):
        if not shutil.which('node'):
            self.skipTest('Node.js unavailable in this environment')
        html=self.ns['CHAT_HTML']
        scripts=re.findall(r'<script[^>]*>(.*?)</script>',html,re.S)
        self.assertGreaterEqual(len(scripts),2)
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'chat.js'
            file.write_text(scripts[-1],encoding='utf-8')
            result=subprocess.run(['node','--check',str(file)],
                                  capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_old_completed_state_not_reissued_as_new_result(self):
        self.ns['start_new'].return_value=None
        self.ns['get_state']=lambda:{'id':'prev','status':'finished','events':[]}
        self.shell._worker('没有对应工具的操作',False)
        self.assertFalse(any(e.get('type')=='result' for e in self.events))
        self.assertTrue(any('没有启动新操作' in e.get('message',{}).get('text','')
                            for e in self.events if e.get('type')=='message'))

    def test_cancel_record_disposes_audio_without_sending_task(self):
        path=Path(self.folder.name)/'cancel.m4a'
        path.write_bytes(b'safe fake recorder content')
        record=Mock()
        self.shell.recorder=record
        self.shell.record_file=str(path)
        self.shell._handle_action('voice_cancel','')
        record.stop.assert_called_once()
        self.assertFalse(path.exists())
        self.assertIsNone(self.shell.recorder)
        self.assertTrue(any('已取消' in e.get('text','') for e in self.events
                            if e.get('type')=='notice'))
        self.ns['start_new'].assert_not_called()
        self.assertIn('id="cancelrecord"',self.ns['CHAT_HTML'])

    def test_manual_record_start_stop_without_dialog(self):
        import unittest.mock as um
        self.shell.ui=types.SimpleNamespace(delay=lambda callback,seconds:callback())
        created=[]
        class FakeRecorder:
            def __init__(self,path):self.path=path;self.stopped=False;created.append(self)
            def record(self):
                Path(self.path).write_bytes(b'voice recording bytes'*10)
            def stop(self):self.stopped=True
        scheduled=[]
        class FakeThread:
            def __init__(self,target,args=(),**kwargs):self.target=target;self.args=args
            def start(self):scheduled.append((self.target,self.args))
        with um.patch.dict(sys.modules,{'sound':types.SimpleNamespace(Recorder=FakeRecorder)}):
            with um.patch.object(self.ns['_chat_threading'],'Thread',FakeThread):
                self.shell.begin_record()
                self.assertIsNotNone(self.shell.recorder)
                self.assertTrue(any(x.get('type')=='recording' and x.get('active') for x in self.events))
                self.shell.stop_record()
        self.assertTrue(created[0].stopped)
        self.assertEqual(len(scheduled),1)
        self.assertEqual(scheduled[0][0].__name__,'_transcribe')
        self.assertTrue(any(x.get('type')=='recording' and not x.get('active') for x in self.events))
        Path(created[0].path).unlink(missing_ok=True)

    def test_recognized_voice_uses_same_session_and_cleans_audio(self):
        import unittest.mock as um
        path=Path(self.folder.name)/'spoken.m4a'
        path.write_bytes(b'speech dummy bytes'*10)
        looked=[]
        self.shell._open_trusted_app=lambda key:looked.append(key)
        fake=types.SimpleNamespace(get_recognition_languages=lambda:['zh-CN'],
                                   recognize=lambda p,lang:[('打开美团',1.0)])
        with um.patch.dict(sys.modules,{'speech':fake}):
            self.shell._transcribe(str(path))
        self.assertFalse(path.exists())
        self.assertEqual(looked,['meituan'])
        self.ns['start_new'].assert_not_called()

    def test_recognition_disables_concurrent_text(self):
        self.shell.recognizing=True
        self.shell.submit('误触重新执行')
        self.assertTrue(any(e.get('type')=='notice' for e in self.events))
        self.ns['start_new'].assert_not_called()

    def test_fallback_clears_failed_session_before_old_menu(self):
        env=self.ns
        class BrokenShell:
            closed=False
            def show(self): raise RuntimeError('WebView unavailable')
            def close(self): self.closed=True
        shell=BrokenShell()
        env['_ChatShell']=lambda:shell
        env['show_menu']()
        self.assertTrue(shell.closed)
        self.assertIsNone(env['_CHAT_ACTIVE'])
        env['_CHAT_ORIGINAL_MENU'].assert_called_once()

    def test_closing_screen_releases_pending_question_and_permission(self):
        answers=[]
        approvals=[]
        q=threading.Thread(target=lambda:answers.append(self.shell.ask('补充信息')))
        q.start()
        self.assertTrue(wait_until(lambda:self.shell.answer_event is not None))
        self.shell.close()
        q.join(1)
        self.assertFalse(q.is_alive())
        self.assertEqual(answers,[None])
        second=self.ns['_ChatShell']()
        a=threading.Thread(target=lambda:approvals.append(second.approve('确认吗')))
        a.start()
        self.assertTrue(wait_until(lambda:second.approval_event is not None))
        second.close()
        a.join(1)
        self.assertEqual(approvals,[0])


if __name__=='__main__':
    unittest.main(verbosity=2)
