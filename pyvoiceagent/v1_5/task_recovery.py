# -*- coding: utf-8 -*-
"""V1.5 task recovery policy. Pure Python; does not touch iOS or the network.

This module never retries a possibly dispatched system write. It archives
uncertain operations and allows unrelated tasks to continue.
"""
import hashlib
import json
from datetime import datetime

WRITE_ROUTES = frozenset(('reminder.create', 'apple_notes.create',
                          'calendar.create', 'local_note.save', 'shortcut.run'))
UNCERTAIN_STATUSES = frozenset(('awaiting_callback', 'needs_review', 'write_unknown'))


def operation_key(route, title, start='', end='', text='', notes=''):
    """Stable operation identity. Text/notes are hashed, never stored in a key."""
    if route not in WRITE_ROUTES:
        raise ValueError('Operation is not a registered write route')
    fields = [str(x or '').strip() for x in (route, title, start, end, text, notes)]
    canonical = json.dumps(fields, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def preflight_disposition(route, module_ready):
    """The absence of a module is a confirmed no-dispatch, not a callback timeout."""
    if route not in WRITE_ROUTES:
        return {'status': 'rejected', 'dispatched': False, 'manual_required': False}
    if not module_ready:
        return {'status': 'unavailable', 'dispatched': False, 'manual_required': False}
    return {'status': 'ready', 'dispatched': False, 'manual_required': False}


def callback_disposition(dispatched, receipt):
    """Treat callbacks as reports, never independent proof of an iOS object."""
    if not dispatched:
        return {'status': 'not_dispatched', 'archive': False, 'retry': False}
    if receipt == 'ok':
        return {'status': 'reported_ok', 'archive': False, 'retry': False}
    if receipt in (None, 'failed', 'cancelled', 'expired', 'malformed'):
        return {'status': 'write_unknown', 'archive': True, 'retry': False}
    return {'status': 'write_unknown', 'archive': True, 'retry': False}


def defer_uncertain(queue, operation, reason, now=None):
    """Idempotently record unresolved writes. Leave other tasks unblocked."""
    if not isinstance(queue, list):
        raise ValueError('Recovery queue is corrupt; refuse to discard history')
    if not isinstance(operation, dict) or not operation.get('key'):
        raise ValueError('Missing operation fingerprint')
    key = operation['key']
    for entry in queue:
        if entry.get('key') == key and entry.get('resolved') is not True:
            return list(queue), False
    if len(queue) >= 2000:
        raise RuntimeError('Recovery queue limit reached; do not overwrite entries')
    record = {'key': key, 'route': operation.get('route', ''),
              'title': operation.get('title', ''),
              'token': operation.get('token', ''),
              'reason': str(reason)[:300],
              'created': now or datetime.now().isoformat(),
              'resolved': False}
    return list(queue) + [record], True


def is_duplicate_blocked(queue, key):
    """Block exact repeated writes when a previous attempt is unresolved."""
    if not isinstance(queue, list):
        raise ValueError('Recovery queue unavailable; unsafe to write')
    return any(row.get('key') == key and row.get('resolved') is not True
               for row in queue)


def mark_resolved(queue, key, confirmed_exists):
    """Only evidence or an explicit user decision may resolve ambiguity."""
    if not isinstance(confirmed_exists, bool):
        raise ValueError('Resolution requires a confirmed boolean outcome')
    changed = False
    updated = []
    for item in queue:
        item = dict(item)
        if item.get('key') == key and item.get('resolved') is not True:
            item['resolved'] = True
            item['result'] = 'confirmed_exists' if confirmed_exists else 'confirmed_absent'
            changed = True
        updated.append(item)
    return updated, changed
