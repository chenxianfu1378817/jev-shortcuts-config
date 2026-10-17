# -*- coding: utf-8 -*-
"""One-shot planning, no extra AI callbacks, real-API usage accounting."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

PATH=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_5_2.py'))
spec=importlib.util.spec_from_file_location('agent_151',PATH)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def action(tool,title='',text='',start='',end='',notes=''):
    return dict(tool=tool,reason='',text=text,title=title,datetime=start,
                end_datetime=end,notes=notes,shortcut_id='')


def state():
    return dict(id='batchA',goal='创建一条备忘录和一个日历事件',created=a.now_iso(),
                status='ready',steps=0,events=[],pending=None,final='',error='')


class OneShotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.before=(a.DATA_DIR,a.STATE_PATH,a.MODULE_REGISTRY_PATH,
                     a.RECOVERY_QUEUE_PATH,a.REMINDER_LEDGER_PATH)
        a.DATA_DIR=self.temp.name
        a.STATE_PATH=os.path.join(self.temp.name,'state.json')
        a.MODULE_REGISTRY_PATH=os.path.join(self.temp.name,'modules.json')
        a.RECOVERY_QUEUE_PATH=os.path.join(self.temp.name,'recovery.json')
        a.REMINDER_LEDGER_PATH=os.path.join(self.temp.name,'reminders.json')
        a.atomic_json(a.MODULE_REGISTRY_PATH,{'modules':{
            'apple_notes.create':{'name':'PYAgentNotes','verified':True},
            'calendar.create':{'name':'PYAgentCalendar','verified':True}
        }})
        self.calls=[]
        shortcut=types.ModuleType('shortcuts')
        shortcut.open_url=lambda url:self.calls.append(url)
        self.module_patch=patch.dict(sys.modules,{'shortcuts':shortcut})
        self.module_patch.start()

    def tearDown(self):
        self.module_patch.stop()
        (a.DATA_DIR,a.STATE_PATH,a.MODULE_REGISTRY_PATH,
         a.RECOVERY_QUEUE_PATH,a.REMINDER_LEDGER_PATH)=self.before
        self.temp.cleanup()

    def batch(self):
        start=(datetime.now().astimezone()+timedelta(days=3)).replace(
            hour=10,minute=0,second=0,microsecond=0)
        return {'actions':[action('apple_notes.create','采购记录','测试备忘录'),
            action('calendar.create','采购会议',start=start.isoformat(),
                   end=(start+timedelta(minutes=30)).isoformat(),notes='讨论供应')], 'question':''}

    def test_one_planning_call_two_writes_and_no_finish_call(self):
        with patch.object(a,'_deepseek_request',return_value=self.batch()) as model, \
             patch.object(a,'prompt_alert',return_value=True):
            s=a.plan_once(state())
            self.assertEqual(s['status'],'awaiting_callback')
            self.assertTrue(s['plan_approved'])
            self.assertEqual(len(self.calls),1)
            self.assertTrue(a.bridge_callback(s['pending']['token'],'ok'))
            middle=a.get_state()
            self.assertEqual(len(self.calls),2)
            self.assertEqual(middle['plan_index'],1)
            self.assertTrue(a.bridge_callback(middle['pending']['token'],'ok'))
        done=a.get_state()
        self.assertEqual(model.call_count,1)
        self.assertEqual(done['status'],'finished')
        self.assertEqual(done['plan_index'],2)
        self.assertEqual(len(self.calls),2)
        self.assertEqual([v['tool'] for v in done['events']],
                         ['apple_notes.create','calendar.create'])
        self.assertIn('苹果备忘录',done['final'])
        self.assertIn('日历',done['final'])

    def test_cannot_execute_unapproved_plan_even_after_manual_resume(self):
        s=state()
        s.update(single_plan=True,plan=self.batch()['actions'],plan_index=0,
                 plan_approved=False,status='paused')
        a.execute_planned_actions(s)
        self.assertEqual(self.calls,[])
        self.assertEqual(s['status'],'paused')
        self.assertEqual(s['plan_index'],0)

    def test_user_decline_does_not_dispatch(self):
        with patch.object(a,'_deepseek_request',return_value=self.batch()), \
             patch.object(a,'prompt_alert',return_value=False):
            s=a.plan_once(state())
        self.assertEqual(s['status'],'paused')
        self.assertFalse(s.get('plan_approved',False))
        self.assertEqual(self.calls,[])

    def test_questions_never_execute_partial_plan(self):
        with patch.object(a,'_deepseek_request',return_value={
                'actions':[],'question':'请给出日历结束时间'}), \
             patch.object(a,'prompt_alert',return_value=True):
            s=a.plan_once(state())
        self.assertEqual(s['status'],'paused')
        self.assertIn('结束时间',s['error'])
        self.assertEqual(self.calls,[])

    def test_reject_partial_plan_asking_question(self):
        bad={'actions':[action('apple_notes.create','记录','正文')],
             'question':'还缺少日期'}
        with self.assertRaises(ValueError):
            a.parse_action_plan(bad,a.available_tool_catalog())

    def test_invalid_timezone_rejected_before_writes(self):
        plan=self.batch()
        plan['actions'][1]['datetime']='2026-10-22T10:00:00'
        with self.assertRaises(ValueError):
            a.parse_action_plan(plan,a.available_tool_catalog())

    def test_unverified_module_rejected(self):
        a.atomic_json(a.MODULE_REGISTRY_PATH,{'modules':{}})
        with self.assertRaises(ValueError):
            a.parse_action_plan(self.batch(),a.available_tool_catalog())

    def test_explicitly_disallowed_legacy_tools(self):
        data={'actions':[action('shortcut.hub_echo','测试')], 'question':''}
        with self.assertRaises(ValueError):
            a.parse_action_plan(data,a.available_tool_catalog())

    def test_provider_usage_actual_and_cumulative(self):
        s=state()
        resp={'choices':[{'finish_reason':'stop','message':{
            'content':json.dumps({'actions':[action('local_note.save','记录','内容')],
                                  'question':''},ensure_ascii=False)}}],
            'usage':{'prompt_tokens':250,'completion_tokens':75,'total_tokens':325,
                     'prompt_cache_hit_tokens':130,'prompt_cache_miss_tokens':120}}
        recorded=[]
        def fake_urlopen(req,timeout=90):
            recorded.append(json.loads(req.data.decode('utf-8')))
            return io.BytesIO(json.dumps(resp).encode('utf-8'))
        with patch.object(a,'urlopen',side_effect=fake_urlopen), \
             patch.object(a,'api_key',return_value='test-only'):
            one=a._deepseek_request([{'role':'system','content':'policy'}],
                                    expect_plan=True,state=s)
            two=a._deepseek_request([{'role':'system','content':'policy'}],
                                    expect_plan=True,state=s)
        self.assertEqual(one['actions'][0]['tool'],'local_note.save')
        self.assertEqual(two['actions'][0]['tool'],'local_note.save')
        self.assertEqual(len(recorded),2)
        self.assertEqual(s['token_usage']['requests_with_usage'],2)
        self.assertEqual(s['token_usage']['prompt_tokens'],500)
        self.assertEqual(s['token_usage']['completion_tokens'],150)
        self.assertEqual(s['token_usage']['prompt_cache_hit_tokens'],260)
        self.assertIn('DeepSeek 2 次',a.token_usage_report(s))

    def test_complex_mode_keeps_legacy_planner(self):
        with patch.object(a,'api_key',return_value='test-key'), \
             patch.object(a,'prompt_alert',return_value=True), \
             patch.object(a,'drive_agent',side_effect=lambda st: st) as old, \
             patch.object(a,'plan_once') as new:
            result = a.start_new('先读取剪贴板再分析', force_stepwise=True)
        self.assertIsInstance(result,dict)
        self.assertEqual(old.call_count,1)
        self.assertEqual(new.call_count,0)

    def test_missing_usage_does_not_invent_tokens(self):
        s=state()
        a.record_token_usage(s,None)
        self.assertNotIn('token_usage',s)
        self.assertIn('未返回',a.token_usage_report(s))

    def test_failed_callback_does_not_run_calendar(self):
        with patch.object(a,'_deepseek_request',return_value=self.batch()), \
             patch.object(a,'prompt_alert',return_value=True):
            s=a.plan_once(state())
            self.assertFalse(a.bridge_callback(s['pending']['token'],'failed'))
        self.assertEqual(len(self.calls),1)
        self.assertEqual(a.get_state()['status'],'needs_review')


if __name__=='__main__':
    unittest.main()
