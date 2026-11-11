"""Exercise the generated WebView click handlers with a minimal DOM."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_2_9.py'


class WebViewControls(unittest.TestCase):
    def test_click_handlers(self):
        engine = {'__name__': 'webview_test'}
        exec(compile(CORE.read_bytes(), str(CORE), 'exec'), engine)
        html = engine['CHAT_HTML']
        script = re.findall(r'<script>(.*?)</script>', html, re.S)[-1]
        fixture = r"""
const assert = require('node:assert/strict');
const ids = JSON.parse(process.argv[1]);
const nodes = Object.fromEntries(ids.map(id => [id, {}]));
global.document = {
  getElementById: id => nodes[id],
  querySelector: () => ({addEventListener() {}})
};
global.window = {
  PYCHAT_BOOT: {nonce: 'test'},
  location: {},
  confirm() { throw new Error('Native WebView dialog unavailable'); }
};
let scrolled = false;
nodes['reg-form'].scrollIntoView = () => { scrolled = true; };
"""
        clicks = """
nodes['reg-open'].onclick();
assert.equal(scrolled, true);
assert.equal(new URL(window.location.href).searchParams.get('action'), 'reg_list');
nodes['agent-exit'].onclick();
const exit = new URL(window.location.href);
assert.equal(exit.searchParams.get('action'), 'exit');
assert.equal(exit.searchParams.get('nonce'), 'test');
"""
        subprocess.run(['node', '-e', fixture + script + clicks,
                        json.dumps(re.findall(r'\bid="([^"]+)"', html))], check=True)

    def test_release_metadata(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        if manifest['sequence'] != 229:
            self.skipTest('Manifest points to another release')
        data = CORE.read_bytes()
        self.assertEqual(manifest['path'], CORE.name)
        self.assertEqual(manifest['size_bytes'], len(data))
        self.assertLessEqual(len(data), 350000)
        self.assertEqual(manifest['sha256'], hashlib.sha256(data).hexdigest())
