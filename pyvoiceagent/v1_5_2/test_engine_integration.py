# -*- coding: utf-8 -*-
"""End-to-end-ish offline integration tests for the actual V1.5 dev engine."""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch


ENGINE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'agent_core_1_5_2.py'))
spec = importlib.util.spec_from_file_location('pyvoiceagent_dev_engine', ENGINE_PATH)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def choice_for(tool, title='', when='', notes='', text=''):
    return dict(tool=tool, title=title, datetime=when, end_datetime='',
                notes=notes, text=text, reason='offline test', shortcut_id='')


def state_for():
    return dict(id='offline-task-1', goal='offline test', status='running',
                steps=0, events=[], pending=None, final='', error='')


class FakeReminder:
    store = []

    def __init__(self):
        self.title = ''
        self.notes = ''
        self.due_date = None
        self.alarms = []

    def save(self):
        self.store.append(self)


class FakeAlarm:
    def __init__(self):
        self.date = None


class DevEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (agent.DATA_DIR, agent.STATE_PATH, agent.REMINDER_LEDGER_PATH,
                    agent.MODULE_REGISTRY_PATH, agent.RECOVERY_QUEUE_PATH, agent.NOTES_DIR)
        agent.DATA_DIR = self.tmp.name
        agent.STATE_PATH = os.path.join(self.tmp.name, 'current_task.json')
        agent.REMINDER_LEDGER_PATH = os.path.join(self.tmp.name, 'reminder_ledger.json')
        agent.MODULE_REGISTRY_PATH = os.path.join(self.tmp.name, 'system_modules.json')
        agent.RECOVERY_QUEUE_PATH = os.path.join(self.tmp.name, 'unresolved_writes.json')
        agent.NOTES_DIR = os.path.join(self.tmp.name, 'notes')
        FakeReminder.store = []
        self.mock_reminders = types.ModuleType('reminders')
        self.mock_reminders.Reminder = FakeReminder
        self.mock_reminders.Alarm = FakeAlarm
        self.mock_reminders.get_reminders = lambda completed=False: list(FakeReminder.store)
        self.reminder_patch = patch.dict(sys.modules, {'reminders': self.mock_reminders})
        self.reminder_patch.start()

    def tearDown(self):
        self.reminder_patch.stop()
        (agent.DATA_DIR, agent.STATE_PATH, agent.REMINDER_LEDGER_PATH,
         agent.MODULE_REGISTRY_PATH, agent.RECOVERY_QUEUE_PATH, agent.NOTES_DIR) = self.old
        self.tmp.cleanup()

    def future(self):
        return (datetime.now().astimezone() + timedelta(days=2)).replace(
            hour=15, minute=0, second=0, microsecond=0).isoformat()

    def test_uninstalled_notes_avoids_dispatch_and_pending(self):
        before = state_for()
        result = agent.run_tool(before, choice_for('apple_notes.create', '测试', text='正文'))
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(before['pending'])
        self.assertEqual(agent.available_tool_catalog().get('apple_notes.create'), None)

    def test_unverified_name_is_not_installed(self):
        agent.atomic_json(agent.MODULE_REGISTRY_PATH,
                          {'modules': {'apple_notes.create': {'name': 'PYAgentNotes'}}})
        self.assertIsNone(agent.verified_system_module('apple_notes.create'))

    def test_registered_module_whitelist(self):
        agent.atomic_json(agent.MODULE_REGISTRY_PATH,
                          {'modules': {'apple_notes.create':
                                       {'name': 'PYAgentNotes', 'verified': True}}})
        self.assertEqual(agent.verified_system_module('apple_notes.create'), 'PYAgentNotes')
        self.assertIsNone(agent.verified_system_module('calendar.create'))

    def test_note_payload_does_not_include_marker_in_body(self):
        state = state_for()
        choice = choice_for('apple_notes.create', '采购记录', text='采购记录\n\n沥青价格待核实')
        payload, encoded, token = agent.bridge_payload(state, choice, 'apple_notes.create', 'PYAgentNotes')
        self.assertEqual(payload['note_body'], '采购记录\n\n沥青价格待核实')
        self.assertNotIn('[PYVoiceAgent:', payload['note_body'])
        self.assertIn('[PYVoiceAgent:', payload['marker'])
        self.assertTrue(token)

    def test_reminder_content_clean_and_verified(self):
        d = self.future()
        with patch.object(agent, 'prompt_alert', return_value=True):
            result = agent.run_tool(state_for(), choice_for('reminder.create',
                                    '测试提醒', when=d, notes='仅用户备注'))
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(result['verified'])
        self.assertEqual(result['outcome'], 'created')
        self.assertEqual(len(FakeReminder.store), 1)
        self.assertEqual(FakeReminder.store[0].notes, '仅用户备注')

    def test_second_reminder_skips_existing(self):
        d = self.future()
        with patch.object(agent, 'prompt_alert', return_value=True):
            a = agent.run_tool(state_for(), choice_for('reminder.create', '测试提醒', d, '备注'))
            b = agent.run_tool(state_for(), choice_for('reminder.create', '测试提醒', d, '备注'))
        self.assertEqual(a['outcome'], 'created')
        self.assertEqual(b['outcome'], 'existing')
        self.assertEqual(len(FakeReminder.store), 1)

    def test_migrate_old_pending_and_continue(self):
        old = state_for()
        old['status'] = 'awaiting_callback'
        old['pending'] = {'tool': 'apple_notes.create', 'title': '旧备忘录',
                          'token': 'old-token', 'marker': '[PYVoiceAgent:old:4]'}
        agent.put_state(old)
        with patch.object(agent, 'api_key', return_value='test-key'), \
             patch.object(agent, 'prompt_alert', return_value=True), \
             patch.object(agent, 'plan_once', side_effect=lambda st: st):
            new = agent.start_new('创建一个不同的本地笔记')
        self.assertIsNotNone(new)
        queue = agent.read_recovery_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['title'], '旧备忘录')
        self.assertEqual(new['goal'], '创建一个不同的本地笔记')

    def test_uncertain_duplicate_blocked_but_unrelated_allowed(self):
        old = state_for()
        old['status'] = 'awaiting_callback'
        old['pending'] = {'tool': 'apple_notes.create', 'title': '旧备忘录',
                          'token': 'old-token', 'marker': '[PYVoiceAgent:old:4]'}
        self.assertTrue(agent.defer_current_pending(old))
        dup = agent.run_tool(state_for(), choice_for('apple_notes.create', '旧备忘录', text='正文'))
        self.assertEqual(dup['status'], 'unavailable')  # gate before journal when module uninstalled
        self.assertTrue(agent.deferred_duplicate(agent.read_recovery_queue(),
                                                'apple_notes.create', '旧备忘录'))
        self.assertFalse(agent.deferred_duplicate(agent.read_recovery_queue(),
                                                 'calendar.create', '不同标题'))

    def test_late_callback_archived_without_claiming_verified(self):
        old = state_for()
        old['status'] = 'awaiting_callback'
        old['pending'] = {'tool': 'apple_notes.create', 'title': '旧备忘录',
                          'token': 'old-token', 'marker': '[PYVoiceAgent:old:4]'}
        agent.defer_current_pending(old)
        agent.put_state(state_for())
        self.assertTrue(agent.bridge_callback('old-token', 'ok'))
        self.assertEqual(agent.read_recovery_queue()[0]['status'], 'reported_ok')
        self.assertFalse(agent.read_recovery_queue()[0]['resolved'])

    def test_missing_module_plan_does_not_fake_success(self):
        state = state_for()
        decision = choice_for('apple_notes.create', '测试', text='正文')
        finish = choice_for('task.finish', text='已经全部完成')
        iterator = iter([decision, finish])
        state = agent.drive_agent(state, planner=lambda _: next(iterator))
        self.assertEqual(state['status'], 'finished')
        self.assertIn('功能未就绪', state['final'])
        self.assertNotIn('已核验 苹果备忘录', state['final'])


if __name__ == '__main__':
    unittest.main()
