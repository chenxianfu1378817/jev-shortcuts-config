"""Repackage the published legacy engine for monotonic phone updates."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '3.0.7'
SEQUENCE = 307


def build(write=False):
    source = (ROOT / 'agent_core_2_3_9.py').read_bytes()
    original = b"VERSION = '2.3.9-deepseek-flash'\n"
    if source.count(original) != 1:
        raise ValueError('Unexpected legacy version marker')
    marker = "VERSION = '{}-legacy-compat'\n".format(VERSION).encode()
    data = source.replace(original, marker, 1)
    old = b"    url='shortcuts://run-shortcut?'+urlencode({'name':item['name'],'input':'text','text':payload})"
    new = b"    from urllib.parse import quote\n" + old[:-1] + b", quote_via=quote)"
    if data.count(old) != 1:
        raise ValueError('Unexpected registered shortcut launch code')
    data = data.replace(old, new, 1)
    entry = b'if __name__ == "__main__":\n    main()\n'
    if not data.endswith(entry):
        raise ValueError('Unexpected engine entry point')
    overlay = (ROOT / 'tools' / 'dialog_recovery.txt').read_bytes()
    semantic = (ROOT / 'tools' / 'semantic_shortcuts.txt').read_bytes()
    data = data[:-len(entry)] + overlay + b'\n' + semantic + b'\n' + entry
    name = 'agent_core_' + VERSION.replace('.', '_') + '.py'
    compile(data, name, 'exec')
    if not 1000 <= len(data) <= 350000:
        raise ValueError('Engine exceeds launcher limits')
    manifest = {'schema': 1, 'sequence': SEQUENCE, 'version': VERSION,
                'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                'size_bytes': len(data),
                'summary': '按用途匹配已登记快捷指令，并在本地校验传参模式；iPhone 待验收。'}
    meta = ROOT / 'manifest.json'
    engine = ROOT / name
    if write:
        engine.write_bytes(data)
        meta.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    elif engine.read_bytes() != data or json.loads(meta.read_text(encoding='utf-8')) != manifest:
        raise ValueError('Online compatibility release differs from reproducible build')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    print(json.dumps(build(parser.parse_args().write), ensure_ascii=False, indent=2))
