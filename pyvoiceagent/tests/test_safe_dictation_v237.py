"""Real hotfix contract: no native microphone entry in chat or legacy voice.

The fallback opens iOS text input; users tap the system keyboard Dictation
microphone themselves. This is deliberate until a native iOS crash is diagnosed.
"""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_3_7.py'
SPEC = importlib.util.spec_from_file_location('safe_dictation_237', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class SafeDictationTests(unittest.TestCase):
    def setUp(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            self.shell = core._ChatShell()
        self.shell.post = Mock()
        self.shell.ui = Mock()
        self.shell.message = Mock()

    def test_chat_voice_commands_never_touch_native_recorder(self):
        native = Mock()
        native.Recorder.side_effect = RuntimeError('hardware must remain disabled')
        with patch.dict(sys.modules, {'sound': native, 'speech': Mock()}):
            self.shell._handle_action('voice_start', '')
            self.shell._handle_action('voice_stop', '')
            self.shell._handle_action('voice_cancel', '')
            self.shell.begin_record()
        native.Recorder.assert_not_called()
        self.assertIsNone(self.shell._voice_session)
        self.assertIsNone(self.shell.recorder)
        self.assertFalse(self.shell.recognizing)
        self.shell.post.assert_called()

    def test_legacy_voice_entry_uses_empty_system_dictation_editor(self):
        dialogs = Mock()
        dialogs.text_dialog.return_value = '帮我查看今天的日程'
        native = Mock()
        native.Recorder.side_effect = RuntimeError('must not be used')
        with patch.dict(sys.modules, {'dialogs': dialogs, 'sound': native}):
            result = core.input_voice(hands_free=True)
        self.assertEqual(result, '帮我查看今天的日程')
        dialogs.text_dialog.assert_called_once_with('系统键盘麦克风听写', '')
        native.Recorder.assert_not_called()

    def test_empty_or_cancelled_dictation_does_not_create_a_task(self):
        dialogs = Mock()
        with patch.dict(sys.modules, {'dialogs': dialogs}):
            dialogs.text_dialog.return_value = None
            self.assertIsNone(core.input_voice())
            dialogs.text_dialog.return_value = '   '
            self.assertIsNone(core.input_voice())
        self.assertIsNone(self.shell._voice_session)

    def test_chat_mic_is_direct_focus_not_url_recording_bridge(self):
        html = core.CHAT_HTML
        self.assertIn("el('entry').focus();toast(", html)
        self.assertIn('键盘上的麦克风听写', html)
        start = html.index("el('mic').onclick=function()")
        end = html.index("};", start) + 2
        button = html[start:end]
        self.assertNotIn("bridge('voice_start'", button)
        self.assertNotIn("bridge('voice_stop'", button)
        self.assertNotIn('sound.Recorder', button)

    def test_bootstrapped_voice_action_is_safe(self):
        with patch.object(core, '_CHAT_BOOTSTRAP_VOICE', True):
            self.shell._handle_action('ready', '')
        self.assertTrue(self.shell.ready)
        self.assertIsNone(self.shell.recorder)
        self.assertFalse(self.shell.recognizing)

    def test_update_preserves_default_tooling_and_theme(self):
        source = CORE.read_text(encoding='utf-8')
        for term in ('def _deepseek_request(', 'def _reg_native_form(',
                     'def _local_calendar_list(', 'def _local_reminder_list(',
                     'def _bu_capture_and_calendar(', 'def _card_palette('):
            self.assertIn(term, source)


if __name__ == '__main__':
    unittest.main()
