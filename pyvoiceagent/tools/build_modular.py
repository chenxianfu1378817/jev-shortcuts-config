#!/usr/bin/env python3
"""Build the Pythonista legacy-safe single-file release from all source modules.

Every feature has its own source file under src/. Generated output alone is
installed by the unchanged iPhone launcher. Never run the engine while building.
"""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import tokenize

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / 'src'
MAX_UPDATE_BYTES = 350000
ENGINE_RX = re.compile(r"VERSION\s*=\s*['\"](\d+\.\d+\.\d+)-[^'\"]+['\"]")


def assembled_source():
    parts = sorted(SOURCE_DIR.glob('[0-9][0-9]_*.py'))
    if len(parts) < 24:
        raise RuntimeError('Some source modules are missing; refusing to build')
    text = ''.join(part.read_text(encoding='utf-8') for part in parts)
    ast.parse(text, filename='assembled-pyvoiceagent.py')
    return text, [part.name for part in parts]


def remove_nonfunctional_lines(source):
    """Remove comments and whitespace without touching multiline HTML/strings."""
    protected = set()
    comments = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.STRING and token.end[0] > token.start[0]:
            protected.update(range(token.start[0], token.end[0] + 1))
        elif token.type == tokenize.COMMENT:
            comments[token.start[0]] = token.start[1]

    lines = []
    for lineno, line in enumerate(source.splitlines(keepends=True), 1):
        if lineno in comments:
            end = '\n' if line.endswith('\n') else ''
            line = line[:comments[lineno]].rstrip() + end
        if lineno not in protected and not line.strip():
            continue
        lines.append(line)
    packed = ''.join(lines)
    # Non-semantic stripping must be proved by AST equality, not assumed.
    if ast.dump(ast.parse(packed)) != ast.dump(ast.parse(source)):
        raise RuntimeError('Generated code differs semantically from modular sources')
    compile(packed, 'generated-pyvoiceagent.py', 'exec')
    return packed


def build(sequence, write=False):
    source, parts = assembled_source()
    match = ENGINE_RX.search(source)
    if not match:
        raise RuntimeError('Source must declare an explicit release VERSION')
    version = match.group(1)
    if int(sequence) < 236:
        raise ValueError('Refusing to publish an obsolete modular sequence')
    packed = remove_nonfunctional_lines(source)
    data = packed.encode('utf-8')
    if not 1000 < len(data) <= MAX_UPDATE_BYTES:
        raise RuntimeError('Bundled engine exceeds old updater safety limit: %s' % len(data))
    filename = 'agent_core_' + version.replace('.', '_') + '.py'
    info = {
        'schema': 1,
        'sequence': sequence,
        'version': version,
        'path': filename,
        'sha256': hashlib.sha256(data).hexdigest(),
        'size_bytes': len(data),
        'summary': '全功能模块化源码；禁用有真机崩溃报告的 Pythonista 原生录音入口，改用 iOS 系统键盘听写。保留文字、AI、工具、用户数据与在线更新，待 iPhone 验收。',
    }
    target = ROOT / filename
    if write:
        target.write_bytes(data)
        (ROOT / 'manifest.json').write_text(
            json.dumps(info, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    else:
        if not target.is_file() or target.read_bytes() != data:
            raise RuntimeError('Generated engine differs from committed release')
        stored = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
        if any(stored.get(key) != value for key, value in info.items()):
            raise RuntimeError('manifest differs from checked source build')
    return {'release': info, 'source_modules': parts}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sequence', type=int, default=238)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.sequence, args.write), ensure_ascii=False, indent=2))
