# -*- coding: utf-8 -*-
"""V2.2.4 keyboard and Chinese text-entry regression; Node DOM mock, not iOS hardware."""
import ast
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_chat_shell_v220 as base

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'chat_shell_v224.py'
ENGINE=ROOT/'agent_core_2_2_4.py'
OLDER=ROOT/'agent_core_2_2_3.py'
ROOT_GUARD='if __name__ == "__main__":'


def html_text():
    original=base.PATCH
    base.PATCH=MODULE
    try:
        temp,namespace,events=base.setup()
        try:
            return namespace['CHAT_HTML']
        finally:
            temp.cleanup()
    finally:
        base.PATCH=original


class KeyboardV224(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=html_text()
        cls.code=ENGINE.read_text('utf-8')

    def test_python_compiles_and_old_updater_accepts_size(self):
        ast.parse(self.code)
        ast.parse(MODULE.read_text('utf-8'))
        self.assertIn("VERSION = '2.2.4-deepseek-flash'",self.code)
        self.assertLessEqual(len(ENGINE.read_bytes()),350000)
        self.assertEqual(self.code.count(ROOT_GUARD),1)

    def test_voice_fix_and_legacy_features_still_intact(self):
        for symbol in ('self.ui.delay(self.stop_record, 0.08)',
                       'def _transcribe(self, path):','class _ChatShell:',
                       'def bridge_callback(','def _bu_capture_and_calendar(',
                       'def _card_palette(','def immediate_check_and_update('):
            self.assertIn(symbol,self.code)

    def test_keyboard_layout_css_and_message_area_scroll(self):
        for fragment in ('visualViewport','function fitKeyboard()',
                         'keyboard-open footer .quick','keyboard-open #mic{display:none}',
                         'id="dismiss"','id="entry"',
                         'flex:1;min-height:0;display:none;overflow-y:auto'):
            self.assertIn(fragment,self.html)
        self.assertIn('font-size:16px',self.html)

    def test_no_premature_chinese_ime_submit(self):
        self.assertIn('!e.isComposing&&(e.ctrlKey||e.metaKey)',self.html)
        self.assertNotIn("if(e.key==='Enter'&&!e.shiftKey)",self.html)

    def test_no_duplicate_user_bubbles_from_webview(self):
        source=re.search(r'function send\(\)\{(.*?)\}\nfunction themeButtons',self.html,re.S).group(1)
        self.assertNotIn("addMessage({role:'user'",source)
        self.assertIn("bridge('send',v)",source)

    def test_runtime_virtual_keyboard_reflows_and_dismisses(self):
        if not shutil.which('node'):
            self.skipTest('Node.js runtime unavailable')
        script=re.findall(r'<script[^>]*>(.*?)</script>',self.html,re.S)[-1]
        runner=r"""
const vm=require('node:vm'),assert=require('node:assert/strict'),fs=require('node:fs');
const js=fs.readFileSync(process.argv[2],'utf8');
let all=new Map(), events={},active=null;
const classList=()=>({names:new Set(),add(x){this.names.add(x)},remove(x){this.names.delete(x)},toggle(x,bool){if(bool)this.add(x);else this.remove(x)},contains(x){return this.names.has(x)}});
function E(id=''){return {id,style:{},children:[],classList:classList(),textContent:'',title:'',value:'',hidden:false,scrollHeight:47,scrollTop:0,
appendChild(e){this.children.push(e);return e},replaceChildren(...c){this.children=c},addEventListener(n,f){(this.events||(this.events={}))[n]=f},
focus(){document.activeElement=this;if(this.events?.focus)this.events.focus()},blur(){if(document.activeElement===this)document.activeElement=null;if(this.events?.blur)this.events.blur()}}}
function el(id){if(!all.has(id))all.set(id,E(id));return all.get(id)}
const document={getElementById:el,createElement:(tag)=>E(),querySelectorAll:()=>[],documentElement:{style:{setProperty(){}}},body:E('body'),activeElement:null};
const vv={height:812,offsetTop:0,events:{},addEventListener(n,f){this.events[n]=f}};
const window={visualViewport:vv,innerHeight:812,location:{href:''},addEventListener(n,f){events[n]=f}};
const sandbox={window,document,setTimeout:(f)=>f(),console};
vm.runInNewContext(js,sandbox,{timeout:3000});
assert.equal(el('app').style.height,'812px');
assert.equal(el('dismiss').hidden,true);
document.activeElement=el('entry');if(el('entry').events.focus)el('entry').events.focus();
vv.height=440;vv.events.resize();
assert.equal(el('app').style.height,'440px');
assert.equal(document.body.classList.contains('keyboard-open'),true);
assert.equal(el('dismiss').hidden,false);
el('entry').scrollHeight=180;el('entry').events.input();
assert.equal(el('entry').style.height,'110px');
let prevented=false;
el('entry').onkeydown({key:'Enter',isComposing:true,preventDefault(){prevented=true}});
assert.equal(prevented,false);
el('entry').value='你好';
el('send').onclick();
assert(window.location.href.includes('action=send'));
assert.equal(el('entry').value,'');
let before=el('chatview').children.filter(r=>r.children.some(c=>c.textContent==='你好')).length;
assert.equal(before,0); // no duplicate optimistic user bubble
window.PYChatReceive({type:'message',message:{role:'user',text:'你好'}});
let after=el('chatview').children.filter(r=>r.children.some(c=>c.textContent==='你好')).length;
assert.equal(after,1);
vv.height=812;vv.events.resize();
assert.equal(document.body.classList.contains('keyboard-open'),false);
console.log('keyboard resize, dismiss, IME, single-send runtime assertions passed');
"""
        with tempfile.TemporaryDirectory() as td:
            js_path=Path(td)/'chat_ui.js'
            runner_path=Path(td)/'verify.js'
            js_path.write_text(script,'utf-8')
            runner_path.write_text(runner,'utf-8')
            check=subprocess.run(['node','--check',str(js_path)],capture_output=True,text=True,timeout=15)
            self.assertEqual(check.returncode,0,check.stderr)
            result=subprocess.run(['node',str(runner_path),str(js_path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_manifest_matches_once_published(self):
        manifest=json.loads((ROOT/'manifest.json').read_text('utf-8'))
        if manifest['version']!='2.2.4':
            self.skipTest('Candidate stage before manifest release')
        self.assertEqual(manifest['path'],ENGINE.name)
        self.assertEqual(manifest['sequence'],224)
        import hashlib
        buf=ENGINE.read_bytes()
        self.assertEqual(len(buf),manifest['size_bytes'])
        self.assertEqual(hashlib.sha256(buf).hexdigest(),manifest['sha256'])

if __name__=='__main__':
    unittest.main(verbosity=2)
