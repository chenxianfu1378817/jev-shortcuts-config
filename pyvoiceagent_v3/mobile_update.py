"""V3 in-app update, compatible with the existing fixed PYVoiceAgent.py loader.

Uses the exact old engine/current.py + update_meta.json protocol, never
touches V2 tasks/history/settings/keys. Only explicitly triggered from Settings.
"""
import hashlib
import json
import os
import re
import tempfile
from urllib.request import Request, urlopen

ROOT = 'https://raw.githubusercontent.com/chenxianfu1378817/jev-shortcuts-config/main/pyvoiceagent'
LEGACY = os.path.join(os.path.expanduser('~/Documents'), 'PYVoiceAgent_Data')
ENGINE_DIR = os.path.join(LEGACY, 'engine')
CURRENT = os.path.join(ENGINE_DIR, 'current.py')
PREVIOUS = os.path.join(ENGINE_DIR, 'previous.py')
META = os.path.join(LEGACY, 'update_meta.json')
LIMIT = 350000


def _atomic(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.'+os.path.basename(path)+'.',
                                 suffix='.part', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def _download(filename, cap, opener=urlopen):
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:json|py)', filename):
        raise ValueError('unsafe release filename')
    req = Request(ROOT + '/' + filename,
                  headers={'User-Agent':'PYVoiceAgent-V3','Cache-Control':'no-cache'})
    with opener(req, timeout=15) as response:
        payload = response.read(cap+1)
    if len(payload) > cap:
        raise ValueError('release exceeds maximum size')
    return payload


def _file_bytes(path):
    with open(path, 'rb') as stream:
        return stream.read()


def _load_meta():
    try:
        with open(META, 'rb') as f:
            item = json.load(f)
        return item if isinstance(item, dict) else {}
    except FileNotFoundError:
        return {}


def check_for_update(downloader=None):
    """Manual explicit update; returns truthful result without auto-restart."""
    fetch = downloader or _download
    previous_engine = None
    original_meta = None
    changed_engine = False
    try:
        original_meta = _file_bytes(META) if os.path.isfile(META) else None
        meta = _load_meta()
        if not meta.get('sha256') and os.path.isfile(CURRENT):
            raise ValueError('现有引擎缺少已记录的 SHA-256，拒绝覆盖')
        current = _file_bytes(CURRENT) if os.path.isfile(CURRENT) else None
        if current is not None and hashlib.sha256(current).hexdigest()!=meta['sha256']:
            raise ValueError('当前引擎校验失败，原版本已保留')
        state_file = os.path.join(LEGACY,'current_task.json')
        if os.path.isfile(state_file):
            with open(state_file, 'r', encoding='utf-8') as stream:
                state = json.load(stream)
            if not isinstance(state, dict):
                raise ValueError('旧任务状态异常，拒绝升级')
            if state.get('pending') and state.get('status') in (
                    'awaiting_callback','needs_review','writing'):
                raise ValueError('存在待核验任务，不自动更新')
        payload = json.loads(fetch('manifest.json',16384).decode('utf-8'))
        seq = payload.get('sequence')
        version = payload.get('version')
        filename = payload.get('path')
        digest = payload.get('sha256')
        size = payload.get('size_bytes')
        if (type(seq) is not int or seq < 300 or seq > 99999
                or type(version) is not str
                or not re.fullmatch(r'\d+\.\d+\.\d+', version)
                or filename != 'agent_core_' + version.replace('.', '_')+'.py'
                or type(digest) is not str
                or not re.fullmatch(r'[a-f0-9]{64}', digest)
                or type(size) is not int or size < 1000 or size > LIMIT):
            raise ValueError('远程清单格式不符合安全要求')
        if seq <= int(meta.get('installed_seq', 0)):
            return {'updated':False,'message':'已是最新版本：'+str(meta.get('installed_version','V3'))}
        if meta.get('broken_version') == version:
            raise ValueError('该版本曾在本机失败，暂不安装')
        data = fetch(filename, size+1)
        if len(data) != size or hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError('新版本文件大小或 SHA-256 不一致')
        compile(data,filename,'exec')
        previous_engine = current
        if current is not None:
            _atomic(PREVIOUS, current)
            meta['previous_sha256'] = hashlib.sha256(current).hexdigest()
        _atomic(CURRENT, data)
        changed_engine = True
        meta.update({'sha256':digest,'installed_seq':seq,'installed_version':version,
                     'last_result':'已安装 '+version})
        _atomic(META, json.dumps(meta,ensure_ascii=False,indent=2).encode('utf-8'))
        return {'updated':True,'message':'已安装 '+version+'。请退出后用原入口重新启动。'}
    except Exception as exc:
        if changed_engine and previous_engine is not None:
            try:
                _atomic(CURRENT, previous_engine)
                if original_meta is not None:
                    _atomic(META, original_meta)
            except OSError:
                pass
        return {'updated':False,
                'message':'更新未完成；旧引擎已尽量保留。原因：'+type(exc).__name__}


def rollback_to_previous():
    """Explicit user request; preserve V3 DB and quarantine broken upgrade."""
    current_data = previous_data = None
    saved_meta = None
    changed = False
    try:
        saved_meta = _file_bytes(META)
        meta = _load_meta()
        current_data = _file_bytes(CURRENT)
        previous_data = _file_bytes(PREVIOUS)
        current_digest = hashlib.sha256(current_data).hexdigest()
        previous_digest = hashlib.sha256(previous_data).hexdigest()
        if current_digest != meta.get('sha256'):
            raise ValueError('Current engine checksum mismatch')
        if previous_digest != meta.get('previous_sha256'):
            raise ValueError('Previous engine checksum mismatch')
        if previous_digest == current_digest:
            raise ValueError('Previous engine is identical to current version')
        import ast
        tree=ast.parse(previous_data.decode('utf-8'))
        versions=[
            node.value.value for node in tree.body
            if isinstance(node,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='VERSION'
                    for t in node.targets)
            and isinstance(node.value,ast.Constant)
            and isinstance(node.value.value,str)
        ]
        if len(versions)!=1:
            raise ValueError('Previous release has no verifiable version')
        match=re.match(r'^(\d+)\.(\d+)\.(\d+)', versions[0])
        if not match:
            raise ValueError('Unknown version format')
        # V2 updates use explicit three-digit sequence 2.3.9 -> 239.
        major,minor,patch=(int(x) for x in match.groups())
        previous_sequence=major*100+minor*10+patch
        if previous_sequence>=int(meta.get('installed_seq',0)):
            raise ValueError('Previous version is not older')
        compile(previous_data,'previous.py','exec')
        _atomic(CURRENT, previous_data)
        changed=True
        meta.update({'installed_seq':previous_sequence,
                     'installed_version':match.group(0),
                     'sha256':previous_digest,
                     'broken_version':str(meta.get('installed_version','')),
                     'last_result':'已回退 '+match.group(0)})
        _atomic(META,json.dumps(meta,ensure_ascii=False,indent=2).encode('utf-8'))
        return {'rolled_back':True,
                'message':'已恢复旧引擎 '+match.group(0)+'。退出并重新启动原入口；V3 个人数据库已保留。'}
    except Exception as exc:
        if changed and current_data is not None:
            try:
                _atomic(CURRENT,current_data)
                if saved_meta is not None:
                    _atomic(META,saved_meta)
            except OSError:
                pass
        return {'rolled_back':False,
                'message':'无法安全回退（'+type(exc).__name__+'），原始文件已尽量保持不变。'}
