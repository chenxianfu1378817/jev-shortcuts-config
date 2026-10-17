# -*- coding: utf-8 -*-
"""V1.7.2 Base64 callback normalization and no-AI safe calendar re-read."""
import base64
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from urllib.parse import quote,parse_qs,urlsplit

PATH=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_7_2.py'))
spec=importlib.util.spec_from_file_location('voice_agent_172',PATH)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class DecodeTests(unittest.TestCase):
    def setUp(self):
        self.body='CALREAD1\n查询到4项日程：\n重阳节\nPYAgent测试01－上午会议\nPYAgent测试02－客户拜访\nPYAgent测试03－下午总结'
        self.b64=base64.b64encode(self.body.encode('utf-8')).decode('ascii')

    def test_plain_base64_is_backward_compatible(self):
        self.assertEqual(a.decode_shortcuts_result_b64(self.b64),self.body)

    def test_percent_encoded_base64_from_shortcuts(self):
        uri=quote(self.b64,safe='')
        self.assertEqual(a.decode_shortcuts_result_b64(uri),self.body)

    def test_percent_encoded_padding_and_symbols(self):
        self.assertEqual(a.decode_shortcuts_result_b64('%2B%2F8%3D'),base64.b64decode('+/8=').decode('latin1') if False else
                         a.decode_shortcuts_result_b64('+/8='))

    def test_line_wrapped_base64_from_shortcuts(self):
        folded='\r\n'.join(self.b64[i:i+76] for i in range(0,len(self.b64),76))
        self.assertEqual(a.decode_shortcuts_result_b64(quote(folded,safe='')),self.body)

    def test_spaces_from_query_plus_conversion(self):
        raw=base64.b64encode(bytes([251,255,250])).decode('ascii')
        self.assertIn('+',raw)
        self.assertEqual(a.decode_shortcuts_result_b64(raw.replace('+',' ')),
                         bytes([251,255,250]).decode('utf-8') if False else
                         a.decode_shortcuts_result_b64(raw)) 

    def test_reject_plain_text_as_base64(self):
        with self.assertRaises((ValueError,UnicodeDecodeError)):
            a.decode_shortcuts_result_b64('CALREAD1%0A%E6%B5%8B%E8%AF%95')

    def test_reject_incomplete_percent_escape(self):
        with self.assertRaisesRegex(ValueError,'百分号'):
            a.decode_shortcuts_result_b64('YWJj%2Z')

    def test_reject_oversize_raw_transport(self):
        with self.assertRaises(ValueError):
            a.decode_shortcuts_result_b64('A'*4001)

    def test_reject_invalid_base64(self):
        with self.assertRaises((ValueError,Exception)):
            a.decode_shortcuts_result_b64('non-base64-digit!')

    def test_reject_overlong_decoded_result(self):
        enc=base64.b64encode(('超长'*1100).encode()).decode()
        with self.assertRaisesRegex(ValueError,'解码内容过长'):
            a.decode_shortcuts_result_b64(enc)


class SafeRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=a.STATE_PATH
        a.STATE_PATH=os.path.join(self.tmp.name,'current_task.json')
        self.tools=types.ModuleType('shortcuts')
        self.calls=[]
        self.tools.open_url=lambda url:self.calls.append(url) or None
        self.context=patch.dict(sys.modules,{'shortcuts':self.tools})
        self.context.start()
        self.start=datetime.now().astimezone()
        self.end=self.start+timedelta(days=1)
        action={'tool':'calendar.list','reason':'读取今天日程','text':'',
                'title':'','datetime':self.start.isoformat(),
                'end_datetime':self.end.isoformat(),'notes':'','shortcut_id':''}
        self.state={'id':'retry_172','goal':'查询今天日程','created':a.now_iso(),
                    'steps':0,'events':[],'pending':{
                         'tool':'calendar.list','token':'old-token','marker':'[PYVoiceAgent:retry_172:0]',
                         'name':'PYAgentCalendarRead','created':self.start.timestamp(),
                         'title':'','origin_step':0,'fingerprint':'foo'},
                    'status':'needs_review','plan':[action],'plan_index':0,
                    'single_plan':True,'plan_approved':True,
                    'error':'快捷指令返回的数据编码异常，待人工核验：Non-base64 digit found',
                    'token_usage':{'requests_with_usage':1,'total_tokens':1102}}
        a.put_state(self.state)
    def tearDown(self):
        self.context.stop()
        a.STATE_PATH=self.old
        self.tmp.cleanup()

    def test_safe_single_calendar_read_is_retryable(self):
        self.assertTrue(a.can_retry_readonly_calendar(self.state))

    def test_repeat_requires_approval(self):
        with patch.object(a,'prompt_alert',return_value=False):
            self.assertFalse(a.retry_last_readonly_calendar(self.state))
        self.assertEqual(self.state['status'],'needs_review')
        self.assertEqual(self.calls,[])

    def test_retry_uses_new_token_original_query_no_new_ai(self):
        with patch.object(a,'prompt_alert',return_value=True), \
             patch.object(a,'_deepseek_request') as ai:
            self.assertTrue(a.retry_last_readonly_calendar(self.state))
        ai.assert_not_called()
        self.assertEqual(len(self.calls),1)
        q=parse_qs(urlsplit(self.calls[0]).query)
        self.assertEqual(q['name'],['PYAgentCalendarRead'])
        current=a.get_state()
        self.assertEqual(current['status'],'awaiting_callback')
        self.assertEqual(current['token_usage']['total_tokens'],1102)
        self.assertNotEqual(current['pending']['token'],'old-token')
        self.assertEqual(current['plan_index'],0)
        self.assertEqual(current['calendar_read_retry_count'],1)

    def test_repeat_cannot_replay_twice(self):
        self.state['calendar_read_retry_count']=1
        self.assertFalse(a.can_retry_readonly_calendar(self.state))

    def test_no_write_retry_even_if_flagged_needs_review(self):
        self.state['pending']['tool']='calendar.create'
        self.state['plan'][0]['tool']='calendar.create'
        self.assertFalse(a.can_retry_readonly_calendar(self.state))
        self.state['plan'][0]['tool']='apple_notes.create'
        self.state['pending']['tool']='apple_notes.create'
        self.assertFalse(a.can_retry_readonly_calendar(self.state))

    def test_mixed_action_plan_cannot_be_replayed(self):
        self.state['plan'].append({'tool':'calendar.create'})
        self.assertFalse(a.can_retry_readonly_calendar(self.state))

    def test_unrelated_pending_error_does_not_trigger_retry(self):
        self.state['error']='快捷指令回调超时'
        self.assertFalse(a.can_retry_readonly_calendar(self.state))

    def test_no_auto_retry_when_not_in_needs_review(self):
        self.state['status']='awaiting_callback'
        self.assertFalse(a.can_retry_readonly_calendar(self.state))


if __name__=='__main__':
    unittest.main()
