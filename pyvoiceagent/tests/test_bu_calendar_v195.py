# -*- coding: utf-8 -*-
"""V1.9.5 BU Calendar regression: every invocation creates a NEW request.

These tests use fake Shortcuts launchers and temporary local journals.
No real Calendar events are created.
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


def sample(mode='day', time='2026-11-10T15:03:00+08:00'):
    return {'session': mode, 'session_calendar_date_bj': time[:10],
            'captured_at_bj': time, 'valid_quote_count': 2, 'suspect_quote_count': 0,
            'records': [{'contract':'BU2612','last_price':4509,'quote_clock':'150000'},
                        {'contract':'BU2701','last_price':4273,'quote_clock':'150000'}],
            'suspect_records':[], 'disclaimer':'参考行情，非官方结算价'}


class EveryRunCreatesCalendarRequest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.urls = []
        m = types.ModuleType('bu_calendar_v195_test')
        self.mod = m
        env = m.__dict__
        env.update(os=os,re=re,datetime=datetime,timedelta=timedelta,hmac=hmac,uuid=uuid,
                   DATA_DIR=self.temp.name,BRIDGE_TIMEOUT=300,MAX_BRIDGE_TEXT=3500)
        env['atomic_json'] = self.write_json
        env['verified_system_module'] = lambda route: None  # unregistered Mac
        env['prompt_alert'] = lambda *args,**kwargs: True
        env['_bu_report'] = lambda s: '\n'.join('{} = {}'.format(x['contract'],x['last_price'])
                                                        for x in s['records'])
        env['bu_capture_run'] = lambda session: sample(
            session, '2026-11-10T23:03:00+08:00' if session == 'night'
                     else '2026-11-10T15:03:00+08:00')
        env['bridge_payload'] = self.fake_payload
        exec(compile(MODULE.read_text(encoding='utf-8'),str(MODULE),'exec'),env)

    @staticmethod
    def write_json(path, data):
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path+'.tmp','w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False)
        os.replace(path+'.tmp',path)

    @staticmethod
    def fake_payload(state,choice,route,name):
        assert name=='PYAgentCalendar' and route=='calendar.create'
        token=uuid.uuid4().hex
        payload={'version':13,'token':token,'route':route,
                 'title':choice['title'],'notes':choice['notes'],
                 'start':choice['datetime'],'end':choice['end_datetime'],
                 'marker':'[PYVoiceAgent:{}:{}]'.format(state['id'],state['steps'])}
        packed=base64.b64encode(json.dumps(payload,ensure_ascii=False).encode()).decode()
        return payload,packed,token

    def publish(self, s=None, launcher=None):
        return self.mod._bu_calendar_publish(s or sample(),
                    launcher or (lambda url:self.urls.append(url)))

    def entries(self):
        return self.mod._bu_calendar_read_ledger()['entries']

    def payloads(self):
        return [json.loads(base64.b64decode(parse_qs(urlparse(url).query)['text'][0]))
                for url in self.urls]

    def test_unenrolled_still_launches(self):
        self.assertEqual(self.publish()['status'],'awaiting_callback')
        self.assertEqual(len(self.urls),1)

    def test_second_same_day_always_launches_again(self):
        self.publish(); self.publish()
        self.assertEqual(len(self.urls),2)
        self.assertEqual(len(self.entries()),2)
        self.assertNotEqual(self.payloads()[0]['token'],self.payloads()[1]['token'])

    def test_unique_markers_for_same_day(self):
        self.publish(); self.publish()
        self.assertNotEqual(self.payloads()[0]['marker'],self.payloads()[1]['marker'])
        self.assertNotEqual(self.payloads()[0]['notes'],self.payloads()[1]['notes'])

    def test_old_ledger_is_retained_and_does_not_block(self):
        self.mod._bu_calendar_write_ledger({
            'schema':1, 'entries':{'2026-11-10:day':{'key':'2026-11-10:day','status':'shortcut_reported_ok'}}})
        self.publish()
        self.assertEqual(len(self.entries()),2)
        self.assertIn('2026-11-10:day',self.entries())

    def test_success_callback_for_first_then_second_request(self):
        self.publish(); self.publish()
        payloads=self.payloads()
        self.assertTrue(self.mod._bu_calendar_handle_callback(payloads[0]['token'],'ok'))
        states={e['token']:e['status'] for e in self.entries().values() if 'token' in e}
        self.assertEqual(states[payloads[0]['token']],'shortcut_reported_ok')
        self.assertEqual(states[payloads[1]['token']],'awaiting_callback')
        self.assertTrue(self.mod._bu_calendar_handle_callback(payloads[1]['token'],'ok'))

    def test_failed_callback_does_not_prevent_new_manual_run(self):
        self.publish()
        token=self.payloads()[0]['token']
        self.assertTrue(self.mod._bu_calendar_handle_callback(token,'failed'))
        self.publish()
        self.assertEqual(len(self.urls),2)
        self.assertEqual(len(self.entries()),2)

    def test_unknown_token_cannot_modify_a_request(self):
        self.publish()
        self.assertFalse(self.mod._bu_calendar_handle_callback('bad-token','ok'))
        self.assertEqual(next(iter(self.entries().values()))['status'],'awaiting_callback')

    def test_duplicate_callback_does_not_create_another_request(self):
        self.publish()
        token=self.payloads()[0]['token']
        self.assertTrue(self.mod._bu_calendar_handle_callback(token,'ok'))
        self.assertTrue(self.mod._bu_calendar_handle_callback(token,'ok'))
        self.assertEqual(len(self.urls),1)
        self.assertEqual(len(self.entries()),1)

    def test_bad_shortcut_launch_logs_uncertainty_but_next_explicit_run_allowed(self):
        def throw(url):
            raise RuntimeError('macOS Shortcuts did not start')
        outcome=self.publish(launcher=throw)
        self.assertEqual(outcome['status'],'needs_review')
        self.assertEqual(len(self.entries()),1)
        self.publish()
        self.assertEqual(len(self.entries()),2)

    def test_corrupted_ledger_does_not_get_overwritten(self):
        path=self.mod.BU_CALENDAR_LEDGER_PATH
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,'w',encoding='utf-8') as f:f.write('{malformed')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.urls)

    def test_plain_test_does_not_create_calendar(self):
        self.assertEqual(self.publish(sample('test'))['status'],'skipped')
        self.assertFalse(self.urls)

    def test_manual_calendar_test_remains_confirmed(self):
        self.mod.prompt_alert=lambda *args,**kw:False
        outcome=self.mod._bu_calendar_publish(sample('test'),lambda url:self.urls.append(url),True)
        self.assertEqual(outcome['status'],'cancelled')
        self.assertFalse(self.urls)

    def test_day_night_preserve_beijing_timestamps(self):
        self.publish(sample('day'))
        self.publish(sample('night','2026-11-10T23:03:00+08:00'))
        ps=self.payloads()
        self.assertEqual(ps[0]['start'],'2026-11-10T15:00:00+08:00')
        self.assertEqual(ps[1]['start'],'2026-11-10T23:00:00+08:00')
        self.assertEqual(ps[1]['end'],'2026-11-10T23:10:00+08:00')

    def test_user_task_state_untouched(self):
        path=os.path.join(self.temp.name,'current_task.json')
        with open(path,'w',encoding='utf-8') as f:f.write('{"id":"existing-ai-task"}')
        self.publish()
        with open(path,encoding='utf-8') as f:
            self.assertEqual(json.load(f)['id'],'existing-ai-task')

    def test_notes_include_quote_and_unique_marker(self):
        self.publish()
        p=self.payloads()[0]
        self.assertIn('BU2612',p['notes'])
        self.assertIn('[PYVoiceAgent:',p['notes'])
        self.assertEqual(p['route'],'calendar.create')


if __name__=='__main__':
    unittest.main(verbosity=2)
