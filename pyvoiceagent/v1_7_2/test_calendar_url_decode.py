# -*- coding: utf-8 -*-
"""Contract tests for duplicate-calendar-shortcut query transport."""
import base64
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

CORE=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_7_2.py'))
sp=importlib.util.spec_from_file_location('voice_agent_171',CORE)
a=importlib.util.module_from_spec(sp)
sp.loader.exec_module(a)


def query_action(start=None,end=None):
    dt=datetime.now().astimezone()
    start=start or dt.isoformat()
    end=end or (dt+timedelta(days=1)).isoformat()
    return {'tool':'calendar.list','title':'','text':'','reason':'',
            'datetime':start,'end_datetime':end,'notes':'','shortcut_id':''}


class CalendarReadBridgeTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.oldpath=a.STATE_PATH
        a.STATE_PATH=os.path.join(self.t.name,'current_task.json')
        self.fake=types.ModuleType('shortcuts')
        self.urls=[]
        self.fake.open_url=lambda url:self.urls.append(url) or None
        self.m=patch.dict(sys.modules,{'shortcuts':self.fake})
        self.m.start()
        self.state={'id':'calendar171','goal':'查询明天有哪些日程','steps':0,
                    'status':'ready','plan':[query_action()], 'single_plan':True,
                    'plan_approved':True,'plan_index':0,
                    'events':[], 'created':a.now_iso()}
    def tearDown(self):
        self.m.stop()
        a.STATE_PATH=self.oldpath
        self.t.cleanup()

    def handoff(self):
        with patch.object(a,'_local_calendar_list',side_effect=AssertionError('must not touch EventKit')):
            a.put_state(self.state)
            a.execute_planned_actions(self.state)
        self.assertEqual(self.state['status'],'awaiting_callback')
        self.assertEqual(len(self.urls),1)
        url=self.urls[0]
        self.assertIn('shortcuts://run-shortcut?',url)
        q=parse_qs(urlsplit(url).query)
        self.assertEqual(q['name'],['PYAgentCalendarRead'])
        payload=json.loads(base64.b64decode(q['text'][0]))
        self.assertEqual(payload['route'],'calendar.list')
        self.assertEqual(payload['start'],self.state['plan'][0]['datetime'])
        self.assertEqual(payload['end'],self.state['plan'][0]['end_datetime'])
        self.assertEqual(payload['token'],self.state['pending']['token'])
        return payload

    def test_calendar_list_routes_to_read_copy_without_eventkit(self):
        self.handoff()

    def test_matching_callback_reports_actual_events_with_one_ai_plan(self):
        payload=self.handoff()
        txt='CALREAD1\n2 项日程\n• 09:00—10:00 项目会议\n• 15:00—16:00 客户回访'
        encoded=base64.b64encode(txt.encode('utf-8')).decode('ascii')
        with patch.object(a,'final_report'):
            self.assertTrue(a.bridge_callback(payload['token'],'ok',encoded))
        s=a.get_state()
        self.assertEqual(s['status'],'finished')
        self.assertEqual(len(s['events']),1)
        self.assertEqual(s['events'][0]['tool'],'calendar.list')
        self.assertIn('项目会议',s['events'][0]['result'])
        self.assertIn('客户回访',s['events'][0]['result'])
        self.assertEqual(s['plan_index'],1)
        self.assertFalse(s['events'][0]['verified'])

    def test_explicit_empty_result_not_silent_guess(self):
        payload=self.handoff()
        txt='CALREAD1\n0 项日程，查询范围内没有结果'
        encoded=base64.b64encode(txt.encode('utf-8')).decode()
        with patch.object(a,'final_report'):
            self.assertTrue(a.bridge_callback(payload['token'],'ok',encoded))
        self.assertIn('0 项日程',a.get_state()['final'])

    def test_plain_ok_callback_without_data_is_rejected(self):
        p=self.handoff()
        self.assertFalse(a.bridge_callback(p['token'],'ok'))
        s=a.get_state()
        self.assertEqual(s['status'],'needs_review')
        self.assertTrue(s['pending'])
        self.assertEqual(s['events'],[])
        self.assertIn('CALREAD1',s['error'])

    def test_wrong_format_is_not_an_empty_calendar(self):
        p=self.handoff()
        for raw in ['', '已完成', 'ERROR: unprivileged']:
            s=a.get_state()
            s['status']='awaiting_callback'
            a.put_state(s)
            encoded=base64.b64encode(raw.encode()).decode()
            self.assertFalse(a.bridge_callback(p['token'],'ok',encoded))
            self.assertEqual(a.get_state()['events'],[])

    def test_wrong_token_is_ignored(self):
        p=self.handoff()
        txt=base64.b64encode('CALREAD1\n0 项日程'.encode()).decode()
        self.assertFalse(a.bridge_callback('wrong-token','ok',txt))
        s=a.get_state()
        self.assertEqual(s['status'],'awaiting_callback')
        self.assertIsNotNone(s['pending'])

    def test_failed_callback_not_reported_as_empty_calendar(self):
        p=self.handoff()
        self.assertFalse(a.bridge_callback(p['token'],'failed'))
        s=a.get_state()
        self.assertEqual(s['status'],'needs_review')
        self.assertEqual(s['events'],[])

    def test_result_size_limit_blocks_overlarge_callback(self):
        p=self.handoff()
        blob=base64.b64encode(('CALREAD1\n'+'内容'*1100).encode()).decode()
        self.assertFalse(a.bridge_callback(p['token'],'ok',blob))
        self.assertEqual(a.get_state()['status'],'needs_review')

    def test_percent_url_encoded_base64_callback(self):
        from urllib.parse import quote
        p=self.handoff()
        plain='CALREAD1\n查询到 4 项日程：\n重阳节\nPYAgent测试01—上午会议'
        raw=base64.b64encode(plain.encode('utf-8')).decode('ascii')
        result=quote(raw,safe='')
        # Pythonista URL handler returns the raw percent-encoded argument.
        with patch.object(a,'final_report'):
            self.assertTrue(a.bridge_callback(p['token'],'ok',result))
        actual=a.get_state()['events'][0]['result']
        self.assertIn('重阳节',actual)
        self.assertIn('PYAgent测试01',actual)

    def test_wrapped_base64_and_pct_encoded_newline(self):
        from urllib.parse import quote
        text='CALREAD1\n查询到4项日程，日程如下：\n测试会议'
        raw=base64.b64encode(text.encode()).decode()
        wrapped=raw[:40]+'\n'+raw[40:]
        encoded=quote(wrapped,safe='')
        self.assertEqual(a.decode_shortcuts_result_b64(encoded),text)

    def test_plus_converted_to_space_accepted(self):
        # Some Pythonista URL argument parsers apply form-style plus decoding.
        sample='CALREAD1\n??'
        raw=base64.b64encode(sample.encode()).decode()
        if '+' not in raw:
            import itertools
            sample=next('CALREAD1\n'+x for x in
                ('?','??','???','汉字','办公','—','费用','月度','q2','❤')
                if '+' in base64.b64encode(('CALREAD1\n'+x).encode()).decode())
            raw=base64.b64encode(sample.encode()).decode()
        result=a.decode_shortcuts_result_b64(raw.replace('+',' '))
        self.assertEqual(result,sample)

    def test_malformed_percent_escape_rejected(self):
        with self.assertRaisesRegex(ValueError,'百分号'):
            a.decode_shortcuts_result_b64('YWJj%QZ')

    def test_invalid_base64_still_rejected(self):
        with self.assertRaises(Exception):
            a.decode_shortcuts_result_b64('This-is-not-Base64%3D')

    def test_old_raw_base64_callback_still_accepted(self):
        raw=base64.b64encode('CALREAD1\n0 项日程'.encode()).decode()
        self.assertEqual(a.decode_shortcuts_result_b64(raw),'CALREAD1\n0 项日程')

    def test_upgrade_gate_allows_only_pending_calendar_read(self):
        self.state['status']='needs_review'
        self.state['pending']={'tool':'calendar.list','token':'a','marker':'m'}
        a.put_state(self.state)
        with patch.object(a,'_release_download',side_effect=RuntimeError('offline')) as network:
            result=a.immediate_check_and_update()
        network.assert_called_once()
        self.assertIn('offline',result['message'])

    def test_upgrade_gate_still_blocks_pending_real_writes(self):
        self.state['status']='needs_review'
        self.state['pending']={'tool':'calendar.create','token':'a','marker':'m'}
        a.put_state(self.state)
        with patch.object(a,'_release_download') as network:
            result=a.immediate_check_and_update()
        network.assert_not_called()
        self.assertIn('待核验',result['message'])

    def test_read_does_not_ask_for_cross_app_write_approval(self):
        with patch.object(a,'prompt_alert') as dialog:
            self.handoff()
        dialog.assert_not_called()

    def test_existing_calendar_creation_shortcut_is_untouched(self):
        self.assertEqual(a.SYSTEM_MODULES['calendar.create'],'PYAgentCalendar')
        self.assertNotIn('calendar.list',a.SYSTEM_MODULES)
        self.assertIn('calendar.list',a.available_tool_catalog())
        self.assertIn('calendar.create',a.TOOL_CATALOG)

    def test_date_range_validation(self):
        dt=datetime.now().astimezone()
        choice=query_action(dt.isoformat(),(dt+timedelta(days=32)).isoformat())
        with self.assertRaises(ValueError):
            a.bridge_payload(self.state,choice,'calendar.list',a.CALENDAR_READ_SHORTCUT)


if __name__=='__main__':
    unittest.main()
