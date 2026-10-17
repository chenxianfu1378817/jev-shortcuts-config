# -*- coding: utf-8 -*-
"""V1.7.4 offline callback / calendar assist regression tests."""
import base64
import importlib.util
import os
import time
import unittest
from unittest.mock import patch

SRC = os.path.join(os.path.dirname(__file__), '..', 'agent_core_1_7_6.py')
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
    def test_prior_menu_and_approved_modules_unchanged(self):
        old_path=os.path.join(os.path.dirname(__file__),'..','agent_core_1_7_5.py')
        old_spec=importlib.util.spec_from_file_location('pyvoice173',old_path)
        old=importlib.util.module_from_spec(old_spec)
        old_spec.loader.exec_module(old)
        self.assertEqual(agent.MAIN_MENU,old.MAIN_MENU)
        self.assertEqual(len(agent.MAIN_MENU),5)
        self.assertEqual(agent.SYSTEM_MODULES,old.SYSTEM_MODULES)
        self.assertEqual(agent.CALENDAR_READ_SHORTCUT,old.CALENDAR_READ_SHORTCUT)
        self.assertEqual(agent.ONE_SHOT_TOOLS,old.ONE_SHOT_TOOLS)

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

    def test_all_day_midnight_times_stay_all_day(self):
        raw='查询成功（最多显示8项）：\n10-18 全天 00:00—23:59 节假日\n10-18 09:00—10:00 例会'
        result=agent._calendar_read_insights(raw, choice())
        self.assertIn('全天事件 1 项',result)
        self.assertIn('可解析具体起止时间的日程：1 项',result)

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
        follow={'actions':[dict(choice('text.respond'),text='两项会议冲突，建议提前准备'),reminder], 'question':''}
        approval=[]
        with patch.object(agent,'put_state'), \
             patch.object(agent,'prompt_alert',side_effect=lambda *a,**k:(approval.append((a[0],a[1])) or False)), \
             patch.object(agent,'_deepseek_request',return_value=follow), \
             patch.object(agent,'execute_planned_actions',side_effect=AssertionError('must not write')):
            agent._finish_research_plan(st,'calendar.assist','已读取日程',True)
        self.assertEqual(approval[0][0],'确认基于已读资料创建事项')
        self.assertIn('两项会议冲突，建议提前准备',approval[0][1])
        self.assertIn('08:30',approval[0][1])
        self.assertEqual(st['status'],'paused')
        self.assertIn('没有写入系统',st['error'])

    def test_calendar_write_without_explanation_is_rejected(self):
        st=state(goal='分析日历并提醒我准备')
        st['status']='running'
        follow={'actions':[dict(choice('reminder.create'),title='准备',datetime='2026-10-18T08:30:00+08:00')], 'question':''}
        with patch.object(agent,'put_state'), \
             patch.object(agent,'_deepseek_request',return_value=follow), \
             patch.object(agent,'prompt_alert',side_effect=AssertionError('no approval without suggestions')):
            agent._finish_research_plan(st,'calendar.assist','从日历读取的原文',True)
        self.assertEqual(st['status'],'paused')
        self.assertIn('先给出日程分析建议',st['error'])

    def test_user_declines_data_upload_no_second_model_call(self):
        st=state()
        with patch.object(agent,'put_state'), \
             patch.object(agent,'_deepseek_request',side_effect=AssertionError('must not call')):
            agent._finish_research_plan(st,'calendar.assist','private calendar',False)
        self.assertEqual(st['status'],'paused')
        self.assertIn('未进行第二次请求',st['error'])


    def test_real_iphone_chinese_date_and_compact_times(self):
        raw = ('查询到4项日程：\n'
               '2026年10月18日 00:0023:59重阳节\n\n'
               '2026年10月18日 09:0009:30PYAgent测试01－上午会议\n\n'
               '2026年10月18日 11:0011:45PYAgent测试02－客户拜访\n\n'
               '2026年10月18日 15:0016:00PYAgent测试03－下午总结')
        result = agent._calendar_read_insights(raw, choice())
        self.assertIn('可解析具体起止时间的日程：3 项', result)
        self.assertIn('09:00—09:30 PYAgent测试01－上午会议', result)
        self.assertIn('11:00—11:45 PYAgent测试02－客户拜访', result)
        self.assertIn('15:00—16:00 PYAgent测试03－下午总结', result)
        self.assertIn('疑似全天事件 1 项', result)
        self.assertIn('未发现时间重叠', result)
        self.assertNotIn('行未能可靠解析', result)

    def test_adjacent_chinese_date_conflicts(self):
        raw = ('查询到2项日程：\n2026年10月18日 09:0009:30会议甲\n'
               '2026年10月18日 09:1510:00会议乙')
        result = agent._calendar_read_insights(raw, choice())
        self.assertIn('本地发现可能冲突：会议甲 和 会议乙', result)

    def test_header_is_not_an_unparseable_event(self):
        raw = ('查询到1项日程：\n2026年10月18日 11:0011:45客户拜访')
        result = agent._calendar_read_insights(raw, choice())
        self.assertIn('可解析具体起止时间的日程：1 项', result)
        self.assertNotIn('行未能可靠解析', result)

    def test_calendar_summary_prefers_analysis_over_raw_readback(self):
        st = state()
        st['research_origin'] = 'calendar.assist'
        st['events'] = [
            dict(tool='calendar.list',status='ok',result='从苹果快捷指令收到：测试会议原始数据'),
            dict(tool='text.respond',status='ok',result='三项定时日程不冲突，重阳节疑似全天')]
        self.assertEqual(agent.verified_final_summary(st),
                         '三项定时日程不冲突，重阳节疑似全天')

    def test_calendar_final_prints_one_report_only(self):
        import io
        from contextlib import redirect_stdout
        st = state()
        st.update(status='finished', research_origin='calendar.assist',
                  final='三项定时日程之间没有冲突；重阳节需核实全天属性',
                  events=[dict(tool='calendar.list',status='ok',result='私密日历原始文本'),
                          dict(tool='text.respond',status='ok',result='重复的AI分析原文')])
        output = io.StringIO()
        with redirect_stdout(output):
            agent.final_report(st,show_dialog=False)
        printed=output.getvalue()
        self.assertEqual(printed.count('三项定时日程之间没有冲突'),1)
        self.assertNotIn('私密日历原始文本',printed)
        self.assertNotIn('重复的AI分析原文',printed)
        self.assertIn('日历读取通道：PYAgentCalendarRead',printed)

    def test_0_to_2359_is_candidate_not_confirmed_all_day(self):
        result = agent._calendar_read_insights(
            '查询到1项日程：\n2026年10月18日 00:0023:59重阳节',choice())
        self.assertIn('疑似全天事件 1 项',result)
        self.assertNotIn('本地发现可能冲突',result)

    def test_timed_and_holiday_no_false_overlap(self):
        raw = ('查询到2项日程：\n2026年10月18日 00:0023:59重阳节\n'
               '2026年10月18日 09:0009:30会面')
        result = agent._calendar_read_insights(raw,choice())
        self.assertIn('已解析的定时日程之间未发现时间重叠',result)
        self.assertNotIn('可能冲突：',result)



    def test_spoken_work_plan_question_becomes_nonwriting_response(self):
        st=state('明天争取把剩下的45号沥青大概300吨抓紧处理出去')
        ambiguous={'actions':[], 'question':'需要给出几点开始和几点结束，是要创建日历吗？'}
        calls=[]
        def model(*a,**k):
            calls.append(1)
            return ambiguous
        with patch.object(agent,'put_state'),\
             patch.object(agent,'available_tool_catalog',return_value={'text.respond':'展示文字'}),\
             patch.object(agent,'_deepseek_request',side_effect=model),\
             patch.object(agent,'execute_planned_actions',side_effect=lambda s:s):
            result=agent.plan_once(st)
        self.assertIs(result,st)
        self.assertEqual(len(calls),1)
        self.assertEqual(st['plan'][0]['tool'],'text.respond')
        self.assertIn('45号沥青大概300吨',st['plan'][0]['text'])
        self.assertIn('尚未写入',st['plan'][0]['text'])
        self.assertNotIn('需要补充信息',st.get('error',''))

    def test_spoken_statement_model_write_is_downgraded_to_text(self):
        st=state('明天争取把剩下的45号沥青大概300吨抓紧处理出去')
        model_plan={'actions':[dict(choice('calendar.create'),title='明日卖沥青',
                                     datetime='2026-10-18T09:00:00+08:00',
                                     end_datetime='2026-10-18T10:00:00+08:00')], 'question':''}
        with patch.object(agent,'put_state'),\
             patch.object(agent,'available_tool_catalog',return_value={'calendar.create':'create'}),\
             patch.object(agent,'_deepseek_request',return_value=model_plan),\
             patch.object(agent,'prompt_alert',side_effect=AssertionError('must not approve surprise write')),\
             patch.object(agent,'execute_planned_actions',side_effect=lambda s:s):
            agent.plan_once(st)
        self.assertEqual(st['plan'][0]['tool'],'text.respond')
        self.assertEqual(st['plan'][0]['datetime'],'')

    def test_explicit_reminder_still_asks_time_instead_of_guessing(self):
        self.assertEqual(agent._casual_dated_work_plan(
            '明天提醒我处理剩下的45号沥青300吨'),'')
        self.assertEqual(agent._casual_dated_work_plan(
            '明天9点创建日历安排45号沥青工作'),'')
        st=state('明天提醒我处理剩下的45号沥青300吨')
        with patch.object(agent,'put_state'),\
             patch.object(agent,'available_tool_catalog',return_value={'reminder.create':'create'}),\
             patch.object(agent,'_deepseek_request',
                          return_value={'actions':[],'question':'请明确希望几点提醒？'}):
            agent.plan_once(st)
        self.assertEqual(st['status'],'paused')
        self.assertIn('几点提醒',st['error'])

    def test_question_without_dated_business_intention_is_not_overridden(self):
        st=state('帮我查询明天的日历有哪些安排')
        with patch.object(agent,'put_state'),\
             patch.object(agent,'available_tool_catalog',return_value={'calendar.list':'read'}),\
             patch.object(agent,'_deepseek_request',
                          return_value={'actions':[],'question':'请给出日历查询日期范围'}):
            agent.plan_once(st)
        self.assertEqual(st['status'],'paused')
        self.assertIn('日期范围',st['error'])

    def test_existing_successful_text_plan_remains_intact(self):
        st=state('明天争取把剩下的45号沥青大概300吨抓紧处理出去')
        rich={'actions':[dict(choice('text.respond'),
                              text='明日跟进45号沥青剩余约300吨，优先核实库存、客户和装车节奏。')], 'question':''}
        with patch.object(agent,'put_state'),\
             patch.object(agent,'available_tool_catalog',return_value={'text.respond':'read'}),\
             patch.object(agent,'_deepseek_request',return_value=rich),\
             patch.object(agent,'execute_planned_actions',side_effect=lambda s:s):
            agent.plan_once(st)
        self.assertEqual(st['plan'][0]['text'],rich['actions'][0]['text'])



if __name__=='__main__':
    unittest.main()
