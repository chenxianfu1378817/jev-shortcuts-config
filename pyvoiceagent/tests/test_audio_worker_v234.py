"""Exercise the WebView stop action, native recorder stub and recognition worker."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

CORE = Path(__file__).resolve().parents[1] / 'agent_core_2_3_4.py'
SPEC = importlib.util.spec_from_file_location('audio_worker', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class AudioWorkerTests(unittest.TestCase):
    def setUp(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            self.shell = core._ChatShell()
        self.shell.ui = Mock()
        self.shell.post = Mock()
        self.shell._voice_trace = Mock()
        self.shell.submit = Mock()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'recording.m4a'
        self.path.write_bytes(b'x' * 128)
        self.shell.record_file = str(self.path)
        self.recorder = self.shell.recorder = Mock()
        self.speech = Mock()
        self.speech.get_recognition_languages.return_value = ['zh-CN']
        self.speech.recognize.return_value = [('录音测试', 1.0)]

    def run_stop(self):
        with patch.object(core._chat_threading, 'Thread') as worker:
            self.shell._handle_action('voice_stop', '')
            self.shell._handle_action('voice_stop', '')
            worker.assert_called_once()
            self.recorder.stop.assert_not_called()
            with patch.object(self.shell.audio_stop_cancel, 'wait', side_effect=lambda t: self.shell.audio_stop_cancel.is_set()), \
                 patch.dict(sys.modules, {'speech': self.speech}):
                worker.call_args.kwargs['target']()

    def test_stop_and_recognize_without_native_timer(self):
        self.run_stop()
        self.recorder.stop.assert_called_once()
        self.speech.recognize.assert_called_once_with(str(self.path), 'zh-CN')
        self.shell.submit.assert_called_once_with('录音测试', from_voice=True)
        self.shell.ui.delay.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.shell.recognizing)

    def test_cancel_during_recognition_drops_result(self):
        def cancel(*args):
            self.shell.cancel_record()
            return [('不应提交', 1.0)]
        self.speech.recognize.side_effect = cancel
        self.run_stop()
        self.shell.submit.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.shell.recognizing)

    def test_close_during_native_stop_cleans_up_without_recognition(self):
        self.recorder.stop.side_effect = self.shell.close
        self.run_stop()
        self.speech.recognize.assert_not_called()
        self.shell.submit.assert_not_called()
        self.assertFalse(self.path.exists())
