"""Verify stale audio callbacks and repeated updater taps on the candidate."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

CORE = Path(__file__).resolve().parents[1] / 'agent_core_2_3_2.py'
SPEC = importlib.util.spec_from_file_location('lifecycle_candidate', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class LifecycleGuards(unittest.TestCase):
    def setUp(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            self.shell = core._ChatShell()
        self.shell.ui = Mock()
        self.shell.post = Mock()
        self.shell.message = Mock()
        self.shell._voice_trace = Mock()
        self.shell._transcribe = Mock()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'recording.m4a'

    def queue_recognition(self):
        self.path.write_bytes(b'test recording')
        self.shell.recorder = Mock()
        self.shell.record_file = str(self.path)
        self.shell.stop_record()
        callback, delay = self.shell.ui.delay.call_args.args
        self.assertEqual(delay, 0.7)
        return callback

    def test_cancel_invalidates_callback_and_removes_audio(self):
        callback = self.queue_recognition()
        self.shell.cancel_record()
        callback()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.shell.recognizing)
        self.shell._transcribe.assert_not_called()

    def test_close_invalidates_callback_and_removes_audio(self):
        callback = self.queue_recognition()
        self.shell.close()
        callback()
        self.assertFalse(self.path.exists())
        self.shell._transcribe.assert_not_called()

    def test_callback_consumes_audio_only_once(self):
        callback = self.queue_recognition()
        callback()
        callback()
        self.shell._transcribe.assert_called_once_with(str(self.path))

    def test_duplicate_update_taps_share_one_worker(self):
        with patch.object(core._chat_threading, 'Thread') as thread, \
             patch.object(core, 'immediate_check_and_update', side_effect=OSError):
            self.shell._handle_action('update', '')
            self.shell._handle_action('update', '')
            thread.assert_called_once()
            thread.call_args.kwargs['target']()
            self.assertFalse(self.shell.updating)
            self.shell._handle_action('update', '')
            self.assertEqual(thread.call_count, 2)
