# -*- coding: utf-8 -*-
"""Offline release regression checks for PYVoiceAgent V1.9.0.

No iPhone, contacts, reminders, calendars, API calls or real files are modified.
"""
import hashlib
import json
import os
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = ROOT / "agent_core_1_9_0.py"

class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = CORE.read_text(encoding="utf-8")
        compile(src, str(CORE), "exec")
        env = {"__name__": "pyvoiceagent_ci_validation"}
        exec(compile(src, str(CORE), "exec"), env)
        cls.env = env
        cls.source = src

    def test_new_version_and_legacy_functions(self):
        e=self.env
        self.assertEqual(e["VERSION"], "1.9.0-deepseek-flash")
        for name in ("main","input_voice","start_new","bridge_callback",
                     "callback","immediate_check_and_update","reminder_ledger_set",
                     "review_pending","show_menu","_V185_SHOW_MENU"):
            self.assertIn(name,e)

    def test_fixed_entry_and_existing_service(self):
        e=self.env
        self.assertEqual(e["APP_FILE"],"PYVoiceAgent.py")
        self.assertIn("PYVoiceAgent.py",e["FIXED_ENTRY_URL"])
        self.assertEqual(e["DEFAULT_MODEL"],"deepseek-flash")
        self.assertEqual(e["BRIDGE_SHORTCUT"],"PYAgentHub")

    def test_existing_tools_preserved(self):
        e=self.env
        names=e["TOOL_CATALOG"]
        for name in ("reminder.create","reminder.list","reminder.complete",
                     "apple_notes.create","calendar.create","calendar.list",
                     "contacts.lookup","webpage.summarize","app.navigate",
                     "shortcut.run","maps.search","local_note.save"):
            self.assertIn(name,names)

    def test_eight_themes_and_appearance_modes(self):
        e=self.env
        self.assertEqual(len(e["CARD_THEMES"]),8)
        self.assertEqual(set(e["DISPLAY_MODES"]),{"跟随系统","浅色模式","深色模式"})
        for theme in e["CARD_THEMES"]:
            light=e["_card_palette"]({"theme":theme,"mode":"浅色模式","custom_color":""}, True)
            dark=e["_card_palette"]({"theme":theme,"mode":"深色模式","custom_color":""}, False)
            self.assertFalse(light["dark"])
            self.assertTrue(dark["dark"])

    def test_follow_system_mode(self):
        e=self.env
        setting={"theme":"活力橙","mode":"跟随系统","custom_color":""}
        self.assertTrue(e["_card_palette"](setting,True)["dark"])
        self.assertFalse(e["_card_palette"](setting,False)["dark"])

    def test_theme_persistence_without_data_migration(self):
        e=self.env
        with tempfile.TemporaryDirectory() as folder:
            old=e["APPEARANCE_PATH"]
            try:
                e["APPEARANCE_PATH"]=os.path.join(folder,"appearance.json")
                saved=e["_card_appearance_save"]({"theme":"典雅紫","mode":"深色模式","custom_color":"#123ABC"})
                loaded=e["_card_appearance_load"]()
                self.assertEqual(saved,loaded)
                self.assertEqual(loaded["custom_color"],"#123ABC")
            finally:
                e["APPEARANCE_PATH"]=old

    def test_color_safety(self):
        e=self.env
        self.assertEqual(e["_card_hex"]("#ff00aa"),"#FF00AA")
        for malformed in ("evil","#123","FFFFFF","",None,12):
            self.assertEqual(e["_card_hex"](malformed),"")

    def test_navigation_pages_present(self):
        e=self.env
        for page in ("home","settings","advanced"):
            self.assertGreaterEqual(len(e["_card_nav_items"](page)),5)
        self.assertIn("tools",self.source)
        self.assertIn("appearance",self.source)

    def test_no_changes_to_url_callback_dispatch(self):
        s=self.source
        self.assertIn("if sys.argv[1] == 'bridge_callback'",s)
        self.assertIn("if sys.argv[1] == 'voice'",s)
        self.assertIn("if sys.argv[1] == 'text'",s)
        self.assertIn("root.present('full_screen', hide_title_bar=True)",s)

    def test_update_blocked_during_unknown_system_write(self):
        e=self.env
        get_state=e["get_state"]
        try:
            e["get_state"]=lambda: {"status":"awaiting_callback","pending":{"tool":"apple_notes.create"}}
            result=e["immediate_check_and_update"]()
            self.assertFalse(result.get("updated"))
            self.assertIn("核验",result.get("message",""))
        finally:
            e["get_state"]=get_state

    def test_no_external_update_on_invalid_manifest(self):
        # Tests update's failure safety while keeping data in a temporary directory.
        e=self.env
        with tempfile.TemporaryDirectory() as d:
            old_data,old_meta=e["DATA_DIR"],e["UPDATE_META_PATH"]
            old_state,old_dl=e["get_state"],e["_release_download"]
            try:
                e["DATA_DIR"]=d
                e["UPDATE_META_PATH"]=os.path.join(d,"meta.json")
                e["get_state"]=lambda: {}
                e["_release_download"]=lambda name, limit: b'{"schema":1,"version":"evil"}'
                result=e["immediate_check_and_update"]()
                self.assertFalse(result.get("updated"))
                self.assertFalse(os.path.isfile(os.path.join(d,"engine","current.py")))
            finally:
                e["DATA_DIR"],e["UPDATE_META_PATH"]=old_data,old_meta
                e["get_state"],e["_release_download"]=old_state,old_dl

    def test_manifest_checks_when_published(self):
        manifest=json.loads((ROOT/"manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version")!="1.9.0":
            self.skipTest("Release manifest is not yet switched to V1.9.0")
        data=CORE.read_bytes()
        self.assertEqual(manifest["path"],CORE.name)
        self.assertEqual(manifest["sequence"],190)
        self.assertEqual(manifest["size_bytes"],len(data))
        self.assertEqual(manifest["sha256"],hashlib.sha256(data).hexdigest())

if __name__=="__main__":
    unittest.main(verbosity=2)
