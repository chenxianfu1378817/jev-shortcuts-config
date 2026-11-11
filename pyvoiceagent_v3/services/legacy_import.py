"""Import only validated V2 launch-mode shortcuts, preserving original files.

V2 'bridge' entries are skipped: they rely on the old callback protocol and
must not silently be converted to new shortcut actions.
"""
import json
import os
import re

ID = re.compile(r'^[a-z][a-z0-9_]{1,31}$')


def preview_legacy_registry(folder):
    source = os.path.join(os.fspath(folder),'shortcut_registry.json')
    if not os.path.isfile(source):
        return {'source':source,'ready':[],'skipped':0}
    if os.path.getsize(source)>256000:
        raise ValueError('Legacy shortcut registry exceeds inspection limit')
    with open(source,'r',encoding='utf-8') as f:
        records=json.load(f)
    if not isinstance(records,dict) or len(records)>100:
        raise ValueError('Invalid legacy registry structure')
    ready=[]
    skipped=0
    for ident,item in sorted(records.items()):
        if not isinstance(ident,str) or not ID.fullmatch(ident) or not isinstance(item,dict):
            skipped+=1
            continue
        if item.get('mode','launch')!='launch':
            skipped+=1
            continue
        name=item.get('name')
        aliases=item.get('aliases')
        if (not isinstance(name,str) or not 1<=len(name)<=70 or
                not isinstance(aliases,list) or not 1<=len(aliases)<=8 or
                not all(isinstance(x,str) and 1<=len(x.strip())<=45 for x in aliases)):
            skipped+=1
            continue
        input_mode=item.get('input_mode','none')
        if input_mode not in ('none','suffix','full'):
            skipped+=1
            continue
        ready.append({
            'tool_id':ident,'shortcut_name':name,
            'aliases':[x.strip() for x in aliases],
            'description':str(item.get('description') or '')[:160],
            'enabled':item.get('enabled',True) is True,
            'input_mode':input_mode,
        })
    return {'source':source,'ready':ready,'skipped':skipped}


def import_legacy_registry(registry,folder):
    """Explicit user-invoked copy into V3; never mutate original V2 data."""
    preview=preview_legacy_registry(folder)
    existing={x['tool_id'] for x in registry.list()}
    imported=[]
    skipped=preview['skipped']
    for item in preview['ready']:
        if item['tool_id'] in existing:
            skipped+=1
            continue
        try:
            registry.register(
                item['tool_id'],item['shortcut_name'],item['aliases'],
                description=item['description'],enabled=item['enabled'],
                input_mode=item['input_mode'],requires_confirmation=True)
            imported.append(item['tool_id'])
        except (ValueError,TypeError):
            skipped+=1
    return {'imported':imported,'skipped':skipped,
            'legacy_untouched':True}
