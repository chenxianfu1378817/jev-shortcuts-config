# -*- coding: utf-8 -*-
"""One-time, pinned-repository repair for a stuck PYVoiceAgent cached engine.

Run from Pythonista Console only after checking this file's SHA-256.
Does not touch the fixed PYVoiceAgent.py entry, Keychain, tasks, or shortcuts.
"""
import hashlib
import json
import os
import re
import time
from urllib.request import Request, urlopen

BASE = 'https://raw.githubusercontent.com/chenxianfu1378817/jev-shortcuts-config/main/pyvoiceagent'
DATA_DIR = os.path.expanduser('~/Documents/PYVoiceAgent_Data')
META = os.path.join(DATA_DIR, 'update_meta.json')
TASK = os.path.join(DATA_DIR, 'current_task.json')
ENGINE = os.path.join(DATA_DIR, 'engine', 'current.py')
BACKUP = os.path.join(DATA_DIR, 'engine', 'previous.py')
LIMIT = 350000


def load_json(path):
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError('本地 JSON 数据格式异常: ' + os.path.basename(path))
    return value


def atomic_bytes(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + '.repair-part'
    with open(temp, 'wb') as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def atomic_json(path, data):
    atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def download(path, limit):
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:json|py)', path):
        raise ValueError('非法下载文件名')
    url = BASE + '/' + path + '?_=' + str(int(time.time()))
    with urlopen(Request(url, headers={'User-Agent': 'PYVoiceAgent-Repair/1.0',
                                       'Cache-Control': 'no-cache'}), timeout=20) as resp:
        raw = resp.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('远程文件过大，拒绝安装')
    return raw


def repair_update():
    state = load_json(TASK)
    if state.get('pending') and state.get('status') in ('awaiting_callback', 'needs_review', 'writing'):
        return '已停止：存在未核验的系统写入；没有修改手机文件。'

    meta = load_json(META)
    if meta.get('broken_version') == '1.5.2':
        return '已停止：1.5.2 曾被本机标记为故障版本，请先核实错误，不能强制重装。'
    try:
        body = download('manifest.json', 16384)
        m = json.loads(body.decode('utf-8'))
        if not isinstance(m, dict):
            raise ValueError('远程版本清单格式异常')
        seq, version, path = m.get('sequence'), m.get('version'), m.get('path')
        expected_hash, expected_size = m.get('sha256'), m.get('size_bytes')
        if (not isinstance(seq, int) or isinstance(seq, bool) or seq < 140
            or not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version)
            or not isinstance(path, str) or not re.fullmatch(r'agent_core_\d+_\d+_\d+\.py', path)
            or not isinstance(expected_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_hash)
            or not isinstance(expected_size, int) or isinstance(expected_size, bool)
            or not 1000 <= expected_size <= LIMIT):
            raise ValueError('远程版本清单字段校验未通过')
        installed = int(meta.get('installed_seq', 0))
        if seq <= installed:
            if os.path.isfile(ENGINE) and meta.get('sha256') == file_hash(ENGINE):
                return '已安装最新版 {}。请从 PYVoiceAgent.py 重新进入菜单。'.format(meta.get('installed_version', version))
            return '更新记录显示已是新版，但缓存与记录不一致；已停止，需先检查。'
        if version == meta.get('broken_version'):
            return '已停止：{} 曾在本机运行失败，未自动重装。'.format(version)
        old = None
        if os.path.isfile(ENGINE):
            with open(ENGINE, 'rb') as f:
                old = f.read()
            if not meta.get('sha256') or hashlib.sha256(old).hexdigest() != meta['sha256']:
                raise ValueError('旧版缓存与校验值不一致；为保护回退功能已停止')
        new = download(path, expected_size + 1)
        if len(new) != expected_size or hashlib.sha256(new).hexdigest() != expected_hash:
            raise ValueError('下载文件大小或 SHA256 不匹配；未覆盖旧引擎')
        compile(new, path, 'exec')
        # Backup the old engine while it is still the known-good pinned version.
        if old is not None:
            atomic_bytes(BACKUP, old)
            meta['previous_sha256'] = hashlib.sha256(old).hexdigest()
            atomic_json(META, meta)  # Backup becomes available for an interrupted install.
        atomic_bytes(ENGINE, new)
        meta['installed_seq'] = seq
        meta['installed_version'] = version
        meta['sha256'] = expected_hash
        meta['last_checked'] = time.time()
        meta['last_result'] = '已安装 ' + version
        try:
            atomic_json(META, meta)
        except Exception:
            if old is not None:
                atomic_bytes(ENGINE, old)
            raise
        return '更新成功：{}。关闭当前运行，再启动原来的 PYVoiceAgent.py。'.format(version)
    except Exception as exc:
        return '更新未成功：{}: {}。旧数据未主动清理，请保留截图。'.format(type(exc).__name__, exc)


def file_hash(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


if __name__ == '__main__':
    print(repair_update())
