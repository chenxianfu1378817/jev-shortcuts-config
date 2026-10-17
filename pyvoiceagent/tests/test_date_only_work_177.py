# -*- coding: utf-8 -*-
"""Offline safety checks for V1.7.7 date-only speech-work autosave."""
import importlib.util
import os
import sys
import types
import unittest
from datetime import date, datetime
from unittest.mock import patch, MagicMock
SRC=os.path.join(os.path.dirname(__file__),'..','agent_core_1_7_7.py')
spec=importlib.util.spec_from_file_location('agent177', SRC)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

def goal():
    return '明天争取把剩下的45号沥青大概300吨抓紧处理出去'

def record():
    return {'entries':{}}

def state():
    return {'id':'state-test','goal':goal(),'status':'ready','steps':0,
            'events':[],'pending':None,'final':'','error':''}

class Reminder:
    def __init__(self,title,day,notes='',alarms=None,completed=False):
        self.title=title
        self.due_date=datetime.fromisoformat(day) if day else None
        self.notes=notes
        self.alarms=alarms or []
        self.completed=completed

class DateOnly177Tests(unittest.TestCase):
    def test_speech_becomes_date_only_no_fake_time(self):
        p=a._spoken_work_plan(goal(),date(2026,10,17))
        self.assertEqual(p['day'],'2026-10-18')
        self.assertIn('45号沥青',p['title'])
        self.assertIn('300吨',p['title'])
        self.assertNotIn('09:00',p['title'])

    def test_weekday_and_year_rollover(self):
        p=a._spoken_work_plan('下周一跟进广西沥青回款',date(2026,10,17))
        self.assertEqual(p['day'],'2026-10-19')
        p=a._spoken_work_plan('1月2日跟进项目报价',date(2026,12,31))
        self.assertEqual(p['day'],'2027-01-02')
        self.assertIsNone(a._spoken_work_plan('本周一跟进项目报价',date(2026,10,17)))

    def test_undated_goal_does_not_invent_date(self):
        p=a._spoken_work_plan('计划整理沥青客户资料',date(2026,10,17))
        self.assertEqual(p['day'],'')

    def test_protect_questions_system_commands_and_explicit_times(self):
        unsafe=['明天提醒我处理45号沥青','明天9点处理45号沥青',
                '明天有哪些日历安排','明天帮我分析沥青市场？',
                '明天把事情处理掉然后发邮件','明天帮我删除日历事项',
                '明天联系客户，再整理报价表','明天的项目进度如何']
        for text in unsafe:
            self.assertIsNone(a._spoken_work_plan(text,date(2026,10,17)),text)

    def test_different_quantities_are_not_collapsed(self):
        a1=a._dayonly_key('把剩下的45号沥青大概300吨抓紧处理出去','2026-10-18')
        a2=a._dayonly_key('把剩下的45号沥青约300吨处理出去','2026-10-18')
        a3=a._dayonly_key('把剩下的45号沥青约350吨处理出去','2026-10-18')
        self.assertEqual(a1,a2)
        self.assertNotEqual(a1,a3)
        self.assertNotEqual(a1,a._dayonly_key('把剩下的45号沥青大概300吨抓紧处理出去','2026-10-19'))

    def test_native_eventkit_uses_date_components_not_clock_or_alarm(self):
        class Components:
            def __init__(self): self.calls={}
            def setCalendar_(self,x): self.calls['calendar']=x
            def setYear_(self,x): self.calls['year']=x
            def setMonth_(self,x): self.calls['month']=x
            def setDay_(self,x): self.calls['day']=x
            def setHour_(self,x): raise AssertionError('clock time invented')
            def setMinute_(self,x): raise AssertionError('clock time invented')
        components=Components()
        item=MagicMock()
        store=MagicMock()
        store.saveReminder_commit_error_.return_value=True
        store.defaultCalendarForNewReminders.return_value=MagicMock()
        ek=MagicMock()
        ek.authorizationStatusForEntityType_.return_value=3
        ek.alloc.return_value.init.return_value=store
        classes={'EKEventStore':ek,
                 'EKReminder':types.SimpleNamespace(reminderWithEventStore_=lambda x:item),
                 'NSCalendar':types.SimpleNamespace(calendarWithIdentifier_=lambda x:'gregorian'),
                 'NSDateComponents':types.SimpleNamespace(alloc=lambda :types.SimpleNamespace(init=lambda :components))}
        with patch.dict(sys.modules,{'objc_util':types.SimpleNamespace(ObjCClass=lambda k:classes[k])}):
            self.assertTrue(a._eventkit_date_only_save('处理300吨沥青','2026-10-18','test'))
        self.assertEqual((components.calls['year'],components.calls['month'],components.calls['day']),
                         (2026,10,18))
        item.setStartDateComponents_.assert_called_once_with(components)
        item.setDueDateComponents_.assert_called_once_with(components)
        item.addAlarm_.assert_not_called()
        store.saveReminder_commit_error_.assert_called_once()

    def test_permission_denied_does_not_touch_calendar(self):
        fake=MagicMock()
        fake.authorizationStatusForEntityType_.return_value=2
        with patch.dict(sys.modules,{'objc_util':types.SimpleNamespace(ObjCClass=lambda k:fake)}):
            with self.assertRaises(PermissionError):
                a._eventkit_date_only_save('事项','2026-10-18','notes')
        fake.alloc.assert_not_called()

    def test_success_writes_ledger_before_system_and_reads_back(self):
        st=state()
        p=a._spoken_work_plan(goal(),date(2026,10,17))
        db=record()
        saved=[]
        entries=[]
        def fake_write(title,day,notes):
            self.assertEqual(db['entries'][a._dayonly_key(title,day)]['status'],'intent')
            self.assertIsNotNone(st['pending'])
            saved.append(title)
            entries.append(Reminder(title,day,notes))
            return True
        with patch.object(a,'_dayonly_load',return_value=db),\
             patch.object(a,'atomic_json'),patch.object(a,'put_state'),\
             patch.object(a,'_eventkit_date_only_save',side_effect=fake_write),\
             patch.dict(sys.modules,{'reminders':types.SimpleNamespace(
                 get_reminders=lambda completed=None:list(entries)),
                 'objc_util':types.SimpleNamespace(ObjCClass=lambda k:types.SimpleNamespace(
                     authorizationStatusForEntityType_=lambda x:3))}):
            res=a._dayonly_save(st,p)
        self.assertEqual(res['status'],'ok')
        self.assertTrue(res['verified'])
        self.assertEqual(len(saved),1)
        self.assertEqual(next(iter(db['entries'].values()))['status'],'verified')
        self.assertIsNone(st['pending'])

    def test_repeat_after_success_does_not_write(self):
        p=a._spoken_work_plan(goal(),date(2026,10,17))
        key=a._dayonly_key(p['title'],p['day'])
        db={'entries':{key:{'status':'verified'}}}
        with patch.object(a,'_dayonly_load',return_value=db),\
             patch.object(a,'_eventkit_date_only_save',side_effect=AssertionError('duplicate write')),\
             patch.dict(sys.modules,{'reminders':types.SimpleNamespace(get_reminders=lambda completed=None:[])}):
            res=a._dayonly_save(state(),p)
        self.assertEqual(res.get('outcome'),'existing',repr(res))

    def test_completed_existing_task_is_not_recreated(self):
        p=a._spoken_work_plan(goal(),date(2026,10,17))
        completed=Reminder(p['title'],p['day'],completed=True)
        with patch.object(a,'_dayonly_load',return_value=record()),\
             patch.object(a,'atomic_json'),\
             patch.object(a,'_eventkit_date_only_save',side_effect=AssertionError('duplicate write')),\
             patch.dict(sys.modules,{'reminders':types.SimpleNamespace(get_reminders=lambda completed=None:[completed]),
                 'objc_util':types.SimpleNamespace(ObjCClass=lambda k:types.SimpleNamespace(
                     authorizationStatusForEntityType_=lambda x:3))}):
            res=a._dayonly_save(state(),p)
        self.assertEqual(res.get('outcome'),'existing',repr(res))

    def test_failed_readback_keeps_intent_and_no_retry(self):
        st=state()
        p=a._spoken_work_plan(goal(),date(2026,10,17))
        db=record()
        calls=[]
        with patch.object(a,'_dayonly_load',return_value=db),\
             patch.object(a,'atomic_json'),patch.object(a,'put_state'),\
             patch.object(a,'time') as tm,\
             patch.object(a,'_eventkit_date_only_save',side_effect=lambda *x:calls.append(x)),\
             patch.dict(sys.modules,{'reminders':types.SimpleNamespace(get_reminders=lambda completed=None:[]),
                 'objc_util':types.SimpleNamespace(ObjCClass=lambda k:types.SimpleNamespace(
                     authorizationStatusForEntityType_=lambda x:3))}):
            first=a._dayonly_save(st,p)
            second=a._dayonly_save(st,p)
        self.assertEqual(first['status'],'needs_review')
        self.assertEqual(second['status'],'blocked_duplicate')
        self.assertEqual(len(calls),1)
        self.assertIsNotNone(st['pending'])
        self.assertEqual(next(iter(db['entries'].values()))['status'],'intent')

    def test_local_voice_path_bypasses_model_and_per_item_approval(self):
        st=state()
        current=dict(status='finished',steps=0,events=[],pending=None)
        with patch.object(a,'get_state',return_value=current),\
             patch.object(a,'put_state'),patch.object(a,'create_event'),\
             patch.object(a,'reminder_seed_prior_state'),\
             patch.object(a,'_dayonly_save',return_value={'status':'ok','verified':True,
                 'result':'已保存工作待办'}),\
             patch.object(a,'prompt_alert',side_effect=AssertionError('no confirmation')),\
             patch.object(a,'_deepseek_request',side_effect=AssertionError('no AI')),\
             patch.object(a,'api_key',side_effect=AssertionError('no API key required')):
            result=a.start_new(goal())
        self.assertEqual(result['status'],'finished')
        self.assertEqual(result['events'],[])
        self.assertIn('已保存',result['final'])

    def test_untouched_original_five_menu_and_tool_restrictions(self):
        self.assertEqual(len(a.MAIN_MENU),5)
        self.assertNotIn('reminder.create_day',a.ONE_SHOT_TOOLS)
        self.assertNotIn('reminder.create_day',a.TOOLS)
        self.assertEqual(a.CALENDAR_READ_SHORTCUT,'PYAgentCalendarRead')
        self.assertEqual(a.SYSTEM_MODULES['calendar.create'],'PYAgentCalendar')

if __name__=='__main__':
    unittest.main()
