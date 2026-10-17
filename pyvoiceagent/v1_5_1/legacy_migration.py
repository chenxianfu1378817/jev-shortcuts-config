# -*- coding: utf-8 -*-
"""Carry unresolved V1.4.3 external writes forward without replaying them."""
import hashlib
from task_recovery import defer_uncertain, is_duplicate_blocked


def migrate_v143_pending(state, queue, now=None):
    """Store a legacy uncertain operation, preserving unrelated task availability.

    Old pending records hold a tool/title/token but can lack the original text,
    so repeat detection must conservatively match route+title as well as keys.
    """
    if not isinstance(state, dict):
        raise ValueError('Invalid legacy task')
    if state.get('status') not in ('awaiting_callback', 'needs_review'):
        return list(queue), False
    p = state.get('pending')
    if not isinstance(p, dict) or not p.get('tool'):
        return list(queue), False
    if p['tool'] not in ('apple_notes.create', 'calendar.create', 'shortcut.run'):
        return list(queue), False
    ident = str(p.get('marker') or p.get('token') or state.get('id', ''))
    if not ident:
        raise ValueError('Legacy pending operation has no identity; preserve task state')
    key = 'legacy:' + hashlib.sha256(ident.encode('utf-8')).hexdigest()
    old = {'key': key, 'route': p['tool'], 'title': str(p.get('title') or ''),
           'token': str(p.get('token') or '')}
    return defer_uncertain(queue, old, 'V1.4.3: 未核实的跨应用写入', now=now)


def block_legacy_replay(queue, route, title, key=None):
    """Block a replay if an old unresolved write targets the same app/title."""
    if key and is_duplicate_blocked(queue, key):
        return True
    for item in queue:
        if (str(item.get('key', '')).startswith('legacy:') and
                item.get('resolved') is not True and
                item.get('route') == route and
                (not item.get('title') or
                 item['title'].strip() == str(title or '').strip())):
            return True
    return False
