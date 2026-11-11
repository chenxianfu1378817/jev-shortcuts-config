"""Chat/UI integration for the new isolated voice session; no microphone needed."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

CORE = Path(__file__).resolve().parents[1] / 'agent_core_2_3_6.py'
SPEC = importlib.util.spec_from_file_location('pyva_modular_current', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class VoiceChatIntegrationTests(unittest.TestCase):
    def setUp(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            self.shell = core._ChatShell()
        self.shell.post = Mock()
        self.shell._voice_trace = Mock()
        self.session = Mock()
        self.session.start.return_value = True
        self.session.stop.return_value = True
        self.patch_session = patch.object(core, '_VoiceSession', return_value=self.session)
        self.patch_session.start()
        self.addCleanup(self.patch_session.stop)

    def test_webview_start_and_stop_only_signal_audio_owner(self):
        self.shell.begin_record()
        self.assertTrue(self.shell.recorder)
        self.session.start.assert_called_once()
        self.shell._handle_action('voice_stop', '')
        self.shell._handle_action('voice_stop', '')
        self.session.stop.assert_called_once()
        self.assertTrue(self.shell.recognizing)
        self.session.cancel.assert_not_called()

    def test_cancel_does_not_stop_native_recorder_from_ui(self):
        self.shell.begin_record()
        self.shell.cancel_record()
        self.session.cancel.assert_called_once()
        self.assertIsNone(self.shell.recorder)
        self.shell.post.assert_any_call({'type': 'recording', 'active': False})

    def test_close_cancels_without_native_stop(self):
        self.shell.begin_record()
        self.shell.close()
        self.session.cancel.assert_called_once()
        self.assertTrue(self.shell.closed)

    def test_no_new_session_during_record_or_recognition(self):
        self.shell.begin_record()
        self.shell.begin_record()
        self.assertEqual(self.session.start.call_count, 1)
        self.shell._voice_progress('stopped')
        self.shell.begin_record()
        self.assertEqual(self.session.start.call_count, 1)

    def test_finished_session_restores_buttons(self):
        self.shell.begin_record()
        self.shell._voice_progress('stopped')
        self.shell._voice_done()
        self.assertIsNone(self.shell.recorder)
        self.assertFalse(self.shell.recognizing)
        self.assertIsNone(self.shell._voice_session)

    def test_voice_result_obeys_shell_closed_state(self):
        self.shell.submit = Mock()
        self.shell.begin_record()
        self.shell._voice_result('识别文字')
        self.shell.submit.assert_called_once_with('识别文字', from_voice=True)
        self.shell.close()
        self.shell._voice_result('不应执行')
        self.shell.submit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
