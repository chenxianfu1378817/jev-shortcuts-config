# -*- coding: utf-8 -*-
"""The on-demand engine update must download real bytes, validate and keep rollback."""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

src=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_5_3.py'))
spec=importlib.util.spec_from_file_location('agent_152',src)
agent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.paths=(agent.DATA_DIR,agent.STATE_PATH,
                    agent.UPDATE_META_PATH,agent.UPDATE_ENGINE_PATH,agent.UPDATE_BACKUP_PATH)
        agent.DATA_DIR=self.tmp.name
        agent.STATE_PATH=os.path.join(self.tmp.name,'current_task.json')
        agent.UPDATE_META_PATH=os.path.join(self.tmp.name,'update_meta.json')
        agent.UPDATE_ENGINE_PATH=os.path.join(self.tmp.name,'engine','current.py')
        agent.UPDATE_BACKUP_PATH=os.path.join(self.tmp.name,'engine','previous.py')
        self.old=(b"# cached engine\n"+b"# preserved\n"*160)
        self.new=(b"# newer engine\n"+b"# verified\n"*160)
        agent._update_atomic_bytes(agent.UPDATE_ENGINE_PATH,self.old)
        self.meta={'installed_version':'1.5.1','installed_seq':151,
                   'sha256':hashlib.sha256(self.old).hexdigest()}
        agent.atomic_json(agent.UPDATE_META_PATH,self.meta)
        self.release={'schema':1,'sequence':152,'version':'1.5.2',
                      'path':'agent_core_1_5_3.py',
                      'size_bytes':len(self.new),'sha256':hashlib.sha256(self.new).hexdigest()}
        self.seen=[]

    def tearDown(self):
        (agent.DATA_DIR,agent.STATE_PATH,agent.UPDATE_META_PATH,
         agent.UPDATE_ENGINE_PATH,agent.UPDATE_BACKUP_PATH)=self.paths
        self.tmp.cleanup()

    def fake_download(self, name, limit):
        self.seen.append(name)
        if name=='manifest.json':
            return json.dumps(self.release).encode('utf-8')
        if name=='agent_core_1_5_3.py':
            return self.new
        raise AssertionError('unexpected download '+name)

    def test_one_tap_installs_verified_new_engine_and_preserves_backup(self):
        with patch.object(agent,'_release_download',side_effect=self.fake_download):
            result=agent.immediate_check_and_update()
        self.assertTrue(result['updated'])
        self.assertEqual(self.seen,['manifest.json','agent_core_1_5_3.py'])
        self.assertEqual(open(agent.UPDATE_ENGINE_PATH,'rb').read(),self.new)
        self.assertEqual(open(agent.UPDATE_BACKUP_PATH,'rb').read(),self.old)
        meta=agent.read_json(agent.UPDATE_META_PATH,{})
        self.assertEqual(meta['installed_version'],'1.5.2')
        self.assertEqual(meta['sha256'],hashlib.sha256(self.new).hexdigest())
        self.assertEqual(meta['previous_sha256'],hashlib.sha256(self.old).hexdigest())

    def test_already_latest_skips_engine_download(self):
        self.release['sequence']=151
        self.release['version']='1.5.1'
        with patch.object(agent,'_release_download',side_effect=self.fake_download):
            result=agent.immediate_check_and_update()
        self.assertFalse(result['updated'])
        self.assertEqual(self.seen,['manifest.json'])
        self.assertEqual(open(agent.UPDATE_ENGINE_PATH,'rb').read(),self.old)

    def test_pending_unverified_write_blocks_update_without_network(self):
        state={'status':'awaiting_callback','pending':{'tool':'apple_notes.create','token':'abc'}}
        agent.put_state(state)
        with patch.object(agent,'_release_download') as fetch:
            result=agent.immediate_check_and_update()
        fetch.assert_not_called()
        self.assertFalse(result['updated'])
        self.assertIn('待核验',result['message'])
        self.assertEqual(open(agent.UPDATE_ENGINE_PATH,'rb').read(),self.old)

    def test_modified_remote_bytes_do_not_overwrite_valid_cache(self):
        self.release['sha256']='0'*64
        with patch.object(agent,'_release_download',side_effect=self.fake_download):
            result=agent.immediate_check_and_update()
        self.assertFalse(result['updated'])
        self.assertIn('SHA256',result['message'])
        self.assertEqual(open(agent.UPDATE_ENGINE_PATH,'rb').read(),self.old)

    def test_failed_compilation_is_not_installed(self):
        self.new=b'def broken(:\n'+b'# extra\n'*220
        self.release['size_bytes']=len(self.new)
        self.release['sha256']=hashlib.sha256(self.new).hexdigest()
        with patch.object(agent,'_release_download',side_effect=self.fake_download):
            result=agent.immediate_check_and_update()
        self.assertFalse(result['updated'])
        self.assertEqual(open(agent.UPDATE_ENGINE_PATH,'rb').read(),self.old)

    def test_corrupted_current_engine_is_never_overwritten(self):
        agent._update_atomic_bytes(agent.UPDATE_ENGINE_PATH,b'# locally modified\n')
        with patch.object(agent,'_release_download',side_effect=self.fake_download):
            result=agent.immediate_check_and_update()
        self.assertFalse(result['updated'])
        self.assertIn('校验异常',result['message'])
        self.assertEqual(open(agent.UPDATE_ENGINE_PATH,'rb').read(),b'# locally modified\n')

    def test_install_success_offers_restart_without_rewriting_fixed_entry(self):
        webbrowser=types.ModuleType('webbrowser')
        opened=[]
        webbrowser.open=lambda url:opened.append(url)
        with patch.object(agent,'_release_download',side_effect=self.fake_download), \
             patch.object(agent,'prompt_alert',return_value=True), \
             patch.dict(sys.modules,{'webbrowser':webbrowser}):
            self.assertTrue(agent.update_from_menu())
        self.assertEqual(opened,[agent.FIXED_ENTRY_URL])

    def test_install_does_not_force_restart_if_declined(self):
        with patch.object(agent,'_release_download',side_effect=self.fake_download), \
             patch.object(agent,'prompt_alert',return_value=False):
            self.assertTrue(agent.update_from_menu())
        self.assertEqual(open(agent.UPDATE_ENGINE_PATH,'rb').read(),self.new)


if __name__=='__main__':
    unittest.main()
