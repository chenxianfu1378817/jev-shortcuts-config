# -*- coding: utf-8 -*-
"""Validate module setup without actually launching iOS Shortcuts."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

CORE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent_core_1_5_2.py'))
spec = importlib.util.spec_from_file_location('dev_agent_enroll', CORE)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class ModuleEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.original = [agent.DATA_DIR, agent.STATE_PATH,
                         agent.MODULE_REGISTRY_PATH, agent.RECOVERY_QUEUE_PATH,
                         agent.NOTES_DIR]
        agent.DATA_DIR = self.dir.name
        agent.STATE_PATH = os.path.join(self.dir.name, 'current_task.json')
        agent.MODULE_REGISTRY_PATH = os.path.join(self.dir.name, 'system_modules.json')
        agent.RECOVERY_QUEUE_PATH = os.path.join(self.dir.name, 'unresolved_writes.json')
        agent.NOTES_DIR = os.path.join(self.dir.name, 'notes')
        self.opened = []
        dialogs = types.ModuleType('dialogs')
        dialogs.list_dialog = lambda title, options: options[0]
        shortcuts = types.ModuleType('shortcuts')
        shortcuts.open_url = lambda url: self.opened.append(url)
        self.modules = patch.dict(sys.modules, {'dialogs': dialogs, 'shortcuts': shortcuts})
        self.modules.start()

    def tearDown(self):
        self.modules.stop()
        (agent.DATA_DIR, agent.STATE_PATH, agent.MODULE_REGISTRY_PATH,
         agent.RECOVERY_QUEUE_PATH, agent.NOTES_DIR) = self.original
        self.dir.cleanup()

    def test_setup_requires_actual_callback_and_user_check(self):
        with patch.object(agent, 'prompt_alert', return_value=True):
            state = agent.install_system_module()
        self.assertEqual(state['status'], 'awaiting_callback')
        self.assertTrue(self.opened)
        self.assertIsNone(agent.verified_system_module('apple_notes.create'))
        with patch.object(agent, 'pretty_status', return_value=None):
            self.assertTrue(agent.bridge_callback(state['pending']['token'], 'ok'))
        self.assertEqual(agent.verified_system_module('apple_notes.create'), 'PYAgentNotes')
        self.assertIsNone(agent.verified_system_module('calendar.create'))

    def test_not_confirmed_keeps_module_disabled(self):
        dialogs = sys.modules['dialogs']
        dialogs.list_dialog = lambda title, options: (options[-1]
            if title == '模块安装验收' else options[0])
        with patch.object(agent, 'prompt_alert', return_value=True):
            state = agent.install_system_module()
        with patch.object(agent, 'pretty_status', return_value=None):
            self.assertTrue(agent.bridge_callback(state['pending']['token'], 'ok'))
        self.assertIsNone(agent.verified_system_module('apple_notes.create'))

    def test_second_enrollment_does_not_create_duplicate(self):
        agent.atomic_json(agent.MODULE_REGISTRY_PATH,
                          {'modules': {'apple_notes.create':
                                       {'name': 'PYAgentNotes', 'verified': True}}})
        with patch.object(agent, 'prompt_alert', return_value=True):
            result = agent.install_system_module()
        self.assertIsNone(result)
        self.assertEqual(self.opened, [])

    def test_wrong_callback_token_never_enables_module(self):
        with patch.object(agent, 'prompt_alert', return_value=True):
            agent.install_system_module()
        self.assertFalse(agent.bridge_callback('fake-token', 'ok'))
        self.assertIsNone(agent.verified_system_module('apple_notes.create'))


if __name__ == '__main__':
    unittest.main()
