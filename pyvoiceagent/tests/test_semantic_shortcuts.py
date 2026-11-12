"""Exercise the published planner-to-shortcut path without network or iOS."""
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class SemanticShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'registry.json'
        path.write_text(json.dumps({
            'save_card': dict(name='保存名片 2', description='把客户名片存进通讯录',
                              aliases=['归档名片'], mode='launch', input_mode='full'),
            'disabled_card': dict(name='禁用工具', description='停用工具',
                                  aliases=['停用工具'], enabled=False),
        }), encoding='utf-8')
        ns = runpy.run_path(str(ROOT / 'agent_core_3_0_7.py'))
        self.engine = ns['plan_once'].__globals__
        self.urls = []
        self.confirmations = []
        self.engine.update(REGISTRY_PATH=str(path), api_key=lambda: 'test',
                           record_token_usage=lambda *args: None,
                           put_state=lambda state: None, create_event=lambda *args: None,
                           prompt_alert=self.confirm)
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, shortcuts=SimpleNamespace(open_url=self.urls.append)).start()

    def confirm(self, title, message):
        self.confirmations.append(title)
        return True

    def run_plan(self, ident):
        goal = '把这位客户的名片收进通讯录'
        action = dict(tool='shortcut.run', reason='用途匹配', title='', text='模型改写',
                      datetime='', end_datetime='', notes='', shortcut_id=ident)
        reply = dict(choices=[dict(message=dict(content=json.dumps(
            dict(actions=[action], question=''))))])

        def respond(request, timeout):
            payload = json.loads(request.data)['messages']
            catalog = json.loads(payload[1]['content'])['registered_shortcuts']
            self.assertEqual(catalog, [dict(id='save_card', name='保存名片 2',
                             purpose='把客户名片存进通讯录',
                             aliases=['归档名片'], input_mode='full')])
            self.assertIn('不要求原话匹配', payload[0]['content'])
            from io import BytesIO
            return BytesIO(json.dumps(reply).encode())

        self.engine['urlopen'] = respond
        state = self.engine['plan_once']({'goal': goal})
        return goal, state

    def test_unlisted_phrase_uses_registered_tool_and_original_text(self):
        goal, state = self.run_plan('save_card')
        self.assertEqual(len(self.urls), 1)
        self.assertEqual(len(self.confirmations), 1)
        self.assertIn('未收到执行成功证明', state['final'])
        self.assertEqual(parse_qs(urlsplit(self.urls[0]).query),
                         {'name': ['保存名片 2'], 'input': ['text'], 'text': [goal]})
        self.assertIn('%202&', self.urls[0])

    def test_disabled_id_from_model_cannot_execute(self):
        _, state = self.run_plan('disabled_card')
        self.assertEqual(state['status'], 'paused')
        self.assertFalse(self.urls or self.confirmations)

    def test_input_modes_reject_missing_suffix_and_discard_unneeded_text(self):
        normalise = self.engine['_semantic_action']
        self.assertEqual(normalise({}, {'text': '模型文字'}, {'input_mode': 'none'})['text'], '')
        with self.assertRaises(ValueError):
            normalise({}, {'text': ' '}, {'input_mode': 'suffix'})
