"""Verify callback exceptions do not escape to Pythonista's debugger."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, PropertyMock, patch

CORE = Path(__file__).resolve().parents[1] / 'agent_core_2_3_5.py'
SPEC = importlib.util.spec_from_file_location('callback_errors', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class CallbackErrors(unittest.TestCase):
    def setUp(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            self.shell = core._ChatShell()
        self.shell.ui = Mock()

    def test_webview_lifecycle_exception_is_caught_without_private_details(self):
        holder = self.shell.holder = Mock()
        with patch.object(type(holder), 'on_screen', new_callable=PropertyMock, create=True,
                          side_effect=RuntimeError('private task text')), \
             patch.object(core, 'atomic_json') as save:
            self.shell.post({'type': 'recording', 'active': False})
            callback, _ = self.shell.ui.delay.call_args.args
            callback()
        report = save.call_args.args[1]
        self.assertEqual(report['stage'], 'webview_reply')
        self.assertEqual(report['type'], 'RuntimeError')
        self.assertNotIn('private task text', str(report))

    def test_dismissed_shell_does_not_run_delayed_action(self):
        work = Mock()
        self.shell._ui_later('voice_start', work, 0.08)
        callback, _ = self.shell.ui.delay.call_args.args
        self.shell.close()
        callback()
        work.assert_not_called()

    def test_schedule_failure_is_reported_without_escaping(self):
        self.shell.ui.delay.side_effect = RuntimeError('schedule failure')
        with patch.object(core, 'atomic_json') as save:
            self.shell._ui_later('voice_cancel', Mock(), 0.08)
        self.assertEqual(save.call_args.args[1]['stage'], 'voice_cancel.schedule')
