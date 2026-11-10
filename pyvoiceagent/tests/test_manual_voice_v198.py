# -*- coding: utf-8 -*-
"""V1.9.8: manual-only microphone with all older voice entry points.

Offline tests use a fake Pythonista sound Recorder and speech recognizer.
They do not claim to simulate actual iPhone microphone hardware.
"""
import importlib.util
import inspect
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

CORE = Path(__file__).resolve().parents[1] / 'agent_core_1_9_8.py'


class ManualVoiceV198Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = CORE.read_text('utf-8')
        compile(src, str(CORE), 'exec')
        spec = importlib.util.spec_from_file_location('pya_198', CORE)
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.source = src

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.saved_paths = {k:getattr(self.m,k) for k in ('DATA_DIR','NOTES_DIR','STATE_PATH')}
        self.addCleanup(self.restore_paths)
        self.m.DATA_DIR = self.temp.name
        self.m.NOTES_DIR = str(Path(self.temp.name)/'notes')
        self.m.STATE_PATH = str(Path(self.temp.name)/'current_task.json')
        self.recorder_instances = []
        instances = self.recorder_instances

        class FakeRecorder:
            def __init__(self, path):
                self.path = path
                self.recording = False
                self.stopped = False
                instances.append(self)
            def record(self, *args, **kwargs):
                if args or kwargs:
                    raise AssertionError('manual recorder must not accept a duration')
                self.recording = True
                with open(self.path, 'wb') as f:
                    f.write(b'AUDIO' * 80)
            def stop(self):
                self.recording = False
                self.stopped = True

        sound = types.ModuleType('sound')
        sound.Recorder = FakeRecorder
        dialogs = types.ModuleType('dialogs')
        def finish_alert(*args,**kwargs):
            self.assertTrue(instances[-1].recording)
            self.assertIn('完成',args)
            return 1
        dialogs.alert = finish_alert
        speech = types.ModuleType('speech')
        speech.get_recognition_languages = lambda:['en-US','zh-CN']
        speech.recognize = lambda path, lang=None: [('我要回家帮我导航', 1.0)]
        self.mocks = mock.patch.dict(sys.modules,{'sound':sound,'dialogs':dialogs,'speech':speech})
        self.mocks.start()
        self.addCleanup(self.mocks.stop)

    def restore_paths(self):
        for k,v in self.saved_paths.items():
            setattr(self.m,k,v)

    def test_hands_free_legacy_argument_does_not_auto_record(self):
        with mock.patch.object(self.m,'_voice_record_auto',side_effect=AssertionError('auto recorder forbidden')), \
             mock.patch.object(self.m,'_voice_speak',side_effect=AssertionError('do not speak before recording')):
            result = self.m.input_voice(hands_free=True)
        self.assertEqual(result, '我要回家帮我导航')
        self.assertEqual(len(self.recorder_instances), 1)
        self.assertTrue(self.recorder_instances[0].stopped)

    def test_normal_voice_still_allows_text_correction(self):
        with mock.patch.object(self.m,'ask_text',return_value='导航回家') as edit:
            result = self.m.input_voice(hands_free=False)
        self.assertEqual(result, '导航回家')
        edit.assert_called_once()

    def test_manual_recorder_has_no_timer_or_meter_loop(self):
        src = inspect.getsource(self.m.input_voice)
        self.assertNotIn('_voice_record_auto(',src)
        self.assertNotIn('_voice_speak(',src)
        self.assertNotIn('VOICE_END_SILENCE',src)
        self.assertIn('_manual_voice_record(path)',src)

    def test_voice_followup_never_auto_starts_microphone(self):
        self.m.get_state = lambda:{'voice_session':True}
        sys.modules['dialogs'].alert = lambda *args,**kwargs:2
        with mock.patch.object(self.m,'input_voice',side_effect=AssertionError('must not auto start')),\
             mock.patch.object(self.m,'ask_text',return_value='后天下午三点'):
            self.assertEqual(self.m._ask_clarification('几点钟？'),'后天下午三点')

    def test_followup_explicit_voice_option_uses_manual_voice(self):
        self.m.get_state = lambda:{'voice_session':True}
        sys.modules['dialogs'].alert = lambda *args,**kwargs:1
        with mock.patch.object(self.m,'input_voice',return_value='下午五点') as voice:
            self.assertEqual(self.m._ask_clarification('什么时候？'),'下午五点')
        voice.assert_called_once_with(hands_free=True,prompt='什么时候？')

    def test_followup_can_defer_without_mic(self):
        sys.modules['dialogs'].alert = lambda *args,**kwargs:3
        with mock.patch.object(self.m,'input_voice',side_effect=AssertionError('no recording')):
            self.assertIsNone(self.m._ask_clarification('哪个地址？'))

    def test_same_fixed_shortcut_url_routes_to_input_voice(self):
        self.assertIn("if sys.argv[1] == 'voice':",self.source)
        self.assertIn("txt = input_voice(hands_free=True)",self.source)
        self.assertIn("('voice', '语音执行', '手动录音",self.source)

    def test_legacy_automated_recorder_no_longer_called_by_entry(self):
        self.assertNotIn('_voice_record_auto(path)',self.source)
        self.assertIn("dialogs.alert('手动录音中'",self.source)

    def test_other_services_unmodified(self):
        for k in ('def bridge_callback(', 'def _bu_capture_and_calendar(',
                  'def _history_search(', 'def immediate_check_and_update(',
                  "if sys.argv[1] == 'bu_close'", "if sys.argv[1] == 'bridge_callback'"):
            self.assertIn(k,self.source)

if __name__ == '__main__':
    unittest.main(verbosity=2)
