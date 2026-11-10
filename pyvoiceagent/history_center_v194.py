# -*- coding: utf-8 -*-
"""V1.9.4 local-only result archive. Embedded into the single-file engine."""
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
HISTORY_SCAN_LIMIT = 1600
HISTORY_RESULT_LIMIT = 80
_HIST_KEY_RX = re.compile(r'^\d{4}-\d{2}/task_[A-Za-z0-9_-]{6,80}\.json$')
_HIST_BU_RX = re.compile(r'^bu/bu_[A-Za-z0-9_-]{8,100}\.json$')


def _history_plain(value, max_len=7000):
    if value is None:
        return ''
    if isinstance(value, str):
        return value[:max_len]
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:max_len]
    except (TypeError, ValueError):
        return str(value)[:max_len]


def _history_event_quality(event):
    status = str(event.get('status', '')).lower()
    tool = str(event.get('tool', ''))
    if status == 'ok' and event.get('verified') is True:
        return '已从系统读回核验'
    if status == 'ok' and tool in ('text.respond', 'task.finish', 'local_note.save'):
        return '本机处理完成'
    if status == 'ok':
        return '执行端报告成功，未独立核验'
    if status == 'blocked_duplicate':
        return '已阻止重复写入'
    if status in ('waiting', 'awaiting_callback', 'handoff'):
        return '已发出请求，未确认结果'
    if status in ('needs_review', 'unknown'):
        return '需要人工核验'
    if status in ('unavailable', 'declined', 'cancelled'):
        return '未执行'
    if status in ('failed', 'error'):
        return '操作失败或状态不确定'
    return '状态未确认'


def _history_record_from_state(state):
    if not isinstance(state, dict):
        return None
    ident = str(state.get('id', ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]{6,80}', ident):
        return None
    events = []
    items = state.get('events', [])
    if not isinstance(items, list):
        items = []
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        params = item.get('params') if isinstance(item.get('params'), dict) else {}
        events.append({
            'tool': _history_plain(item.get('tool'), 100),
            'status': _history_plain(item.get('status'), 60),
            'quality': _history_event_quality(item),
            'verified': item.get('verified') is True,
            'title': _history_plain(params.get('title'), 180),
            'at': _history_plain(item.get('at'), 45),
            'result': _history_plain(item.get('result'), 7000),
        })
    created = _history_plain(state.get('created'), 40)
    try:
        datetime.fromisoformat(created.replace('Z', '+00:00'))
        month = created[:7]
        if not re.fullmatch(r'\d{4}-\d{2}', month) or not 1 <= int(month[-2:]) <= 12:
            raise ValueError('bad month')
    except (TypeError, ValueError):
        month = datetime.now().strftime('%Y-%m')
    return {
        'schema': 1, 'kind': 'task', 'id': ident,
        'archive_key': month+'/task_'+ident+'.json',
        'created': created,
        'updated': datetime.now().astimezone().isoformat(timespec='seconds'),
        'goal': _history_plain(state.get('goal'), 2100),
        'status': _history_plain(state.get('status'), 60),
        'final': _history_plain(state.get('final'), 11000),
        'error': _history_plain(state.get('error'), 1200),
        'events': events, 'source': 'PYVoiceAgent',
        'pending_action': {
            'tool': _history_plain((state.get('pending') or {}).get('tool'), 100),
            'title': _history_plain((state.get('pending') or {}).get('title'), 180),
        } if isinstance(state.get('pending'), dict) else {},
        'note': '快捷指令回报成功不等于苹果 App 实际内容已核验。',
    }


def _history_md(record):
    lines = ['# '+(_history_plain(record.get('goal'), 150) or 'PYVoiceAgent 执行记录'), '',
             '- 创建时间：'+_history_plain(record.get('created'), 45),
             '- 更新/采集时间：'+_history_plain(record.get('updated'), 45),
             '- 状态：'+_history_plain(record.get('status'), 80),
             '- 来源：'+_history_plain(record.get('source'), 60), '']
    if record.get('final'):
        lines += ['## 任务结果', '', _history_plain(record['final'], 11000), '']
    if record.get('error'):
        lines += ['## 异常／待核验事项', '', _history_plain(record['error'], 1200), '']
    if record.get('pending_action'):
        pending = record['pending_action']
        lines += ['## 当前待核验操作', '',
                  '{}：{}'.format(pending.get('tool', ''), pending.get('title', '')), '']
    if record.get('events'):
        lines += ['## 逐项执行凭据', '']
        for i, event in enumerate(record['events'], 1):
            lines += ['### {}. {}'.format(i, event.get('tool', '工具')),
                      '- 核验情况：'+_history_plain(event.get('quality'), 100),
                      '- 工具状态：'+_history_plain(event.get('status'), 100)]
            if event.get('title'):
                lines.append('- 标题：'+_history_plain(event['title'], 180))
            if event.get('result'):
                lines += ['', _history_plain(event['result'], 7000), '']
    lines += ['---', '注：记录保存在本机。快捷指令回报成功不代表独立读回苹果日历或备忘录内容。', '']
    return '\n'.join(lines)


def _history_atomic_text(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + '.tmp'
    with open(temp, 'w', encoding='utf-8') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _history_auto_record(state):
    """Archive each durable state transition; no network and no tool replays."""
    rec = _history_record_from_state(state)
    if rec is None:
        return None
    key = rec['archive_key']
    folder = os.path.join(HISTORY_DIR, key.split('/')[0])
    basename = key.split('/')[1][:-5]
    record_path = os.path.join(folder, basename+'.json')
    markdown_path = os.path.join(folder, basename+'.md')
    # The shared atomic_json only ensures DATA_DIR, not history/YYYY-MM.
    # Create this task's month folder before writing either archive file.
    os.makedirs(folder, exist_ok=True)
    # No raw planner, pending callback token, credential or untrusted code.
    atomic_json(record_path, rec)
    _history_atomic_text(markdown_path, _history_md(rec))
    return record_path


def _history_safe_path(key):
    if isinstance(key, str) and _HIST_KEY_RX.fullmatch(key):
        return os.path.join(HISTORY_DIR, *key.split('/'))
    if isinstance(key, str) and _HIST_BU_RX.fullmatch(key):
        return os.path.join(DATA_DIR, 'bu_futures', key.split('/', 1)[1])
    raise ValueError('历史档案标识不合法')


def _history_read(key):
    path = _history_safe_path(key)
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    if key.startswith('bu/'):
        if not isinstance(raw, dict) or raw.get('product') != 'BU' or not isinstance(raw.get('records'), list):
            raise ValueError('BU 原始行情格式不正确')
        label = {'day':'日盘', 'night':'夜盘', 'test':'测试'}.get(raw.get('session'), '未知')
        return {'schema':1, 'kind':'bu', 'archive_key':key,
                'created':_history_plain(raw.get('captured_at_bj'),45),
                'updated':_history_plain(raw.get('captured_at_bj'),45),
                'goal':'BU沥青期货{}报价｜{}'.format(label, _history_plain(raw.get('session_calendar_date_bj'),20)),
                'status':'行情已保存（日历写入状态另行核验）',
                'source':'新浪财经（非官方结算）',
                'final':_bu_report(raw), 'error':'', 'events':[]}
    if not isinstance(raw, dict) or raw.get('archive_key') != key or raw.get('kind') != 'task':
        raise ValueError('历史任务档案与请求不一致')
    return raw


def _history_search(query='', limit=HISTORY_RESULT_LIMIT):
    """Read user-local task archives and existing BU snapshot JSON files."""
    needle = str(query or '').strip().casefold()[:100]
    found, all_paths = [], []
    if os.path.isdir(HISTORY_DIR):
        for month in os.listdir(HISTORY_DIR):
            if not re.fullmatch(r'\d{4}-\d{2}', month):
                continue
            folder = os.path.join(HISTORY_DIR, month)
            if os.path.isdir(folder):
                all_paths += [(month+'/'+name, os.path.join(folder, name))
                              for name in os.listdir(folder)
                              if re.fullmatch(r'task_[A-Za-z0-9_-]{6,80}\.json', name)]
    bu_dir = os.path.join(DATA_DIR, 'bu_futures')
    if os.path.isdir(bu_dir):
        all_paths += [('bu/'+name, os.path.join(bu_dir, name))
                      for name in os.listdir(bu_dir)
                      if _HIST_BU_RX.fullmatch('bu/'+name)]
    def file_time(item):
        try:
            return os.path.getmtime(item[1])
        except OSError:
            return 0
    all_paths.sort(key=file_time, reverse=True)
    for key, path in all_paths[:HISTORY_SCAN_LIMIT]:
        try:
            record = _history_read(key)
        except (ValueError, UnicodeDecodeError, OSError, TypeError):
            continue
        parts = [record.get('goal',''), record.get('final',''),
                 record.get('error',''), record.get('created','')]
        for item in record.get('events',[]):
            if isinstance(item,dict):
                parts.extend([_history_plain(item.get('title'),180),
                              _history_plain(item.get('result'),7000),
                              _history_plain(item.get('tool'),100)])
        if needle and needle not in '\n'.join(str(x) for x in parts).casefold():
            continue
        qualities = [e.get('quality') for e in record.get('events',[]) if isinstance(e,dict)]
        grade = ('含未核验操作' if any('未独立核验' in str(v) or '人工核验' in str(v)
                                    for v in qualities) else '见详情核验状态')
        found.append({'key':key, 'title':_history_plain(record.get('goal'),120),
                      'created':_history_plain(record.get('created'),35),
                      'status':_history_plain(record.get('status'),60),
                      'quality':grade,
                      'preview':_history_plain(record.get('final') or record.get('error'),190)})
        if len(found) >= max(1,min(100,int(limit))):
            break
    return found


def _history_markdown_for_key(key):
    return _history_md(_history_read(key))


def _history_share_path(key):
    path = _history_safe_path(key)
    if key.startswith('bu/'):
        txt = path[:-5]+'.txt'
        if os.path.isfile(txt):
            return txt
        _history_atomic_text(txt, _history_markdown_for_key(key))
        return txt
    md = path[:-5]+'.md'
    if not os.path.isfile(md):
        _history_atomic_text(md, _history_markdown_for_key(key))
    return md


# Preserve the verified 1.9.3 state writer and fixed entry, adding only
# best-effort local history archives. No network calls or Apple writes.
_V193_PUT_STATE = put_state

def put_state(state):
    _V193_PUT_STATE(state)
    try:
        _history_auto_record(state)
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        print('【历史归档】保存失败，原任务记录已保留：'+str(error)[:160])


_V193_MAIN = main

def main():
    try:
        old = get_state()
        if isinstance(old, dict) and old.get('id'):
            _history_auto_record(old)
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        print('【历史归档】旧任务迁移未完成：'+str(error)[:150])
    return _V193_MAIN()
