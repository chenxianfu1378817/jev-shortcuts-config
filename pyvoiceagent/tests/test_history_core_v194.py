# -*- coding: utf-8 -*-
"""V1.9.4 offline integrated regression. Does not access iOS or the network."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT/'agent_core_1_9_4.py'

class CoreIntegrationV194(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code = CORE.read_text(encoding='utf-8')
        compile(code, str(CORE), 'exec')
        spec = importlib.util.spec_from_file_location('PYVoiceAgent194', str(CORE))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.source = code

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mod = self.m
        self.original = {name:getattr(self.mod,name) for name in ('DATA_DIR','HISTORY_DIR','STATE_PATH')}
        self.addCleanup(self.restore_paths)
        root = Path(self.temp.name)
        self.mod.DATA_DIR = str(root)
        self.mod.HISTORY_DIR = str(root/'history')
        self.mod.STATE_PATH = str(root/'current_task.json')

    def restore_paths(self):
        for name,value in self.original.items():
            setattr(self.mod,name,value)

    def task(self,ident='report123456'):
        return {'id':ident,'created':'2026-11-10T12:51:00+08:00',
                'goal':'11月10日沥青行情整理','status':'finished','steps':1,
                'final':'沥青报价总结','error':'','pending':None,
                'events':[{'tool':'text.respond','status':'ok','result':'镇海6240',
                           'at':'2026-11-10T12:52:00+08:00'}]}

    def test_fixed_entry(self):
        for x in ("if sys.argv[1] == 'voice':",
                  "if sys.argv[1] == 'bridge_callback':",
                  "if sys.argv[1] == 'bu_close':"):
            self.assertIn(x,self.source)
        self.assertEqual(self.mod.APP_FILE,'PYVoiceAgent.py')

    def test_version_and_baseline(self):
        self.assertEqual(self.mod.VERSION,'1.9.4-deepseek-flash')
        self.assertTrue(callable(self.mod._V193_PUT_STATE))
        self.assertTrue(callable(self.mod._V193_MAIN))
        self.assertEqual(len(self.mod.CARD_THEMES),8)

    def test_archive_and_search(self):
        self.mod.put_state(self.task())
        hits=self.mod._history_search('镇海6240')
        self.assertEqual(len(hits),1)
        self.assertIn('沥青行情',hits[0]['title'])

    def test_no_overwrite(self):
        self.mod.put_state(self.task())
        self.mod.put_state(self.task('report999999'))
        self.assertEqual(len(self.mod._history_search()),2)

    def test_current_state_unchanged(self):
        self.mod.put_state(self.task())
        self.assertEqual(self.mod.get_state()['events'][0]['result'],'镇海6240')

    def test_markdown_export(self):
        self.mod.put_state(self.task())
        f=Path(self.temp.name)/'history/2026-11/task_report123456.md'
        self.assertTrue(f.exists())
        self.assertIn('镇海6240',f.read_text())

    def test_pending_token_redacted(self):
        s=self.task()
        s['pending']={'tool':'calendar.create','title':'测试日程','token':'never-share-this-token'}
        self.mod.put_state(s)
        text=(Path(self.temp.name)/'history/2026-11/task_report123456.json').read_text()
        self.assertIn('calendar.create',text)
        self.assertNotIn('never-share-this-token',text)

    def test_shortcut_result_not_verified(self):
        self.assertIn('未独立核验',self.mod._history_event_quality(
            {'tool':'calendar.create','status':'ok','verified':False}))

    def test_history_ui_entry(self):
        self.assertIn('archive',[r[0] for r in self.mod._card_nav_items('home')])
        self.assertIn("elif self.page == 'archive_detail'",self.source)
        self.assertIn('history_copy',self.source)
        self.assertIn('history_share',self.source)
        self.assertIn('clipboard.set(md)',self.source)

    def test_original_tools_preserved(self):
        for name in ('text.respond','reminder.create','calendar.create',
                     'apple_notes.create','contacts.lookup','webpage.summarize',
                     'shortcut.run','calendar.list'):
            self.assertIn(name,self.mod.TOOL_CATALOG)

    def test_disabled_tool_not_claimed_ready(self):
        result='\\n'.join(y for x,y in self.mod._card_tool_rows('calendar.create'))
        self.assertIn('未配置',result)

    def test_text_respond_unchanged(self):
        result=self.mod.run_tool({}, {'tool':'text.respond','text':'报价检查'})
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['result'],'报价检查')

    def test_existing_BU_snapshot_search(self):
        folder=Path(self.temp.name)/'bu_futures'
        folder.mkdir()
        path=folder/'bu_20261110_125154_e72d2_test.json'
        path.write_text(json.dumps({
             'product':'BU','session':'test','captured_at_bj':'2026-11-10T12:51:54+08:00',
             'session_calendar_date_bj':'2026-11-10','valid_quote_count':1,
             'suspect_quote_count':0,
             'records':[{'contract':'BU2612','last_price':4509,
                         'quote_clock':'113000','volume':51800}],
             'disclaimer':'仅供参考'},ensure_ascii=False))
        self.assertEqual(len(self.mod._history_search('BU2612')),1)

    def test_update_pipeline_unchanged(self):
        self.assertTrue(callable(self.mod.immediate_check_and_update))
        self.assertIn('manifest.json',self.source)

if __name__=='__main__':
    unittest.main(verbosity=2)
