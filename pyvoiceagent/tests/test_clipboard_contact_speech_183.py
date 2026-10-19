# -*- coding: utf-8 -*-
"""Regression for issue: '保存我刚才复制的联系人' incorrectly sent to AI.

Simulated Apple Contacts and clipboard, no private data or real write.
"""
import importlib.util
import tempfile
import types
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch

root=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("agent_core_183",root/"agent_core_1_8_3.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

class Person:
    def __init__(self):
        self.first_name=""
        self.organization=""
        self.phone=[]
    @property
    def full_name(self):
        return self.first_name

class Contacts:
    IPHONE="iPhone"
    Person=Person
    def __init__(self,other=None):
        self.people=list(other or [])
        self.queued=[]
        self.writes=0
        self.saves=0
    def is_authorized(self):
        return True
    def get_all_people(self):
        return list(self.people)
    def add_person(self,person):
        self.writes+=1
        self.queued.append(person)
    def save(self):
        self.saves+=1
        self.people.extend(self.queued)
        self.queued.clear()
    def revert(self):
        self.queued.clear()

class NewSpeechContactTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(engine.VERSION,"1.8.3-deepseek-flash")
        self.assertEqual(len(engine.APP_FEATURE_ROUTES),22)

    def test_user_screenshot_phrase_matches(self):
        phrases=(
            "保存我刚才复制的联系人",
            "保存我刚才复制的联系人。",
            "请帮我保存刚才复制的联系人",
            "把刚复制的联系人保存一下",
            "将刚复制的联系方式保存起来",
            "把微信好友发来的联系人添加到手机",
            "把剪贴板里的联系人添加到手机通讯录",
            "把刚复制的联系人录入通讯录",
            "微信里刚收到的联系方式帮我保存一下",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(engine._cc_trigger(phrase),phrase)

    def test_non_import_intents_do_not_match(self):
        phrases=(
            "帮我查询刚才复制的联系人",
            "不要保存我刚才复制的联系人",
            "我想知道能不能保存我刚才复制的联系人",
            "如何保存我刚才复制的联系人",
            "把我刚才复制的联系人保存到备忘录",
            "把我刚才复制的联系人添加到提醒事项",
            "刚复制的联系人帮我发给张经理",
            "帮我把刚复制的联系人分享到微信",
            "把我刚复制的联系人照片保存到相册",
            "把刚复制的联系人头像保存下来",
            "保存我刚才复制的联系人然后发消息",
            "先保存我刚才复制的联系人再打开微信",
            "查看刚才复制的联系人手机号",
            "保存我刚才复制的联系人信息并总结",
            "保存我刚才复制的联系人，再帮我打开抖音",
            "微信扫一扫",
            "抖音搜索道路沥青",
            "把刚才复制的网页保存到文件夹",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertFalse(engine._cc_trigger(phrase),phrase)

    def test_invocation_has_no_ai_calls(self):
        with patch.object(engine,"_cc_import_clipboard",return_value={"status":"ok"}) as saver,\
             patch.object(engine,"api_key",side_effect=AssertionError("No DeepSeek")),\
             patch.object(engine,"_local_or_ai_dispatch",side_effect=AssertionError("No App router")),\
             patch.object(engine,"_sb_generate_from_speech",side_effect=AssertionError("No builder")),\
             patch.object(engine,"_maybe_auto_work_plan",side_effect=AssertionError("No reminder path")):
            done=engine.start_new("保存我刚才复制的联系人")
        self.assertEqual(done["status"],"ok")
        saver.assert_called_once()

    def test_clipboard_validation_rejects_random_chat(self):
        with self.assertRaises(ValueError):
            engine._cc_parse_clipboard("你好，我是张三，最近有空吗？")
        with self.assertRaises(ValueError):
            engine._cc_parse_clipboard("张三\n13800138000\n13900139000")
        with self.assertRaises(ValueError):
            engine._cc_parse_clipboard("快来看这个链接 https://example.com\n张三\n13800138000")

    def test_exact_import_save_readback_and_no_cloud(self):
        contact_api=Contacts()
        text="姓名：张三\n单位：广西某道路工程有限公司\n手机：13800138000"
        with tempfile.TemporaryDirectory() as temp,\
             patch.object(engine,"DATA_DIR",temp),\
             patch.object(engine,"CLIP_CONTACT_LEDGER_PATH",str(Path(temp)/"ledger.json")) ,\
             patch.object(engine,"CLIP_CONTACT_LAST_PATH",str(Path(temp)/"last.json")) ,\
             patch.object(engine,"prompt_alert",return_value=True) as approve,\
             patch.object(engine,"api_key",side_effect=AssertionError("AI forbidden")) ,\
             patch.dict(sys.modules,{"contacts":contact_api,"clipboard":types.SimpleNamespace(get=lambda:text)}):
            out=engine.start_new("保存我刚才复制的联系人")
            journal=json.loads((Path(temp)/"ledger.json").read_text())
        self.assertEqual(out["status"],"ok")
        self.assertTrue(out["verified"])
        self.assertEqual(contact_api.writes,1)
        self.assertEqual(contact_api.saves,1)
        self.assertEqual(contact_api.people[0].full_name,"张三")
        self.assertEqual(contact_api.people[0].organization,"广西某道路工程有限公司")
        self.assertEqual(contact_api.people[0].phone,[("iPhone","13800138000")])
        self.assertTrue(all(x["state"]=="verified" for x in journal.values()))
        approve.assert_called_once()

    def test_duplicate_existing_mobile_no_save(self):
        already=Person()
        already.first_name="同事"
        already.phone=[("work","+86 13800138000")]
        contact_api=Contacts(other=[already])
        with tempfile.TemporaryDirectory() as temp,\
             patch.object(engine,"DATA_DIR",temp),\
             patch.object(engine,"CLIP_CONTACT_LEDGER_PATH",str(Path(temp)/"ledger.json")) ,\
             patch.object(engine,"CLIP_CONTACT_LAST_PATH",str(Path(temp)/"last.json")) ,\
             patch.object(engine,"prompt_alert",side_effect=AssertionError("Don't ask to create duplicate")) ,\
             patch.dict(sys.modules,{"contacts":contact_api,"clipboard":types.SimpleNamespace(
                 get=lambda:"姓名：张三\n单位：某公司\n电话：13800138000")}):
            out=engine.start_new("保存我刚才复制的联系人")
        self.assertEqual(out["status"],"existing")
        self.assertEqual(contact_api.writes,0)
        self.assertEqual(contact_api.saves,0)

    def test_user_cancel_no_save(self):
        contact_api=Contacts()
        with tempfile.TemporaryDirectory() as temp,\
             patch.object(engine,"DATA_DIR",temp),\
             patch.object(engine,"CLIP_CONTACT_LEDGER_PATH",str(Path(temp)/"ledger.json")) ,\
             patch.object(engine,"CLIP_CONTACT_LAST_PATH",str(Path(temp)/"last.json")) ,\
             patch.object(engine,"prompt_alert",return_value=False),\
             patch.dict(sys.modules,{"contacts":contact_api,"clipboard":types.SimpleNamespace(
                 get=lambda:"姓名：张三\n单位：广西道路工程\n电话：13800138000")}):
            out=engine.start_new("保存我刚才复制的联系人")
        self.assertEqual(out["status"],"declined")
        self.assertEqual(contact_api.writes,0)

if __name__=="__main__":
    unittest.main()
