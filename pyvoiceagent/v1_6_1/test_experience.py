# -*- coding: utf-8 -*-
"""UI/behavior regression tests for v1.6.1's real usability refinements."""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import patch

BASE=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_6_1.py'))
spec=importlib.util.spec_from_file_location('pyvoice161',BASE)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def action(tool,title='',text=''):
    return {'tool':tool,'reason':'','text':text,'title':title,
            'datetime':'','end_datetime':'','notes':'','shortcut_id':''}


def contact(name,company='',phone=''):
    return types.SimpleNamespace(full_name=name,organization=company,
        phone=[('mobile',phone)] if phone else [],email=[])


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.people=[]
        self.fake_contacts=types.ModuleType('contacts')
        self.fake_contacts.get_all_people=lambda:self.people

    def test_exact_contact_name_beats_partial_name_and_company(self):
        self.people=[
            contact('张经理助理',phone='0111'),
            contact('张经理',phone='0222'),
            contact('林经理','张经理企业',phone='0333')]
        with patch.dict(sys.modules,{'contacts':self.fake_contacts}):
            r=a._local_contacts_lookup(action('contacts.lookup','张经理'))
        self.assertEqual(r['status'],'ok')
        self.assertIn('精确匹配 1 人',r['result'])
        self.assertIn('0222',r['result'])
        self.assertNotIn('0111',r['result'])
        self.assertNotIn('0333',r['result'])

    def test_partial_name_ranked_before_company_and_whitespace_normalized(self):
        self.people=[
            contact('赵伟','张氏供应链',phone='0333'),
            contact('张 海',phone='0111'),
            contact('罗张海',phone='0222')]
        with patch.dict(sys.modules,{'contacts':self.fake_contacts}):
            r=a._local_contacts_lookup(action('contacts.lookup',' 张 '))
        self.assertIn('0111',r['result'])
        self.assertIn('0222',r['result'])
        self.assertIn('0333',r['result'])
        self.assertLess(r['result'].index('0111'),r['result'].index('0222'))
        self.assertLess(r['result'].index('0222'),r['result'].index('0333'))

    def test_company_match_still_returns_correct_person(self):
        self.people=[contact('李先生','广西沥青业务',phone='0888'),
                     contact('周女士','其他公司',phone='0999')]
        with patch.dict(sys.modules,{'contacts':self.fake_contacts}):
            r=a._local_contacts_lookup(action('contacts.lookup','广西沥青'))
        self.assertIn('0888',r['result'])
        self.assertNotIn('0999',r['result'])

    def test_many_contacts_warns_to_narrow_query(self):
        self.people=[contact('张{:03}'.format(i),phone='1{:03}'.format(i)) for i in range(20)]
        with patch.dict(sys.modules,{'contacts':self.fake_contacts}):
            r=a._local_contacts_lookup(action('contacts.lookup','张'))
        self.assertIn('20 人',r['result'])
        self.assertIn('补充姓名或公司缩小范围',r['result'])
        self.assertEqual(r['result'].count('电话:'),8)

    def test_no_open_browser_for_native_map(self):
        fake=types.ModuleType('shortcuts')
        paths=[]
        fake.open_url=lambda url:paths.append(url) or None
        with patch.dict(sys.modules,{'shortcuts':fake}), \
             patch('webbrowser.open') as browser:
            r=a._local_maps_search(action('maps.search','南宁东站'))
        self.assertEqual(r['status'],'ok')
        self.assertEqual(len(paths),1)
        self.assertTrue(paths[0].startswith('maps://?q='))
        browser.assert_not_called()

    def test_map_fallback_uses_system_url_handler(self):
        fake=types.ModuleType('shortcuts')
        paths=[]
        def handle(url):
            paths.append(url)
            if url.startswith('maps://'):
                raise RuntimeError('no handler')
        fake.open_url=handle
        with patch.dict(sys.modules,{'shortcuts':fake}):
            r=a._local_maps_search(action('maps.search','南宁东站'))
        self.assertEqual(r['status'],'ok')
        self.assertTrue(paths[1].startswith('https://maps.apple.com/'))
        self.assertFalse(r['verified'])

    def test_map_two_handler_failures_report_failure(self):
        fake=types.ModuleType('shortcuts')
        fake.open_url=lambda _: (_ for _ in ()).throw(RuntimeError('no app'))
        with patch.dict(sys.modules,{'shortcuts':fake}):
            r=a._local_maps_search(action('maps.search','南宁东站'))
        self.assertEqual(r['status'],'failed')

    def test_map_must_be_last_in_plan(self):
        actions=[action('maps.search','南宁东站'),action('contacts.lookup','张经理')]
        with self.assertRaisesRegex(ValueError,'地图搜索必须排在'):
            a.parse_action_plan({'actions':actions,'question':''},a.available_tool_catalog())

    def test_map_last_still_allowed(self):
        actions=[action('contacts.lookup','张经理'),action('maps.search','南宁东站')]
        plan=a.parse_action_plan({'actions':actions,'question':''},a.available_tool_catalog())
        self.assertEqual(len(plan['actions']),2)

    def test_compact_report_preserves_actual_usage_and_unverified_shortcuts(self):
        s={'events':[{'tool':'reminder.list','status':'ok','result':'本地查询到 2 项未完成提醒：\n• 10-15 审车\n• 10-16 联系客户'},
                     {'tool':'apple_notes.create','status':'ok','verified':False,'result':'回调 ok'},
                     {'tool':'calendar.create','status':'ok','verified':False,'result':'回调 ok'},
                     {'tool':'maps.search','status':'ok','verified':False,'result':'地图跳转已请求'}],
           'status':'finished',
           'token_usage':{'requests_with_usage':1,'prompt_tokens':1000,
                          'completion_tokens':200,'total_tokens':1200,
                          'prompt_cache_hit_tokens':0}}
        compact=a.concise_execution_summary(s)
        self.assertIn('4 / 4',compact)
        self.assertIn('待到苹果 App 核验',compact)
        self.assertIn('DeepSeek 1 次',compact)
        self.assertIn('1200 Token',compact)
        self.assertLess(len(compact),950)

    def test_compact_contact_preview_limits_private_details_in_popup(self):
        big='本地通讯录找到 202 人：\n'+('\n'.join('• 测试人员{}\\n    电话: 100{}'.format(i,i) for i in range(60)))
        s={'events':[{'tool':'contacts.lookup','status':'ok','result':big}],'status':'finished'}
        summary=a.concise_execution_summary(s)
        self.assertLess(len(summary),500)
        self.assertNotIn('10050',summary)
        self.assertIn('202 人',summary)

    def test_bounded_preview_does_not_fail_on_empty(self):
        self.assertEqual(a._brief_result_text(''),'')
        self.assertEqual(a.concise_execution_summary({'events':[],'status':'finished'}).splitlines()[0],
                         '操作结果：0 / 0 项报告成功')

    def test_map_handoff_persisted_before_app_switch(self):
        import copy
        state={'id':'maps-test','single_plan':True,'plan_approved':True,
               'plan':[action('maps.search','南宁东站')],
               'plan_index':0,'steps':0,'events':[],'status':'ready'}
        snapshots=[]
        def persist(current):
            snapshots.append(copy.deepcopy(current))
        with patch.object(a,'put_state',side_effect=persist), \
             patch.object(a,'final_report') as report, \
             patch.object(a,'run_tool',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                a.execute_planned_actions(state)
        report.assert_called_once()
        self.assertGreaterEqual(len(snapshots),2)
        self.assertEqual(snapshots[-1]['status'],'finished')
        self.assertEqual(snapshots[-1]['plan_index'],1)
        self.assertEqual(snapshots[-1]['events'][-1]['status'],'handoff')

    def test_map_handoff_result_updated_after_system_url_request_returns(self):
        state={'id':'maps-test','single_plan':True,'plan_approved':True,
               'plan':[action('maps.search','南宁东站')],
               'plan_index':0,'steps':0,'events':[],'status':'ready'}
        with patch.object(a,'put_state'),patch.object(a,'final_report'),\
             patch.object(a,'run_tool',return_value={
                 'status':'ok','verified':False,'result':'已请求打开原生苹果地图'}):
            result=a.execute_planned_actions(state)
        self.assertEqual(result['status'],'finished')
        self.assertEqual(result['plan_index'],1)
        self.assertEqual(result['events'][-1]['status'],'ok')
        self.assertFalse(result['events'][-1]['verified'])

    def test_map_handoff_failure_remains_recoverable_not_duplicate_launch(self):
        state={'id':'maps-test','single_plan':True,'plan_approved':True,
               'plan':[action('maps.search','南宁东站')],
               'plan_index':0,'steps':0,'events':[],'status':'ready'}
        with patch.object(a,'put_state'),patch.object(a,'final_report'),\
             patch.object(a,'run_tool',side_effect=OSError('no map handler')) as call:
            a.execute_planned_actions(state)
            a.execute_planned_actions(state)
        self.assertEqual(call.call_count,1)
        self.assertEqual(state['status'],'paused')
        self.assertEqual(state['events'][-1]['status'],'failed')

    def test_concise_handoff_is_pending_not_false_success(self):
        s={'events':[{'tool':'maps.search','status':'handoff',
                     'result':'即将打开地图'}],'status':'finished'}
        summary=a.concise_execution_summary(s)
        self.assertIn('1 项待系统跳转',summary)
        self.assertIn('尚未核验',summary)

    def test_main_menu_unchanged(self):
        self.assertEqual(len(a.MAIN_MENU),5)
        self.assertTrue(a.MAIN_MENU[3].endswith('立即更新版本'))

if __name__=='__main__':
    unittest.main()
