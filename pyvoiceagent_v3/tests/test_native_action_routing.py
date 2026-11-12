"""Regression for AI/tool routing; does not open real iPhone applications."""
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from pyvoiceagent_v3.core.dispatcher import Agent
from pyvoiceagent_v3 import mobile
from pyvoiceagent_v3.services.native_routes import AMAP_URI, match_native
from pyvoiceagent_v3.storage.sqlite_store import LocalStore


class NativeActionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        llm = Mock()
        llm.answer.return_value = '问答回复'
        self.agent = Agent(LocalStore(os.path.join(self.temp.name, 'v3.sqlite3')), llm=llm)
        self.llm = llm

    def test_open_amap_is_local_and_never_marked_completed(self):
        result = self.agent.submit('打开高德导航')
        self.assertEqual(result.status, 'waiting_confirmation')
        self.assertEqual(result.action['kind'], 'ios_url_handoff')
        self.assertEqual(result.action['url'], AMAP_URI)
        self.assertFalse(result.action['executed'])
        self.llm.answer.assert_not_called()
        calls = []
        outcome = mobile._handoff(self.agent, result.task_id, True, opener=calls.append)
        self.assertEqual(outcome.status, 'handoff_ready')
        self.assertEqual(calls, [AMAP_URI])
        self.assertEqual(self.agent.store.get_task(result.task_id)['status'], 'needs_review')

    def test_explicit_open_app_does_not_ask_redundant_confirmation(self):
        with patch.object(mobile, '_alert') as alert, \
             patch.object(mobile, '_confirm') as confirm, \
             patch.object(mobile.webbrowser, 'open', return_value=True) as opener:
            mobile._send(self.agent, '打开高德地图')
        confirm.assert_not_called()
        opener.assert_called_once_with(AMAP_URI)
        self.assertIn('已尝试', alert.call_args.args[0])
        self.assertEqual(self.agent.history.list(limit=1)[0]['status'], 'needs_review')
        self.llm.answer.assert_not_called()

    def test_missing_app_is_not_reported_as_success(self):
        result = self.agent.submit('打开高德导航')
        with self.assertRaises(RuntimeError):
            mobile._handoff(self.agent, result.task_id, True, opener=lambda _: False)
        self.assertEqual(self.agent.store.get_task(result.task_id)['status'], 'needs_review')

    def test_unknown_tool_action_is_failed_locally(self):
        for phrase in ('打开未知软件', '导航到某个地方', '帮我创建提醒明天开会'):
            with self.subTest(phrase=phrase):
                result = self.agent.submit(phrase)
                self.assertEqual(result.status, 'failed')
                self.assertIn('没有执行', result.message)
        self.llm.answer.assert_not_called()

    def test_actual_questions_still_use_deepseek(self):
        for phrase in ('如何打开高德导航？', '高德地图有什么优点？'):
            result = self.agent.submit(phrase)
            self.assertEqual(result.status, 'waiting_consent')
            answer = self.agent.approve_remote(result.task_id, True)
            self.assertEqual(answer.status, 'completed')
        self.assertEqual(self.llm.answer.call_count, 2)

    def test_whitelist_rejects_tampered_external_url(self):
        result = self.agent.submit('打开高德导航')
        row = self.agent.store.get_task(result.task_id)
        action = dict(result.action)
        action['url'] = 'https://example.com/unsafe'
        with self.agent.store._connect() as db:
            db.execute('UPDATE tasks SET action_json=? WHERE task_id=?',
                       (json.dumps(action), result.task_id))
        with self.assertRaises(ValueError):
            self.agent.confirm_handoff(result.task_id, True)

    def test_no_broad_match_on_similar_words(self):
        self.assertIsNone(match_native('高德导航有什么功能'))
        self.assertIsNone(match_native('打开高德导航到北京'))
