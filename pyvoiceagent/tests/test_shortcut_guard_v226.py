# -*- coding: utf-8 -*-
"""V2.2.6 protects paused and pending local tasks from shortcut handoff overwrites."""
import ast
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock
import test_registered_shortcuts_v225 as v225

ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT/'agent_core_2_2_6.py'
MOD=ROOT/'shortcut_tools_v226.py'

class ThreadInline:
    def __init__(self,target=None,**kwargs):self.target=target
    def start(self):self.target()

class PausedTaskGuardTests(unittest.TestCase):
    def setUp(self):
        before=v225.ADDON
        v225.ADDON=MOD
        try:
            self.unit=v225.ToolsV225(methodName='test_local_exact_and_suffix_first_avoids_ai')
            self.unit.setUp()
        finally:
            v225.ADDON=before
        self.env=self.unit.env
        self.unit.save()
        self.shell=v225.ShellStub()
        self.queue=[]
        self.shell.ui.delay=lambda fn,n:self.queue.append(fn)
        self.env['_chat_threading']=type('Threads',(),{'Thread':ThreadInline})

    def tearDown(self):
        self.unit.tearDown()

    def test_engine_embeds_safe_module_and_legacy_cap(self):
        data=CORE.read_bytes()
        src=data.decode('utf8')
        ast.parse(src)
        self.assertIn("VERSION = '2.2.6-deepseek-flash'",src)
        self.assertIn(MOD.read_text('utf8'),src)
        self.assertLessEqual(len(data),350000)

    def test_pending_or_paused_task_never_overwritten(self):
        for status in ('awaiting_callback','needs_review','running',
                       'writing','paused','needs_input','replan_pending'):
            with self.subTest(status=status):
                self.env['get_state']()['status']=status
                self.env['get_state']()['id']='important_previous'
                self.env['_reg_invoke'](self.shell,'打开工作台',self.env['_reg_match']('打开工作台'))
                self.assertEqual(self.env['get_state']()['id'],'important_previous')
                self.assertEqual(self.env['get_state']()['status'],status)
                self.assertEqual(len(self.queue),0)

    def test_state_rechecked_after_user_approval_before_shortcuts_launch(self):
        self.env['get_state']().clear()
        self.env['get_state']()['status']='finished'
        self.env['_reg_invoke'](self.shell,'打开工作台',self.env['_reg_match']('打开工作台'))
        self.assertEqual(len(self.queue),1)
        self.env['get_state']()['status']='paused'
        self.env['get_state']()['id']='saved_job'
        self.queue.pop(0)()
        self.assertEqual(self.env['get_state']()['id'],'saved_job')
        self.assertEqual(self.env['get_state']()['status'],'paused')
        self.assertEqual(self.unit.native_urls,[])
        self.assertTrue(any('未覆盖' in text for role,text in self.shell.messages))

    def test_manifest_matches_post_publication(self):
        mf=json.loads((ROOT/'manifest.json').read_text('utf8'))
        if mf.get('version')!='2.2.6':
            self.skipTest('Not yet published')
        data=CORE.read_bytes()
        self.assertEqual(mf['path'],CORE.name)
        self.assertEqual(mf['sequence'],226)
        self.assertEqual(mf['size_bytes'],len(data))
        self.assertEqual(mf['sha256'],hashlib.sha256(data).hexdigest())

if __name__=='__main__':
    unittest.main(verbosity=2)
