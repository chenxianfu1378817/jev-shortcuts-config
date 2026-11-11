"""Exercise candidate registration against a temporary registry."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_2_8.py'
SPEC = importlib.util.spec_from_file_location('registration_candidate', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        temp = self.enter_temp()
        self.path = Path(temp) / 'registry.json'
        for name, value in [('REGISTRY_PATH', str(self.path)), ('get_state', lambda: {})]:
            override = patch.object(core, name, value)
            override.start()
            self.addCleanup(override.stop)
        self.item = dict(id='work_tool', name='工作台', description='打开工作台',
                         aliases=['打开工作台'])

    def enter_temp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return temp.name

    def test_registration_is_local_and_stale_bridge_is_inert(self):
        self.assertIn('href="#reg-form">登记快捷指令', core.CHAT_HTML)
        self.assertIn('id="reg-form"', core.CHAT_HTML)
        self.assertNotIn('data-legacy="add_shortcut"', core.CHAT_HTML)
        shell = Mock()
        with patch.object(core, '_REG_OLD_ACTION') as legacy:
            core._ChatShell._handle_action(shell, 'legacy', 'add_shortcut')
            legacy.assert_not_called()
        shell.post.assert_called_once()
        self.assertFalse(self.path.exists())

    def test_save_toggle_delete_preserve_other_entries_and_unknown_fields(self):
        old = {'bad_tool': 'legacy invalid value',
               'work_tool': {'name': '工作台', 'description': '旧描述', 'extra': 42}}
        self.path.write_text(json.dumps(old))
        core._reg_save(self.item)
        core._reg_change('work_tool', enabled=False)
        stored = json.loads(self.path.read_text())
        self.assertEqual(stored['bad_tool'], old['bad_tool'])
        self.assertEqual(stored['work_tool']['extra'], 42)
        self.assertFalse(stored['work_tool']['enabled'])
        core._reg_change('work_tool', delete=True)
        self.assertEqual(json.loads(self.path.read_text()), {'bad_tool': old['bad_tool']})

    def test_malformed_registry_is_left_intact(self):
        self.path.write_bytes(b'{"interrupted":')
        with self.assertRaises(ValueError):
            core._reg_save(self.item)
        self.assertEqual(self.path.read_bytes(), b'{"interrupted":')

    def test_toggle_cannot_enable_duplicate_alias(self):
        core._reg_save(self.item)
        core._reg_save(dict(self.item, id='other_tool', enabled=False))
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            core._reg_change('other_tool', enabled=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_pending_callback_blocks_registry_mutation(self):
        core._reg_save(self.item)
        before = self.path.read_bytes()
        with patch.object(core, 'get_state', return_value={'status': 'awaiting_callback'}):
            with self.assertRaises(ValueError):
                core._reg_change('work_tool', delete=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_deferred_launch_failure_clears_busy(self):
        core._reg_save(dict(self.item, confirm=False))
        match = core._reg_match('打开工作台')
        shell = Mock(closed=False)
        queued = []
        shell.ui.delay.side_effect = lambda callback, delay: queued.append(callback)

        def inline_thread(target, **kwargs):
            return Mock(start=target)

        with patch.object(core._chat_threading, 'Thread', side_effect=inline_thread):
            core._reg_invoke(shell, '打开工作台', match)
        self.assertEqual(len(queued), 1)
        with patch.object(core, 'put_state', side_effect=OSError('disk write failed')):
            queued[0]()
        shell.status.assert_called_with(False, False)
        shell.message.assert_called_once()
        self.assertIn('未确认', shell.message.call_args.args[1])

    def test_candidate_fits_legacy_update_limit(self):
        self.assertLessEqual(CORE.stat().st_size, 350000)
