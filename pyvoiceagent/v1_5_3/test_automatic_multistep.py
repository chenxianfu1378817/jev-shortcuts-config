# -*- coding: utf-8 -*-
"""Offline full callback sequence: Notes -> Calendar -> task.finish."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

CORE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent_core_1_5_3.py'))
spec = importlib.util.spec_from_file_location('pyvoiceagent_multistep', CORE)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def decision(tool, title='', text='', start='', end='', notes=''):
    return {'tool': tool, 'reason': 'offline sequence',
            'title': title, 'text': text, 'datetime': start,
            'end_datetime': end, 'notes': notes, 'shortcut_id': ''}


class MultistepTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.before = (agent.DATA_DIR, agent.STATE_PATH, agent.MODULE_REGISTRY_PATH,
                       agent.RECOVERY_QUEUE_PATH, agent.REMINDER_LEDGER_PATH)
        agent.DATA_DIR = self.directory.name
        agent.STATE_PATH = os.path.join(self.directory.name, 'state.json')
        agent.MODULE_REGISTRY_PATH = os.path.join(self.directory.name, 'modules.json')
        agent.RECOVERY_QUEUE_PATH = os.path.join(self.directory.name, 'unresolved.json')
        agent.REMINDER_LEDGER_PATH = os.path.join(self.directory.name, 'ledger.json')
        agent.atomic_json(agent.MODULE_REGISTRY_PATH, {'modules': {
            'apple_notes.create': {'name':'PYAgentNotes', 'verified':True},
            'calendar.create': {'name':'PYAgentCalendar', 'verified':True}
        }})
        self.calls = []
        mod = types.ModuleType('shortcuts')
        mod.open_url = lambda url: self.calls.append(url)
        self.installed = patch.dict(sys.modules, {'shortcuts': mod})
        self.installed.start()
        self.approvals = patch.object(agent, 'prompt_alert', return_value=True)
        self.approvals.start()

    def tearDown(self):
        self.approvals.stop()
        self.installed.stop()
        (agent.DATA_DIR, agent.STATE_PATH, agent.MODULE_REGISTRY_PATH,
         agent.RECOVERY_QUEUE_PATH, agent.REMINDER_LEDGER_PATH) = self.before
        self.directory.cleanup()

    def init_task(self):
        return {'id': 'multistep', 'status':'ready', 'goal':'创建备忘录和日历',
                'created':agent.now_iso(), 'steps':0, 'events':[],
                'pending':None, 'final':'', 'error':''}

    def steps(self):
        first = (datetime.now().astimezone() + timedelta(days=3)).replace(hour=15, minute=0, second=0, microsecond=0)
        return iter([
            decision('apple_notes.create', title='会议备忘', text='测试跨 App 自动执行'),
            decision('calendar.create', title='例会安排', start=first.isoformat(),
                     end=(first + timedelta(minutes=30)).isoformat(), notes='准备资料'),
            decision('task.finish', text='三个步骤已完成')
        ])

    def test_two_matching_callbacks_finish_without_repeat(self):
        iterator = self.steps()
        with patch.object(agent, 'call_planner', side_effect=lambda _: next(iterator)):
            current = agent.drive_agent(self.init_task())
            self.assertEqual(current['status'], 'awaiting_callback')
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(current['pending']['tool'], 'apple_notes.create')
            first_token = current['pending']['token']
            agent.bridge_callback(first_token, 'ok')
            middle = agent.get_state()
            self.assertEqual(middle['status'], 'awaiting_callback')
            self.assertEqual(len(self.calls), 2)
            self.assertEqual(middle['pending']['tool'], 'calendar.create')
            agent.bridge_callback(middle['pending']['token'], 'ok')
        done = agent.get_state()
        self.assertEqual(done['status'], 'finished')
        self.assertIsNone(done['pending'])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([x['tool'] for x in done['events']],
                         ['apple_notes.create', 'calendar.create', 'task.finish'])
        self.assertIn('苹果备忘录', done['final'])
        self.assertIn('日历', done['final'])
        self.assertIn('仅收到工具成功报告', done['final'])

    def test_failed_callback_does_not_dispatch_second_step(self):
        iterator = self.steps()
        with patch.object(agent, 'call_planner', side_effect=lambda _: next(iterator)):
            state = agent.drive_agent(self.init_task())
            self.assertFalse(agent.bridge_callback(state['pending']['token'], 'failed'))
        paused = agent.get_state()
        self.assertEqual(paused['status'], 'needs_review')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(paused['pending']['tool'], 'apple_notes.create')


if __name__ == '__main__':
    unittest.main()
