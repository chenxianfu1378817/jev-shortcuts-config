# -*- coding: utf-8 -*-
"""V2.2.2 backward-updater-size, native fallback and iPhone safe-area regression."""
import ast
import hashlib
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'agent_core_2_2_2.py'
BASE = ROOT / 'agent_core_2_1_0.py'
OLD = ROOT / 'agent_core_2_2_1.py'
MANIFEST = ROOT / 'manifest.json'

class CompatReleaseV222(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CANDIDATE.read_text(encoding='utf-8')
        cls.data = CANDIDATE.read_bytes()
        cls.previous = OLD.read_text(encoding='utf-8')

    def test_version_and_one_entry_guard(self):
        ast.parse(self.source)
        self.assertIn("VERSION = '2.2.2-deepseek-flash'", self.source)
        self.assertEqual(self.source.count('if __name__ == "__main__":'), 1)

    def test_old_installed_updater_byte_limit(self):
        self.assertIn('MAX_UPDATE_BYTES = 350000', BASE.read_text(encoding='utf-8'))
        self.assertLessEqual(len(self.data), 350000)
        self.assertGreater(len(self.data), 200000)

    def test_removed_duplicate_old_webview_but_not_new_chat(self):
        self.assertNotIn('WEBUI_HTML = "<!doctype html>', self.source)
        self.assertIn('CHAT_HTML = r"""<!doctype html>', self.source)
        self.assertIn('class _ChatShell:', self.source)
        self.assertIn('def _webui_safe_json(value):', self.source)

    def test_original_native_fallback_available_without_waiting_6_seconds(self):
        self.assertIn('_WEBUI_NATIVE_SHOW = _card_ui_show', self.source)
        self.assertIn('_WEBUI_NATIVE_RESULT = _result_ui_show', self.source)
        self.assertIn('_CHAT_ORIGINAL_MENU = show_menu', self.source)
        self.assertNotIn("def _webui_show(page='home'", self.source)

    def test_all_original_business_logic_preserved(self):
        for method in ('def bridge_callback(', 'def start_new(', 'def _local_quick_intent(',
                       'def immediate_check_and_update(', 'def _bu_capture_and_calendar(',
                       'def _history_search(', 'def _card_appearance_save(',
                       'def _result_card_model('):
            with self.subTest(method=method):
                self.assertIn(method, self.source)

    def test_header_keeps_clear_of_ios_status_bar(self):
        self.assertIn('viewport-fit=cover', self.source)
        self.assertIn('padding:max(68px,calc(16px + env(safe-area-inset-top,0px)))', self.source)
        self.assertIn('html,body{height:100%;margin:0;overflow:hidden', self.source)

    def test_bottom_composer_and_header_tabs_persist(self):
        self.assertIn('max(24px,calc(12px + env(safe-area-inset-bottom,0px)))', self.source)
        self.assertIn('class="tabs"', self.source)
        self.assertIn('id="chatview"', self.source)
        self.assertIn('id="footer"', self.source)
        self.assertIn('flex:1;min-height:0;display:none;overflow-y:auto', self.source)

    def test_protected_privacy_voice_and_settings_still_present(self):
        for item in ('def _voice_authorize_ai(state):', 'def prompt_alert(title, message',
                     'def _ask_clarification(question):', 'def cancel_record(self):',
                     'def _legacy_action(self, action):'):
            self.assertIn(item, self.source)

    def test_manifest_matches_at_release(self):
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        if m['version'] != '2.2.2':
            self.skipTest('Candidate staged; check again after manifest release')
        self.assertEqual(m['path'], CANDIDATE.name)
        self.assertEqual(m['sequence'], 222)
        self.assertEqual(m['size_bytes'], len(self.data))
        self.assertEqual(m['sha256'], hashlib.sha256(self.data).hexdigest())

if __name__ == '__main__':
    unittest.main(verbosity=2)
