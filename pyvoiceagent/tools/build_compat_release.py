"""Repackage the published legacy engine for monotonic phone updates."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '3.0.4'
SEQUENCE = 304


def build(write=False):
    source = (ROOT / 'agent_core_2_3_9.py').read_bytes()
    original = b"VERSION = '2.3.9-deepseek-flash'\n"
    if source.count(original) != 1:
        raise ValueError('Unexpected legacy version marker')
    marker = "VERSION = '{}-legacy-compat'\n".format(VERSION).encode()
    data = source.replace(original, marker, 1)
    name = 'agent_core_' + VERSION.replace('.', '_') + '.py'
    compile(data, name, 'exec')
    if not 1000 <= len(data) <= 350000:
        raise ValueError('Engine exceeds launcher limits')
    manifest = {'schema': 1, 'sequence': SEQUENCE, 'version': VERSION,
                'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                'size_bytes': len(data),
                'summary': '恢复 V2.3.9 完整工具引擎、原生界面及旧工具配置；iPhone 待验收。'}
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
