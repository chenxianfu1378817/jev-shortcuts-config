"""Private local SQLite store: atomic tasks, idempotency and durable handoffs.

No Pythonista SDK imports. Every connection is confined to a single call;
concurrent writes are serialized with SQLite BEGIN IMMEDIATE.
"""
import contextlib
import datetime
import json
import os
import re
import sqlite3
import uuid

from ..core.models import InputError
from ..core.state_machine import check_transition

_ID_RX = re.compile(r'^[A-Za-z0-9_-]{8,128}$')


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


class LocalStore:
    def __init__(self, filename):
        self.filename = os.path.abspath(os.fspath(filename))
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.filename, timeout=8, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=8000')
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextlib.contextmanager
    def _tx(self):
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    @contextlib.contextmanager
    def _read(self):
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    def _initialize(self):
        with self._tx() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('Unsupported database schema; user data left unchanged')
            db.execute('''CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                text TEXT NOT NULL, status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                action_json TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                event_type TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY, value_json TEXT NOT NULL
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS tools (
                tool_id TEXT PRIMARY KEY, shortcut_name TEXT NOT NULL,
                description TEXT NOT NULL, aliases_json TEXT NOT NULL,
                enabled INTEGER NOT NULL, input_mode TEXT NOT NULL,
                requires_confirmation INTEGER NOT NULL
            )''')
            db.execute('PRAGMA user_version=1')

    def create_task(self, text, request_id=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise InputError('请输入1到2000字的任务文字')
        clean = text.strip()
        req = request_id or uuid.uuid4().hex
        if not isinstance(req, str) or not _ID_RX.fullmatch(req):
            raise InputError('request_id must be 8-128 ASCII letters/digits/_/-')
        with self._tx() as db:
            old = db.execute('SELECT * FROM tasks WHERE request_id=?', (req,)).fetchone()
            if old:
                if old['text'] != clean:
                    raise InputError('同一个 request_id 不能用于不同任务')
                return dict(old), False
            tid, when = uuid.uuid4().hex, _stamp()
            db.execute('''INSERT INTO tasks
                (task_id,request_id,text,status,message,action_json,created_at,updated_at)
                VALUES (?, ?, ?, 'queued', '', '', ?, ?)''', (tid, req, clean, when, when))
            db.execute('INSERT INTO events(task_id,event_type,created_at) VALUES(?,?,?)',
                       (tid, 'queued', when))
            return dict(db.execute('SELECT * FROM tasks WHERE task_id=?', (tid,)).fetchone()), True

    def get_task(self, task_id):
        with self._read() as db:
            row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            return dict(row) if row else None

    def move_task(self, task_id, status, message='', action=None):
        with self._tx() as db:
            row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if row is None:
                raise KeyError('Task does not exist')
            check_transition(row['status'], status)
            if action is not None and (not isinstance(action, dict) or len(json.dumps(action)) > 4096):
                raise InputError('Invalid pending action payload')
            when = _stamp()
            db.execute('''UPDATE tasks SET status=?, message=?, action_json=?, updated_at=?
                          WHERE task_id=?''',
                       (status, str(message)[:4000], json.dumps(action, ensure_ascii=False)
                        if action is not None else row['action_json'], when, task_id))
            db.execute('INSERT INTO events(task_id,event_type,created_at) VALUES(?,?,?)',
                       (task_id, status, when))
            return dict(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())

    def list_tasks(self, limit=20, offset=0):
        if not isinstance(limit, int) or not 1 <= limit <= 100 or offset < 0:
            raise InputError('Invalid history window')
        with self._read() as db:
            return [dict(row) for row in db.execute('''
                SELECT * FROM tasks ORDER BY created_at DESC, task_id DESC
                LIMIT ? OFFSET ?''', (limit, offset))]

    def task_events(self, task_id):
        with self._read() as db:
            return [dict(row) for row in db.execute(
                'SELECT event_type, created_at FROM events WHERE task_id=? ORDER BY seq', (task_id,))]

    def running_tasks(self, limit=100):
        """Inspect potentially interrupted work without changing it."""
        with self._read() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM tasks WHERE status='running' "
                "ORDER BY created_at LIMIT ?", (max(1, min(100, limit)),))]

    def mark_interrupted(self, task_id):
        """Explicit operator quarantine; no retry of unknown external effects."""
        row = self.get_task(task_id)
        if row is None:
            raise KeyError('No such task')
        if row['status'] != 'running':
            return row
        try:
            return self.move_task(task_id, 'needs_review',
                '上次执行意外中断，外部动作状态不确定；请人工核验，不自动重试。')
        except ValueError:
            # Another process already finalized it: return the committed state.
            return self.get_task(task_id)

    def get_setting(self, key, default=None):
        with self._read() as db:
            row = db.execute('SELECT value_json FROM settings WHERE setting_key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def put_setting(self, key, value):
        raw = json.dumps(value, ensure_ascii=False)
        if len(raw) > 4096:
            raise InputError('Setting too large')
        with self._tx() as db:
            db.execute('INSERT OR REPLACE INTO settings(setting_key,value_json) VALUES(?,?)',
                       (key, raw))

    def list_tools(self):
        with self._read() as db:
            return [dict(row) for row in db.execute('SELECT * FROM tools ORDER BY tool_id')]

    def put_tool(self, record):
        with self._tx() as db:
            # Reject enabled alias conflicts atomically.
            aliases = set(a.casefold() for a in record['aliases'])
            for row in db.execute('SELECT tool_id, aliases_json,enabled FROM tools'):
                if row['tool_id'] != record['tool_id'] and row['enabled'] and record['enabled']:
                    if aliases.intersection(a.casefold() for a in json.loads(row['aliases_json'])):
                        raise InputError('触发语句与另一个启用工具重复')
            db.execute('''INSERT OR REPLACE INTO tools
                (tool_id,shortcut_name,description,aliases_json,enabled,input_mode,requires_confirmation)
                VALUES(?,?,?,?,?,?,?)''',
                (record['tool_id'], record['shortcut_name'], record['description'],
                 json.dumps(record['aliases'], ensure_ascii=False), int(record['enabled']),
                 record['input_mode'], int(record['requires_confirmation'])))

    def backup(self, destination):
        """SQLite-native consistent backup; never overwrite an existing backup."""
        dest = os.path.abspath(os.fspath(destination))
        if os.path.exists(dest):
            raise FileExistsError('Refusing to overwrite existing backup')
        if dest == self.filename:
            raise ValueError('Backup cannot overwrite source')
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with self._read() as original:
            target = sqlite3.connect(dest)
            try:
                original.backup(target)
            finally:
                target.close()
        return dest
