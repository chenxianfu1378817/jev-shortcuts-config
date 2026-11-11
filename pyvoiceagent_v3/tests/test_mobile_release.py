"""V3 mobile delivery smoke and failure-injection tests, no iOS runtime needed."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from pyvoiceagent_v3 import mobile, mobile_update
from pyvoiceagent_v3.core.dispatcher import Agent
from pyvoiceagent_v3.storage.sqlite_store import LocalStore

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT/'pyvoiceagent_v3'/'tools'/'build_mobile_release.py'
SPEC = importlib.util.spec_from_file_location('v3_release_builder_test', BUILDER)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class MobileApplicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = temp.name
        self.agent = Agent(LocalStore(os.path.join(self.dir,'agent.sqlite3')))

    def test_local_hello_and_history(self):
        with patch.object(mobile, '_alert') as alert:
            mobile._send(self.agent, '你好')
            self.assertIn('你好', alert.call_args.args[1])
            with patch.object(mobile, '_choose', return_value=None):
                mobile._history(self.agent)
        self.assertGreaterEqual(len(self.agent.history.list()), 1)

    def test_ai_requires_per_request_consent(self):
        llm = Mock()
        llm.answer.return_value = '这是测试回答'
        self.agent.llm = llm
        with patch.object(mobile, '_alert'), patch.object(mobile, '_confirm',
                                                          return_value=False):
            mobile._send(self.agent, '分析最新道路沥青价格')
        llm.answer.assert_not_called()
        self.assertEqual(self.agent.history.list(limit=1)[0]['status'],'cancelled')
        with patch.object(mobile, '_alert'), patch.object(mobile, '_confirm',
                                                          return_value=True):
            mobile._send(self.agent, '分析最新道路沥青价格')
        llm.answer.assert_called_once()
        self.assertEqual(self.agent.history.list(limit=1)[0]['status'],'completed')

    def test_shortcut_is_never_invoked_without_confirmation(self):
        self.agent.shortcuts.register('go_pay','Test Payment', ['打开付款码'])
        opened = Mock()
        with patch.object(mobile,'_alert'), patch.object(mobile,'_confirm',
                                                          return_value=False), \
             patch.object(mobile.webbrowser, 'open',opened):
            mobile._send(self.agent, '打开付款码')
        opened.assert_not_called()
        self.assertEqual(self.agent.history.list(limit=1)[0]['status'],'cancelled')

    def test_shortcut_url_handoff_is_encoded_and_unverified(self):
        self.agent.shortcuts.register('pay_test','支付宝 付款码', ['显示付款码'],
                                       input_mode='full')
        outcome = self.agent.submit('显示付款码')
        calls = []
        result = mobile._handoff(self.agent,outcome.task_id,True,opener=calls.append)
        self.assertEqual(result.status,'handoff_ready')
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0].startswith('shortcuts://run-shortcut?'))
        self.assertIn('%E6%94%AF%E4%BB%98%E5%AE%9D',calls[0])
        self.assertEqual(self.agent.store.get_task(outcome.task_id)['status'],
                         'needs_review')

    def test_shortcut_launch_failure_is_not_claimed_success(self):
        self.agent.shortcuts.register('open_x','Missing Shortcut', ['启动测试'])
        outcome=self.agent.submit('启动测试')
        with self.assertRaises(RuntimeError):
            mobile._handoff(self.agent,outcome.task_id,True,
                            opener=Mock(side_effect=RuntimeError('not installed')))
        self.assertEqual(self.agent.store.get_task(outcome.task_id)['status'],
                         'needs_review')

    def test_theme_persistence_and_backup(self):
        self.agent.appearance.change(theme='典雅紫',mode='深色模式')
        reloaded=Agent(LocalStore(os.path.join(self.dir,'agent.sqlite3')))
        self.assertEqual(reloaded.appearance.read()['theme'],'典雅紫')
        target=os.path.join(self.dir,'backup','archive.sqlite3')
        reloaded.store.backup(target)
        with self.assertRaises(FileExistsError):
            reloaded.store.backup(target)

    def test_fake_i_phone_menu_enters_and_exits_without_audio_or_webview(self):
        sys_modules={'dialogs':Mock(),'console':Mock()}
        sys_modules['dialogs'].list_dialog.side_effect=['输入任务 / AI 对话','退出']
        sys_modules['dialogs'].text_dialog.return_value='你好'
        with patch.dict(sys.modules,sys_modules), \
             patch.object(mobile,'create_agent',return_value=self.agent):
            self.assertEqual(mobile.run(argv=[]),0)
        self.assertEqual(self.agent.history.list(limit=1)[0]['status'],'completed')

    def test_legacy_callback_is_blocked_not_run_automatically(self):
        sys_modules={'dialogs':Mock(),'console':Mock()}
        with patch.dict(sys.modules,sys_modules), \
             patch.object(mobile,'create_agent',return_value=self.agent):
            self.assertEqual(mobile.run(argv=['bridge_callback','secret-token']),0)
        self.assertEqual(self.agent.history.list(),[])

    def test_old_keychain_is_read_only(self):
        fake=Mock()
        fake.get_password.side_effect=['', 'previous-key']
        with patch.dict(sys.modules,{'keychain':fake}):
            self.assertEqual(mobile._key(),'previous-key')
        fake.set_password.assert_not_called()


class MobileReleaseTests(unittest.TestCase):
    def test_release_size_sha_and_all_python_modules(self):
        engine, manifest = builder.make_release()
        self.assertEqual(manifest['version'],'3.0.0')
        self.assertEqual(manifest['sequence'],300)
        self.assertLessEqual(len(engine),350000)
        self.assertEqual(hashlib.sha256(engine).hexdigest(),manifest['sha256'])
        namespace={'__name__':'v3_embedded_test'}
        exec(compile(engine,'release_v3_test.py','exec'),namespace)
        package=base64.b64decode(namespace['_BUNDLE_B64'])
        self.assertEqual(hashlib.sha256(package).hexdigest(),
                         namespace['_BUNDLE_SHA256'])
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            self.assertIn('pyvoiceagent_v3/mobile.py',archive.namelist())
            self.assertIn('pyvoiceagent_v3/mobile_update.py',archive.namelist())
            self.assertIn('pyvoiceagent_v3/core/dispatcher.py',archive.namelist())
            self.assertFalse(any('/tests/' in x for x in archive.namelist()))

    def test_embedded_package_installs_once_without_touching_v2(self):
        engine,_=builder.make_release()
        namespace={'__name__':'v3_embedded_test'}
        exec(compile(engine,'release_v3_test.py','exec'),namespace)
        with tempfile.TemporaryDirectory() as root:
            fake_documents=os.path.join(root,'Documents')
            os.makedirs(fake_documents)
            old_data=os.path.join(fake_documents,'PYVoiceAgent_Data')
            os.makedirs(old_data)
            old_marker=os.path.join(old_data,'shortcut_registry.json')
            Path(old_marker).write_text('keep v2 data',encoding='utf-8')
            with patch.object(namespace['os'].path,'expanduser',
                              side_effect=lambda path: root if path=='~' else path):
                first=namespace['_install']()
                second=namespace['_install']()
            self.assertEqual(first,second)
            self.assertTrue(os.path.isfile(os.path.join(
                first,'pyvoiceagent_v3','mobile.py')))
            self.assertEqual(Path(old_marker).read_text(encoding='utf-8'),
                             'keep v2 data')

    def test_embedded_package_bad_hash_is_rejected(self):
        engine,_=builder.make_release()
        namespace={'__name__':'v3_embedded_test'}
        exec(compile(engine,'release_v3_test.py','exec'),namespace)
        namespace['_BUNDLE_SHA256']='0'*64
        with tempfile.TemporaryDirectory() as root:
            with patch.object(namespace['os'].path,'expanduser',
                              side_effect=lambda path: root if path=='~' else path):
                with self.assertRaises(RuntimeError):
                    namespace['_install']()


class UpdateSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base=self.temp.name
        self.engine=os.path.join(base,'engine')
        os.makedirs(self.engine)
        self.current=os.path.join(self.engine,'current.py')
        self.backup=os.path.join(self.engine,'previous.py')
        self.meta=os.path.join(base,'update_meta.json')
        old=b'VERSION="3.0.0"\n'
        Path(self.current).write_bytes(old)
        self.old=old
        Path(self.meta).write_text(json.dumps({
            'installed_seq':300,'sha256':hashlib.sha256(old).hexdigest(),
            'installed_version':'3.0.0'}),encoding='utf-8')
        for attr,path in [('LEGACY',base),('ENGINE_DIR',self.engine),
                          ('CURRENT',self.current),('PREVIOUS',self.backup),
                          ('META',self.meta)]:
            mock=patch.object(mobile_update,attr,path)
            mock.start()
            self.addCleanup(mock.stop)

    def _fetch(self,good=True):
        payload=b'VERSION="3.0.1"\n'
        manifest={'schema':1,'sequence':301,'version':'3.0.1',
                  'path':'agent_core_3_0_1.py','size_bytes':len(payload),
                  'sha256':hashlib.sha256(payload).hexdigest() if good else '0'*64}
        def get(name,limit):
            return json.dumps(manifest).encode() if name=='manifest.json' else payload
        # Override strict >=1000 bytes minimum with realistic fixture.
        payload=b'VERSION="3.0.1"\n' + b'#'+ b'Z'*1200+b'\n'
        manifest['size_bytes']=len(payload)
        manifest['sha256']=hashlib.sha256(payload).hexdigest() if good else '0'*64
        return get,payload

    def test_update_writes_checked_engine_and_backup(self):
        fetch,payload=self._fetch()
        result=mobile_update.check_for_update(downloader=fetch)
        self.assertTrue(result['updated'],result['message'])
        self.assertEqual(Path(self.current).read_bytes(),payload)
        self.assertEqual(Path(self.backup).read_bytes(),self.old)
        self.assertEqual(json.loads(Path(self.meta).read_text())['installed_seq'],301)

    def test_bad_sha_never_overwrites(self):
        fetch,_=self._fetch(False)
        result=mobile_update.check_for_update(downloader=fetch)
        self.assertFalse(result['updated'])
        self.assertEqual(Path(self.current).read_bytes(),self.old)

    def test_broken_pending_task_blocks_update(self):
        Path(os.path.join(self.temp.name,'current_task.json')).write_text(
            json.dumps({'pending':{'tool':'reminder.create'},
                        'status':'needs_review'}),encoding='utf-8')
        fetch,_=self._fetch()
        self.assertFalse(mobile_update.check_for_update(downloader=fetch)['updated'])
        self.assertEqual(Path(self.current).read_bytes(),self.old)

    def test_corrupt_old_engine_blocks_update(self):
        Path(self.current).write_text('tamper',encoding='utf-8')
        fetch,_=self._fetch()
        self.assertFalse(mobile_update.check_for_update(downloader=fetch)['updated'])
        self.assertEqual(Path(self.current).read_text(), 'tamper')


if __name__=='__main__':
    unittest.main()
