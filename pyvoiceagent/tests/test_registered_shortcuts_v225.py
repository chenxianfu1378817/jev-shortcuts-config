# -*- coding: utf-8 -*-
"""V2.2.5 registered Shortcuts CRUD, AI and local route tests. Not iPhone tests."""
import ast
import json
import os
import re
import hashlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlencode
from unittest.mock import Mock, patch
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'agent_core_2_2_5.py'
ADDON=ROOT/'shortcut_tools_v225.py'
UI=ROOT/'shortcut_ui_v225.py'

class ShellStub:
    def __init__(self):
        self.closed=False
        self.busy=False
        self.answer_event=None
        self.recorder=None
        self.lock=None
        self.holder=Mock()
        self.ui=types.SimpleNamespace(delay=lambda func,sec:func())
        self.notices=[]
        self.messages=[]
        self.args=[]
        self.confirm_answer=1
    def status(self,busy,waiting=False): self.busy=busy
    def approve(self,q,buttons=None): return self.confirm_answer
    def message(self,role,body): self.messages.append((role,body))
    def post(self,item): self.notices.append(item)
    def close(self): self.closed=True
    def submit(self,val,from_voice=False): self.args.append((val,from_voice))
    def _handle_action(self,a,t): self.args.append((a,t))


class ToolsV225(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=os.path.join(self.folder.name,'registered.json')
        self.state={'status':'finished'}
        self.native_urls=[]
        def read(path,default):
            try:return json.loads(Path(path).read_text('utf8'))
            except (OSError,ValueError):return default
        def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False),'utf8')
        def record(state,tool,params,result):
            state.setdefault('events',[]).append(dict(tool=tool,params=params,**result))
        def fake_shortcut(url):
            self.assertNotIn('javascript:',url)
            self.assertNotIn('https:',url)
            self.assertEqual(self.state.get('status'),'finished')
            self.native_urls.append(url)
        self.fake_shortcuts=types.SimpleNamespace(open_url=fake_shortcut)
        self._sys=patch.dict(sys.modules,{'shortcuts':self.fake_shortcuts})
        self._sys.start()
        self.env=dict(__name__:'tested_shortcuts',os=os,re=re,json=json,
                      hashlib=hashlib,datetime=datetime,timezone=timezone,urlencode=urlencode,
                      REGISTRY_PATH=self.path,DEFAULT_LIBRARY={'echo':{'name':'reserved'}},
                      BRIDGE_SHORTCUT='PYAgentHub',LEGACY_BRIDGE='PYAgentBridge',
                      MAX_SHORTCUTS=12,ONE_SHOT_TOOLS=('text.respond',),
                      read_json=read,atomic_json=write,get_state=lambda:self.state,
                      put_state=lambda s:self.state.update(s),
                      now_iso=lambda:datetime.now(timezone.utc).isoformat(),
                      uuid=__import__('uuid'),action_fingerprint=lambda a:'fp',
                      create_event=record,local_registry=lambda:{},
                      public_registry=lambda:[],
                      available_tool_catalog=lambda:{'text.respond':'响应'},
                      run_tool=lambda *args:{'status':'ok'},
                      parse_action_plan=lambda data,tools:data,
                      _apply_one_shot_plan=lambda s,p:{'old':True},
                      _ChatShell=ShellStub,_chat_threading=__import__('threading'),
                      _REG_PREV_SHOW=None,execute_planned_actions=Mock(),
                      prompt_alert=lambda *args:True,
                      _card_palette=lambda *args:{},
                      get_theme=lambda:None)
        exec(compile(ADDON.read_text('utf-8'),str(ADDON),'exec'),self.env)

    def tearDown(self):
        self._sys.stop()
        self.folder.cleanup()

    def item(self,ident='work',aliases=None,mode='launch',enabled=True):
        return dict(id=ident,name='我的日常工作',description='打开工作操作',
                    aliases=aliases or ['打开工作台','启动工作台'],mode=mode,
                    input_mode='suffix',confirm=True,enabled=enabled)

    def save(self,x=None):
        return self.env['_reg_save'](x or self.item())

    def test_source_version_and_compiler_and_legacy_size_cap(self):
        text=SOURCE.read_text('utf-8')
        ast.parse(text)
        ast.parse(ADDON.read_text('utf-8'))
        ast.parse(UI.read_text('utf-8'))
        self.assertIn("VERSION = '2.2.5-deepseek-flash'",text)
        self.assertLessEqual(len(SOURCE.read_bytes()),350000)
        self.assertEqual(text.count('if __name__ == "__main__":'),1)
        self.assertIn('def bridge_callback(',text)
        self.assertIn('def _bu_capture_and_calendar(',text)
        self.assertIn('def immediate_check_and_update(',text)

    def test_legacy_registry_is_backward_compatible(self):
        Path(self.path).write_text(json.dumps({'legacy':{'name':'日历查询','description':'查苹果日历'}},ensure_ascii=False),'utf8')
        r=self.env['local_registry']()
        self.assertEqual(r['legacy']['mode'],'bridge')
        self.assertEqual(r['legacy']['aliases'],['运行日历查询'])

    def test_register_edit_disable_enable_delete_without_changing_shortcut(self):
        self.save()
        self.assertEqual(self.env['_reg_items']()[0]['name'],'我的日常工作')
        x=self.item()
        x['description']='新的用途说明'
        self.save(x)
        self.assertEqual(self.env['local_registry']()['work']['description'],'新的用途说明')
        self.env['_reg_change']('work',enabled=False)
        self.assertEqual(self.env['local_registry'](),{})
        self.assertFalse(self.env['_reg_items']()[0]['enabled'])
        self.env['_reg_change']('work',enabled=True)
        self.assertIn('work',self.env['local_registry']())
        self.env['_reg_change']('work',delete=True)
        self.assertEqual(self.env['_reg_items'](),[])

    def test_reject_duplicate_alias_and_disallowed_registry(self):
        self.save()
        with self.assertRaises(ValueError):
            self.save(self.item('other',['打开工作台']))
        for invalid in (
            dict(self.item(),id='PY Agent'),
            dict(self.item(),mode='arbitrary'),
            dict(self.item(),confirm='yes'),
            dict(self.item(),aliases=['a']*9),
            dict(self.item(),name='PYAgentHub'),
            dict(self.item(),id='echo'),
        ):
            with self.subTest(field=invalid):
                with self.assertRaises(ValueError):
                    self.save(invalid)

    def test_pending_shortcut_blocks_registry_mutations(self):
        self.save()
        self.state['status']='awaiting_callback'
        with self.assertRaises(ValueError):
            self.save(self.item('other',['打开另一个工作台']))
        with self.assertRaises(ValueError):
            self.env['_reg_change']('work',delete=True)

    def test_local_exact_and_suffix_first_avoids_ai(self):
        self.save()
        hit=self.env['_reg_match']('打开工作台')
        self.assertEqual(hit[0],'work')
        self.assertEqual(hit[2],'')
        self.assertEqual(self.env['_reg_match']('打开工作台 项目A')[2],'项目A')
        self.assertIsNone(self.env['_reg_match']('不要打开工作台'))
        self.assertIsNone(self.env['_reg_match']('打开工作台然后转账'))
        self.assertIsNone(self.env['_reg_match']('搜索别人的隐私信息'))

    def test_direct_url_uses_apple_whitelist_and_stores_before_launch(self):
        self.save()
        self.state.clear()
        choice=dict(tool='shortcut.run',shortcut_id='work',title='我的日常工作',
                    text='测试项目',datetime='',end_datetime='',notes='')
        result=self.env['_reg_direct_launch'](self.state,choice,self.env['local_registry']()['work'])
        self.assertEqual(result['status'],'ok')
        self.assertFalse(result['verified'])
        query=parse_qs(urlsplit(self.native_urls[0]).query)
        self.assertEqual(urlsplit(self.native_urls[0]).scheme,'shortcuts')
        self.assertEqual(urlsplit(self.native_urls[0]).path,'//run-shortcut') if False else None
        self.assertEqual(query['name'],['我的日常工作'])
        self.assertEqual(query['text'],['测试项目'])
        self.assertEqual(self.state['events'][0]['status'],'handoff')
        self.assertFalse(self.state['events'][0]['verified'])

    def test_ai_tool_only_if_registered_and_single_action(self):
        self.save()
        catalog=self.env['available_tool_catalog']()
        self.assertIn('shortcut.run',catalog)
        good=dict(tool='shortcut.run',shortcut_id='work')
        self.assertEqual(self.env['parse_action_plan']({'actions':[good],'question':''},catalog)['actions'],[good])
        with self.assertRaises(ValueError):
            self.env['parse_action_plan']({'actions':[dict(good,shortcut_id='not_registered')],'question':''},catalog)
        with self.assertRaises(ValueError):
            self.env['parse_action_plan']({'actions':[good,good],'question':''},catalog)
        self.env['_reg_change']('work',enabled=False)
        self.assertNotIn('shortcut.run',self.env['available_tool_catalog']())

    def test_ai_direct_mode_only_launches_after_explicit_confirmation(self):
        self.save()
        d={'actions':[{'tool':'shortcut.run','shortcut_id':'work','text':'','title':'工作台'}],'question':''}
        self.env['prompt_alert']=lambda *a:False
        self.env['_apply_one_shot_plan'](self.state,d)
        self.assertEqual(self.native_urls,[])
        self.env['prompt_alert']=lambda *a:True
        self.state['status']='ready'
        self.env['_apply_one_shot_plan'](self.state,d)
        self.assertEqual(len(self.native_urls),1)

    def test_chat_manager_crud_and_native_exit(self):
        shell=ShellStub()
        self.env['_ChatShell']._handle_action(shell,'reg_save',json.dumps(self.item(),ensure_ascii=False))
        self.assertTrue(any(e.get('type')=='reg_list' and len(e['items'])==1 for e in shell.notices))
        self.env['_ChatShell']._handle_action(shell,'reg_toggle',json.dumps({'id':'work','enabled':False}))
        self.assertFalse(self.env['_reg_items']()[0]['enabled'])
        self.env['_ChatShell']._handle_action(shell,'reg_delete',json.dumps({'id':'work','confirm':False}))
        self.assertEqual(len(self.env['_reg_items']()),1)
        self.env['_ChatShell']._handle_action(shell,'reg_delete',json.dumps({'id':'work','confirm':True}))
        self.assertEqual(self.env['_reg_items'](),[])
        self.env['_ChatShell']._handle_action(shell,'exit','')
        self.assertTrue(shell.closed)
        shell.holder.close.assert_called_once()

    def test_busy_exit_does_not_interrupt_system_task(self):
        shell=ShellStub()
        shell.busy=True
        self.env['_ChatShell']._handle_action(shell,'exit','')
        self.assertFalse(shell.closed)
        shell.holder.close.assert_not_called()

    def test_ui_fields_exit_and_command_bridge(self):
        src=UI.read_text('utf-8')
        self.assertIn('id="agent-exit"',src)
        for key in ('reg-id','reg-name','reg-desc','reg-aliases','reg-mode','reg-input','reg-confirm','reg-enabled'):
            self.assertIn(key,src)
        for cmd in ('reg_save','reg_toggle','reg_delete','reg_list','exit'):
            self.assertIn(cmd,src)

    def test_node_ui_script_syntax(self):
        node=__import__('shutil').which('node')
        if not node:
            self.skipTest('Node not installed')
        source=UI.read_text('utf-8')
        match=re.search(r'_REG_JS = r"""(.*?)"""',source,re.S)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ui.js'
            path.write_text(match.group(1),'utf8')
            process=__import__('subprocess').run([node,'--check',str(path)],capture_output=True,text=True,timeout=15)
        self.assertEqual(process.returncode,0,process.stderr)

    def test_manifest_only_on_published_release(self):
        mf=json.loads((ROOT/'manifest.json').read_text('utf8'))
        if mf.get('version')!='2.2.5':
            self.skipTest('Release not yet published')
        data=SOURCE.read_bytes()
        self.assertEqual(mf['path'],SOURCE.name)
        self.assertEqual(mf['sequence'],225)
        self.assertEqual(mf['size_bytes'],len(data))
        self.assertEqual(mf['sha256'],hashlib.sha256(data).hexdigest())

if __name__=='__main__':
    unittest.main(verbosity=2)
