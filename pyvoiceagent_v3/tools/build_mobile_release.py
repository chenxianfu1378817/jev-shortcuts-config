"""Reproducible packaging for the existing PYVoiceAgent.py GitHub updater.

One signed-by-SHA256 manifest + one Python source, <=350000 bytes. On iPhone,
the source expands ordinary Python imports into a versioned private runtime
directory; V2 personal files are never bundled or overwritten.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY / 'pyvoiceagent_v3'
RELEASE_DIR = REPOSITORY / 'pyvoiceagent'
TEMPLATE = PACKAGE / 'tools' / 'mobile_engine_template.txt'
VERSION = '3.0.2'
SEQUENCE = 302
LEGACY_CAP = 350000


def _paths():
    collected = []
    for file in sorted(PACKAGE.rglob('*')):
        if not file.is_file():
            continue
        relative = file.relative_to(REPOSITORY).as_posix()
        if '/__pycache__/' in relative or '/tests/' in relative or '/tools/' in relative:
            continue
        if file.suffix not in ('.py','.json'):
            continue
        if any(part.startswith('.') for part in file.relative_to(PACKAGE).parts):
            continue
        collected.append((file,relative))
    names = {item[1] for item in collected}
    required = {
        'pyvoiceagent_v3/mobile.py',
        'pyvoiceagent_v3/mobile_update.py',
        'pyvoiceagent_v3/core/dispatcher.py',
        'pyvoiceagent_v3/services/llm.py',
        'pyvoiceagent_v3/storage/sqlite_store.py',
    }
    if not required <= names or len(collected) < 16:
        raise RuntimeError('V3 mobile package is incomplete')
    return collected


def bundle_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as z:
        for file,relative in _paths():
            raw = file.read_bytes()
            if len(raw) > 120000:
                raise RuntimeError('Unexpected oversized V3 source module')
            if file.suffix == '.py':
                compile(raw.decode('utf-8'),relative,'exec')
            info = zipfile.ZipInfo(relative, date_time=(2020,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 << 16)
            z.writestr(info,raw,compress_type=zipfile.ZIP_DEFLATED,
                       compresslevel=9)
    return buffer.getvalue()


def make_release():
    packed = bundle_bytes()
    sha = hashlib.sha256(packed).hexdigest()
    template = TEMPLATE.read_text(encoding='utf-8')
    if template.count('__BUNDLE_SHA256__') != 1 or template.count('__BUNDLE_BASE64__') != 1:
        raise RuntimeError('Embedded package markers missing or duplicated')
    source = template.replace('__BUNDLE_SHA256__',sha).replace(
        '__BUNDLE_BASE64__', base64.b64encode(packed).decode('ascii'))
    data = source.encode('utf-8')
    compile(data,'agent_core_3_0_1.py','exec')
    if not 2000 < len(data) <= LEGACY_CAP:
        raise RuntimeError('Mobile package violates old 350000 byte updater limit')
    manifest = {
        'schema': 1, 'sequence': SEQUENCE, 'version': VERSION,
        'path': 'agent_core_' + VERSION.replace('.', '_') + '.py',
        'sha256': hashlib.sha256(data).hexdigest(),
        'size_bytes': len(data),
        'summary': 'V3.0.2：修正 DeepSeek 角色与真实快捷指令 Tool Calls 分流、高德原生唤起和假完成状态；保护旧数据，iPhone 待验收。',
    }
    return data, manifest


def build(write=False):
    data, manifest = make_release()
    engine = RELEASE_DIR / manifest['path']
    meta = RELEASE_DIR / 'manifest.json'
    if write:
        engine.parent.mkdir(parents=True,exist_ok=True)
        engine.write_bytes(data)
        meta.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',
                        encoding='utf-8')
    else:
        if not engine.is_file() or engine.read_bytes() != data:
            raise RuntimeError('Committed mobile release differs from reproducible build')
        stored = json.loads(meta.read_text(encoding='utf-8'))
        if any(stored.get(key) != value for key,value in manifest.items()):
            raise RuntimeError('Published manifest does not match generated engine')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write',action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.write),ensure_ascii=False,indent=2))
