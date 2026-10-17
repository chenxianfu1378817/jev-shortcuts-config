# -*- coding: utf-8 -*-
"""PYVoiceAgent 1.7.9 offline shortcut-generation tests.
No iOS runtime or iCloud signing is required for these structural tests.
"""
import hashlib
import importlib.util
import os
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

HERE=Path(__file__).resolve().parent.parent
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,HERE/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
b=load("shortcut_builder_179.py","builder179")
a=load("agent_core_1_7_9.py","core179")

class ShortcutBuilder179Tests(unittest.TestCase):
    def test_no_false_positive_normal_work_plan(self):
        self.assertIsNone(b._sb_plan_from_voice("明天处理300吨45号沥青"))
        self.assertIsNone(b._sb_plan_from_voice("查询今天苹果日历"))
        self.assertIsNone(b._sb_plan_from_voice("帮我打开百度地图"))

    def test_show_shortcut_input_plan(self):
        p=b._sb_plan_from_voice("创建快捷指令：显示传入内容")
        self.assertEqual((p["template"],p["name"]),("show_input","PYGen_ShowInput"))
        self.assertNotIn("error",p)

    def test_map_dynamic_input_plan(self):
        p=b._sb_plan_from_voice("创建快捷指令：用苹果地图搜索输入地点")
        self.assertEqual(p["template"],"apple_map_search")

    def test_fixed_text_and_web_plans(self):
        p=b._sb_plan_from_voice("创建快捷指令：显示 欢迎")
        self.assertEqual(p["template"],"show_text")
        self.assertEqual(p["value"],"欢迎")
        p=b._sb_plan_from_voice("生成快捷指令：打开网页 https://www.example.com/path")
        self.assertEqual(p["template"],"open_web")
        self.assertEqual(p["value"],"https://www.example.com/path")

    def test_baidu_navigation_not_falsely_claimed(self):
        p=b._sb_plan_from_voice("创建快捷指令：导航到南宁东站")
        self.assertIn("error",p)
        self.assertNotIn("template",p)

    def test_third_party_appintent_not_invented(self):
        p=b._sb_plan_from_voice("创建快捷指令：通过百度地图自动打车")
        self.assertIn("error",p)
        p=b._sb_plan_from_voice("生成快捷指令：发送微信给朋友")
        self.assertIn("error",p)

    def test_template_action_id_allowlist_and_reference_validity(self):
        for goal in ["创建快捷指令：显示传入内容",
                     "创建快捷指令：显示消息 测试",
                     "创建快捷指令：打开百度地图",
                     "创建快捷指令：用苹果地图搜索输入地点"]:
            plan=b._sb_plan_from_voice(goal)
            wf=b._sb_workflow(plan)
            self.assertLessEqual(len(wf["WFWorkflowActions"]),5)
            self.assertTrue(all(x["WFWorkflowActionIdentifier"] in b._SB_ALLOWED
                                for x in wf["WFWorkflowActions"]))
            self.assertEqual(len(set(x["WFWorkflowActionParameters"]["UUID"]
                                    for x in wf["WFWorkflowActions"])),
                             len(wf["WFWorkflowActions"]))
            self.assertTrue(all("UUID" in x["WFWorkflowActionParameters"]
                                for x in wf["WFWorkflowActions"]))
            encoded=plistlib.dumps(wf,fmt=plistlib.FMT_BINARY)
            self.assertEqual(len(plistlib.loads(encoded)["WFWorkflowActions"]),
                             len(wf["WFWorkflowActions"]))
            self.assertEqual(set(wf.keys()) & {"WFWorkflowActions","WFWorkflowTypes"},
                             {"WFWorkflowActions","WFWorkflowTypes"})

    def test_variable_input_and_utf16_offsets(self):
        p=b._sb_plan_from_voice("创建快捷指令：显示传入内容")
        wf=b._sb_workflow(p)
        self.assertTrue(wf["WFWorkflowHasShortcutInputVariables"])
        msg=wf["WFWorkflowActions"][0]["WFWorkflowActionParameters"]["Text"]
        self.assertIn("{3, 1}",msg["Value"]["attachmentsByRange"])
        self.assertEqual(msg["Value"]["attachmentsByRange"]["{3, 1}"]["Type"],
                         "ExtensionInput")
        token=b._sb_text("🚀",{"Type":"ExtensionInput"})
        self.assertIn("{2, 1}",token["Value"]["attachmentsByRange"])

    def test_map_search_has_url_encoding_and_input(self):
        p=b._sb_plan_from_voice("创建快捷指令：用苹果地图搜索输入地点")
        wf=b._sb_workflow(p)
        ids=[x["WFWorkflowActionIdentifier"] for x in wf["WFWorkflowActions"]]
        self.assertEqual(ids,["is.workflow.actions.urlencode",
                              "is.workflow.actions.url",
                              "is.workflow.actions.openurl"])
        self.assertIn("ExtensionInput",str(wf))
        self.assertIn("https://maps.apple.com/?q=",str(wf))

    def test_https_rejects_local_private_credential_and_http(self):
        for url in ("http://example.com","https://localhost/a",
                    "https://192.168.1.10/a","https://127.0.0.1/a",
                    "https://username:secret@example.com/","https://10.0.0.1/",
                    "https://foo.local/","https://example.com:8080/path",
                    "https://[::1]/","https://evil .com/a"):
            self.assertFalse(b._sb_secure_https(url),url)
        self.assertTrue(b._sb_secure_https("https://example.com/"))

    def test_compile_writes_unsigned_not_installed(self):
        p=b._sb_plan_from_voice("创建快捷指令：显示传入内容")
        with tempfile.TemporaryDirectory() as d:
            result=b._sb_compile(p,d)
            self.assertEqual(Path(result["path"]).suffix,".shortcut")
            self.assertIn("unsigned.shortcut",result["path"])
            self.assertTrue(result["unsigned"])
            wf=plistlib.loads(Path(result["path"]).read_bytes())
            self.assertEqual(len(wf["WFWorkflowActions"]),1)
            self.assertEqual(result["sha256"],hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest())

    def test_repeated_same_request_reuses_file_no_override(self):
        p=b._sb_plan_from_voice("创建快捷指令：显示传入内容")
        with tempfile.TemporaryDirectory() as d:
            a1=b._sb_compile(p,d)
            before=os.stat(a1["path"]).st_mtime_ns
            a2=b._sb_compile(p,d)
            self.assertTrue(a2["reused"])
            self.assertEqual(before,os.stat(a1["path"]).st_mtime_ns)
            self.assertEqual(a1["sha256"],a2["sha256"])

    def test_file_tamper_is_never_overwritten(self):
        p=b._sb_plan_from_voice("创建快捷指令：显示传入内容")
        with tempfile.TemporaryDirectory() as d:
            x=b._sb_compile(p,d)
            Path(x["path"]).write_bytes(b"unexpected")
            with self.assertRaises(FileExistsError):
                b._sb_compile(p,d)
            self.assertEqual(Path(x["path"]).read_bytes(),b"unexpected")

    def test_mobile_goal_calls_builder_first_not_deepseek_or_reminders(self):
        with tempfile.TemporaryDirectory() as d:
            result=b._sb_plan_from_voice("创建快捷指令：显示传入内容")
            with patch.object(a,"_sb_generate_from_speech",
                              return_value={"status":"generated","result":{"name":"PYGen_ShowInput"}}) as g,\
                 patch.object(a,"_maybe_auto_work_plan",
                              side_effect=AssertionError("must not be reminder")) as rem,\
                 patch.object(a,"api_key",side_effect=AssertionError("must not call model")):
                got=a.start_new("创建快捷指令：显示传入内容")
                self.assertEqual(got["status"],"generated")
                g.assert_called_once()
                rem.assert_not_called()

    def test_regular_task_paths_unchanged(self):
        old=load("agent_core_1_7_8.py","legacy178")
        self.assertEqual(a.MAIN_MENU,old.MAIN_MENU)
        self.assertEqual(a.SYSTEM_MODULES,old.SYSTEM_MODULES)
        self.assertEqual(a.ONE_SHOT_TOOLS,old.ONE_SHOT_TOOLS)
        self.assertEqual(a.BRIDGE_SHORTCUT,old.BRIDGE_SHORTCUT)
        self.assertEqual(a.CALENDAR_READ_SHORTCUT,old.CALENDAR_READ_SHORTCUT)

    def test_signed_not_implicitly_registered(self):
        p=b._sb_plan_from_voice("创建快捷指令：显示传入内容")
        with tempfile.TemporaryDirectory() as d:
            with patch.object(a,"DATA_DIR",d),\
                 patch.object(a,"prompt_alert",return_value=False),\
                 patch.object(a,"api_key",side_effect=AssertionError("No DeepSeek")):
                result=a._sb_generate_from_speech("创建快捷指令：显示传入内容")
            self.assertEqual(result["status"],"generated")
            metadata=Path(d,"GeneratedShortcuts",p["name"]+".metadata.json")
            j=__import__("json").loads(metadata.read_text(encoding="utf-8"))
            self.assertFalse(j["installed"])
            self.assertFalse(j["validated_on_iphone"])

    def test_generator_denies_arbitrary_plist_actions(self):
        with self.assertRaises(ValueError):
            b._sb_action("is.workflow.actions.sendmessage",WFMessageText="secret")
        with self.assertRaises(ValueError):
            b._sb_workflow({"template":"custom","name":"PYGen_Test","value":""})


if __name__=="__main__":
    unittest.main()
