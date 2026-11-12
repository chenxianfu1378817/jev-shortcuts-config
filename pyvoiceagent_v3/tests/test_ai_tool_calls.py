"""DeepSeek function-calling selection must never bypass the local allowlist."""
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from pyvoiceagent_v3.core.dispatcher import Agent
from pyvoiceagent_v3.services.llm import DeepSeekText, RemoteError
from pyvoiceagent_v3.storage.sqlite_store import LocalStore
from pyvoiceagent_v3 import mobile


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body, ensure_ascii=False).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class ToolPlannerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.agent = Agent(LocalStore(os.path.join(tmp.name, 'agent.sqlite3')))
        self.agent.shortcuts.register(
            'wechat_scan', '微信扫一扫', ['微信扫一扫'], input_mode='full')

    def test_llm_receives_real_catalog_and_tool_schema(self):
        def open_mock(request, timeout):
            self.assertEqual(timeout, 18)
            body = json.loads(request.data.decode('utf-8'))
            self.assertEqual(body['model'], 'deepseek-flash')
            self.assertEqual(body['thinking'], {'type': 'disabled'})
            self.assertEqual(body['tool_choice'], 'auto')
            self.assertEqual(body['tools'][0]['function']['name'], 'select_registered_shortcut')
            ids = body['tools'][0]['function']['parameters']['properties']['tool_id']['enum']
            self.assertEqual(ids, ['wechat_scan'])
            self.assertIn('微信扫一扫', body['messages'][0]['content'])
            return FakeResponse({'choices': [{'message': {
                'content': None, 'tool_calls': [{
                    'type': 'function', 'function': {
                        'name': 'select_registered_shortcut',
                        'arguments': json.dumps({'tool_id': 'wechat_scan'})
                    }
                }]
            }}]})
        client = DeepSeekText('fake_secret', opener=open_mock)
        self.assertEqual(client.select_tool('帮我打开微信扫码', self.agent.shortcuts.list()),
                         'wechat_scan')

    def test_no_tool_response_is_not_fake_completion(self):
        client = DeepSeekText('fake_secret', opener=lambda req, timeout:
                              FakeResponse({'choices':[{'message': {'content':'我不会打开'}}]}))
        self.assertIsNone(client.select_tool('帮我打开微信扫码', self.agent.shortcuts.list()))

    def test_hallucinated_or_multiple_tool_calls_are_rejected(self):
        catalog = self.agent.shortcuts.list()
        for arguments in ('{"tool_id":"unknown_app"}', 'not json',
                          '{"tool_id":"wechat_scan","url":"https://x"}'):
            with self.subTest(arguments=arguments):
                client = DeepSeekText('fake_secret', opener=lambda req, timeout:
                    FakeResponse({'choices':[{'message': {
                        'tool_calls':[{'function':{
                            'name':'select_registered_shortcut',
                            'arguments':arguments}}]}}]}))
                with self.assertRaises(RemoteError):
                    client.select_tool('帮我打开微信扫码', catalog)
        multi = {'choices':[{'message': {'tool_calls': [
            {'function': {'name': 'select_registered_shortcut',
                          'arguments': '{"tool_id":"wechat_scan"}'}},
            {'function': {'name': 'select_registered_shortcut',
                          'arguments': '{"tool_id":"wechat_scan"}'}}]}}]}
        client = DeepSeekText('fake_secret', opener=lambda req, timeout: FakeResponse(multi))
        with self.assertRaises(RemoteError):
            client.select_tool('帮我打开微信扫码', catalog)

    def test_near_alias_uses_llm_planner_then_local_confirmation(self):
        llm = Mock()
        llm.select_tool.return_value = 'wechat_scan'
        self.agent.llm = llm
        proposed = self.agent.submit('帮我打开微信扫码', request_id='agent_tool_0001')
        self.assertEqual(proposed.status, 'waiting_consent')
        self.assertIsNone(proposed.action)
        result = self.agent.approve_remote(proposed.task_id, True)
        self.assertEqual(result.status, 'waiting_confirmation')
        self.assertEqual(result.action['shortcut_name'], '微信扫一扫')
        self.assertFalse(result.action['executed'])
        repeat = self.agent.approve_remote(proposed.task_id, True)
        self.assertFalse(repeat.fresh)
        llm.select_tool.assert_called_once()
        self.assertEqual(self.agent.store.get_task(proposed.task_id)['status'],
                         'waiting_confirmation')

    def test_ai_choose_missing_tool_is_failed_not_executed(self):
        llm = Mock()
        llm.select_tool.return_value = 'not_registered'
        self.agent.llm = llm
        result = self.agent.submit('帮我打开微信扫码')
        outcome = self.agent.approve_remote(result.task_id, True)
        self.assertEqual(outcome.status, 'failed')
        self.assertIn('未执行', outcome.message)
        self.assertEqual(self.agent.store.task_events(result.task_id)[-1]['event_type'], 'failed')

    def test_phone_send_handoff_after_ai_selection(self):
        self.agent.llm = Mock()
        self.agent.llm.select_tool.return_value = 'wechat_scan'
        with patch.object(mobile, '_alert'), \
             patch.object(mobile, '_confirm', return_value=True) as confirm, \
             patch.object(mobile.webbrowser, 'open', return_value=True) as opener:
            mobile._send(self.agent, '帮我打开微信扫码')
        confirm.assert_called_once()
        opener.assert_called_once()
        self.assertTrue(opener.call_args.args[0].startswith('shortcuts://run-shortcut?'))
        self.assertEqual(self.agent.history.list(limit=1)[0]['status'], 'needs_review')


if __name__ == '__main__':
    unittest.main()
