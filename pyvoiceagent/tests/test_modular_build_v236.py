"""Validate all business/UI sources are included in the modular release."""
import ast
import json
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools' / 'build_modular.py'
SPEC = importlib.util.spec_from_file_location('modular_build_v236', SCRIPT)
build_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_module)


class ModularBuildTests(unittest.TestCase):
    def test_all_feature_buckets_present(self):
        source, parts = build_module.assembled_source()
        self.assertGreaterEqual(len(parts), 24)
        self.assertTrue((ROOT / 'src' / '39_voice_session.py').is_file())
        self.assertFalse(any('39_voice_session' in x for x in parts))
        self.assertNotIn('class _VoiceSession:', source)
        expected = ('11_contacts_clipboard', '22_deepseek', '26_shortcuts_bridge',
                    '27_ios_services', '29_agent_execution',
                    '30_shortcuts_generator', '32_updater',
                    '34_bu_market',
                    '40_ui_cards', '41_history', '42_result',
                    '43_chat', '44_registered_tools')
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(any(x.startswith(name) for x in parts))
        ast.parse(source)

    def test_public_features_not_dropped(self):
        tree = ast.parse(build_module.assembled_source()[0])
        methods = {node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ('_deepseek_request', '_reg_native_form', '_reg_save',
                     'bridge_callback', '_local_calendar_list',
                     '_local_reminder_list', '_local_contacts_lookup',
                     '_local_maps_search', '_bu_capture_and_calendar',
                     '_history_search', 'immediate_check_and_update',
                     '_card_palette', '_result_card_model', '_voice_speak'):
            with self.subTest(name=name):
                self.assertIn(name, methods)

    def test_generated_single_file_matches_manifest(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['version'] == '2.3.9':
            result = build_module.build(sequence=manifest['sequence'], write=False)
            self.assertEqual(result['release']['version'], manifest['version'])
            self.assertLessEqual(result['release']['size_bytes'], 350000)
        else:
            source = build_module.remove_nonfunctional_lines(build_module.assembled_source()[0])
            self.assertEqual(source.encode('utf-8'),
                             (ROOT / 'agent_core_2_3_9.py').read_bytes())
            self.assertLessEqual(len(source.encode('utf-8')), 350000)

    def test_comment_stripping_has_same_ast(self):
        source, _ = build_module.assembled_source()
        clean = build_module.remove_nonfunctional_lines(source)
        self.assertEqual(ast.dump(ast.parse(clean)), ast.dump(ast.parse(source)))


if __name__ == '__main__':
    unittest.main()
