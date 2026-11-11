"""Isolated single-owner audio lifecycle tests. No Pythonista modules required."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'src' / '39_voice_session.py'
SPEC = importlib.util.spec_from_file_location('audio_session_v236', SOURCE)
voice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(voice)


class AudioBackend:
    def __init__(self, folder, failing_stop=False):
        self.folder = folder
        self.failing_stop = failing_stop
        self.record_thread = None
        self.stop_thread = None
        self.stops = 0
        self.started = threading.Event()
        self.stop_done = threading.Event()

    def recorder(self, path):
        backend = self
        class Recorder:
            def record(self):
                backend.record_thread = threading.get_ident()
                Path(path).write_bytes(b'0' * 256)
                backend.started.set()

            def stop(self):
                backend.stops += 1
                backend.stop_thread = threading.get_ident()
                backend.stop_done.set()
                if backend.failing_stop:
                    raise RuntimeError('native audio error')
        return Recorder()


class VoiceSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = AudioBackend(self.temp.name)
        self.texts = []
        self.errors = []
        self.stages = []
        self.progress = []
        self.done = threading.Event()
        self.spoken = Mock()
        self.spoken.get_recognition_languages.return_value = ['zh-CN']
        self.spoken.recognize.return_value = [('你好', [])]
        self.sound = Mock()
        self.sound.Recorder.side_effect = self.backend.recorder

    def session(self):
        return voice._VoiceSession(self.temp.name, self.stages.append,
                                   self.progress.append, self.texts.append,
                                   self.errors.append, self.done.set)

    def wait(self):
        self.assertTrue(self.done.wait(6), 'audio thread failed to finish')

    def test_record_stop_and_release_on_one_worker(self):
        with patch.dict(sys.modules, {'sound': self.sound, 'speech': self.spoken}):
            session = self.session()
            self.assertTrue(session.start())
            self.assertTrue(self.backend.started.wait(3))
            self.assertTrue(session.stop())
            self.assertFalse(session.stop())
            self.wait()
        self.assertEqual(self.texts, ['你好'])
        self.assertEqual(self.backend.record_thread, self.backend.stop_thread)
        self.assertNotEqual(self.backend.stop_thread, threading.get_ident())
        self.assertEqual(self.backend.stops, 1)
        self.assertIn('recording', self.progress)
        self.assertIn('stopped', self.progress)
        self.assertEqual(list(Path(self.temp.name).glob('*.m4a')), [])

    def test_cancel_before_start_never_executes_task(self):
        with patch.dict(sys.modules, {'sound': self.sound, 'speech': self.spoken}):
            session = self.session()
            self.assertTrue(session.start())
            session.cancel()
            self.wait()
        self.assertEqual(self.texts, [])
        self.assertEqual(list(Path(self.temp.name).glob('*.m4a')), [])

    def test_cancel_during_recognition_drops_text(self):
        recognized = threading.Event()
        release = threading.Event()
        def transcribe(*args):
            recognized.set()
            release.wait(5)
            return [('不应提交', [])]
        self.spoken.recognize.side_effect = transcribe
        with patch.dict(sys.modules, {'sound': self.sound, 'speech': self.spoken}):
            session = self.session()
            session.start()
            self.assertTrue(self.backend.started.wait(3))
            session.stop()
            self.assertTrue(recognized.wait(4))
            session.cancel()
            release.set()
            self.wait()
        self.assertEqual(self.texts, [])

    def test_native_stop_exception_is_not_retried(self):
        self.backend.failing_stop = True
        with patch.dict(sys.modules, {'sound': self.sound, 'speech': self.spoken}):
            session = self.session()
            session.start()
            self.assertTrue(self.backend.started.wait(3))
            session.stop()
            self.wait()
        self.assertEqual(self.backend.stops, 1)
        self.assertEqual(self.texts, [])
        self.assertEqual(self.errors, ['RuntimeError'])


if __name__ == '__main__':
    unittest.main()
