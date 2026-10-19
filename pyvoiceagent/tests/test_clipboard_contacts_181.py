# -*- coding: utf-8 -*-
"""PYVoiceAgent 1.8.1: offline contact import and permission tests.
No Apple Contacts or clipboard is accessed. Fake modules simulate iOS APIs.
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

BASE=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("core181", BASE/"agent_core_1_8_1.py")
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class FakePerson:
    def __init__(self):
        self.first_name=''
        self.organization=''
        self.phone=[]

    @property
    def full_name(self):
        return self.first_name


class FakeContacts:
    IPHONE='iPhone'
    def __init__(self,people=None,authorized=True,fail_save=False,fail_read_after_write=False):
        self.people=list(people or [])
        self.pending=[]
        self.authorized=authorized
        self.fail_save=fail_save
        self.fail_read_after_write=fail_read_after_write
        self.adds=0
        self.saves=0
        self.reverts=0

    Person=FakePerson

    def is_authorized(self):
        return self.authorized

    def get_all_people(self):
        if self.fail_read_after_write and self.saves:
            raise RuntimeError("readback failed")
        return list(self.people)

    def add_person(self,p):
        self.adds+=1
        self.pending.append(p)

    def save(self):
        self.saves+=1
        if self.fail_save:
            raise RuntimeError("mock uncertain save")
        self.people.extend(self.pending)
        self.pending.clear()

    def revert(self):
        self.reverts+=1
        self.pending.clear()


class Contacts181Tests(unittest.TestCase):
    def test_explicit_contact_command_triggers_locally(self):
        for goal in ("把微信刚复制的联系人保存到手机通讯录",
                     "把剪贴板里的联系方式录入通讯录",
                     "把微信好友发来的姓名单位电话添加到通讯录",
                     "将刚复制的手机号存进手机联系人"):
            self.assertTrue(a._cc_trigger(goal), goal)
        for goal in ("微信扫一扫","帮我查询这个联系人",
                     "总结剪贴板里的通讯录文字","添加通讯录联系人然后发短信",
                     "把微信联系人删除","微信里找个客户"):
            self.assertFalse(a._cc_trigger(goal),goal)

    def test_labelled_three_lines(self):
        entry=a._cc_parse_clipboard("姓名：张三\n单位：广西北投养护集团有限公司\n电话：13800138000")
        self.assertEqual(entry,{'name':'张三','organization':'广西北投养护集团有限公司','phone':'13800138000'})

    def test_inline_fields_and_country_code(self):
        entry=a._cc_parse_clipboard("姓名:李四，单位:中建路桥集团，手机:+86 139 0000 5678")
        self.assertEqual(entry['name'],'李四')
        self.assertEqual(entry['organization'],'中建路桥集团')
        self.assertEqual(entry['phone'],'13900005678')

    def test_unlabelled_three_lines_and_single_line(self):
        for value in ("王五\n中国建筑股份有限公司\n137 1234 5678",
                      "王五 中国建筑股份有限公司 13712345678"):
            result=a._cc_parse_clipboard(value)
            self.assertEqual((result['name'],result['phone']),('王五','13712345678'))
            self.assertIn('中国建筑',result['organization'])

    def test_name_and_number_without_org(self):
        self.assertEqual(a._cc_parse_clipboard('姓名:赵六\n手机:13612345678')['organization'],'')

    def test_duplicate_mobile_in_same_text_ok(self):
        result=a._cc_parse_clipboard('姓名：陈七\n手机：13800138000\n备注：再次确认 13800138000')
        self.assertEqual(result['phone'],'13800138000')

    def test_reject_two_different_phone_numbers(self):
        with self.assertRaisesRegex(ValueError,'多个'):
            a._cc_parse_clipboard('姓名：张三\n电话：13800138000\n微信朋友电话13900139000')

    def test_reject_unreliable_parses(self):
        for sample in ("你好，我是张三，在路上，电话13800138000",
                       "姓名:王五\n电话:12345678",
                       "王经理\n13800138000",
                       "张三 13611111111 https://bad.example",
                       "A"*1900):
            with self.assertRaises(ValueError, msg=sample[:20]):
                a._cc_parse_clipboard(sample)

    def test_phone_normalization(self):
        for p in ('+86 138-0013-8000','0086-138 0013 8000','8613800138000','13800138000'):
            self.assertEqual(a._cc_digits(p),'13800138000')

    def test_local_route_before_any_deepseek(self):
        with patch.object(a,'_cc_import_clipboard',return_value={'status':'ok'}) as call, \
             patch.object(a,'api_key',side_effect=AssertionError('DeepSeek forbidden')), \
             patch.object(a,'_sb_generate_from_speech',side_effect=AssertionError('builder forbidden')):
            self.assertEqual(a.start_new('把微信刚复制的联系人保存到通讯录')['status'],'ok')
            call.assert_called_once_with()

    def test_authorization_required_no_write(self):
        fake=FakeContacts(authorized=False)
        with tempfile.TemporaryDirectory() as d, \
             patch.object(a,'DATA_DIR',d),\
             patch.object(a,'CLIP_CONTACT_LEDGER_PATH',str(Path(d)/'ledger.json')),\
             patch.object(a,'CLIP_CONTACT_LAST_PATH',str(Path(d)/'last.json')),\
             patch.dict(sys.modules,{'contacts':fake,'clipboard':types.SimpleNamespace(
                 get=lambda:'姓名:张三\n单位:中建五局\n手机:13800138000')}):
            result=a._cc_import_clipboard()
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(fake.adds,0)

    def test_save_readback_and_no_token(self):
        fake=FakeContacts()
        with tempfile.TemporaryDirectory() as d,\
             patch.object(a,'DATA_DIR',d),\
             patch.object(a,'CLIP_CONTACT_LEDGER_PATH',str(Path(d)/'ledger.json')),\
             patch.object(a,'CLIP_CONTACT_LAST_PATH',str(Path(d)/'last.json')),\
             patch.object(a,'prompt_alert',return_value=True) as confirm,\
             patch.dict(sys.modules,{'contacts':fake,'clipboard':types.SimpleNamespace(
                 get=lambda:'姓名:张三\n单位:广西北投养护集团\n电话:13800138000')}):
            result=a._cc_import_clipboard()
            ledger=json.loads(Path(d,'ledger.json').read_text())
            last=json.loads(Path(d,'last.json').read_text())
            self.assertTrue(all(v['state']=='verified' for v in ledger.values()))
        self.assertEqual(result['status'],'ok')
        self.assertTrue(result['verified'])
        self.assertNotIn('13800138000',result['result'])
        self.assertEqual(last['status'],'ok')
        self.assertEqual(fake.adds,1)
        self.assertEqual(fake.saves,1)
        self.assertEqual(fake.people[0].organization,'广西北投养护集团')
        confirm.assert_called_once()

    def test_duplicate_number_skips_write(self):
        p=FakePerson();p.first_name='张某';p.phone=[('work','+86 138-0013-8000')]
        fake=FakeContacts(people=[p])
        with tempfile.TemporaryDirectory() as d,\
             patch.object(a,'DATA_DIR',d),\
             patch.object(a,'CLIP_CONTACT_LEDGER_PATH',str(Path(d)/'ledger.json')),\
             patch.object(a,'CLIP_CONTACT_LAST_PATH',str(Path(d)/'last.json')),\
             patch.object(a,'prompt_alert',side_effect=AssertionError('should not ask')), \
             patch.dict(sys.modules,{'contacts':fake,'clipboard':types.SimpleNamespace(
                 get=lambda:'姓名：张三\n电话：13800138000')}):
            result=a._cc_import_clipboard()
        self.assertEqual(result['status'],'existing')
        self.assertTrue(result['verified'])
        self.assertEqual(fake.adds,0)

    def test_same_name_different_phone_needs_review(self):
        p=FakePerson();p.first_name='张三';p.phone=[('mobile','13900005678')]
        fake=FakeContacts(people=[p])
        with tempfile.TemporaryDirectory() as d,\
             patch.object(a,'DATA_DIR',d),\
             patch.object(a,'CLIP_CONTACT_LEDGER_PATH',str(Path(d)/'ledger.json')),\
             patch.object(a,'CLIP_CONTACT_LAST_PATH',str(Path(d)/'last.json')),\
             patch.dict(sys.modules,{'contacts':fake,'clipboard':types.SimpleNamespace(
                 get=lambda:'姓名:张三\n电话:13800138000')}):
            result=a._cc_import_clipboard()
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(fake.adds,0)

    def test_cancel_does_not_create_or_reserve(self):
        fake=FakeContacts()
        with tempfile.TemporaryDirectory() as d,\
             patch.object(a,'DATA_DIR',d),\
             patch.object(a,'CLIP_CONTACT_LEDGER_PATH',str(Path(d)/'ledger.json')),\
             patch.object(a,'CLIP_CONTACT_LAST_PATH',str(Path(d)/'last.json')),\
             patch.object(a,'prompt_alert',return_value=False),\
             patch.dict(sys.modules,{'contacts':fake,'clipboard':types.SimpleNamespace(
                 get=lambda:'姓名:李四\n电话:13800138000')}):
            result=a._cc_import_clipboard()
            self.assertFalse(Path(d,'ledger.json').exists())
        self.assertEqual(result['status'],'declined')
        self.assertEqual(fake.saves,0)

    def test_uncertain_contacts_save_blocks_retry(self):
        fake=FakeContacts(fail_save=True)
        with tempfile.TemporaryDirectory() as d,\
             patch.object(a,'DATA_DIR',d),\
             patch.object(a,'CLIP_CONTACT_LEDGER_PATH',str(Path(d)/'ledger.json')),\
             patch.object(a,'CLIP_CONTACT_LAST_PATH',str(Path(d)/'last.json')),\
             patch.object(a,'prompt_alert',return_value=True),\
             patch.dict(sys.modules,{'contacts':fake,'clipboard':types.SimpleNamespace(
                 get=lambda:'姓名:李四\n电话:13800138000')}):
            first=a._cc_import_clipboard()
            second=a._cc_import_clipboard()
        self.assertEqual(first['status'],'needs_review')
        self.assertEqual(second['status'],'needs_review')
        self.assertEqual(fake.adds,1)
        self.assertEqual(fake.saves,1)


if __name__=='__main__':
    unittest.main()
