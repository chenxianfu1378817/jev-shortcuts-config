"""Exercise the chat window's native presentation and dismissal lifecycle."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_3_0.py'
SPEC = importlib.util.spec_from_file_location('native_exit_candidate', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class NativeExitTests(unittest.TestCase):
    def test_native_dismissal_releases_modal_even_when_waiting_for_approval(self):
        holder = Mock(bounds=(0, 0, 390, 844))
        web = Mock()
        fake_ui = SimpleNamespace(
            get_screen_size=lambda: (390, 844),
            View=Mock(return_value=holder),
            WebView=Mock(return_value=web),
            delay=Mock(),
        )
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            shell = core._ChatShell()
        shell.busy = True
        pending_approval = threading.Event()
        shell.approval_event = pending_approval
        shell.approval_choice = 1

        def dismiss_via_native_title_bar():
            holder.present.assert_called_once_with('full_screen', hide_title_bar=False)
            self.assertFalse(shell.closed)
            holder.on_screen = False

        holder.wait_modal.side_effect = dismiss_via_native_title_bar
        with patch.dict(sys.modules, {'ui': fake_ui}), \
             patch.object(core, '_card_appearance_load', return_value={}), \
             patch.object(core, '_card_palette', return_value={'background': '#ffffff'}), \
             patch.object(core, 'put_state') as write_task:
            self.assertTrue(shell.show())
            write_task.assert_not_called()

        self.assertTrue(shell.closed)
        self.assertTrue(pending_approval.is_set())
        self.assertEqual(shell.approval_choice, 0)
        self.assertNotIn('agent-exit', web.load_html.call_args.args[0])
        self.assertIn('id="reg-open"', web.load_html.call_args.args[0])

    def test_manifest_matches_engine(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        if manifest['sequence'] != 230:
            self.skipTest('Manifest points to another release')
        data = CORE.read_bytes()
        self.assertEqual(manifest['path'], CORE.name)
        self.assertEqual(manifest['size_bytes'], len(data))
        self.assertLessEqual(len(data), 350000)
        self.assertEqual(manifest['sha256'], hashlib.sha256(data).hexdigest())
