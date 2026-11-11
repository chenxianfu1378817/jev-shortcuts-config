# -*- coding: utf-8 -*-
"""V2.2.1 legacy function navigation and spoken response regression (simulated)."""
import ast
import unittest
from pathlib import Path
from unittest.mock import Mock
from test_chat_shell_v220 import setup

ROOT=Path(__file__).resolve().parents[1]

class ChatV221Test(unittest.TestCase):
    def setUp(self):
        self.folder,self.ns,self.logs=setup()
        self.shell=self.ns['_ChatShell']()
        self.shell.post=lambda message:self.logs.append(message)
        self.ns['_voice_report']=Mock()

    def tearDown(self):
        self.shell.close()
        self.folder.cleanup()

    def test_v221_candidate_compiles_and_embeds_full_backend(self):
        code=(ROOT/'agent_core_2_2_1.py').read_text('utf-8')
        ast.parse(code)
        self.assertIn("VERSION = '2.2.1-deepseek-flash'",code)
        self.assertIn('def bridge_callback(',code)
        self.assertIn('def _bu_capture_and_calendar(',code)
        self.assertIn('def _ChatShell' if False else 'class _ChatShell',code)
        self.assertEqual(code.count('if __name__ == "__main__":'),1)

    def test_all_important_old_settings_reachable(self):
        html=self.ns['CHAT_HTML']
        for label in ('DeepSeek 配置','语音隐私授权','系统模块验证','查看工具库',
                      '恢复暂停任务','核验待处理操作','测试 DeepSeek',
                      '快捷指令回传测试','登记快捷指令','测试备忘录',
                      '测试日历','清除任务状态','检查在线更新'):
            with self.subTest(label=label):
                self.assertIn(label,html)

    def test_settings_only_allow_explicit_finite_actions(self):
        self.shell._handle_action('legacy','arbitrary_shell_script')
        self.assertTrue(any(e.get('type')=='notice' and '未授权' in e.get('text','')
                            for e in self.logs))

    def test_existing_settings_dispatch_reused_without_rewriting(self):
        invoked=[]
        self.ns['_V200_DISPATCH']=lambda action,payload:invoked.append((action,payload))
        self.ns['get_state']=lambda:{'status':'finished'}
        self.shell.ui=type('UI',(),{'delay':staticmethod(lambda func,t:func())})()
        self.shell._handle_action('legacy','ai_settings')
        self.assertEqual(invoked,[('ai_settings','')])
        self.assertTrue(any('设置操作' in e.get('text','')
                            for e in self.logs if e.get('type')=='notice'))

    def test_tool_library_stays_accessible(self):
        self.ns['_card_tool_rows']=lambda pattern:[('calendar.list','日历读取'),('text.respond','文本反馈')]
        self.shell._handle_action('tools','')
        match=next(e for e in self.logs if e.get('type')=='tools')
        self.assertEqual(len(match['items']),2)

    def test_voice_result_preserves_short_spoken_feedback(self):
        self.ns['_CHAT_ACTIVE']=self.shell
        self.shell.report=lambda state:self.logs.append({'result':state['status']})
        data={'status':'finished','voice_session':True}
        self.ns['final_report'](data)
        self.assertEqual(self.logs,[{'result':'finished'}])
        self.ns['_voice_report'].assert_called_once_with(data)
        self.ns['_CHAT_ORIGINAL_FINAL'].assert_not_called()

    def test_silent_text_result_does_not_speak(self):
        self.ns['_CHAT_ACTIVE']=self.shell
        self.shell.report=lambda state:None
        self.ns['final_report']({'status':'finished','voice_session':False})
        self.ns['_voice_report'].assert_not_called()

    def test_shortcut_callback_audio_and_result_reopen(self):
        self.ns['_CHAT_ACTIVE']=None
        self.ns['sys'].argv=['PYVoiceAgent.py','bridge_callback','safetoken','ok']
        data={'status':'finished','voice_session':True}
        self.ns['final_report'](data)
        self.assertEqual(self.ns['_CHAT_CALLBACK_RESULT']['title'],'执行完成')
        self.ns['_voice_report'].assert_called_once_with(data)

if __name__=='__main__':
    unittest.main(verbosity=2)
