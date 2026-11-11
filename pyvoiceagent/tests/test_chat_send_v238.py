"""Regression tests for iPhone IME-safe WebView chat dispatch in V2.3.8.

No real iOS UI, DeepSeek, Apple shortcuts or data writes are invoked.
"""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'agent_core_2_3_8.py'
SPEC = importlib.util.spec_from_file_location('pyva_send_v238', ENGINE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class ChatSendTests(unittest.TestCase):
    def setUp(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            self.shell = core._ChatShell()
        self.shell.ui = Mock()
        self.shell.post = Mock()
        self.shell.submit = Mock()
        self.shell._send_trace = Mock()
        self.scheduled = []
        def defer(stage, callback, delay):
            self.scheduled.append((stage, callback, delay))
        self.shell._ui_later = defer

    def test_send_does_not_process_inside_navigation_callback(self):
        self.shell._receive_bridge('send', '支付宝付款码')
        self.shell.submit.assert_not_called()
        self.assertEqual(len(self.scheduled), 1)
        self.assertEqual(self.scheduled[0][0], 'bridge_send_schedule')
        self.assertTrue(self.shell._send_pending)
        self.shell.post.assert_not_called()
        with patch.object(core._chat_threading, 'Thread') as thread:
            target = None
            def constructor(**kwargs):
                nonlocal target
                target = kwargs['target']
                class FakeThread:
                    def start(self): target()
                return FakeThread()
            thread.side_effect = constructor
            self.scheduled.pop(0)[1]()
        self.shell.submit.assert_called_once_with('支付宝付款码')
        self.assertFalse(self.shell._send_pending)
        self.shell.post.assert_any_call({'type':'send_ack','ok':True})

    def test_duplicate_while_queued_is_not_run_twice(self):
        self.shell._receive_bridge('send', '你好')
        self.shell._receive_bridge('send', '你好')
        self.assertEqual(len(self.scheduled), 1)
        self.shell.post.assert_any_call({'type':'send_ack','ok':False})

    def test_duplicate_recent_send_is_rejected(self):
        self.shell._receive_bridge('send', '测试')
        self.shell._send_pending = False
        self.shell._receive_bridge('send', '测试')
        self.assertEqual(len(self.scheduled), 1)
        self.shell.post.assert_any_call({'type':'send_ack','ok':False})

    def test_busy_task_keeps_draft(self):
        self.shell.busy = True
        self.shell._receive_bridge('send', '查日历')
        self.assertEqual(len(self.scheduled), 0)
        self.shell.post.assert_any_call({'type':'send_ack','ok':False})

    def test_worker_start_failure_is_negative_ack(self):
        self.shell._receive_bridge('send', '你好')
        with patch.object(core._chat_threading, 'Thread',
                          side_effect=RuntimeError('thread refused')):
            with patch.object(self.shell, '_callback_error'):
                self.scheduled[0][1]()
        self.shell.post.assert_any_call({'type':'send_ack','ok':False})
        self.assertFalse(self.shell._send_pending)

    def test_normal_bridge_actions_deferred_too(self):
        self.shell._handle_action = Mock()
        self.shell._receive_bridge('theme', '活力橙')
        self.shell._handle_action.assert_not_called()
        self.assertEqual(self.scheduled[0][0], 'bridge_theme')
        self.scheduled[0][1]()
        self.shell._handle_action.assert_called_once_with('theme', '活力橙')

    def test_js_avoids_keyboard_blur_and_ime_send_race(self):
        source = (ROOT / 'src' / '43_chat.py').read_text(encoding='utf-8')
        block = source.split('function send(){', 1)[1].split('function themeButtons()', 1)[0]
        self.assertNotIn("el('entry').blur()", block)
        self.assertNotIn("el('entry').value=''", block)
        self.assertIn("if(composing)", block)
        self.assertIn("bridge('send',v)", block)
        self.assertIn("setTimeout(function()", block)
        self.assertIn("m.type==='send_ack'", source)
        self.assertIn("el('entry').value=''", source)
        self.assertIn("compositionstart", source)
        self.assertIn("compositionend", source)
        self.assertIn("outer._receive_bridge(action, text)", source)
        delegate = source.split("class Bridge:", 1)[1].split("web.delegate = Bridge()", 1)[0]
        self.assertNotIn("outer._handle_action(action,text)", delegate)

    def test_send_trace_never_captures_user_text(self):
        from tempfile import TemporaryDirectory
        import json
        with TemporaryDirectory() as folder:
            with patch.object(core, 'DATA_DIR', folder):
                self.shell._send_trace = core._ChatShell._send_trace.__get__(self.shell)
                self.shell._send_trace('processing')
                record = json.loads((Path(folder) / 'send_last_stage.json').read_text(encoding='utf-8'))
                self.assertEqual(record['stage'], 'processing')
                self.assertEqual(set(record), {'version', 'stage', 'at'})


if __name__ == '__main__':
    unittest.main()
