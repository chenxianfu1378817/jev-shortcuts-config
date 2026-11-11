"""Pure CPython tests for V2.3.9 Pythonista native chat safe-mode.

Tests deliberately use mocks: they are not iPhone hardware or UIKit tests.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_3_9.py'
SPEC = importlib.util.spec_from_file_location('pyvoiceagent_native_v239', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class FakeView:
    def __init__(self, frame=(0, 0, 100, 100), **kwargs):
        self.frame = frame
        self.width = frame[2]
        self.height = frame[3]
        self.text = kwargs.get('text', '')
        self.title = kwargs.get('title', '')
        self.subviews = []
        self.enabled = True
        self.on_screen = False
        self.content_size = (0, 0)

    def add_subview(self, item):
        self.subviews.append(item)

    def present(self, *args, **kwargs):
        self.on_screen = True
        self.layout()

    def layout(self):
        pass

    def wait_modal(self):
        self.on_screen = False

    def close(self):
        self.on_screen = False


class NativeChatTests(unittest.TestCase):
    def setUp(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]), \
             patch.object(core, '_card_appearance_load',
                          return_value={'theme':'活力橙','mode':'浅色模式',
                                        'custom_color':''}):
            self.shell = core._NativeChatShell()
        self.shell._native_trace = Mock()
        self.shell._callback_error = Mock()
        self.shell._ui_later = lambda stage, fn, delay: fn()
        self.shell.ui = SimpleNamespace(delay=lambda fn, wait: fn())
        self.root = SimpleNamespace(entry=SimpleNamespace(text='你好'),
                                    send=SimpleNamespace(enabled=True),
                                    status=SimpleNamespace(text=''))
        self.shell._native_root = self.root

    def test_probe_does_not_execute_agent_or_touch_task_files(self):
        self.shell.submit = Mock()
        self.shell._native_send(diagnostic=True)
        self.shell.submit.assert_not_called()
        self.assertEqual(self.root.entry.text, '你好')
        self.assertIn('没有执行任何', self.root.status.text)
        self.shell._native_trace.assert_not_called()

    def test_native_send_runs_task_outside_button_callback(self):
        self.shell.submit = Mock()
        queue = []
        class ThreadStub:
            def __init__(self, target, **kwargs):
                queue.append(target)
            def start(self):
                pass
        with patch.object(core._chat_threading, 'Thread', ThreadStub):
            self.shell._native_send()
        self.shell.submit.assert_not_called()
        self.assertFalse(self.root.send.enabled)
        self.assertEqual(len(queue), 1)
        queue[0]()
        self.shell.submit.assert_called_once_with('你好')
        self.assertEqual(self.root.entry.text, '')
        self.assertTrue(self.root.send.enabled)
        self.assertEqual(self.shell._native_trace.call_args_list[0].args[0],
                         'native_send_received')

    def test_duplicate_tap_is_blocked_before_worker_runs(self):
        self.shell.submit = Mock()
        queue = []
        class ThreadStub:
            def __init__(self, target, **kwargs):
                queue.append(target)
            def start(self):
                pass
        with patch.object(core._chat_threading, 'Thread', ThreadStub):
            self.shell._native_send()
            self.shell._native_send()
        self.assertEqual(len(queue), 1)

    def test_worker_error_retains_text_and_no_auto_retry(self):
        self.shell.submit = Mock(side_effect=RuntimeError('mock failure'))
        queue = []
        class ThreadStub:
            def __init__(self, target, **kwargs):
                queue.append(target)
            def start(self):
                pass
        with patch.object(core._chat_threading, 'Thread', ThreadStub):
            self.shell._native_send()
        queue[0]()
        self.assertEqual(self.root.entry.text, '你好')
        self.shell.submit.assert_called_once()
        self.shell._callback_error.assert_called_once()

    def test_busy_state_retains_draft(self):
        self.shell.busy = True
        self.shell.submit = Mock()
        self.shell._native_send()
        self.shell.submit.assert_not_called()
        self.assertEqual(self.root.entry.text, '你好')

    def test_same_input_is_not_erased_when_user_edits(self):
        self.shell.submit = Mock()
        queue = []
        class ThreadStub:
            def __init__(self, target, **kwargs):
                queue.append(target)
            def start(self):
                pass
        with patch.object(core._chat_threading, 'Thread', ThreadStub):
            self.shell._native_send()
        self.root.entry.text = '你好，我补充一点'
        queue[0]()
        self.assertEqual(self.root.entry.text, '你好，我补充一点')

    def test_default_native_show_never_constructs_webview(self):
        fake_ui = SimpleNamespace(
            View=FakeView, Label=FakeView, TextView=FakeView, Button=FakeView,
            get_screen_size=lambda: (390, 760),
            convert_rect=lambda frame, parent, view: frame,
            delay=lambda func, seconds: func(),
            WebView=Mock(side_effect=AssertionError('WebView forbidden')))
        self.shell._native_root = None
        self.shell.ui = None
        with patch.dict(sys.modules, {'ui': fake_ui}):
            self.assertTrue(self.shell.show())
        fake_ui.WebView.assert_not_called()
        self.assertIsNone(self.shell.web)
        self.assertTrue(self.shell.closed)

    def test_all_eight_palette_choices_remain_available(self):
        self.assertEqual(len(core.CARD_THEMES), 8)
        self.assertTrue(all(x in core.CARD_THEMES for x in
                            ('活力橙','科技蓝','翡翠绿','典雅紫','中国红',
                             '玫瑰粉','深海青','石墨黑')))

    def test_native_source_does_not_load_html_or_url_scheme(self):
        source = (ROOT/'src'/'43_native_chat.py').read_text(encoding='utf-8')
        self.assertNotIn('web.load_html(', source)
        self.assertNotIn('ui.WebView(', source)
        self.assertNotIn('webview_should_start_load', source)
        self.assertIn('def _native_send(', source)
        self.assertIn('def show_menu():', source)


if __name__ == '__main__':
    unittest.main()
