import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import urllib.error

from pyvoiceagent_v3.services.llm import DeepSeekText, RemoteError
from pyvoiceagent_v3.adapters.pythonista_cli import run
from pyvoiceagent_v3.storage.sqlite_store import LocalStore
from pyvoiceagent_v3.core.models import InputError


class FakeResponse:
    def __init__(self,payload):
        self.payload=payload
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,n):
        return self.payload[:n]


class NetworkAndCliTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def client(self, payload, call=None):
        def fake(req,timeout):
            if call is not None:
                return call(req,timeout)
            return FakeResponse(payload)
        return DeepSeekText('sensitive_key_123',opener=fake)

    def test_json_response(self):
        data={'choices':[{'message':{'content':'你好，来自 DeepSeek'}}]}
        client=self.client(json.dumps(data,ensure_ascii=False).encode())
        self.assertEqual(client.answer('你好'), '你好，来自 DeepSeek')

    def test_auth_header_not_logged(self):
        def fake(req,timeout):
            self.assertTrue(req.headers['Authorization'].endswith('sensitive_key_123'))
            self.assertEqual(timeout,18)
            raise urllib.error.URLError('secret credentials in raw exception')
        with self.assertRaises(RemoteError) as cm:
            self.client(b'',fake).answer('请介绍云计算')
        self.assertNotIn('secret',str(cm.exception))
        self.assertIn('网络',str(cm.exception))

    def test_timeout_is_handled(self):
        def time_out(req,timeout):
            raise TimeoutError('real token in exception')
        with self.assertRaises(RemoteError):
            self.client(b'',time_out).answer('你好')

    def test_empty_ai_response_is_rejected(self):
        for raw in (b'',b'null',b'[]',b'{}',b'{"choices":[]}',b'{"choices":[{"message":{"content":""}}]}'):
            with self.subTest(raw=raw):
                with self.assertRaises(RemoteError):
                    self.client(raw).answer('问个问题')

    def test_oversized_remote_response_is_rejected(self):
        with self.assertRaises(RemoteError):
            self.client(b'x'*262150).answer('你好')

    def test_refuse_non_tls_endpoint_and_empty_key(self):
        with self.assertRaises(InputError):
            DeepSeekText('secret',endpoint='http://example.com')
        with self.assertRaises(InputError):
            DeepSeekText('')

    def test_cli_check_no_network_and_uses_independent_db(self):
        text=[]
        data=os.path.join(self.folder.name,'v3-data')
        self.assertEqual(run(['--data',data,'--check'], output_fn=text.append),0)
        self.assertTrue(any('未调用' in t for t in text))
        self.assertTrue(os.path.isfile(os.path.join(data,'agent_v3.sqlite3')))
        self.assertFalse(os.path.isdir(os.path.join(self.folder.name,'PYVoiceAgent_Data')))

    def test_cli_commands_and_safe_exit(self):
        inp=iter(['/主题 科技蓝','/设置','你好','/退出'])
        out=[]
        self.assertEqual(run(['--data',self.folder.name],input_fn=lambda p:next(inp),output_fn=out.append),0)
        self.assertTrue(any('科技蓝' in x for x in out))
        self.assertTrue(any('未联网' in x for x in out))
        self.assertIn('已安全退出',out[-1])

    def test_cli_unknown_instruction_never_goes_online(self):
        inp=iter(['帮我查询最新新闻','/exit'])
        out=[]
        run(['--data',self.folder.name],input_fn=lambda prompt:next(inp),output_fn=out.append)
        self.assertTrue(any('AI 授权方式' in x for x in out))

    def test_project_core_has_no_apple_sdk_imports(self):
        root=Path(__file__).resolve().parents[1]
        for section in ('core','storage','services'):
            for path in (root/section).glob('*.py'):
                source=path.read_text(encoding='utf8')
                for forbidden in ('import ui','import sound','import speech','import objc_util',
                                  'import dialogs','from objc_util import'):
                    with self.subTest(path=path.name, forbidden=forbidden):
                        self.assertNotIn('\n'+forbidden,source)


if __name__ == '__main__':
    unittest.main()
