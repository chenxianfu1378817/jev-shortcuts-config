# -*- coding: utf-8 -*-
"""V1.9.6 actual engine regression for Pythonista recording and local archive.

Runs on CPython with a fake Recorder, no Apple APIs or real user data.
"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CORE = Path(__file__).resolve().parents[1] / 'agent_core_1_9_6.py'


class RecordAndArchiveRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = CORE.read_text(encoding='utf-8')
        compile(source, str(CORE), 'exec')
        spec = importlib.util.spec_from_file_location('pyvoice_agent_196_test', str(CORE))
        cls.engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.engine)
        cls.source = source

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        e = self.engine
        self.saved = {key: getattr(e, key) for key in
                      ('DATA_DIR','HISTORY_DIR','NOTES_DIR','STATE_PATH')}
        self.addCleanup(self.restore_paths)
        e.DATA_DIR = self.temp.name
        e.HISTORY_DIR = os.path.join(self.temp.name, 'history')
        e.NOTES_DIR = os.path.join(self.temp.name, 'notes')
        e.STATE_PATH = os.path.join(self.temp.name, 'current_task.json')

    def restore_paths(self):
        for key, value in self.saved.items():
            setattr(self.engine, key, value)

    @staticmethod
    def task(code='taskabc12345'):
        return {'id':code, 'created':'2026-11-10T21:20:00+08:00',
                'goal':'我要回家帮我导航', 'status':'finished',
                'final':'已整理导航指令', 'error':'', 'pending':None,
                'events':[{'tool':'text.respond','status':'ok','result':'完成'}]}

    def test_positional_record_duration_supported(self):
        class Recorder:
            recording = True
            meters = {'average':(-25.0,-26.0),'peak':(-2.0,-2.0)}
            def __init__(self):
                self.args = None
                self.stopped = False
            def record(self, value):
                self.args = value
            def stop(self):
                self.stopped = True
                self.recording = False
        recorder=Recorder()
        ticks=iter(x * 0.25 for x in range(1000))
        with mock.patch.object(self.engine.time, 'monotonic', side_effect=lambda:next(ticks)), \
             mock.patch.object(self.engine.time, 'sleep', return_value=None):
            state=self.engine._voice_record_auto('/no/real/file.m4a', recorder)
        self.assertEqual(state, 'recorded')
        self.assertEqual(recorder.args, self.engine.VOICE_LISTEN_LIMIT)
        self.assertTrue(recorder.stopped)

    def test_recording_stops_even_if_meter_fails(self):
        class Recorder:
            recording=True
            def __init__(self): self.stopped=False
            def record(self, limit): pass
            @property
            def meters(self): return {}
            def stop(self): self.stopped=True
        recorder=Recorder()
        with mock.patch.object(self.engine.time,'monotonic',side_effect=[1,2,3,4]):
            state=self.engine._voice_record_auto('ignored',recorder)
        self.assertEqual(state,'meter_unavailable')
        self.assertTrue(recorder.stopped)

    def test_first_history_archive_creates_month_directory(self):
        e=self.engine
        result=e._history_auto_record(self.task())
        self.assertTrue(result.endswith('task_taskabc12345.json'))
        self.assertTrue(os.path.isfile(result))
        md=result[:-5]+'.md'
        self.assertTrue(os.path.isfile(md))
        with open(result,encoding='utf-8') as stream:
            info=json.load(stream)
        self.assertEqual(info['goal'],'我要回家帮我导航')

    def test_state_and_archive_written_together(self):
        e=self.engine
        e.put_state(self.task())
        self.assertTrue(os.path.isfile(e.STATE_PATH))
        self.assertEqual(len(e._history_search('导航')),1)

    def test_next_task_does_not_overwrite_previous_archive(self):
        e=self.engine
        e.put_state(self.task())
        e.put_state(self.task('taskdef67890'))
        self.assertEqual(len(e._history_search('导航')),2)

    def test_data_not_uploaded_or_deleted(self):
        e=self.engine
        e.put_state(self.task())
        fname=os.path.join(e.DATA_DIR,'my_private_config.json')
        with open(fname,'w',encoding='utf-8') as stream:stream.write('preserve me')
        e.put_state(self.task('taskdef67890'))
        self.assertEqual(Path(fname).read_text('utf-8'),'preserve me')

    def test_bu_sources_still_present(self):
        s=self.source
        self.assertIn("if sys.argv[1] == 'bu_close'",s)
        self.assertIn("if sys.argv[1] == 'bridge_callback'",s)
        self.assertIn("if sys.argv[1] == 'voice'",s)
        self.assertIn("def _bu_calendar_compact_notes(",s)
        self.assertIn("payload['marker'] = ''",s)
        self.assertIn("def _history_auto_record(",s)
        self.assertIn("def immediate_check_and_update(",s)

if __name__ == '__main__':
    unittest.main(verbosity=2)
