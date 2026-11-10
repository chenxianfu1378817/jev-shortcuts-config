# -*- coding: utf-8 -*-
"""PYVoiceAgent 1.9.6 Apple Calendar concise-note regression tests.
All operations use fake Shortcuts and temp storage; no real calendar modifications.
"""
import base64
from datetime import datetime, timedelta, timezone
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import types
import unittest
import uuid
from urllib.parse import parse_qs, urlparse

MODULE = Path(__file__).resolve().parents[1] / 'bu_calendar_module.py'


def sample(mode='night',time='2026-11-10T21:12:44+08:00'):
    return {'session':mode,'session_calendar_date_bj':time[:10],'captured_at_bj':time,
            'valid_quote_count':3,'suspect_quote_count':0,
            'records':[
                {'contract':'BU2611','last_price':4900,'quote_clock':'210438','volume':378},
                {'contract':'BU2612','last_price':4408,'quote_clock':'211246','volume':6515},
                {'contract':'BU2809','last_price':3635,'quote_clock':'150000','volume':12}],
            'suspect_records':[],'disclaimer':'很长的来源声明不能进入日历'}


class CompactCalendarNoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.urls=[]
        m=types.ModuleType('calendar196')
        self.mod=m
        m.__dict__.update(os=os,re=re,datetime=datetime,timedelta=timedelta,hmac=hmac,
                          uuid=uuid,DATA_DIR=self.temp.name,BRIDGE_TIMEOUT=300)
        m.atomic_json=self.atomic_json
        m.prompt_alert=lambda *a,**k:True
        m.bridge_payload=self.fake_payload
        m._bu_report=lambda snap:'FULL RAW REPORT SHOULD NOT BE IN CALENDAR'
        exec(compile(MODULE.read_text(encoding='utf-8'),str(MODULE),'exec'),m.__dict__)

    @staticmethod
    def atomic_json(path,value):
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path+'.tmp','w',encoding='utf-8') as file:
            json.dump(value,file,ensure_ascii=False)
        os.replace(path+'.tmp',path)

    @staticmethod
    def fake_payload(state,choice,route,name):
        assert route == 'calendar.create' and name == 'PYAgentCalendar'
        token=uuid.uuid4().hex
        marker='[PYVoiceAgent:{}:{}]'.format(state['id'],state['steps'])
        payload={'version':13,'token':token,'route':route,'title':choice['title'],
                 'notes':choice['notes'],'marker':marker,
                 'start':choice['datetime'],'end':choice['end_datetime']}
        encoded=base64.b64encode(json.dumps(payload,ensure_ascii=False).encode('utf-8')).decode('ascii')
        return payload,encoded,token

    def publish(self,snap=None):
        return self.mod._bu_calendar_publish(snap or sample(),self.urls.append)

    def payload(self):
        return json.loads(base64.b64decode(parse_qs(urlparse(self.urls[-1]).query)['text'][0]))

    def test_only_prices_and_short_warning(self):
        txt=self.mod._bu_calendar_compact_notes(sample())
        self.assertIn('BU2611  4900',txt)
        self.assertIn('BU2612  4408',txt)
        self.assertIn('BU2809  3635 *',txt)
        for extra in ('新浪财经','采集日期','来源','成交量','行情时间','210438','PYVoiceAgent:','很长的来源声明'):
            self.assertNotIn(extra,txt)
        self.assertLess(len(txt),180)

    def test_night_stale_hour_flagged(self):
        txt=self.mod._bu_calendar_compact_notes(sample())
        self.assertIn('BU2809  3635 *',txt)
        self.assertNotIn('BU2612  4408 *',txt)
        self.assertIn('*为非本时段或可疑报价',txt)

    def test_day_15_hour_is_not_flagged(self):
        s=sample('day','2026-11-10T15:03:00+08:00')
        self.assertIn('BU2809  3635',self.mod._bu_calendar_compact_notes(s))
        self.assertNotIn('BU2809  3635 *',self.mod._bu_calendar_compact_notes(s))

    def test_test_mode_uses_capture_time(self):
        s=sample('test','2026-11-10T21:12:44+08:00')
        self.assertIn('BU2809  3635 *',self.mod._bu_calendar_compact_notes(s))

    def test_suspect_rows_visible_but_flagged(self):
        s=sample()
        s['suspect_records']=[{'contract':'BU2803','last_price':3650,'quote_clock':'233000'}]
        txt=self.mod._bu_calendar_compact_notes(s)
        self.assertIn('BU2803  3650 *',txt)

    def test_invalid_duplicate_rows_not_shown(self):
        s=sample()
        s['records'].append({'contract':'BU2611','last_price':1,'quote_clock':'211212'})
        s['records'].append({'contract':'WRONG','last_price':2,'quote_clock':'211212'})
        self.assertEqual(self.mod._bu_calendar_compact_notes(s).count('BU2611'),1)
        self.assertNotIn('WRONG',self.mod._bu_calendar_compact_notes(s))

    def test_no_valid_quotes_raises(self):
        s=sample();s['records']=[];s['suspect_records']=[]
        with self.assertRaises(ValueError):
            self.mod._bu_calendar_compact_notes(s)

    def test_title_and_event_time_preserved(self):
        data=self.mod._bu_calendar_event_fields(sample())
        self.assertIn('夜盘',data['title'])
        self.assertIn('11月10日',data['title'])
        self.assertEqual(data['start'],'2026-11-10T23:00:00+08:00')
        self.assertEqual(data['end'],'2026-11-10T23:10:00+08:00')

    def test_calendar_payload_does_not_embed_marker_in_notes(self):
        self.assertEqual(self.publish()['status'],'awaiting_callback')
        payload=self.payload()
        self.assertEqual(payload['marker'], '')  # Shortcut cannot append internal marker
        entries=self.mod._bu_calendar_read_ledger()['entries']
        self.assertTrue(next(iter(entries.values()))['marker'].startswith('[PYVoiceAgent:'))
        self.assertNotIn('[PYVoiceAgent:',payload['notes'])
        self.assertIn('BU2612',payload['notes'])
        self.assertNotIn('行情时间',payload['notes'])
        self.assertEqual(payload['route'],'calendar.create')

    def test_second_run_still_launches_new_event(self):
        self.publish();p1=self.payload()
        self.publish();p2=self.payload()
        self.assertEqual(len(self.urls),2)
        self.assertNotEqual(p1['token'],p2['token'])

    def test_callback_still_matched_by_token(self):
        self.publish();token=self.payload()['token']
        self.assertTrue(self.mod._bu_calendar_handle_callback(token,'ok'))
        record=next(iter(self.mod._bu_calendar_read_ledger()['entries'].values()))
        self.assertEqual(record['status'],'shortcut_reported_ok')

    def test_detailed_snapshot_report_preserved_in_source(self):
        self.assertIn('def bu_capture_run(', (MODULE.parent/'bu_snapshot_module.py').read_text('utf-8'))
        self.assertNotIn('FULL RAW REPORT SHOULD NOT BE IN CALENDAR',
                         self.mod._bu_calendar_event_fields(sample())['notes'])

if __name__=='__main__':
    unittest.main(verbosity=2)
