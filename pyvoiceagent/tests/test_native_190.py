# -*- coding: utf-8 -*-
"""V1.9 offline regression tests; no device writes / no external network."""
import hashlib,importlib.util,json,os,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pynative_contacts as contacts
import pynative_router as router
import pynative_vision as vision
import pynative_updater as updater
import pynative_registry as registry
CORE=ROOT/"agent_core_1_9_0.py"
SPEC=importlib.util.spec_from_file_location("test_core_v190",str(CORE))
core=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)

class NativeTests(unittest.TestCase):
    def test_manifest_hashes(self):
        release=json.loads((ROOT/"manifest.json").read_text(encoding="utf-8"))
        raw=CORE.read_bytes()
        self.assertEqual(release["size_bytes"],len(raw))
        self.assertEqual(release["sha256"],hashlib.sha256(raw).hexdigest())
        manifest=(ROOT/"native_modules_manifest.json").read_bytes()
        rows=updater.manifest_validate(manifest)
        for row in rows:
            raw=(ROOT/(row["name"]+".py")).read_bytes()
            self.assertEqual(len(raw),row["size_bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row["sha256"])
    def test_cold_install_and_checked_load(self):
        manifest=(ROOT/"native_modules_manifest.json").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            result=updater.install(tmp,manifest,lambda filename,max_bytes:(ROOT/filename).read_bytes())
            self.assertEqual(result["status"],"updated")
            self.assertEqual(len(result["changed"]),5)
            mod=updater.load(tmp,"pynative_router")
            self.assertEqual(mod.validate_target("weixin://scanqrcode"),"weixin://scanqrcode")
            self.assertEqual(updater.install(tmp,manifest,lambda f,n:None)["status"],"current")
            with open(os.path.join(tmp,"active","pynative_router.py"),"ab") as f:f.write(b"# altered")
            with self.assertRaises(ValueError):updater.load(tmp,"pynative_router")
    def test_bad_manifest_or_download(self):
        bad={"schema":1,"modules":[{"name":"unknown"}]}
        with self.assertRaises(ValueError):updater.manifest_validate(json.dumps(bad))
        with tempfile.TemporaryDirectory() as tmp:
            raw=(ROOT/"native_modules_manifest.json").read_bytes()
            with self.assertRaises(ValueError):
                updater.install(tmp,raw,lambda filename,limit:b"tampered")
            self.assertFalse(os.path.exists(os.path.join(tmp,"installed.json")))
    def test_app_url_allowlist_and_open_request(self):
        for target in ("weixin://scanqrcode","baidumap://map/place/search?query=%E5%8D%97%E5%AE%81",
                       "https://uri.amap.com/search?keyword=Test"):
            self.assertEqual(router.validate_target(target),target)
        for target in ("javascript://alert(1)","https://attacker.com","http://uri.amap.com/",
                       "https://user:pass@uri.amap.com/","file:///etc/passwd"):
            with self.assertRaises(ValueError):router.validate_target(target)
        calls=[]
        res=router.open_target("weixin://scanqrcode",open_func=calls.append,background=False)
        self.assertEqual(res["status"],"ok")
        self.assertFalse(res["verified"])
        self.assertEqual(calls,["weixin://scanqrcode"])
        self.assertEqual(router.open_target("weixin://scanqrcode",background=True)["status"],"unavailable")
    def test_ocr_mock_private(self):
        result=vision.recognize_bytes(b"fake image bytes",engine=lambda data:["广西沥青","报价 5800"])
        self.assertEqual(result["text"],"广西沥青\n报价 5800")
        self.assertEqual(result["lines"],2)
        self.assertEqual(registry.tool_info("vision.ocr")["permission"],"photo_read")
        with self.assertRaises(ValueError):registry.tool_info("unlisted.execute")
        with self.assertRaises(ValueError):vision.recognize_bytes(b"x"* (15*1024*1024+1))
    def test_ocr_file_url_bridge_and_cleanup(self):
        """Simulate Objective-C signatures and inspect the real temporary image."""
        import types
        from unittest.mock import patch
        calls=[]
        class FakeRequest:
            def alloc(self): return self
            def init(self): return self
            def setRecognitionLevel_(self,level): pass
            def setUsesLanguageCorrection_(self,value): pass
            def results(self): return [self]
            def topCandidates_(self,limit): return [self]
            def string(self): return "本地中文识别正常"
        class FakeHandler:
            def alloc(self): return self
            def initWithURL_options_(self,url,opts):
                self.assert_exists(url)
                return self
            def assert_exists(self,path):
                self_path=path
                self.assert_valid_image(self_path)
            def assert_valid_image(self,path):
                self_checked=os.path.isfile(path)
                if not self_checked: raise AssertionError("temporary image absent")
                with open(path,"rb") as handle:
                    if not handle.read().startswith(bytes((255,216,255))):
                        raise AssertionError("temporary image bytes invalid")
                calls.append(path)
            def performRequests_error_(self,reqs,error): return True
        fake=types.ModuleType("objc_util")
        fake.ObjCClass=lambda name:FakeRequest() if name=="VNRecognizeTextRequest" else FakeHandler()
        fake.load_framework=lambda name:None
        fake.ns=lambda value:value
        fake.nsurl=lambda path:path
        with patch.dict(sys.modules,{"objc_util":fake}):
            recognized=vision.recognize_bytes(bytes((255,216,255))+b"test_jpeg_payload"*3)
        self.assertEqual(recognized["text"],"本地中文识别正常")
        self.assertEqual(len(calls),1)
        self.assertFalse(os.path.exists(calls[0]))
    def test_contacts_match_previous_parser(self):
        inputs=("姓名：张三\n单位：测试科技有限公司\n电话：13800138000",
                "姓名:李四，单位:广西交通集团，手机:+86 139 1234 5678",
                "王五\n广西路桥工程有限公司\n13700138000")
        for sample in inputs:
            self.assertEqual(contacts.parse_clipboard(sample),core._cc_parse_clipboard(sample))
    def test_single_plan_prevents_ocr_data_upload(self):
        no=core.run_tool({"single_plan":False},{"tool":"vision.ocr"})
        self.assertEqual(no["status"],"unavailable")
        self.assertIn("vision.ocr",core.TOOL_CATALOG)
        self.assertIn("vision.ocr",core.ONE_SHOT_TOOLS)
    def test_native_calendar_fallback(self):
        original=core._local_calendar_list
        old_bridge=core.start_bridge_tool
        core._local_calendar_list=lambda _:{"status":"unavailable","result":"no permission"}
        core.start_bridge_tool=lambda *args:{"status":"waiting","result":"legacy"}
        try:
            result=core.run_tool({},{"tool":"calendar.list"})
            self.assertEqual(result["status"],"waiting")
        finally:
            core._local_calendar_list=original
            core.start_bridge_tool=old_bridge
    def test_native_router_built_in_whitelist(self):
        choice={"shortcut_id":"wechat_scan","text":""}
        label,target=core._app_route_target(choice)
        self.assertTrue(label)
        self.assertEqual(target,"weixin://scanqrcode")
        with self.assertRaises(ValueError):
            core._app_route_target({"shortcut_id":"arbitrary_url","text":"https://evil.test"})
if __name__=="__main__":
    unittest.main(verbosity=2)
