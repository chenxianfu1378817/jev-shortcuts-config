"""Run the generated form handler through local persistence and its UI reply."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_3_1.py'
SPEC = importlib.util.spec_from_file_location('registry_candidate', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)

FIXTURE = r"""
const assert = require('node:assert/strict');
const nodes = {
    'reg-id': {value: 'test_tool'},
    'reg-name': {value: '打开工作台'},
    'reg-desc': {value: '测试快捷指令'},
    'reg-aliases': {value: '启动工作台，打开工作台'},
    'reg-mode': {value: 'launch'},
    'reg-input': {value: 'none'},
    'reg-confirm': {checked: true},
    'reg-enabled': {checked: true},
    'reg-status': {}, 'reg-list': {appendChild() {}},
    'reg-open': {}, 'reg-save': {}, 'reg-clear': {}, 'reg-refresh': {}
};
global.document = {
    activeElement: {blur() {}},
    getElementById: id => nodes[id],
    createElement: () => ({appendChild() {}}),
    querySelector: () => ({addEventListener() {}})
};
global.window = {PYCHAT_BOOT: {nonce: process.argv[1]}};
let expire;
global.setTimeout = callback => {expire = callback; return 1;};
global.clearTimeout = () => {};
"""
CLICK = """
nodes['reg-save'].onclick();
assert.equal(nodes['reg-status'].textContent, '正在保存…');
const raw = window.PYRegistryTake();
assert.equal(window.PYRegistryTake(), '');
assert.equal(window.location, undefined);
"""


class RegistrySaveTests(unittest.TestCase):
    def run_form(self, tail, *args):
        return subprocess.check_output(
            ['node', '-e', FIXTURE + core._REG_JS + CLICK + tail, *args],
            text=True,
        ).strip()

    def test_click_saves_file_and_renders_acknowledgement(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'registry.json'
            with patch.object(core, '_chat_transcript_load', return_value=[]):
                shell = core._ChatShell()
            shell.holder = Mock(on_screen=True)
            shell.ui = Mock()
            raw = self.run_form('console.log(raw);', shell.nonce)
            shell.web = Mock()
            shell.web.eval_js.return_value = raw
            with patch.object(core, 'REGISTRY_PATH', str(path)), \
                 patch.object(core, 'ensure_dirs'), \
                 patch.object(core, 'get_state', return_value={}):
                shell._poll_registry()

            stored = json.loads(path.read_text())
            self.assertEqual(stored['test_tool']['name'], '打开工作台')
            self.assertEqual(stored['test_tool']['aliases'], ['启动工作台', '打开工作台'])
            deliver, delay = shell.ui.delay.call_args_list[0].args
            self.assertEqual(delay, 0.0)
            deliver()
            js = shell.web.eval_js.call_args.args[0]
            self.run_form(
                """
const reply = JSON.parse(process.argv[2]);
window.PYChatReceive({...reply, request_id: reply.request_id + 1});
assert.equal(nodes['reg-status'].textContent, '正在保存…');
window.PYChatReceive(reply);
assert.equal(nodes['reg-status'].textContent, '工具已保存：test_tool');
""",
                shell.nonce, js.removeprefix('window.PYChatReceive(').removesuffix(');'),
            )

    def test_invalid_form_and_write_failure_return_visible_errors(self):
        shell = Mock(busy=False)
        invalid = core._reg_result(shell, 'reg_save', '{}')
        self.assertIn('工具 ID', invalid['text'])
        with patch.object(core, '_reg_save', side_effect=OSError('disk error')):
            failed = core._reg_result(shell, 'reg_save', '{}')
        self.assertIn('工具库操作失败', failed['text'])

    def test_timeout_preserves_form_and_drops_unconsumed_request(self):
        self.run_form(
            """
nodes['reg-save'].onclick();
expire();
assert.match(nodes['reg-status'].textContent, /未收到操作结果/);
assert.equal(nodes['reg-name'].value, '打开工作台');
assert.equal(window.PYRegistryTake(), '');
""",
            'test-nonce',
        )

    def test_manifest_matches_engine(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text())
        if manifest['sequence'] != 231:
            self.skipTest('Manifest points to another release')
        data = CORE.read_bytes()
        self.assertEqual(manifest['path'], CORE.name)
        self.assertEqual(manifest['size_bytes'], len(data))
        self.assertLessEqual(len(data), 350000)
        self.assertEqual(manifest['sha256'], hashlib.sha256(data).hexdigest())
