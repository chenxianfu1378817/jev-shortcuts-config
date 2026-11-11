"""Concurrent persistence and task-state guard regression for V2.3.5.

CPython mocks only; these tests do not exercise native iPhone dialogs.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[1] / 'agent_core_2_3_5.py'
SPEC = importlib.util.spec_from_file_location('safe_storage_v235', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class StorageSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.registry = root / 'shortcut_registry.json'
        self.task = root / 'current_task.json'
        self.task.write_text('{}', encoding='utf-8')
        for p in (
            patch.object(core, 'DATA_DIR', str(root)),
            patch.object(core, 'REGISTRY_PATH', str(self.registry)),
            patch.object(core, 'STATE_PATH', str(self.task)),
            patch.object(core, 'ensure_dirs'),
        ):
            p.start()
            self.addCleanup(p.stop)

    def item(self, number):
        return dict(id='tool{}'.format(number), name='测试工具{}'.format(number),
                    description='不执行真实快捷指令', aliases=['运行工具{}'.format(number)],
                    enabled=True, confirm=True, mode='launch', input_mode='none')

    def test_multiple_json_writers_never_share_temp_file(self):
        path = self.registry
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: core.atomic_json(str(path), {'writer': n}), range(120)))
        self.assertIn('writer', json.loads(path.read_text(encoding='utf-8')))
        self.assertEqual(list(path.parent.glob('.shortcut_registry.json.*.tmp')), [])

    def test_concurrent_registrations_cannot_lose_entries(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: core._reg_save(self.item(n), new_only=True), range(10)))
        stored = json.loads(self.registry.read_text(encoding='utf-8'))
        self.assertEqual(len(stored), 10)

    def test_corrupt_task_file_blocks_mutation(self):
        core._reg_save(self.item(1))
        original = self.registry.read_bytes()
        self.task.write_text('{"pending":', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '当前任务文件'):
            core._reg_save(self.item(2))
        with self.assertRaisesRegex(ValueError, '当前任务文件'):
            core._reg_change('tool1', delete=True)
        self.assertEqual(self.registry.read_bytes(), original)

    def test_pending_task_stages_fail_closed(self):
        core._reg_save(self.item(1))
        before = self.registry.read_bytes()
        for stage in ('awaiting_callback', 'needs_review', 'running', 'writing',
                      'paused', 'needs_input', 'replan_pending'):
            with self.subTest(stage=stage):
                self.task.write_text(json.dumps({'status': stage}), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, '未完成'):
                    core._reg_save(self.item(2))
        self.task.write_text(json.dumps({'status': 'ready', 'pending': {'token': 'x'}}),
                             encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '未完成'):
            core._reg_change('tool1', enabled=False)
        self.assertEqual(self.registry.read_bytes(), before)

    def test_failed_replace_leaves_existing_json_and_cleans_temporary_file(self):
        core.atomic_json(str(self.registry), {'baseline': 1})
        with patch.object(core.os, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                core.atomic_json(str(self.registry), {'baseline': 2})
        self.assertEqual(json.loads(self.registry.read_text(encoding='utf-8')),
                         {'baseline': 1})
        self.assertEqual(list(self.registry.parent.glob('.shortcut_registry.json.*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
