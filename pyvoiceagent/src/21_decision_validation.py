def parse_decision(raw):
    if not isinstance(raw, dict):
        raise ValueError('AI 输出不是 JSON 对象')
    legacy = {'tool','reason','text','title','datetime','notes'}
    if set(raw.keys()) == legacy:
        raw = dict(raw, end_datetime='', shortcut_id='')
    if set(raw.keys()) != set(DECISION_SCHEMA['required']):
        raise ValueError('AI 字段不符合约定格式')
    if any(not isinstance(raw[x], str) for x in DECISION_SCHEMA['required']):
        raise ValueError('AI 返回的字段类型错误')
    if raw['tool'] not in TOOLS:
        raise ValueError('AI 请求了没有授权的工具')
    for field in ('text', 'title', 'datetime', 'notes', 'end_datetime', 'shortcut_id'):
        if len(raw[field]) > MAX_AI_OUTPUT:
            raise ValueError('AI 字段过长，已拒绝执行')
    if raw['tool'] in ('local_note.save', 'reminder.create', 'apple_notes.create', 'calendar.create') and not raw['title'].strip():
        raise ValueError('写入任务没有标题')
    if raw['tool'] in ('reminder.create', 'calendar.create') and not raw['datetime'].strip():
        raise ValueError('提醒缺少具体日期时间')
    if raw['tool'] == 'calendar.create' and not raw['end_datetime'].strip():
        raise ValueError('日历事件必须给出结束日期时间')
    if raw['tool'] == 'shortcut.run' and not raw['shortcut_id'].strip():
        raise ValueError('自定义快捷指令缺少工具库 ID')
    if raw['tool'] == 'app.navigate':
        _app_route_target(raw)
    return raw
