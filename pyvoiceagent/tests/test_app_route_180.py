# -*- coding: utf-8 -*-
"""Pure Python validation: navigation-only app router. No real iOS launches."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

BASE=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("core180",BASE/"agent_core_1_8_0.py")
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def decision(route, text=""):
    return {"tool":"app.navigate","reason":"用户请求打开内部功能",
            "title":"","text":text,"notes":"","datetime":"",
            "end_datetime":"","shortcut_id":route}


class AppRouter180Tests(unittest.TestCase):
    def test_catalog_preserves_all_legacy_system_routes(self):
        self.assertEqual(core.VERSION,"1.8.0-deepseek-flash")
        self.assertEqual(core.BRIDGE_SHORTCUT,"PYAgentHub")
        self.assertEqual(core.CALENDAR_READ_SHORTCUT,"PYAgentCalendarRead")
        self.assertEqual(core.SYSTEM_MODULES["apple_notes.create"],"PYAgentNotes")
        self.assertEqual(core.SYSTEM_MODULES["calendar.create"],"PYAgentCalendar")
        self.assertEqual(len(core.APP_FEATURE_ROUTES),22)
        self.assertNotIn("transfer",core.APP_FEATURE_ROUTES)
        self.assertNotIn("vpn",core.APP_FEATURE_ROUTES)

    def test_all_routes_only_use_fixed_safe_schemes(self):
        safe={"weixin","wxwork","dingtalk","baidumap","https","snssdk1128",
              "xhsdiscover","taobao","imeituan","alipay","bear","mqqapi"}
        for route,(label,base,param) in core.APP_FEATURE_ROUTES.items():
            self.assertTrue(label)
            self.assertIn(urlsplit(base).scheme,safe)
            self.assertNotIn("javascript:",base)
            self.assertNotIn("file:",base)
            self.assertIn(param,(None,"query","destination","keyword","q","term"))

    def test_disabled_by_default_and_enabled_by_explicit_local_file(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core,"APP_ROUTER_ENABLED_PATH",str(Path(d)/"opt.json")):
            self.assertFalse(core._app_router_enabled())
            self.assertNotIn("app.navigate",core.available_tool_catalog())
            Path(core.APP_ROUTER_ENABLED_PATH).write_text('{"enabled":true,"shortcut_name":"Unknown","user_confirmed":true}')
            self.assertFalse(core._app_router_enabled())
            Path(core.APP_ROUTER_ENABLED_PATH).write_text(
                json.dumps({"enabled":True,"shortcut_name":"PYAgentAppRouter","user_confirmed":True}))
            self.assertTrue(core._app_router_enabled())
            self.assertIn("app.navigate",core.available_tool_catalog())

    def test_dynamic_text_is_percent_encoded_and_never_executed_as_url(self):
        label,url=core._app_route_target(decision("douyin_search","沥青&app=evil"))
        self.assertEqual(label,"抖音搜索")
        self.assertEqual(parse_qs(urlsplit(url).query)["keyword"],["沥青&app=evil"])
        self.assertEqual(urlsplit(url).scheme,"snssdk1128")
        for term in ("","\nattack","x"*91):
            with self.assertRaises(ValueError):
                core._app_route_target(decision("douyin_search",term))

    def test_routes_do_not_allow_freeform_url_or_static_extra_text(self):
        for route in ("http_open","wechat_send","shadowrocket_disconnect"):
            with self.assertRaises(ValueError):
                core._app_route_target(decision(route))
        with self.assertRaises(ValueError):
            core._app_route_target(decision("wechat_scan","https://bad.example"))
        with self.assertRaises(ValueError):
            core.parse_decision(decision("douyin_search",""))

    def test_live_shortcut_input_follows_exact_name_and_url_encoding(self):
        called=[]
        shim=types.SimpleNamespace(open_url=lambda url:called.append(url))
        with tempfile.TemporaryDirectory() as d, patch.object(core,"APP_ROUTER_ENABLED_PATH",str(Path(d)/"opt.json")),patch.dict(sys.modules,{"shortcuts":shim}):
            Path(core.APP_ROUTER_ENABLED_PATH).write_text(
                json.dumps({"enabled":True,"shortcut_name":"PYAgentAppRouter","user_confirmed":True}))
            result=core._app_route_handoff({},decision("xhs_search","沥青路面"))
        self.assertEqual(result["status"],"ok")
        self.assertFalse(result["verified"])
        outer=urlsplit(called[0])
        self.assertEqual(outer.scheme,"shortcuts")
        self.assertEqual(outer.netloc,"run-shortcut")
        params=parse_qs(outer.query)
        self.assertEqual(params["name"],["PYAgentAppRouter"])
        self.assertEqual(params["input"],["text"])
        self.assertEqual(parse_qs(urlsplit(params["text"][0]).query)["keyword"],["沥青路面"])

    def test_plan_rejects_wrong_sequence_and_rejects_unknown(self):
        a=decision("wechat_scan")
        b={"tool":"text.respond","reason":"","text":"测试","title":"",
           "datetime":"","end_datetime":"","notes":"","shortcut_id":""}
        with self.assertRaises(ValueError):
            core.parse_action_plan({"actions":[a,b],"question":""},set(core.TOOL_CATALOG))
        self.assertEqual(core.parse_action_plan(
            {"actions":[b,a],"question":""},set(core.TOOL_CATALOG))["actions"][-1]["tool"],
            "app.navigate")

    def test_handoff_is_committed_before_shortcuts_launch_and_no_callback_wait(self):
        a=decision("wechat_scan")
        state={"id":"test","status":"ready","single_plan":True,
               "plan_approved":True,"plan":[a],"plan_index":0,
               "events":[],"steps":0}
        observed=[]
        def add(s,t,params,result):
            s["events"].append({"tool":t,"params":params,**result})
        def route(s,d):
            observed.append((s["status"],s["plan_index"],s["events"][-1]["status"]))
            return {"status":"ok","result":"已经请求打开微信扫一扫","verified":False}
        with patch.object(core,"create_event",side_effect=add),\
             patch.object(core,"run_tool",side_effect=route),\
             patch.object(core,"put_state"),\
             patch.object(core,"final_report"):
            core.execute_planned_actions(state)
        self.assertEqual(observed,[("finished",1,"handoff")])
        self.assertEqual(state["status"],"finished")
        self.assertEqual(state["events"][-1]["status"],"ok")
        self.assertIsNone(state.get("pending"))


if __name__=="__main__":
    unittest.main()
