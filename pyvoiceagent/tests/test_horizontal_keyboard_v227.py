# -*- coding: utf-8 -*-
"""V2.2.7 fixes iOS WKWebView horizontal drift after text submit (simulated)."""
import ast
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'agent_core_2_2_7.py'
BASE=ROOT/'agent_core_2_2_6.py'


class HorizontalLayoutV227(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=SOURCE.read_text('utf-8')
        hit=re.search(r'CHAT_HTML\s*=\s*r"""(.*?)"""',cls.src,re.S)
        if not hit: raise AssertionError('Embedded local WebView HTML missing')
        cls.html=hit.group(1)

    def test_python_and_legacy_updater_contract(self):
        ast.parse(self.src)
        self.assertEqual(self.src.count('if __name__ == "__main__":'),1)
        self.assertIn("VERSION = '2.2.7-deepseek-flash'",self.src)
        self.assertLess(len(SOURCE.read_bytes()),350000)
        self.assertIn('MAX_UPDATE_BYTES = 350000',self.src)

    def test_remove_horizontal_transform_and_lock_screen_width(self):
        self.assertIn('#app{position:fixed;top:0;left:0;right:0;transform:none;',self.html)
        self.assertIn('max-width:100%;min-width:0',self.html)
        self.assertNotIn('left:50%;transform:translateX(-50%)',self.html)
        self.assertIn('overflow-x:hidden;background:var(--bg)',self.html)
        self.assertIn('overflow-y:auto;overflow-x:hidden',self.html)

    def test_keyboard_reset_on_blur_send_and_viewport_resize(self):
        self.assertIn("app.style.left='0px'",self.html)
        self.assertIn("app.style.transform='none'",self.html)
        self.assertIn('document.documentElement.scrollLeft=0',self.html)
        self.assertIn('document.body.scrollLeft=0',self.html)
        self.assertIn('setTimeout(fitKeyboard,350)',self.html)
        self.assertIn("window.visualViewport.addEventListener('resize',fitKeyboard)",self.html)

    def test_unchanged_voice_task_tools_and_exit(self):
        for fragment in ('class _ChatShell:','def stop_record(self):',
                         'self.ui.delay(self.stop_record, 0.08)',
                         'def _reg_save(data):','def _reg_match(goal):',
                         'id="agent-exit"','def bridge_callback(',
                         'def _bu_capture_and_calendar(', 'def immediate_check_and_update('):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment,self.src)
        self.assertIn('id="entry"',self.html)
        self.assertIn('id="chatview"',self.html)

    def test_node_simulation_keyboard_open_send_close(self):
        node=shutil.which('node')
        if not node: self.skipTest('Node is not installed')
        scripts=re.findall(r'<script[^>]*>(.*?)</script>',self.html,re.S)
        self.assertTrue(scripts)
        runner=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const js=fs.readFileSync(process.argv[2],'utf8');
let all=new Map(),ev={},scrollCalls=0;
const classList=()=>({names:new Set(),add(x){this.names.add(x)},remove(x){this.names.delete(x)},toggle(x,on){if(on)this.add(x);else this.remove(x)},contains(x){return this.names.has(x)}});
function E(id=''){return {id,style:{},children:[],classList:classList(),textContent:'',title:'',value:'',hidden:false,scrollHeight:47,scrollTop:0,scrollLeft:50,
appendChild(e){this.children.push(e);return e},replaceChildren(...c){this.children=c},addEventListener(n,f){(this.events||(this.events={}))[n]=f},
focus(){document.activeElement=this;this.events?.focus?.()},blur(){if(document.activeElement===this)document.activeElement=null;this.events?.blur?.()}}}
function el(id){if(!all.has(id))all.set(id,E(id));return all.get(id)}
const document={getElementById:el,createElement:(tag)=>E(),querySelectorAll:()=>[],documentElement:{style:{setProperty(){}},scrollLeft:70},body:E('body'),activeElement:null};
const vv={height:812,offsetTop:0,offsetLeft:0,events:{},addEventListener(k,v){this.events[k]=v}};
const window={visualViewport:vv,innerHeight:812,location:{href:''},addEventListener(k,v){ev[k]=v},scrollTo(x,y){scrollCalls++;assert.equal(x,0);assert.equal(y,0)}};
const sandbox={window,document,setTimeout:(f)=>f(),console};
vm.runInNewContext(js,sandbox,{timeout:3000});
const app=el('app'),entry=el('entry');
assert.equal(app.style.left,'0px');
assert.equal(app.style.transform,'none');
assert.equal(app.style.height,'812px');
entry.focus();
vv.height=440;vv.offsetTop=3;vv.offsetLeft=350;vv.events.resize();
assert.equal(app.style.left,'0px');
assert.equal(app.style.height,'440px');
assert(document.body.classList.contains('keyboard-open'));
entry.value='测试输入文字';
el('send').onclick();
assert(window.location.href.includes('action=send'));
assert.equal(entry.value,'');
vv.height=812;vv.offsetTop=0;vv.offsetLeft=0;vv.events.resize();
assert.equal(app.style.left,'0px');
assert.equal(app.style.top,'0px');
assert.equal(app.style.height,'812px');
assert.equal(document.documentElement.scrollLeft,0);
assert.equal(document.body.scrollLeft,0);
assert.equal(document.body.classList.contains('keyboard-open'),false);
assert(scrollCalls>0);
window.PYChatReceive({type:'message',message:{role:'user',text:'测试输入文字'}});
let rendered=el('chatview').children.filter(row=>row.children.some(child=>child.textContent==='测试输入文字'));
assert.equal(rendered.length,1);
console.log('webview root pinned, text sent, viewport restored and only one message rendered');
"""
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/'chat.js'; script.write_text(scripts[-1],'utf-8')
            spec=Path(td)/'check.js';spec.write_text(runner,'utf-8')
            syntax=subprocess.run([node,'--check',str(script)],capture_output=True,text=True,timeout=20)
            self.assertEqual(syntax.returncode,0,syntax.stderr)
            test=subprocess.run([node,str(spec),str(script)],capture_output=True,text=True,timeout=20)
            self.assertEqual(test.returncode,0,test.stdout+'\n'+test.stderr)

    def test_release_manifest_after_publishing(self):
        m=json.loads((ROOT/'manifest.json').read_text('utf-8'))
        if m.get('version')!='2.2.7':
            self.skipTest('Candidate release: manifest not yet advanced')
        data=SOURCE.read_bytes()
        self.assertEqual(m['path'],SOURCE.name)
        self.assertEqual(m['sequence'],227)
        self.assertEqual(m['size_bytes'],len(data))
        self.assertEqual(m['sha256'],hashlib.sha256(data).hexdigest())


if __name__=='__main__':
    unittest.main(verbosity=2)
