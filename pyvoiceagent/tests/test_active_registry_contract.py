"""No-side-effect registry regression tests against the active manifest engine.

Rebinds all state paths to a temporary directory; never calls iOS dialogs.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]


class ActiveRegistryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest_file = PROJECT / "manifest.json"
        if not manifest_file.exists():
            raise unittest.SkipTest("no manifest in isolated local workspace")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        path = PROJECT / manifest["path"]
        spec = importlib.util.spec_from_file_location("active_pyvoiceagent_contract", path)
        cls.core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.core)

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.registry_path = Path(folder.name) / "shortcut_registry.json"
        for override in (
            patch.object(self.core, "REGISTRY_PATH", str(self.registry_path)),
            patch.object(self.core, "ensure_dirs"),
            patch.object(self.core, "get_state", return_value={}),
        ):
            override.start()
            self.addCleanup(override.stop)
        self.item = {
            "id": "work_tool", "name": "打开工作台", "description": "本地测试工具",
            "aliases": ["打开工作台"], "mode": "launch", "input_mode": "none",
            "enabled": True, "confirm": True,
        }

    def test_new_tool_stores_data_without_launch(self):
        self.assertEqual(self.core._reg_save(self.item, new_only=True), "work_tool")
        saved = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertTrue(saved["work_tool"]["confirm"])

    def test_disabled_item_remains_after_another_save(self):
        self.core._reg_save(dict(self.item, enabled=False))
        self.core._reg_save(dict(self.item, id="other_tool", aliases=["其他工具"]))
        raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertFalse(raw["work_tool"]["enabled"])
        self.assertIn("other_tool", raw)

    def test_preserves_unknown_future_user_fields(self):
        self.core._reg_save(self.item)
        raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        raw["work_tool"]["future_attribute"] = {"keep": True}
        self.registry_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        self.core._reg_save(dict(self.item, description="修改描述"))
        updated = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["work_tool"]["future_attribute"], {"keep": True})

    def test_corrupted_file_not_silently_overwritten(self):
        self.registry_path.write_text('{"broken":', encoding="utf-8")
        before = self.registry_path.read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.core._reg_save(self.item)
        self.assertEqual(self.registry_path.read_bytes(), before)

    def test_pending_callback_blocks_changes(self):
        self.core._reg_save(self.item)
        before = self.registry_path.read_bytes()
        with patch.object(self.core, "get_state", return_value={"status": "awaiting_callback"}):
            with self.assertRaises(ValueError):
                self.core._reg_save(dict(self.item, description="不应覆盖"))
        self.assertEqual(self.registry_path.read_bytes(), before)

    def test_duplicate_id_rejected_without_overwrite(self):
        self.core._reg_save(self.item, new_only=True)
        before = self.registry_path.read_bytes()
        with self.assertRaises(ValueError):
            self.core._reg_save(dict(self.item, name="名称变更"), new_only=True)
        self.assertEqual(self.registry_path.read_bytes(), before)

    def test_enable_rejects_duplicate_alias(self):
        self.core._reg_save(self.item)
        self.core._reg_save(dict(self.item, id="other_tool", enabled=False))
        with self.assertRaises(ValueError):
            self.core._reg_change("other_tool", enabled=True)
        raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertFalse(raw["other_tool"]["enabled"])


if __name__ == "__main__":
    unittest.main()
