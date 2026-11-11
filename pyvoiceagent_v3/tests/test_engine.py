import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from pyvoiceagent_v3.core.dispatcher import Agent
from pyvoiceagent_v3.core.models import InputError, InvalidTransition
from pyvoiceagent_v3.services.history import HistoryService
from pyvoiceagent_v3.services.settings import THEMES, MODES, AppearanceSettings
from pyvoiceagent_v3.storage.sqlite_store import LocalStore


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.store = LocalStore(self.root/'v3.sqlite3')
        self.agent = Agent(self.store)

    def test_local_hello_never_calls_remote(self):
        out = self.agent.submit('你好')
        self.assertEqual(out.status, 'completed')
        self.assertIn('未联网', out.message)
        self.assertEqual([x['event_type'] for x in self.store.task_events(out.task_id)],
                         ['queued','completed'])

    def test_help_settings_history_tools_all_local(self):
        for cmd in ('/帮助','/设置','/历史','/工具','/诊断'):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.agent.submit(cmd).status,'completed')
        self.assertEqual(len(self.store.list_tasks()), 5)

    def test_network_requires_separate_user_consent(self):
        mocked = type('FakeLLM', (), {'answer': lambda self,x: 'AI响应'+x})()
        agent = Agent(self.store, llm=mocked)
        result = agent.submit('请介绍Pythonista')
        self.assertEqual(result.status,'waiting_consent')
        self.assertTrue(result.confirmation_required)
        self.assertIn('尚未发送',result.message)
        self.assertEqual(agent.approve_remote(result.task_id, False).status,'cancelled')

    def test_approved_remote_call_happens_once(self):
        class Remote:
            count = 0
            def answer(self, value):
                self.count += 1
                return '回应：'+value
        r = Remote()
        agent = Agent(self.store, r)
        result = agent.submit('什么是AI')
        self.assertEqual(r.count, 0)
        one = agent.approve_remote(result.task_id, True)
        two = agent.approve_remote(result.task_id, True)
        self.assertEqual(one.status,'completed')
        self.assertEqual(two.status,'completed')
        self.assertFalse(two.fresh)
        self.assertEqual(r.count,1)

    def test_missing_llm_not_claimed_success(self):
        pending = self.agent.submit('世界新闻')
        result = self.agent.approve_remote(pending.task_id, True)
        self.assertEqual(result.status,'failed')
        self.assertIn('RuntimeError',result.message)

    def test_corrupt_response_is_not_retried(self):
        class Remote:
            calls=0
            def answer(self, text):
                self.calls+=1
                raise ValueError('API key secret in raw error')
        r=Remote()
        agent=Agent(self.store,r)
        task=agent.submit('苹果最新新闻')
        result=agent.approve_remote(task.task_id, True)
        self.assertEqual(result.status,'failed')
        self.assertNotIn('secret',result.message)
        agent.approve_remote(task.task_id, True)
        self.assertEqual(r.calls,1)

    def test_idempotency_same_request_id_keeps_original(self):
        first=self.agent.submit('你好', request_id='same_event_001')
        second=self.agent.submit('你好', request_id='same_event_001')
        self.assertEqual(first.task_id, second.task_id)
        self.assertTrue(first.fresh)
        self.assertFalse(second.fresh)
        self.assertEqual(len(self.store.list_tasks()),1)

    def test_recycled_request_id_with_different_text_rejected(self):
        self.agent.submit('你好', request_id='same_event_002')
        with self.assertRaises(InputError):
            self.agent.submit('付款', request_id='same_event_002')

    def test_invalid_input_never_creates_task(self):
        for text in ('', '   ', 'x'*2001, None):
            with self.subTest(text=str(text)[:10]):
                with self.assertRaises(InputError):
                    self.agent.submit(text)
        self.assertEqual(self.store.list_tasks(),[])

    def test_no_unsafe_db_state_changes(self):
        result=self.agent.submit('你好')
        with self.assertRaises(InvalidTransition):
            self.store.move_task(result.task_id,'running','should fail')
        self.assertEqual(self.store.get_task(result.task_id)['status'],'completed')

    def test_repeated_concurrent_request_only_one_row(self):
        def worker(_):
            return self.agent.submit('你好', request_id='concurrency_1234').task_id
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            ids=list(executor.map(worker,range(32)))
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(len(self.store.list_tasks()),1)

    def test_transaction_rollback_on_invalid_transition(self):
        task=self.agent.submit('你好')
        before=self.store.task_events(task.task_id)
        with self.assertRaises(InvalidTransition):
            self.store.move_task(task.task_id,'waiting_consent','invalid')
        self.assertEqual(self.store.task_events(task.task_id), before)

    def test_backup_consistent_and_non_destructive(self):
        self.agent.submit('你好')
        path=self.root/'backup'/'v3.bak.sqlite3'
        self.assertEqual(self.store.backup(path),str(path))
        self.assertEqual(sqlite3.connect(path).execute('SELECT count(*) FROM tasks').fetchone()[0],1)
        with self.assertRaises(FileExistsError):
            self.store.backup(path)
        self.assertEqual(len(self.store.list_tasks()),1)

    def test_fail_closed_on_future_schema_version(self):
        with sqlite3.connect(self.store.filename) as db:
            db.execute('PRAGMA user_version=999')
        with self.assertRaisesRegex(RuntimeError, 'schema'):
            LocalStore(self.store.filename)
        self.assertEqual(sqlite3.connect(self.store.filename).execute('PRAGMA user_version').fetchone()[0],999)

    def test_history_pagination_read_only(self):
        for i in range(6):
            self.agent.submit('你好 '+str(i))
        hist=self.agent.history.list(2,offset=1)
        self.assertEqual(len(hist),2)
        self.assertEqual(len(self.store.list_tasks()),6)
        with self.assertRaises(InputError):
            self.agent.history.list(1000)

    def test_all_eight_themes_and_all_modes(self):
        self.assertEqual(len(THEMES),8)
        for theme in THEMES:
            x=self.agent.appearance.change(theme=theme)
            self.assertEqual(self.agent.appearance.read()['theme'],theme)
            self.assertEqual(self.agent.appearance.palette(),THEMES[theme])
        for mode in MODES:
            self.agent.appearance.change(mode=mode)
            self.assertEqual(self.agent.appearance.read()['mode'],mode)

    def test_bad_theme_does_not_erase_previous_preference(self):
        self.agent.appearance.change(theme='科技蓝',custom_color='#1122AA')
        before=self.agent.appearance.read()
        for args in ({'theme':'不存在'}, {'mode':'超级模式'}, {'custom_color':'blue'}):
            with self.assertRaises(InputError):
                self.agent.appearance.change(**args)
        self.assertEqual(self.agent.appearance.read(),before)

    def test_disabled_duplicate_alias_preserved(self):
        tool=self.agent.shortcuts.register('workapp','工作台',['打开工作台'],enabled=True)
        self.agent.shortcuts.register('idle_app','其他',['打开工作台'],enabled=False)
        self.assertEqual(len(self.agent.shortcuts.list()),2)
        with self.assertRaises(InputError):
            self.agent.shortcuts.register('idle_app','其他',['打开工作台'],enabled=True)
        self.assertEqual(len(self.agent.shortcuts.list()),2)
        self.assertFalse(next(x for x in self.agent.shortcuts.list() if x['tool_id']=='idle_app')['enabled'])

    def test_tool_consent_is_handoff_not_real_execution(self):
        self.agent.shortcuts.register('open_video','抖音',['抖音'])
        result=self.agent.submit('打开抖音')
        self.assertEqual(result.status,'waiting_confirmation')
        self.assertTrue(result.action['requires_user_action'])
        self.assertIs(result.action['executed'],False)
        approved=self.agent.confirm_handoff(result.task_id,True)
        self.assertEqual(approved.status,'handoff_ready')
        self.assertFalse(approved.action['executed'])
        unverified=self.agent.mark_handoff_unverified(result.task_id)
        self.assertEqual(unverified.status,'needs_review')
        self.assertEqual(self.agent.cancel_review(result.task_id).status,'cancelled')

    def test_tool_denial_does_not_trigger_write(self):
        self.agent.shortcuts.register('open_map','地图',['地图'])
        request=self.agent.submit('打开地图')
        self.assertEqual(self.agent.confirm_handoff(request.task_id,False).status,'cancelled')
        self.assertEqual([x['event_type'] for x in self.store.task_events(request.task_id)], ['queued', 'waiting_confirmation', 'cancelled'])

    def test_conflicting_alias_error_is_atomic(self):
        self.agent.shortcuts.register('first','演示1',['执行演示'])
        with self.assertRaises(InputError):
            self.agent.shortcuts.register('second','演示2',['执行演示'])
        self.assertEqual(len(self.agent.shortcuts.list()),1)

    def test_unknown_or_invalid_tool_is_not_registered(self):
        invalid = [dict(tool_id='bad tool',shortcut_name='a',aliases=['x']),
                   dict(tool_id='okay',shortcut_name='',aliases=['x']),
                   dict(tool_id='okay',shortcut_name='a',aliases=[]),
                   dict(tool_id='okay',shortcut_name='a',aliases=['x','x']),
                   dict(tool_id='okay',shortcut_name='a',aliases=['x'],input_mode='freeform')]
        for args in invalid:
            with self.subTest(args=args):
                with self.assertRaises(InputError):
                    self.agent.shortcuts.register(**args)
        self.assertEqual(self.agent.shortcuts.list(),[])

    def test_legacy_history_preview_readonly_and_skips_corrupt(self):
        root=self.root/'old_data'
        folder=root/'history'/'2026-11'
        folder.mkdir(parents=True)
        entry=folder/'task_abcdef12.json'
        original={'archive_key':'2026-11/task_abcdef12.json','kind':'task',
                  'goal':'测试历史', 'status':'finished','created':'2026-11-11'}
        entry.write_text(json.dumps(original,ensure_ascii=False),encoding='utf8')
        (folder/'task_abcdef13.json').write_text('{broken',encoding='utf8')
        preview=HistoryService.preview_legacy(root)
        self.assertEqual(preview['scanned'],2)
        self.assertEqual(preview['skipped'],1)
        self.assertEqual(len(preview['entries']),1)
        self.assertEqual(json.loads(entry.read_text(encoding='utf8')),original)
        self.assertTrue(preview['read_only'])

    def test_legacy_history_file_name_traversal_ignored(self):
        root=self.root/'old_data2'
        folder=root/'history'/'2026-11'
        folder.mkdir(parents=True)
        (folder/'anything.txt').write_text('secret')
        self.assertEqual(HistoryService.preview_legacy(root)['scanned'],0)

    def test_interrupted_running_is_never_replayed(self):
        pending=self.agent.submit('未知外部请求')
        self.store.move_task(pending.task_id,'running','mock in flight')
        before=self.store.running_tasks()
        self.assertEqual(len(before),1)
        result=self.store.mark_interrupted(pending.task_id)
        self.assertEqual(result['status'],'needs_review')
        self.assertIn('不自动重试',result['message'])
        self.assertEqual(self.store.running_tasks(),[])
        self.assertEqual(self.store.mark_interrupted(pending.task_id)['status'],'needs_review')

    def test_interrupted_inspection_does_not_mutate(self):
        pending=self.agent.submit('外部请求')
        self.store.move_task(pending.task_id,'running','in flight')
        events=self.store.task_events(pending.task_id)
        self.store.running_tasks()
        self.assertEqual(self.store.task_events(pending.task_id), events)

    def test_database_file_separate_from_v2_data(self):
        self.assertNotIn('PYVoiceAgent_Data/', self.store.filename)


if __name__ == '__main__':
    unittest.main()
