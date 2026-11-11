"""Verify the shortcut manager preserves the existing chat window."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_3_3.py'
SPEC = importlib.util.spec_from_file_location('registry_return', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class RegistryReturnTests(unittest.TestCase):
    def test_open_and_dismiss_without_replacing_chat(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            shell = core._ChatShell()
        holder = shell.holder = Mock()
        web = shell.web = Mock()
        queued = []

        with patch.object(core, 'add_shortcut_registration') as manager, \
             patch.object(core._chat_threading, 'Thread',
                          side_effect=lambda target, **kwargs: Mock(start=lambda: queued.append(target))):
            shell.request_registry()
            shell.request_registry()
            self.assertEqual(len(queued), 1)
            queued.pop()()
            manager.assert_called_once()
            self.assertFalse(shell.registry_requested)
            shell.request_registry()
            queued.pop()()
            self.assertEqual(manager.call_count, 2)
        holder.close.assert_not_called()
        web.eval_js.assert_not_called()
        self.assertFalse(shell.closed)

    def test_dismissed_chat_skips_queued_registry_open(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            shell = core._ChatShell()
        queued = []
        with patch.object(core, 'add_shortcut_registration') as manager, \
             patch.object(core._chat_threading, 'Thread',
                          side_effect=lambda target, **kwargs: Mock(start=lambda: queued.append(target))):
            shell.request_registry()
            shell.close()
            queued.pop()()
            manager.assert_not_called()
        self.assertFalse(shell.registry_requested)

    def test_release_metadata(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        if manifest['sequence'] != 233:
            self.skipTest('Manifest points to another release')
        data = CORE.read_bytes()
        self.assertEqual(manifest['path'], CORE.name)
        self.assertEqual(manifest['size_bytes'], len(data))
        self.assertLessEqual(len(data), 350000)
        self.assertEqual(manifest['sha256'], hashlib.sha256(data).hexdigest())
