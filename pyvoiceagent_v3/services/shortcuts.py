"""Local shortcut allowlist; no Apple actions execute inside this module."""
import json
import re
from ..core.models import InputError

_TOOL_ID = re.compile(r'^[a-z][a-z0-9_]{1,31}$')
_INPUT_MODES = ('none', 'full', 'suffix')


class ShortcutRegistry:
    def __init__(self, store):
        self.store = store

    def register(self, tool_id, shortcut_name, aliases, description='',
                 enabled=True, input_mode='none', requires_confirmation=True):
        if not isinstance(tool_id, str) or not _TOOL_ID.fullmatch(tool_id):
            raise InputError('Invalid tool ID')
        if not isinstance(shortcut_name, str) or not 1 <= len(shortcut_name.strip()) <= 80:
            raise InputError('Shortcut name must have 1-80 characters')
        if not isinstance(description, str) or len(description) > 300:
            raise InputError('Description too long')
        if not isinstance(aliases, (list, tuple)) or not 1 <= len(aliases) <= 12:
            raise InputError('1-12 trigger aliases required')
        clean = [x.strip() for x in aliases if isinstance(x, str)]
        if len(clean) != len(aliases) or any(not 1 <= len(x) <= 80 for x in clean):
            raise InputError('Invalid alias')
        if len(set(x.casefold() for x in clean)) != len(clean):
            raise InputError('Duplicate aliases inside tool')
        if input_mode not in _INPUT_MODES:
            raise InputError('Unknown input mode')
        if type(enabled) is not bool or type(requires_confirmation) is not bool:
            raise InputError('Tool flags must be booleans')
        record = {'tool_id': tool_id, 'shortcut_name': shortcut_name.strip(),
                  'description': description, 'aliases': clean,
                  'enabled': enabled, 'input_mode': input_mode,
                  'requires_confirmation': True}  # V3 Phase 1 always requires consent
        self.store.put_tool(record)
        return record

    def list(self):
        records = []
        for row in self.store.list_tools():
            records.append({
                'tool_id': row['tool_id'], 'shortcut_name': row['shortcut_name'],
                'description': row['description'], 'aliases': json.loads(row['aliases_json']),
                'enabled': bool(row['enabled']), 'input_mode': row['input_mode'],
                'requires_confirmation': True,
            })
        return records

    def match(self, text):
        query = str(text or '').strip().casefold()
        for tool in self.list():
            if not tool['enabled']:
                continue
            for alias in tool['aliases']:
                name = alias.casefold()
                if query == name or query in ('打开'+name, '运行'+name, '执行'+name):
                    return dict(tool, matched_alias=alias)
        return None

    def prepare_action(self, tool, text):
        if not tool or not tool.get('enabled'):
            raise InputError('Unregistered or disabled tool')
        if tool['input_mode'] == 'full':
            value = text
        elif tool['input_mode'] == 'suffix':
            match = tool.get('matched_alias', '')
            index = text.casefold().find(match.casefold()) if match else -1
            # For an AI-selected tool, the literal alias may not occur in the
            # user's phrase; forward original text instead of silently losing it.
            value = text[index + len(match):].strip() if index >= 0 else text
        else:
            value = ''
        return {'kind': 'ios_shortcut_handoff', 'tool_id': tool['tool_id'],
                'shortcut_name': tool['shortcut_name'], 'input_text': value[:2000],
                'requires_user_action': True, 'executed': False}
