# -*- coding: utf-8 -*-
"""Offline simulations for practical phone tools, strict privacy & safe mutations."""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

src=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_6_0.py'))
spec=importlib.util.spec_from_file_location('phone_agent_160',src)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def action(tool,title='',body='',start='',end='',notes=''):
    return dict(tool=tool,reason='',text=body,title=title,
                datetime=start,end_datetime=end,notes=notes,shortcut_id='')


def state(goal='查看今天的待办'):
    return dict(id='test160',goal=goal,created=a.now_iso(),
                status='ready',steps=0,events=[],pending=None,final='',error='')


class ReminderStub:
    def __init__(self,title,date=None,done=False):
        self.title=title
        self.due_date=date
        self.completed=done
        self.notes=''
        self.alarms=[]
        self.saved=0
    def save(self):
        self.saved+=1


class PracticalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_state=a.STATE_PATH
        self.old_data=a.DATA_DIR
        a.DATA_DIR=self.temp.name
        a.STATE_PATH=os.path.join(self.temp.name,'task.json')
        self.reminder_items=[]
        reminders=types.ModuleType('reminders')
        def get_reminders(calendar=None,completed=None):
            return [r for r in self.reminder_items if completed is None or r.completed==completed]
        reminders.get_reminders=get_reminders
        self.contacts_items=[]
        contacts=types.ModuleType('contacts')
        contacts.get_all_people=lambda:list(self.contacts_items)
        self.clip_text='采购报价：甲 4320 元，乙 4350 元'
        clipboard=types.ModuleType('clipboard')
        clipboard.get=lambda:self.clip_text
        self.modules=patch.dict(sys.modules,{'reminders':reminders,'contacts':contacts,'clipboard':clipboard})
        self.modules.start()
        self.now=datetime.now().astimezone()
        self.tomorrow=self.now+timedelta(days=1)

    def tearDown(self):
        self.modules.stop()
        a.STATE_PATH=self.old_state
        a.DATA_DIR=self.old_data
        self.temp.cleanup()

    def approved_plan(self,actions,goal='查看今天的待办'):
        s=state(goal)
        s.update(single_plan=True,plan=actions,plan_index=0,plan_approved=True)
        return s

    def test_read_reminders_local_and_filtered(self):
        self.reminder_items=[
            ReminderStub('联系供应商',self.now-timedelta(hours=2)),
            ReminderStub('明天采购',self.tomorrow),
            ReminderStub('已办完',self.now,True),
            ReminderStub('没设时间')]
        start=(self.now-timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        end=(self.now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        result=a._local_reminder_list(action('reminder.list',start=start.isoformat(),end=end.isoformat()))
        self.assertEqual(result['status'],'ok')
        self.assertIn('联系供应商',result['result'])
        self.assertNotIn('明天采购',result['result'])
        self.assertNotIn('没设时间',result['result'])
        self.assertNotIn('已办完',result['result'])

    def test_read_all_pending_with_undated_items(self):
        self.reminder_items=[ReminderStub('无日期'),ReminderStub('明天采购',self.tomorrow)]
        result=a._local_reminder_list(action('reminder.list'))
        self.assertIn('无日期',result['result'])
        self.assertIn('明天采购',result['result'])

    def test_reminder_complete_only_unique_exact_match_with_confirmation(self):
        r=ReminderStub('联系供应商',self.tomorrow)
        self.reminder_items=[r]
        with patch.object(a,'prompt_alert',return_value=True) as confirm:
            result=a._local_reminder_complete(action('reminder.complete','联系供应商'))
        self.assertEqual(result['status'],'ok')
        self.assertTrue(result['verified'])
        self.assertTrue(r.completed)
        self.assertEqual(r.saved,1)
        confirm.assert_called_once()

    def test_complete_refused_when_two_identical_open_reminders(self):
        self.reminder_items=[ReminderStub('项目A'),ReminderStub('项目A')]
        with patch.object(a,'prompt_alert') as confirm:
            result=a._local_reminder_complete(action('reminder.complete','项目A'))
        self.assertEqual(result['status'],'failed')
        confirm.assert_not_called()
        self.assertTrue(all(not x.completed for x in self.reminder_items))

    def test_complete_declined_preserves_reminder(self):
        r=ReminderStub('验收任务');self.reminder_items=[r]
        with patch.object(a,'prompt_alert',return_value=False):
            result=a._local_reminder_complete(action('reminder.complete','验收任务'))
        self.assertEqual(result['status'],'declined')
        self.assertFalse(r.completed)

    def test_contact_lookup_matches_name_and_company_locally(self):
        self.contacts_items=[
            types.SimpleNamespace(full_name='张经理',organization='广西采购部',
                                  phone=[('mobile','13800000000')],email=[]),
            types.SimpleNamespace(full_name='李经理',organization='广西采购部',
                                  phone=[('mobile','13900000000')],email=[]),
            types.SimpleNamespace(full_name='王经理',organization='另一家公司',
                                  phone=[('mobile','13700000000')],email=[])]
        result=a._local_contacts_lookup(action('contacts.lookup','张经理'))
        self.assertEqual(result['status'],'ok')
        self.assertIn('13800000000',result['result'])
        self.assertNotIn('13900000000',result['result'])

    def test_contact_search_does_not_upload_phone_to_deepseek(self):
        self.contacts_items=[types.SimpleNamespace(full_name='张经理',organization='',
                              phone=[('手机','13800000000')],email=[])]
        request=[]
        planned={'actions':[action('contacts.lookup','张经理')],'question':''}
        def fake_ai(msg,**kwargs):
            request.append(str(msg))
            return planned
        with patch.object(a,'_deepseek_request',side_effect=fake_ai), \
             patch.object(a,'prompt_alert',return_value=True):
            outcome=a.plan_once(state('查找张经理电话'))
        self.assertEqual(outcome['status'],'finished')
        self.assertEqual(len(request),1)
        self.assertNotIn('13800000000',request[0])
        self.assertIn('13800000000',outcome['events'][0]['result'])
        self.assertEqual(outcome['plan_index'],1)

    def test_maps_search_encodes_query_without_dialing(self):
        sent=[]
        with patch('webbrowser.open',side_effect=lambda uri: sent.append(uri) or True):
            result=a._local_maps_search(action('maps.search','南宁东站'))
        self.assertEqual(result['status'],'ok')
        self.assertTrue(sent[0].startswith('https://maps.apple.com/?q='))
        self.assertFalse(result['verified'])

    def test_clipboard_only_read_if_explicitly_requested_and_authorized(self):
        logged=[]
        def fake_ai(msg,**kwargs):
            logged.append(json.loads(msg[1]['content']))
            return {'actions':[action('text.respond',body='三条要点')], 'question':''}
        with patch.object(a,'_deepseek_request',side_effect=fake_ai), \
             patch.object(a,'prompt_alert',return_value=True):
            s=a.plan_once(state('总结刚复制的报价内容'))
        self.assertEqual(s['status'],'finished')
        self.assertIn('clipboard_text',logged[0])
        self.assertEqual(logged[0]['clipboard_text'],self.clip_text)
        self.assertEqual(s['events'][0]['result'],'三条要点')
        logged.clear()
        with patch.object(a,'_deepseek_request',side_effect=fake_ai), \
             patch.object(a,'prompt_alert',return_value=True):
            a.plan_once(state('找张经理的电话'))
        self.assertNotIn('clipboard_text',logged[0])

    def test_clipboard_refusal_does_not_call_model(self):
        with patch.object(a,'prompt_alert',return_value=False), \
             patch.object(a,'_deepseek_request') as request:
            s=a.plan_once(state('请总结剪贴板内容'))
        self.assertEqual(s['status'],'paused')
        request.assert_not_called()

    def test_clipboard_too_long_fails_without_upload(self):
        self.clip_text='秘密'*a.MAX_CLIPBOARD_CONTEXT
        with patch.object(a,'prompt_alert',return_value=True), \
             patch.object(a,'_deepseek_request') as request:
            s=a.plan_once(state('总结刚复制的内容'))
        request.assert_not_called()
        self.assertIn('内容过长',s['error'])

    def test_plan_rejects_ambiguous_reminder_date_range(self):
        bad={'actions':[action('reminder.list',start=self.now.isoformat())],'question':''}
        with self.assertRaises(ValueError):
            a.parse_action_plan(bad,a.available_tool_catalog())

    def test_ai_action_cannot_call_unregistered_shortcuts(self):
        bad={'actions':[action('shortcut.run','工具')],'question':''}
        with self.assertRaises(ValueError):
            a.parse_action_plan(bad,a.available_tool_catalog())

    def test_stepwise_privacy_barrier(self):
        s=state('查张经理电话')
        raw=action('contacts.lookup','张经理')
        with patch.object(a,'run_tool') as execute:
            a.drive_agent(s,planner=lambda st:raw)
        execute.assert_not_called()
        self.assertEqual(s['status'],'paused')
        self.assertIn('隐私',s['error'])

    def test_one_ai_plan_multiple_local_tools_no_extra_requests(self):
        self.reminder_items=[ReminderStub('供应商报价确认',self.tomorrow)]
        self.contacts_items=[types.SimpleNamespace(full_name='张经理',organization='',
                              phone=[('work','18812345678')],email=[])]
        plan={'actions':[action('reminder.list'),action('contacts.lookup','张经理')],
              'question':''}
        with patch.object(a,'_deepseek_request',return_value=plan) as ai, \
             patch.object(a,'prompt_alert',return_value=True):
            result=a.plan_once(state('查待办并找张经理电话'))
        self.assertEqual(ai.call_count,1)
        self.assertEqual(result['status'],'finished')
        self.assertEqual(len(result['events']),2)
        self.assertIn('18812345678',result['events'][1]['result'])

    def test_validate_text_answer_not_empty(self):
        with self.assertRaises(ValueError):
            a.parse_action_plan({'actions':[action('text.respond',body='')],'question':''},
                                a.available_tool_catalog())


if __name__=='__main__':
    unittest.main()
