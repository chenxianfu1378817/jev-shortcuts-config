import unittest
from system_module_preflight import verified_target, available_tools, preflight


class PreflightTests(unittest.TestCase):
    def test_no_module_installed(self):
        self.assertIsNone(verified_target('apple_notes.create', {}))
        self.assertEqual(preflight('apple_notes.create', {})['status'], 'unavailable')
        self.assertFalse(preflight('calendar.create', {})['needs_manual_review'])

    def test_name_without_validation_is_not_enough(self):
        state = {'modules': {'apple_notes.create': {'name': 'PYAgentNotes'}}}
        self.assertIsNone(verified_target('apple_notes.create', state))

    def test_mismatched_shortcut_name(self):
        state = {'modules': {'apple_notes.create': {'name': 'PYAgentHub', 'verified': True}}}
        self.assertIsNone(verified_target('apple_notes.create', state))

    def test_verified_module(self):
        state = {'modules': {'apple_notes.create': {'name': 'PYAgentNotes', 'verified': True}}}
        self.assertEqual(verified_target('apple_notes.create', state), 'PYAgentNotes')
        self.assertEqual(preflight('apple_notes.create', state)['status'], 'ready')

    def test_tool_list_excludes_unavailable(self):
        catalog = {'reminder.create': 1, 'apple_notes.create': 2, 'calendar.create': 3}
        self.assertEqual(list(available_tools(catalog, {})), ['reminder.create'])

    def test_bad_registry_fails_closed(self):
        for bad in [None, '', [], {'modules': []}]:
            self.assertEqual(preflight('calendar.create', bad)['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
