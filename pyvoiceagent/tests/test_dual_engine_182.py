# -*- coding: utf-8 -*-
"""Offline V1.8.2 hybrid fast local / DeepSeek fallback tests.
No actual Contacts, Apple Shortcuts or iOS permissions needed.
"""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

BASE=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("core182",BASE/"agent_core_1_8_2.py")
agent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class Hybrid182Tests(unittest.TestCase):
    def test_release_and_existing_capabilities_unchanged(self):
        self.assertEqual(agent.VERSION,'1.8.2-deepseek-flash')
        self.assertEqual(agent.APP_ROUTER_SHORTCUT,'PYAgentAppRouter')
        self.assertEqual(len(agent.APP_FEATURE_ROUTES),22)
        self.assertIn('calendar.assist',agent.RESEARCH_ACTIONS)
        self.assertIn('reminder.create',agent.TOOL_CATALOG)
        self.assertIn('contacts.lookup',agent.LOCAL_READ_ACTIONS)
        self.assertIn('clipboard.read',agent.TOOL_CATALOG)

    def test_fixed_aliases_22_routes_stay_whitelisted(self):
        for key,aliases in agent._LOCAL_QUICK_STATIC.items():
            self.assertIn(key,agent.APP_FEATURE_ROUTES)
            for alias in aliases:
                out=agent._local_quick_intent('帮我打开'+alias)
                self.assertEqual(out,{'type':'LOCAL','shortcut_id':key,'text':''},alias)

    def test_user_examples(self):
        cases={
            '微信扫一扫':('wechat_scan',''),
            '打开企业微信文档':('wxwork_docs',''),
            '帮我打开钉钉待办':('dingtalk_tasks',''),
            '打开在抖音搜索道路沥青':('douyin_search','道路沥青'),
            '帮我在抖音上搜索广西沥青':('douyin_search','广西沥青'),
            '小红书搜索特立尼达湖沥青':('xhs_search','特立尼达湖沥青'),
            '在百度地图搜索南宁东站':('baidu_search','南宁东站'),
            '用百度地图导航到钦州港':('baidu_route','钦州港'),
            '高德地图查询南宁东站':('amap_search','南宁东站'),
            '淘宝搜索SBS改性剂':('taobao_search','SBS改性剂'),
            '熊掌记搜索项目笔记':('bear_search','项目笔记'),
            '支付宝查快递':('alipay_express',''),
            '打开新浪财经沥青期货':('sina_bu','')
        }
        for prompt,(key,text) in cases.items():
            with self.subTest(prompt=prompt):
                p=agent._local_quick_intent(prompt)
                self.assertIsNotNone(p)
                self.assertEqual((p['shortcut_id'],p['text']),(key,text))

    def test_compound_instructions_always_fall_through(self):
        cases=[
            '抖音搜索道路沥青，然后总结视频',
            '先查抖音道路沥青，然后添加提醒事项',
            '在抖音搜索道路沥青并且帮我整理资料',
            '如果有空就打开微信扫一扫',
            '不要打开微信扫一扫',
            '别打开支付宝扫一扫',
            '请帮我打开淘宝订单然后保存备忘录',
            '抖音搜索道路沥青发给客户',
            '小红书搜湖沥青下载视频',
            '打开钉钉待办然后完成待办事项',
            '先查看日历再打开企业微信文档',
            '查看明天日历，如果有拜访请创建提醒',
            '搜索道路沥青', # platform is ambiguous
            '在两个App里搜索道路沥青',
            '打开微信扫一扫并给朋友转账',
            '抖音搜索道路沥青\n然后分析'
        ]
        for prompt in cases:
            with self.subTest(prompt=prompt):
                self.assertIsNone(agent._local_quick_intent(prompt))

    def test_requires_precise_platform_and_action(self):
        for text in ('抖音道路沥青','看看抖音','微信','淘宝','企业微信','百度地图',
                     '在微信里搜一个人','打开未知软件','小红书页面'):
            self.assertIsNone(agent._local_quick_intent(text),text)

    def test_ambiguous_missing_keyword_requests_clarification(self):
        for prompt in ('抖音搜索','打开抖音搜索','小红书搜索','高德地图搜索'):
            value=agent._local_quick_intent(prompt)
            self.assertEqual(value['type'],'CLARIFY',prompt)
            self.assertTrue(value['question'])

    def test_query_is_not_executable_url_and_follows_fixed_allowlist(self):
        value=agent._local_quick_intent('抖音搜索沥青&admin=1')
        self.assertEqual(value['type'],'LOCAL')
        action={'shortcut_id':value['shortcut_id'],'text':value['text']}
        _,target=agent._app_route_target(action)
        self.assertEqual(urlsplit(target).scheme,'snssdk1128')
        self.assertEqual(parse_qs(urlsplit(target).query)['keyword'],['沥青&admin=1'])
        self.assertNotIn('admin',''.join(parse_qs(urlsplit(target).query).keys()))

    def test_no_dynamic_unicode_control_or_unbounded_search(self):
        self.assertIsNone(agent._local_quick_intent('抖音搜索'+'沥'*94))
        self.assertIsNone(agent._local_quick_intent('抖音搜索内容\r危险命令'))
        self.assertIsNone(agent._local_quick_intent('抖音搜索内容\n危险命令'))

    def test_clipboard_contacts_remain_locally_handled_by_original_route(self):
        with patch.object(agent,'_cc_import_clipboard',return_value={'status':'ok'}) as grab,\
             patch.object(agent,'_local_or_ai_dispatch',
                          side_effect=AssertionError('contact must bypass router')),\
             patch.object(agent,'api_key',
                          side_effect=AssertionError('DeepSeek must not be invoked')):
            v=agent.start_new('把刚复制的联系人保存到通讯录')
        self.assertEqual(v['status'],'ok')
        grab.assert_called_once()

    def test_quick_intent_does_not_call_deepseek(self):
        with tempfile.TemporaryDirectory() as folder,\
             patch.object(agent,'STATE_PATH',str(Path(folder)/'state.json')),\
             patch.object(agent,'api_key',side_effect=AssertionError('AI should not run')),\
             patch.object(agent,'_sb_generate_from_speech',return_value=None),\
             patch.object(agent,'_maybe_auto_work_plan',return_value=None),\
             patch.object(agent,'available_tool_catalog',return_value={'app.navigate':'route'}),\
             patch.object(agent,'execute_planned_actions',side_effect=lambda s: s) as task:
            got=agent.start_new('抖音搜索道路沥青')
            persisted=json.loads(Path(folder,'state.json').read_text())
        self.assertEqual(got['routing_engine'],'local')
        self.assertTrue(got['plan_approved'])
        self.assertEqual(got['plan'][0]['shortcut_id'],'douyin_search')
        self.assertEqual(got['plan'][0]['text'],'道路沥青')
        self.assertEqual(persisted['plan'][0]['tool'],'app.navigate')
        task.assert_called_once()

    def test_existing_pending_write_not_overwritten(self):
        previous={'status':'awaiting_callback','pending':{'token':'xyz'},
                  'id':'old','goal':'existing pending write'}
        with tempfile.TemporaryDirectory() as folder,\
             patch.object(agent,'STATE_PATH',str(Path(folder)/'state.json')),\
             patch.object(agent,'_sb_generate_from_speech',return_value=None),\
             patch.object(agent,'_maybe_auto_work_plan',return_value=None),\
             patch.object(agent,'available_tool_catalog',return_value={'app.navigate':'route'}),\
             patch.object(agent,'execute_planned_actions',side_effect=AssertionError('cannot navigate')):
            Path(folder,'state.json').write_text(json.dumps(previous))
            got=agent.start_new('微信扫一扫')
            saved=json.loads(Path(folder,'state.json').read_text())
        self.assertEqual(got['status'],'needs_review')
        self.assertEqual(saved,previous)

    def test_unavailable_shortcut_falls_back_to_regular_ai(self):
        with patch.object(agent,'_sb_generate_from_speech',return_value=None),\
             patch.object(agent,'_maybe_auto_work_plan',return_value=None),\
             patch.object(agent,'available_tool_catalog',return_value={}),\
             patch.object(agent,'api_key',return_value=None):
            # Same response as before: request API key if it is not configured.
            got=agent.start_new('微信扫一扫')
        self.assertIsNone(got)

    def test_compound_falls_through_to_model_without_auto_jump(self):
        with patch.object(agent,'_sb_generate_from_speech',return_value=None),\
             patch.object(agent,'_maybe_auto_work_plan',return_value=None),\
             patch.object(agent,'api_key',return_value=None),\
             patch.object(agent,'_local_fast_execute',side_effect=AssertionError('cannot fast route')):
            got=agent.start_new('抖音搜索道路沥青然后总结视频')
        self.assertIsNone(got)

    def test_explicit_clarify_does_not_call_ai(self):
        with patch.object(agent,'_sb_generate_from_speech',return_value=None),\
             patch.object(agent,'_maybe_auto_work_plan',return_value=None),\
             patch.object(agent,'api_key',side_effect=AssertionError('should ask locally')):
            got=agent.start_new('抖音搜索')
        self.assertEqual(got['status'],'clarify')

    def test_fast_plan_handoff_before_app_switch(self):
        action={'tool':'app.navigate','reason':'test','text':'道路沥青',
                'title':'','datetime':'','end_datetime':'',
                'notes':'','shortcut_id':'douyin_search'}
        state={'id':'111','status':'ready','single_plan':True,'plan_approved':True,
               'plan':[action],'plan_index':0,'events':[],'steps':0}
        snapshot=[]
        def make_event(st,tool,params,result):
            st['events'].append({'tool':tool,'params':params,**result})
        def before_launch(st,choice):
            snapshot.append((st['status'],st['plan_index'],st['events'][-1]['status']))
            return {'status':'ok','verified':False,'result':'已发送打开请求'}
        with patch.object(agent,'create_event',side_effect=make_event),\
             patch.object(agent,'run_tool',side_effect=before_launch),\
             patch.object(agent,'put_state'),patch.object(agent,'final_report'):
            done=agent.execute_planned_actions(state)
        self.assertEqual(snapshot,[('finished',1,'handoff')])
        self.assertEqual(done['status'],'finished')
        self.assertNotIn('pending',done)

    def test_all_local_keys_authorized_and_single_jump_only(self):
        keys=set(agent._LOCAL_QUICK_STATIC)|set(x[0] for x in agent._LOCAL_QUICK_DYNAMIC)
        self.assertEqual(len(keys),22)
        self.assertEqual(keys,set(agent.APP_FEATURE_ROUTES))


if __name__=='__main__':
    unittest.main()
