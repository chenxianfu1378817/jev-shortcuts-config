# -*- coding: utf-8 -*-
"""UI/behavior regression tests for v1.6.1's real usability refinements."""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import patch

BASE=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_6_2.py'))
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

    def test_native_maps_system_handler_not_pythonista_webview(self):
        urls=[]
        with patch.object(a,'_open_native_maps',side_effect=lambda url: urls.append(url) or True), \
             patch('webbrowser.open') as browser:
            result=a._local_maps_search(action('maps.search','南宁东站'))
        self.assertEqual(result['status'],'ok')
        self.assertEqual(len(urls),1)
        self.assertTrue(urls[0].startswith('maps://?q='))
        browser.assert_not_called()

    def test_map_system_refusal_does_not_open_web_view(self):
        with patch.object(a,'_open_native_maps',return_value=False) as native, \
             patch('webbrowser.open') as browser:
            result=a._local_maps_search(action('maps.search','南宁东站'))
        self.assertEqual(result['status'],'failed')
        self.assertIn('没有打开网页',result['result'])
        native.assert_called_once()
        browser.assert_not_called()

    def test_map_native_error_does_not_claim_success(self):
        with patch.object(a,'_open_native_maps',side_effect=RuntimeError('no app')):
            result=a._local_maps_search(action('maps.search','南宁东站'))
        self.assertEqual(result['status'],'failed')
        self.assertIn('没有改用内置网页',result['result'])

    def test_uikit_open_is_main_thread_and_targets_system_maps(self):
        urls=[]
        fake=types.ModuleType('objc_util')
        class UIApplication:
            @classmethod
            def sharedApplication(cls):
                return cls()
            def openURL_(self,url):
                urls.append(url)
                return True
        fake.ObjCClass=lambda name: UIApplication if name=='UIApplication' else None
        fake.nsurl=lambda item:'NSURL:'+item
        fake.on_main_thread=lambda fn:fn
        with patch.dict(sys.modules, {'objc_util':fake}):
            ok=a._open_native_maps('maps://?q=station')
        self.assertTrue(ok)
        self.assertEqual(urls,['NSURL:maps://?q=station'])

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

    def test_clipboard_input_asks_no_duplicate_approval(self):
        dialogs=types.ModuleType('dialogs')
        dialogs.list_dialog=lambda title,choices:'2. 使用剪贴板内容'
        clipboard=types.ModuleType('clipboard')
        clipboard.get=lambda:'在苹果地图搜索南宁东站，不要开始导航'
        with patch.dict(sys.modules, {'dialogs':dialogs,'clipboard':clipboard}), \
             patch.object(a,'prompt_alert',return_value=True) as prompt, \
             patch.object(a,'start_new',side_effect=lambda goal: a.prompt_alert('发送给 AI 规划',goal)):
            started=a.show_text_menu()
        self.assertTrue(started)
        self.assertEqual(prompt.call_count,1)

    def test_text_submission_closes_all_menus_instead_of_reopening(self):
        dialogs=types.ModuleType('dialogs')
        calls=[]
        responses=iter(['2. 文字／剪贴板任务','1. 手动输入任务'])
        def choose(title, choices):
            calls.append(title)
            return next(responses)
        dialogs.list_dialog=choose
        with patch.dict(sys.modules, {'dialogs':dialogs}), \
             patch.object(a,'ask_text',return_value='在地图搜索南宁东站'), \
             patch.object(a,'start_new') as send:
            a.show_menu()
        send.assert_called_once()
        self.assertEqual(len(calls),2)

    def test_map_handoff_has_no_blocking_dialog_before_switch(self):
        state={'id':'maps-test','single_plan':True,'plan_approved':True,
               'plan':[action('maps.search','南宁东站')],
               'plan_index':0,'steps':0,'events':[],'status':'ready'}
        snapshots=[]
        with patch.object(a,'put_state',side_effect=lambda st:snapshots.append(st['status'])), \
             patch.object(a,'final_report') as report, \
             patch.object(a,'run_tool',return_value={'status':'ok','result':'地图已接收'}):
            a.execute_planned_actions(state)
        report.assert_called_once_with(state,show_dialog=False)
        self.assertIn('finished',snapshots)
        self.assertEqual(state['status'],'finished')

    def test_header_displays_actual_loaded_engine_version(self):
        dialogs=types.ModuleType('dialogs')
        titles=[]
        def choose(title,choices):
            titles.append(title)
            return None
        dialogs.list_dialog=choose
        with patch.dict(sys.modules, {'dialogs':dialogs}):
            a.show_menu()
        self.assertIn('V1.6.2',titles[0])

    def test_main_menu_unchanged(self):
        self.assertEqual(len(a.MAIN_MENU),5)
        self.assertTrue(a.MAIN_MENU[3].endswith('立即更新版本'))

if __name__=='__main__':
    unittest.main()
