"""Current SQLite history, and *read-only* V2 legacy history inspection."""
import json
import os
import re

_LEGACY_MONTH = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
_LEGACY_FILENAME = re.compile(r'^task_[A-Za-z0-9_-]{6,80}\.json$')


class HistoryService:
    def __init__(self, store):
        self.store = store

    def list(self, limit=20, offset=0):
        return [{'task_id': row['task_id'], 'text': row['text'],
                 'status': row['status'], 'message': row['message'],
                 'created_at': row['created_at']} for row in
                self.store.list_tasks(limit, offset)]

    @staticmethod
    def preview_legacy(data_dir, limit=60):
        """Never imports/moves/modifies V2 files; reports corrupt entries."""
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise ValueError('Invalid limit')
        root = os.path.join(os.fspath(data_dir), 'history')
        if not os.path.isdir(root):
            return {'entries': [], 'scanned': 0, 'skipped': 0, 'read_only': True}
        entries, scanned, skipped = [], 0, 0
        for month in sorted(os.scandir(root), key=lambda x:x.name, reverse=True):
            if not _LEGACY_MONTH.fullmatch(month.name) or not month.is_dir(follow_symlinks=False):
                continue
            for entry in sorted(os.scandir(month.path), key=lambda x:x.name, reverse=True):
                if len(entries) >= limit or scanned >= 500:
                    break
                if not _LEGACY_FILENAME.fullmatch(entry.name) or not entry.is_file(follow_symlinks=False):
                    continue
                scanned += 1
                try:
                    if entry.stat(follow_symlinks=False).st_size > 1024*1024:
                        raise ValueError('oversized')
                    with open(entry.path, 'r', encoding='utf-8') as file:
                        raw = json.load(file)
                    expected = month.name+'/'+entry.name
                    if (not isinstance(raw, dict) or raw.get('archive_key') != expected or
                            raw.get('kind') != 'task'):
                        raise ValueError('wrong archive kind')
                    entries.append({'archive_key': expected,
                                    'goal': str(raw.get('goal') or '')[:160],
                                    'status': str(raw.get('status') or '')[:60],
                                    'created': str(raw.get('created') or '')[:45]})
                except (OSError, UnicodeError, ValueError, TypeError):
                    skipped += 1
            if len(entries) >= limit or scanned >= 500:
                break
        return {'entries': entries, 'scanned': scanned,
                'skipped': skipped, 'read_only': True}
