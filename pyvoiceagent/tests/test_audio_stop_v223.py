# -*- coding: utf-8 -*-
"""V2.2.3 crash regression for Pythonista Recorder/WebView callback lifecycle.
Simulated mocked Recorder and speech, not a physical iOS run.
"""
import ast
import hashlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_chat_shell_v220 import setup
import test_chat_shell_v220 as base

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'chat_shell_v223.py'
ENGINE=ROOT/'agent_core_2_2_3.py'

class RecorderMock:
    def __init__(self,path):
        self.path=path
        self.started=False
        self.stopped=False
        self.calls=0
        self.error=None
    def record(self):
        self.started=True
        Path(self.path).write_bytes(b'fake audio'*30)
    def stop(self):
        self.calls+=1
        self.stopped=True
        if self.error:
            raise self.error

class AudioRegressionV223(unittest.TestCase):
    def setUp(self):
        old=base.PATCH
        base.PATCH=PATCH
        try:
            self.temp,self.env,self.events=setup()
        finally:
            base.PATCH=old
        self.shell=self.env['_ChatShell']()
        self.shell.post=lambda payload:self.events.append(payload)
        self.queue=[]
        self.shell.ui=types.SimpleNamespace(delay=lambda fn,seconds:self.queue.append((fn,seconds)))
        self.recorder=None
        def make(path):
            self.recorder=RecorderMock(path)
            return self.recorder
        self.sound_patch=patch.dict(sys.modules,{'sound':types.SimpleNamespace(Recorder=make)})
        self.sound_patch.start()

    def tearDown(self):
        self.sound_patch.stop()
        self.shell.close()
        self.temp.cleanup()

    def run_scheduled(self):
        fn,delay=self.queue.pop(0)
        fn()
        return delay

    def test_compile_engine_and_respect_old_updater_cap(self):
        s=ENGINE.read_text('utf-8')
        ast.parse(s)
        self.assertIn("VERSION = '2.2.3-deepseek-flash'",s)
        self.assertLessEqual(len(ENGINE.read_bytes()),350000)
        self.assertEqual(s.count('if __name__ == "__main__":'),1)
        self.assertIn(PATCH.read_text('utf-8'),s)
        for name in ('def bridge_callback(', 'def _bu_capture_and_calendar(',
                     'def _result_card_model(', 'def immediate_check_and_update('):
            self.assertIn(name,s)

    def test_stop_is_not_executed_in_webview_navigation_delegate(self):
        self.shell._handle_action('voice_start','')
        self.assertIsNone(self.recorder)
        self.assertEqual(len(self.queue),1)
        self.run_scheduled()
        self.assertTrue(self.recorder.started)
        self.assertFalse(self.recorder.stopped)
        self.shell._handle_action('voice_stop','')
        self.assertFalse(self.recorder.stopped)
        self.assertEqual(len(self.queue),1)
        self.assertTrue(self.shell.recognizing)
        self.shell._handle_action('voice_stop','')  # rapid double tap
        self.assertEqual(len(self.queue),1)
        delay=self.run_scheduled()
        self.assertAlmostEqual(delay,.08)
        self.assertTrue(self.recorder.stopped)
        self.assertEqual(self.recorder.calls,1)
        self.assertEqual(len(self.queue),1)
        self.assertAlmostEqual(self.queue[0][1],.7)

    def test_recognition_runs_after_stop_and_cleans_m4a(self):
        self.shell.begin_record()
        self.assertTrue(self.recorder.started)
        called=[]
        opened=[]
        fake_speech=types.SimpleNamespace(
            get_recognition_languages=lambda:['zh-CN'],
            recognize=lambda path,lang:called.append((path,lang)) or [('打开美团',[])])
        self.shell._open_trusted_app=lambda k:opened.append(k)
        self.shell._handle_action('voice_stop','')
        self.run_scheduled()
        self.assertTrue(self.recorder.stopped)
        self.assertFalse(called)
        path=self.recorder.path
        with patch.dict(sys.modules,{'speech':fake_speech}):
            self.run_scheduled()
        self.assertEqual(len(called),1)
        self.assertEqual(opened,['meituan'])
        self.assertFalse(Path(path).exists())
        self.assertFalse(self.shell.recognizing)
        self.env['start_new'].assert_not_called()
        stage=json.loads((Path(self.temp.name)/'voice_last_stage.json').read_text())
        self.assertEqual(stage['stage'],'idle')
        self.assertNotIn('text',stage)

    def test_error_in_recorder_stop_aborts_transcription_and_retains_ui(self):
        self.shell.begin_record()
        self.recorder.error=RuntimeError('simulated recorder stop error')
        path=self.recorder.path
        self.shell._handle_action('voice_stop','')
        self.run_scheduled()
        self.assertFalse(self.queue)
        self.assertFalse(Path(path).exists())
        self.assertFalse(self.shell.recognizing)
        self.assertTrue(any('停止录音失败' in e.get('message',{}).get('text','')
                            for e in self.events if e.get('type')=='message'))
        stage=json.loads((Path(self.temp.name)/'voice_last_stage.json').read_text())
        self.assertEqual(stage['stage'],'stop_failed')

    def test_recognize_failure_shows_message_and_no_system_task(self):
        self.shell.begin_record()
        self.shell._handle_action('voice_stop','')
        self.run_scheduled()
        fake=types.SimpleNamespace(get_recognition_languages=lambda:['zh-CN'],
                                   recognize=lambda *x:(_ for _ in ()).throw(
                                       RuntimeError('offline recognition failed')))
        with patch.dict(sys.modules,{'speech':fake}):
            self.run_scheduled()
        self.assertFalse(self.shell.recognizing)
        self.assertTrue(any('语音识别未完成' in e.get('message',{}).get('text','')
                            for e in self.events if e.get('type')=='message'))
        self.env['start_new'].assert_not_called()

    def test_cancel_does_not_invoke_transcription(self):
        self.shell.begin_record()
        self.shell._handle_action('voice_cancel','')
        self.assertFalse(self.recorder.stopped)
        self.run_scheduled()
        self.assertTrue(self.recorder.stopped)
        self.assertEqual(len(self.queue),0)
        self.assertFalse(Path(self.recorder.path).exists())
        self.env['start_new'].assert_not_called()

    def test_closing_view_before_delayed_recognition_does_not_recognize(self):
        self.shell.begin_record()
        self.shell._handle_action('voice_stop','')
        self.run_scheduled()
        path=self.recorder.path
        self.shell.close()
        fake=types.SimpleNamespace(get_recognition_languages=Mock(),
                                   recognize=Mock())
        with patch.dict(sys.modules,{'speech':fake}):
            self.run_scheduled()
        fake.recognize.assert_not_called()
        self.assertFalse(Path(path).exists())

    def test_no_new_microphone_before_previous_recognition(self):
        self.shell.begin_record()
        self.shell._handle_action('voice_stop','')
        self.run_scheduled()
        self.shell._handle_action('voice_start','')
        self.assertEqual(len(self.queue),1)

    def test_manifest_exact_match_when_published(self):
        manifest=json.loads((ROOT/'manifest.json').read_text('utf-8'))
        if manifest['version']!='2.2.3':
            self.skipTest('Candidate not yet official')
        data=ENGINE.read_bytes()
        self.assertEqual(len(data),manifest['size_bytes'])
        self.assertEqual(hashlib.sha256(data).hexdigest(),manifest['sha256'])

if __name__=='__main__':
    unittest.main(verbosity=2)
