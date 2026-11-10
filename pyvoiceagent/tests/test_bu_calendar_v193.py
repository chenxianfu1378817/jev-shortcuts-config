# -*- coding: utf-8 -*-
"""Offline simulations only: no live Apple Calendar writes or iPhone UI."""
import base64
import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import types
import unittest
from urllib.parse import parse_qs, urlparse
import uuid

MODULE = Path(__file__).with_name('bu_calendar_module_v193.py')
if not MODULE.exists():
    MODULE = Path(__file__).resolve().parents[1] / 'bu_calendar_module_v193.py'


def snapshot(mode='day',dt='2026-11-10T15:03:00+08:00'):
    return dict(session=mode, session_calendar_date_bj=dt[:10],
                captured_at_bj=dt, valid_quote_count=2, suspect_quote_count=0,
                records=[dict(contract='BU2612',last_price=4509,quote_clock='150000',volume=100),
                         dict(contract='BU2701',last_price=4273,quote_clock='150000',volume=120)],
                suspect_records=[], disclaimer='测试数据，非官方结算价')


class BUCalendarTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.urls=[]
        self.enrolled=True
        self.module=types.ModuleType('bu_calendar_test')
        n=self.module.__dict__
        n.update({'os':os,'re':re,'datetime':datetime.datetime,'timedelta':datetime.timedelta,
                  'hmac':hmac,'uuid':uuid,'DATA_DIR':self.dir.name,
                  'BRIDGE_TIMEOUT':300,'BU_CALENDAR_MAX_NOTE':3400,
                  'MAX_BRIDGE_TEXT':3500})
        def read(path, fallback=None):
            if not os.path.exists(path): return fallback or {}
            with open(path,encoding='utf-8') as f: return json.load(f)
        n['read_json']=read
        def save(path, data):
            os.makedirs(os.path.dirname(path),exist_ok=True)
            with open(path+'.tmp','w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
            os.replace(path+'.tmp',path)
        n['atomic_json']=save
        n['verified_system_module']=lambda route: 'PYAgentCalendar' if self.enrolled else None
        n['_bu_report']=lambda s: '合约：'+','.join(r['contract']+'='+str(r['last_price']) for r in s['records'])+'；'+s['disclaimer']
        n['prompt_alert']=lambda *args,**kwargs:True
        n['bu_capture_run']=lambda session: snapshot(session,'2026-11-10T23:03:00+08:00' if session=='night' else '2026-11-10T15:03:00+08:00')
        def bridge_payload(state,choice,route,shortcut_name):
            assert route=='calendar.create'
            assert shortcut_name=='PYAgentCalendar'
            assert choice['notes'] and len(choice['notes'])<=3500
            token=uuid.uuid4().hex
            payload=dict(version=13,token=token,route=route,title=choice['title'],notes=choice['notes'],
                         start=choice['datetime'],end=choice['end_datetime'],text='',shortcut_id='',
                         marker='[PYVoiceAgent:{}:{}]'.format(state['id'],state['steps']))
            return payload,base64.b64encode(json.dumps(payload,ensure_ascii=False).encode()).decode(),token
        n['bridge_payload']=bridge_payload
        exec(compile(MODULE.read_text(encoding='utf-8'),str(MODULE),'exec'),n)

    @property
    def funcs(self):return self.module.__dict__
    def publish(self,s):return self.funcs['_bu_calendar_publish'](s,lambda url:self.urls.append(url))

    def test_day_entry_and_full_notes(self):
        out=self.publish(snapshot())
        self.assertEqual(out['status'],'awaiting_callback')
        self.assertEqual(len(self.urls),1)
        entry=list(self.funcs['_bu_calendar_read_ledger']()['entries'].values())[0]
        self.assertEqual(entry['start'],'2026-11-10T15:00:00+08:00')
        self.assertIn('BU2612',self.parse_url()['notes'])
        self.assertIn('BU2701',self.parse_url()['notes'])
        self.assertEqual(self.parse_url()['route'],'calendar.create')

    def parse_url(self):
        self.assertEqual(urlparse(self.urls[-1]).scheme,'shortcuts')
        q=parse_qs(urlparse(self.urls[-1]).query)
        self.assertEqual(q['name'][0],'PYAgentCalendar')
        return json.loads(base64.b64decode(q['text'][0]).decode('utf-8'))

    def test_night_on_same_beijing_date(self):
        s=snapshot('night','2026-11-10T23:03:00+08:00')
        self.publish(s)
        data=self.parse_url()
        self.assertEqual(data['start'],'2026-11-10T23:00:00+08:00')
        self.assertEqual(data['end'],'2026-11-10T23:10:00+08:00')
        self.assertIn('夜盘',data['title'])

    def test_no_calendar_in_plain_test(self):
        result=self.publish(snapshot('test'))
        self.assertEqual(result['status'],'skipped')
        self.assertFalse(self.urls)

    def test_calendar_test_requires_confirmation(self):
        self.funcs['prompt_alert']=lambda *a,**k:False
        result=self.funcs['_bu_calendar_publish'](snapshot('test'),lambda x:self.urls.append(x),True)
        self.assertEqual(result['status'],'cancelled')
        self.assertFalse(self.urls)

    def test_unenrolled_calendar_no_jump(self):
        self.enrolled=False
        result=self.publish(snapshot())
        self.assertEqual(result['status'],'not_configured')
        self.assertFalse(self.urls)
        self.assertFalse(os.path.exists(self.funcs['BU_CALENDAR_LEDGER_PATH']))

    def test_duplicate_protection(self):
        self.publish(snapshot())
        outcome=self.publish(snapshot())
        self.assertEqual(outcome['status'],'duplicate')
        self.assertEqual(len(self.urls),1)

    def test_two_sessions_distinct(self):
        self.publish(snapshot())
        self.publish(snapshot('night','2026-11-10T23:03:00+08:00'))
        self.assertEqual(len(self.urls),2)
        self.assertEqual(len(self.funcs['_bu_calendar_read_ledger']()['entries']),2)

    def test_callback_ok_report_not_independent_verification(self):
        self.publish(snapshot())
        token=self.parse_url()['token']
        self.assertTrue(self.funcs['_bu_calendar_handle_callback'](token,'ok'))
        status=next(iter(self.funcs['_bu_calendar_read_ledger']()['entries'].values()))['status']
        self.assertEqual(status,'shortcut_reported_ok')

    def test_wrong_token_leaves_state(self):
        self.publish(snapshot())
        self.assertFalse(self.funcs['_bu_calendar_handle_callback']('bogus','ok'))
        self.assertEqual(next(iter(self.funcs['_bu_calendar_read_ledger']()['entries'].values()))['status'],'awaiting_callback')

    def test_failed_callback_kept_for_manual_review(self):
        self.publish(snapshot())
        token=self.parse_url()['token']
        self.assertTrue(self.funcs['_bu_calendar_handle_callback'](token,'failed'))
        status=next(iter(self.funcs['_bu_calendar_read_ledger']()['entries'].values()))['status']
        self.assertEqual(status,'needs_review')
        self.assertEqual(self.publish(snapshot())['status'],'duplicate')

    def test_duplicate_callback_ignored(self):
        self.publish(snapshot())
        token=self.parse_url()['token']
        self.assertTrue(self.funcs['_bu_calendar_handle_callback'](token,'ok'))
        self.assertTrue(self.funcs['_bu_calendar_handle_callback'](token,'ok'))
        self.assertEqual(len(self.funcs['_bu_calendar_read_ledger']()['entries']),1)

    def test_expired_callback_review(self):
        self.publish(snapshot())
        ledger=self.funcs['_bu_calendar_read_ledger']()
        item=next(iter(ledger['entries'].values()))
        item['created'] -= 301
        self.funcs['_bu_calendar_write_ledger'](ledger)
        self.assertTrue(self.funcs['_bu_calendar_handle_callback'](item['token'],'ok'))
        self.assertEqual(next(iter(self.funcs['_bu_calendar_read_ledger']()['entries'].values()))['status'],'needs_review')

    def test_launcher_exception_locked(self):
        def throw(url):raise RuntimeError('unreliable open')
        result=self.funcs['_bu_calendar_publish'](snapshot(),throw)
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(self.publish(snapshot())['status'],'duplicate')

    def test_corrupt_ledger_refuses_override(self):
        path=self.funcs['BU_CALENDAR_LEDGER_PATH']
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,'w') as f:f.write('[1,2,3]')
        with self.assertRaises(ValueError):self.publish(snapshot())

    def test_malformed_json_ledger_refuses_duplicate(self):
        path=self.funcs['BU_CALENDAR_LEDGER_PATH']
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,'w') as f:f.write('{invalid json')
        with self.assertRaises(ValueError):self.publish(snapshot())
        self.assertFalse(self.urls)

    def test_note_too_long_rejected(self):
        self.funcs['_bu_report']=lambda s:'a'*3450
        with self.assertRaises(ValueError):self.publish(snapshot())
        self.assertFalse(self.urls)

    def test_snapshot_capture_failure_no_handoff(self):
        self.funcs['bu_capture_run']=lambda *args:(_ for _ in ()).throw(OSError('offline'))
        with self.assertRaises(OSError):self.funcs['_bu_capture_and_calendar']('day')
        self.assertFalse(self.urls)

    def test_plain_test_capture_never_writes_calendar(self):
        self.funcs['_bu_capture_and_calendar']('test')
        self.assertFalse(self.urls)

    def test_invalid_callback_status_keeps_pending(self):
        self.publish(snapshot())
        token=self.parse_url()['token']
        self.assertTrue(self.funcs['_bu_calendar_handle_callback'](token,'surprise'))
        self.assertEqual(next(iter(self.funcs['_bu_calendar_read_ledger']()['entries'].values()))['status'],'awaiting_callback')

    def test_capture_preserves_normal_task_state(self):
        state_path=os.path.join(self.dir.name,'current_task.json')
        with open(state_path,'w',encoding='utf-8') as f:f.write('{"id":"user-normal-task"}')
        self.publish(snapshot())
        with open(state_path,encoding='utf-8') as f:self.assertEqual(json.load(f)['id'],'user-normal-task')



class CoreIntegrationTests(unittest.TestCase):
    def test_released_core_compile_and_routes(self):
        core = Path(__file__).resolve().parents[1] / 'agent_core_1_9_3.py'
        if not core.exists():
            self.skipTest('Published integration core not present in this local test folder')
        source=core.read_text(encoding='utf-8')
        compile(source, str(core), 'exec')
        self.assertIn("VERSION = '1.9.3-deepseek-flash'", source)
        self.assertIn("if sys.argv[1] == 'bu_close'", source)
        self.assertIn('_bu_capture_and_calendar(mode)', source)
        self.assertIn('_bu_calendar_handle_callback(', source)
        for name in ('def input_voice(', 'def bridge_callback(', 'def show_menu():', 'def _card_ui_show('):
            self.assertIn(name, source)

    def test_integrated_main_routes_preserved(self):
        core=Path(__file__).resolve().parents[1] / 'agent_core_1_9_3.py'
        if not core.exists(): self.skipTest('Integrated file not present locally')
        ns={'__name__':'pyvoiceagent_ci'}
        exec(compile(core.read_text(encoding='utf-8'),str(core),'exec'),ns)
        import sys
        original_argv=sys.argv
        calls=[]
        ns['_bu_capture_and_calendar']=lambda mode:calls.append(('BU',mode))
        ns['_bu_calendar_handle_callback']=lambda token, status: False
        ns['bridge_callback']=lambda *args:calls.append(('LEGACY',args))
        try:
            sys.argv=['PYVoiceAgent.py','bu_close','day']
            ns['main']()
            sys.argv=['PYVoiceAgent.py','bridge_callback','abc','ok','']
            ns['main']()
        finally:
            sys.argv=original_argv
        self.assertEqual(calls,[('BU','day'),('LEGACY',('abc','ok',''))])

    def test_integrated_real_payload_format(self):
        core=Path(__file__).resolve().parents[1] / 'agent_core_1_9_3.py'
        if not core.exists(): self.skipTest('Integrated file not present locally')
        ns={'__name__':'pyvoiceagent_ci'}
        exec(compile(core.read_text(encoding='utf-8'),str(core),'exec'),ns)
        with tempfile.TemporaryDirectory() as d:
            ns['BU_CALENDAR_LEDGER_PATH']=os.path.join(d,'calendar_ledger.json')
            ns['DATA_DIR']=d
            ns['verified_system_module']=lambda route:'PYAgentCalendar'
            ns['prompt_alert']=lambda *args,**kwargs:True
            urls=[]
            current=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            live=current.replace(hour=15,minute=3,second=0,microsecond=0).isoformat()
            actual=ns['_bu_calendar_publish'](snapshot('day',live),lambda url:urls.append(url))
            self.assertEqual(actual['status'],'awaiting_callback')
            q=parse_qs(urlparse(urls[0]).query)
            payload=json.loads(base64.b64decode(q['text'][0]).decode('utf-8'))
            self.assertEqual(payload['route'],'calendar.create')
            self.assertIn('T15:00:00+08:00',payload['start'])
            self.assertIn('BU2612',payload['notes'])

if __name__=='__main__':unittest.main(verbosity=2)