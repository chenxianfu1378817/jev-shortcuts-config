# -*- coding: utf-8 -*-
"""V1.8.5: foreground hands-free utterances and consent, with simulated iPhone APIs."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("core185", ROOT / "agent_core_1_8_5.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class Clock:
    def __init__(self):
        self.t = 0.0
    def monotonic(self):
        return self.t
    def sleep(self, amount):
        self.t += amount


class Recorder:
    def __init__(self, samples):
        self.samples = list(samples)
        self.index = 0
        self.recording = False
        self.stops = 0
        self.duration = None
    def record(self, duration=None):
        self.recording = True
        self.duration = duration
    @property
    def meters(self):
        i = self.index
        self.index += 1
        value = self.samples[min(i, len(self.samples)-1)]
        return {'average': (value, value), 'peak': (value + 3, value + 3)}
    def stop(self):
        self.stops += 1
        self.recording = False


class HandsFree185Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = tmp.name
        for name, value in [
            ('DATA_DIR', self.folder),
            ('STATE_PATH', str(Path(self.folder)/'state.json')),
            ('VOICE_PRIVACY_PATH', str(Path(self.folder)/'voice_privacy.json'))]:
            p = patch.object(agent, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(agent, 'VOICE_SESSION_ACTIVE', False)
        p.start()
        self.addCleanup(p.stop)

    def test_new_release_and_fixed_entry(self):
        self.assertEqual(agent.VERSION, '1.8.5-deepseek-flash')
        self.assertEqual(agent.APP_FILE, 'PYVoiceAgent.py')
        self.assertEqual(agent.MAX_CLARIFICATION_ROUNDS, 4)
        self.assertEqual(len(agent.APP_FEATURE_ROUTES), 22)

    def test_level_reads_pythonista_average_meter(self):
        self.assertEqual(agent._voice_level({'average': (-37.0, -24.0)}), -24.0)
        self.assertIsNone(agent._voice_level({'average': ('invalid',)}))
        self.assertIsNone(agent._voice_level({'peak': (-2, -2)}))
        self.assertIsNone(agent._voice_level(None))

    def _meter_run(self, samples):
        clock = Clock()
        recorder = Recorder(samples)
        with patch.object(agent.time, 'monotonic', clock.monotonic),\
             patch.object(agent.time, 'sleep', clock.sleep):
            outcome = agent._voice_record_auto('placeholder.m4a', recorder=recorder)
        return outcome, recorder, clock

    def test_detect_speech_then_silence_auto_stop(self):
        result, recorder, clock = self._meter_run([-61]*4 + [-18]*9 + [-60]*30)
        self.assertEqual(result, 'recorded')
        self.assertEqual(recorder.stops, 1)
        self.assertEqual(recorder.duration, agent.VOICE_LISTEN_LIMIT)
        self.assertLess(clock.t, 8.0)

    def test_no_speech_exits_without_recorded_flag(self):
        result, rec, clock = self._meter_run([-64]*100)
        self.assertEqual(result, 'no_speech')
        self.assertEqual(rec.stops, 1)
        self.assertLess(clock.t, 8.0)

    def test_missing_meter_stops_recorder(self):
        rec = Recorder([-58])
        rec.meters  # validate recorder interface itself
        class Bad(Recorder):
            @property
            def meters(self):
                return None
        clock = Clock()
        bad = Bad([-58])
        with patch.object(agent.time, 'monotonic', clock.monotonic),\
             patch.object(agent.time, 'sleep', clock.sleep):
            result = agent._voice_record_auto('placeholder.m4a', recorder=bad)
        self.assertEqual(result, 'meter_unavailable')
        self.assertEqual(bad.stops, 1)

    def test_listen_has_finite_hard_limit_even_with_constant_speech(self):
        result, rec, clock = self._meter_run([-60]*4 + [-16]*400)
        self.assertEqual(result, 'recorded')
        self.assertLessEqual(clock.t, 27.0)
        self.assertEqual(rec.stops, 1)

    def test_voice_question_automatically_listens_in_voice_session(self):
        agent.put_state({'status': 'needs_input', 'voice_session': True,
                         'clarify_question': '几点？', 'goal': '创建测试日历'})
        with patch.object(agent, 'input_voice', return_value='下午两点') as microphone,\
             patch.dict(sys.modules, {'dialogs': types.SimpleNamespace(alert=lambda *a, **k:
                    (_ for _ in ()).throw(AssertionError('Should not tap')))}):
            value=agent._ask_clarification('几点开始？')
        self.assertEqual(value, '下午两点')
        microphone.assert_called_once_with(hands_free=True, prompt='几点开始？')

    def test_text_mode_keeps_voice_and_text_fallback(self):
        agent.put_state({'status': 'needs_input', 'voice_session': False})
        fake = types.SimpleNamespace(alert=lambda *a, **kw: 1)
        with patch.dict(sys.modules, {'dialogs': fake}),\
             patch.object(agent, 'input_voice', return_value='两点') as record:
            self.assertEqual(agent._ask_clarification('几点？'), '两点')
        record.assert_called_once_with(hands_free=True, prompt='几点？')

    def test_initial_voice_launch_uses_auto_stop_mode(self):
        with patch.object(agent, 'input_voice', return_value='你好') as record,\
             patch.object(agent, 'start_new', return_value={}) as submit,\
             patch.object(sys, 'argv', ['PYVoiceAgent.py', 'voice']):
            agent.main()
        self.assertTrue(agent.VOICE_SESSION_ACTIVE)
        record.assert_called_once_with(hands_free=True)
        submit.assert_called_once_with('你好')

    def test_old_question_answer_goes_directly_to_existing_task(self):
        agent.put_state({'status':'needs_input', 'goal':'明天召开测试会议',
                         'voice_session': True, 'clarify_question':'几点？'})
        agent.VOICE_SESSION_ACTIVE = True
        with patch.object(agent, 'resume_clarification', return_value={'ok':True}) as resume,\
             patch.object(agent, '_cc_trigger', side_effect=AssertionError('new task?')),\
             patch.object(agent, '_maybe_auto_work_plan', side_effect=AssertionError('must not save')):
            self.assertEqual(agent.start_new('下午三点'), {'ok':True})
        self.assertEqual(resume.call_args.kwargs['initial_answer'], '下午三点')

    def test_spoken_cancel_does_not_run_ai(self):
        agent.put_state({'status':'needs_input', 'goal':'测试任务',
                         'voice_session': True, 'clarify_question':'哪一天？'})
        agent.VOICE_SESSION_ACTIVE = True
        with patch.object(agent, '_voice_speak'),\
             patch.object(agent, '_deepseek_request', side_effect=AssertionError('no AI')):
            state=agent.start_new('取消任务')
        self.assertEqual(state['status'], 'paused')

    def test_first_cloud_share_requires_explicit_opt_in(self):
        state={'goal':'随便说句话', 'voice_session':True}
        fake=types.SimpleNamespace(alert=lambda *a,**kw:1)
        with patch.dict(sys.modules, {'dialogs':fake}):
            self.assertTrue(agent._voice_authorize_ai(state))
        self.assertTrue(agent.read_json(agent.VOICE_PRIVACY_PATH,{}).get('voice_text_auto_share'))
        with patch.dict(sys.modules, {'dialogs':types.SimpleNamespace(alert=lambda *a, **kw:
                              (_ for _ in ()).throw(AssertionError('consent already stored')))}):
            self.assertTrue(agent._voice_authorize_ai(state))

    def test_cloud_share_rejection_does_not_write_permission(self):
        state={'goal':'测试', 'voice_session':True}
        fake=types.SimpleNamespace(alert=lambda *a,**kw:3)
        with patch.dict(sys.modules, {'dialogs':fake}):
            self.assertFalse(agent._voice_authorize_ai(state))
        self.assertFalse(Path(agent.VOICE_PRIVACY_PATH).exists())

    def test_recording_removed_after_transcription(self):
        class FakeSpeech:
            @staticmethod
            def get_recognition_languages():
                return ['zh-CN']
            @staticmethod
            def recognize(path, language=None):
                return [('安排测试提醒', [])]
        def simulated_record(path):
            Path(path).write_bytes(b'FAKE M4A FILE' * 20)
            return 'recorded'
        with patch.dict(sys.modules, {'speech': FakeSpeech}),\
             patch.object(agent, '_voice_speak'),\
             patch.object(agent, '_voice_record_auto', side_effect=simulated_record):
            words=agent.input_voice(hands_free=True)
        self.assertEqual(words, '安排测试提醒')
        self.assertEqual(list(Path(self.folder).glob('voice_*.m4a')), [])

    def test_silent_voice_never_calls_recognition(self):
        fake=types.SimpleNamespace(get_recognition_languages=lambda:[],
            recognize=lambda *args: (_ for _ in ()).throw(AssertionError('must not recognize silence')))
        with patch.dict(sys.modules, {'speech': fake}),\
             patch.object(agent, '_voice_speak'),\
             patch.object(agent, '_voice_record_auto', return_value='no_speech'):
            self.assertIsNone(agent.input_voice(hands_free=True))
        self.assertEqual(list(Path(self.folder).glob('voice_*.m4a')), [])

    def test_reporting_does_not_speak_contact_numbers(self):
        state={'status':'finished','voice_session':True,
               'events':[{'tool':'contacts.lookup','status':'ok',
                          'result':'张三：13800138000'}]}
        with patch.object(agent, '_voice_speak') as talk:
            agent._voice_report(state)
            agent._voice_report(state)
        self.assertEqual(talk.call_count,1)
        self.assertNotIn('13800138000',talk.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
