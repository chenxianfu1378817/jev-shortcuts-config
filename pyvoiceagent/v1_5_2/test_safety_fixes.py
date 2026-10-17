# -*- coding: utf-8 -*-
"""Regression coverage for approval, late callbacks and existing reminders."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent_core_1_5_2.py'))
spec = importlib.util.spec_from_file_location('pyvoiceagent_safety', ENGINE)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class SafetyFixes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (a.DATA_DIR, a.STATE_PATH, a.RECOVERY_QUEUE_PATH, a.REMINDER_LEDGER_PATH)
        a.DATA_DIR = self.tmp.name
        a.STATE_PATH = os.path.join(self.tmp.name, 'state.json')
        a.RECOVERY_QUEUE_PATH = os.path.join(self.tmp.name, 'recovery.json')
        a.REMINDER_LEDGER_PATH = os.path.join(self.tmp.name, 'reminder_ledger.json')

    def tearDown(self):
        (a.DATA_DIR, a.STATE_PATH, a.RECOVERY_QUEUE_PATH, a.REMINDER_LEDGER_PATH) = self.old
        self.tmp.cleanup()

    def test_confirmation_has_a_real_cancel_button(self):
        dialogs = types.ModuleType('dialogs')
        captured = []
        def fake_alert(*args, **kwargs):
            captured.append(kwargs)
            return 2
        dialogs.alert = fake_alert
        with patch.dict(sys.modules, {'dialogs': dialogs}):
            self.assertFalse(a.prompt_alert('确认事项', '内容'))
        self.assertEqual(captured[-1]['hide_cancel_button'], False)

    def test_late_callback_does_not_interrupt_new_pending(self):
        old = dict(status='awaiting_callback', pending={
            'tool': 'apple_notes.create', 'title': '旧备忘录', 'token': 'OLDTOKEN',
            'marker': '[PYVoiceAgent:old:1]'})
        self.assertTrue(a.defer_current_pending(old))
        new = dict(id='newtask', goal='测试新日历', status='awaiting_callback',
                   created=a.now_iso(), steps=0, events=[], final='', error='',
                   pending={'tool':'calendar.create', 'title':'新的日历',
                            'token':'NEWTOKEN', 'marker':'[PYVoiceAgent:new:0]'})
        a.put_state(new)
        self.assertTrue(a.bridge_callback('OLDTOKEN', 'ok'))
        self.assertEqual(a.get_state()['status'], 'awaiting_callback')
        self.assertEqual(a.get_state()['pending']['token'], 'NEWTOKEN')
        self.assertEqual(a.read_recovery_queue()[0]['status'], 'reported_ok')
        self.assertFalse(a.read_recovery_queue()[0]['resolved'])

    def test_unknown_token_leaves_pending_unmodified(self):
        new = dict(id='n', goal='测试', status='awaiting_callback',
                   created=a.now_iso(), steps=0, events=[], final='', error='',
                   pending={'tool':'calendar.create', 'title':'日历',
                            'token':'EXPECTED', 'marker':'[PYVoiceAgent:n:0]'})
        a.put_state(new)
        self.assertFalse(a.bridge_callback('NOT_EXPECTED', 'ok'))
        self.assertEqual(a.get_state()['pending']['token'], 'EXPECTED')

    def test_same_task_reminder_must_read_real_ios_state(self):
        choice = dict(tool='reminder.create', title='已保存提醒',
                      datetime=(datetime.now().astimezone() + timedelta(days=2)).isoformat(),
                      end_datetime='', notes='测试', text='', shortcut_id='')
        fp = a.action_fingerprint(choice)
        state = dict(id='x', status='running', steps=1, events=[
            {'tool':'reminder.create', 'status':'ok',
             'params':{'fingerprint': fp}}],
            pending=None, goal='测试', created=a.now_iso(), final='', error='')
        fake = types.ModuleType('reminders')
        fake.get_reminders = lambda completed=False: []
        with patch.dict(sys.modules, {'reminders': fake}), patch.object(a, 'prompt_alert', return_value=False):
            result = a.run_tool(state, choice)
        self.assertEqual(result['status'], 'declined')
        self.assertNotEqual(result['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
