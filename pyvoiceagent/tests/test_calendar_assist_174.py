# -*- coding: utf-8 -*-
"""V1.7.4 offline callback / calendar assist regression tests."""
import base64
import importlib.util
import os
import time
import unittest
from unittest.mock import patch

SRC = os.path.join(os.path.dirname(__file__), '..', 'agent_core_1_7_4.py')
spec = importlib.util.spec_from_file_location('pyvoice174', SRC)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def choice(tool='calendar.assist'):
    return dict(tool=tool, title='', text='', reason='', notes='',
                datetime='2026-10-18T00:00:00+08:00',
                end_datetime='2026-10-19T00:00:00+08:00',
                shortcut_id='')


def state(goal='分析10月18日日历有没有冲突并提出准备建议，不要创建新事项'):
    return dict(id='unit-test-123', goal=goal, status='ready', steps=0,
                events=[], pending=None, error='', final='')


def encoded(msg):
    return base64.b64encode(msg.encode('utf-8')).decode('ascii')


class CalendarAssist174Tests(unittest.TestCase):
    def test_routes_to_existing_read_shortcut_not_eventkit(self):
        st = state()
        with patch.object(agent, 'put_state'), patch.object(agent, 'execute_planned_actions', side_effect=lambda x:x):
            result=agent.research_then_plan(st, choice())
        self.assertIs(result, st)
        self.assertEqual(st['plan'][0]['tool'], 'calendar.list')
        self.assertEqual(st['research_phase'], 'awaiting_calendar')
        self.assertEqual(st['research_origin'], 'calendar.assist')
        self.assertTrue(st['plan_approved'])

    def test_detects_overlap_and_retains_times(self):
        raw = '查询成功（最多显示8项）：\n10-18 09:00—10:00 会议甲\n10-18 09:30—11:00 会议乙\n10-18 14:00—15:00 汇报'
        result = agent._calendar_read_insights(raw, choice())
        self.assertIn('09:00—10:00',result)
        self.assertIn('09:30—11:00',result)
        self.assertIn('会议甲 和 会议乙',result)
        self.assertIn('最多只返回8项',result)

    def test_no_overlap_only_for_parseable_events(self):
        raw = '查询成功（最多显示8项）：\n10-18 09:00—10:00 会议甲\n10-18 10:00—11:00 会议乙'
        result = agent._calendar_read_insights(raw, choice())
        self.assertIn('未发现时间重叠', result)
        self.assertNotIn('可能冲突：', result)

    def test_all_day_and_missing_time_unevaluable(self):
        raw='查询成功（最多显示8项）：\n10-18 全天 客户活动\n10-18 项目交流\n10-18 09:00—10:00 例会'
        result=agent._calendar_read_insights(raw, choice())
        self.assertIn('全天事件 1 项',result)
        self.assertIn('1 行未能可靠解析',result)
        self.assertIn('不能判断这些日程的冲突',result)

    def test_empty_result_is_not_global_calendar_assertion(self):
        result=agent._calendar_read_insights('0 项日程，查询范围内没有结果',choice())
        self.assertIn('检索范围和权限内',result)

    def test_callback_resume_second_phase_exactly_once(self):
        st=state()
        st.update(single_plan=True,plan=[choice('calendar.list')],plan_index=0,
                  plan_approved=True,research_origin='calendar.assist',
                  research_phase='awaiting_calendar',calendar_assist_action=choice(),
                  status='awaiting_callback')
        st['pending']=dict(tool='calendar.list',token='abc123',created=time.time(),
                           name='PYAgentCalendarRead',marker='[PYVoiceAgent:test:0]',
                           title='',fingerprint='123')
        reply = encoded('CALREAD1\n查询成功（最多显示8项）：\n10-18 09:00—10:00 会议甲\n10-18 09:30—11:00 会议乙')
        follow={'actions':[dict(choice('text.respond'),text='会议甲与会议乙有时间冲突')], 'question':''}
        calls=[]
        with patch.object(agent,'get_state',return_value=st), \
             patch.object(agent,'put_state'), \
             patch.object(agent,'prompt_alert',return_value=True), \
             patch.object(agent,'_deepseek_request',side_effect=lambda *a,**kw: (calls.append('ai') or follow)), \
             patch.object(agent,'execute_planned_actions',side_effect=lambda s: s):
            self.assertTrue(agent.bridge_callback('abc123','ok',reply))
            self.assertFalse(agent.bridge_callback('abc123','ok',reply))
        self.assertEqual(calls,['ai'])
        self.assertIsNone(st['pending'])
        self.assertEqual(st['plan'][0]['tool'],'text.respond')
        self.assertEqual(st['research_phase'],'analysis_complete')
        self.assertEqual(len([e for e in st['events'] if e['tool']=='calendar.list']),1)

    def test_invalid_read_reply_never_calls_ai(self):
        st=state()
        st.update(status='awaiting_callback',research_origin='calendar.assist',
                  research_phase='awaiting_calendar')
        st['pending']=dict(tool='calendar.list',token='abc',created=time.time(),
                           name='PYAgentCalendarRead',marker='marker',title='')
        with patch.object(agent,'get_state',return_value=st), \
             patch.object(agent,'put_state'), \
             patch.object(agent,'_deepseek_request',side_effect=AssertionError('must not call')):
            self.assertFalse(agent.bridge_callback('abc','ok',encoded('ok')))
        self.assertEqual(st['status'],'needs_review')
        self.assertIsNotNone(st['pending'])

    def test_reminder_requires_original_intent_and_explicit_confirmation(self):
        st=state(goal='分析10月18日日程后提醒我提前30分钟准备')
        st['status']='running'
        reminder=dict(choice('reminder.create'),title='提前准备',
                      datetime='2026-10-18T08:30:00+08:00')
        follow={'actions':[reminder], 'question':''}
        approval=[]
        with patch.object(agent,'put_state'), \
             patch.object(agent,'prompt_alert',side_effect=lambda *a,**k:(approval.append(a[0]) or False)), \
             patch.object(agent,'_deepseek_request',return_value=follow), \
             patch.object(agent,'execute_planned_actions',side_effect=AssertionError('must not write')):
            agent._finish_research_plan(st,'calendar.assist','已读取日程',True)
        self.assertIn('确认基于已读资料创建事项',approval)
        self.assertEqual(st['status'],'paused')
        self.assertIn('没有写入系统',st['error'])

    def test_user_declines_data_upload_no_second_model_call(self):
        st=state()
        with patch.object(agent,'put_state'), \
             patch.object(agent,'_deepseek_request',side_effect=AssertionError('must not call')):
            agent._finish_research_plan(st,'calendar.assist','private calendar',False)
        self.assertEqual(st['status'],'paused')
        self.assertIn('未进行第二次请求',st['error'])


if __name__=='__main__':
    unittest.main()
