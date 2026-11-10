# -*- coding: utf-8 -*-
"""PYVoiceAgent V1.9.3 - calendar archiving of BU market snapshots.

Embedded in the monolithic release engine, no extra file installed on iPhone.
It deliberately reuses the enrolled PYAgentCalendar Shortcuts bridge.
A separate idempotency ledger prevents overwriting normal voice task state.
"""

BU_CALENDAR_LEDGER_PATH = os.path.join(DATA_DIR, 'bu_futures', 'calendar_ledger.json')
BU_CALENDAR_SHORTCUT = 'PYAgentCalendar'
BU_CALENDAR_MAX_NOTE = 3400


def _bu_calendar_key(snapshot):
    session = snapshot.get('session')
    if session not in ('day', 'night', 'test'):
        raise ValueError('未授权的 BU 日历行情类型')
    day = str(snapshot.get('session_calendar_date_bj', ''))
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('行情日期不存在或格式错误')
    return '{}:{}'.format(day, session)


def _bu_calendar_read_ledger():
    # Refuse unreadable or malformed journals: otherwise retries can create duplicate events.
    import json
    if os.path.exists(BU_CALENDAR_LEDGER_PATH):
        try:
            with open(BU_CALENDAR_LEDGER_PATH, 'r', encoding='utf-8') as stream:
                data = json.load(stream)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ValueError('BU 日历同步日志无法读取，已停止创建以防重复：' + str(error)[:120]) from error
    else:
        data = {}
    if not isinstance(data, dict):
        raise ValueError('BU 日历同步状态格式异常，拒绝覆盖')
    entries = data.get('entries', {})
    if not isinstance(entries, dict):
        raise ValueError('BU 日历同步记录格式异常，拒绝覆盖')
    return {'schema': 1, 'entries': entries}


def _bu_calendar_write_ledger(ledger):
    os.makedirs(os.path.dirname(BU_CALENDAR_LEDGER_PATH), exist_ok=True)
    atomic_json(BU_CALENDAR_LEDGER_PATH, ledger)


def _bu_calendar_event_fields(snapshot):
    """Create a Beijing-calendar-day event; local Calendar UI may change day in other TZs."""
    from datetime import datetime, timezone, timedelta
    current = datetime.fromisoformat(snapshot['captured_at_bj'])
    if current.tzinfo is None:
        raise ValueError('采集时间必须带时区')
    cn = current.astimezone(timezone(timedelta(hours=8)))
    key = _bu_calendar_key(snapshot)
    if current.date().isoformat() != snapshot['session_calendar_date_bj'] and cn.date().isoformat() != snapshot['session_calendar_date_bj']:
        raise ValueError('采集日期与北京时间日历日期不一致')
    mode = snapshot['session']
    if mode == 'day':
        title = 'BU沥青期货日盘报价｜{:02d}月{:02d}日'.format(cn.month, cn.day)
        start = cn.replace(hour=15, minute=0, second=0, microsecond=0)
        duration = 10
    elif mode == 'night':
        title = 'BU沥青期货夜盘报价｜{:02d}月{:02d}日'.format(cn.month, cn.day)
        start = cn.replace(hour=23, minute=0, second=0, microsecond=0)
        duration = 10
    else:
        title = 'BU沥青期货测试快照（验收后可删除）'
        start = cn.replace(second=0, microsecond=0)
        duration = 5
    end = start + timedelta(minutes=duration)
    # Shortcut module expects ISO8601 w/ offset; no timezone field to configure.
    content = _bu_report(snapshot)
    if len(content) > BU_CALENDAR_MAX_NOTE:
        # Never silently lose full quotes: leave result only in local TXT/JSON.
        raise ValueError('BU 报价过长，未自动写日历；完整报告仍已本地归档')
    return {'key': key, 'title': title, 'notes': content, 'start': start.isoformat(timespec='seconds'),
            'end': end.isoformat(timespec='seconds')}


def _bu_calendar_publish(snapshot, launcher=None, require_confirmation=False):
    """Attempt once, record intent durably before handing off to iOS.

    The actual Apple calendar write is performed by the enrolled Shortcut,
    never by Pythonista's private calendar store. Callback is a *report*,
    not an independent EventKit readback.
    """
    if snapshot.get('session') == 'test' and not require_confirmation:
        return {'status': 'skipped', 'message': '测试快照不会自动创建苹果日程'}
    if snapshot.get('session') not in ('day', 'night', 'test'):
        return {'status': 'skipped', 'message': '未知时段，未写日程'}
    if verified_system_module('calendar.create') != BU_CALENDAR_SHORTCUT:
        return {'status': 'not_configured',
                'message': 'BU报价已经本地归档；苹果日历模块 PYAgentCalendar 尚未完成首次验收，未发起写入'}
    fields = _bu_calendar_event_fields(snapshot)
    key = fields['key']
    ledger = _bu_calendar_read_ledger()
    if key in ledger['entries']:
        prev = ledger['entries'][key]
        status = prev.get('status', 'unknown') if isinstance(prev, dict) else 'invalid'
        return {'status': 'duplicate',
                'message': '本日此时段已有日历操作记录（{}）；为防重不自动创建第二条，请先在苹果日历核验'.format(status)}
    if require_confirmation and not prompt_alert('创建测试日历',
            '将创建一条真实的苹果日历测试事件（可手动删除），是否继续？'):
        return {'status': 'cancelled', 'message': '已取消测试日历写入'}
    state = {'id': 'bu_' + key.replace('-', '').replace(':', '_'), 'steps': 0}
    choice = {'tool': 'calendar.create', 'reason': 'BU行情归档', 'title': fields['title'],
              'text': '', 'notes': fields['notes'], 'datetime': fields['start'],
              'end_datetime': fields['end'], 'shortcut_id': ''}
    # Marker is part of the note as well, to help user check duplicates.
    marker = '[PYVoiceAgent:{}:{}]'.format(state['id'], state['steps'])
    choice['notes'] = fields['notes'] + '\n\n' + marker
    payload, encoded, token = bridge_payload(state, choice, 'calendar.create', BU_CALENDAR_SHORTCUT)
    # Persist the exact one-time request BEFORE leaving Pythonista.
    ledger['entries'][key] = {
        'key': key, 'status': 'awaiting_callback', 'token': token,
        'created': datetime.now().timestamp(), 'title': fields['title'],
        'start': fields['start'], 'end': fields['end'], 'marker': payload['marker'],
        'snapshot_captured_at_bj': snapshot['captured_at_bj'],
        'note': '苹果日历操作可能已执行；无回调时不可盲目重试',
    }
    _bu_calendar_write_ledger(ledger)
    from urllib.parse import urlencode
    url = 'shortcuts://run-shortcut?' + urlencode({
        'name': BU_CALENDAR_SHORTCUT, 'input': 'text', 'text': encoded})
    try:
        if launcher is None:
            import shortcuts
            launcher = shortcuts.open_url
        launcher(url)
    except Exception as exc:
        ledger = _bu_calendar_read_ledger()
        entry = ledger['entries'].get(key, {})
        if entry.get('token') == token:
            entry['status'] = 'needs_review'
            entry['error'] = '快捷指令跳转异常，可能已经启动：' + str(exc)[:150]
            _bu_calendar_write_ledger(ledger)
        return {'status': 'needs_review', 'message': '系统跳转不确定；请检查苹果日历后再处理：' + str(exc)[:130]}
    return {'status': 'awaiting_callback', 'message': '已将 BU 报价交给 PYAgentCalendar，等待日历快捷指令回传（不等于写入已核验）'}


def _bu_calendar_handle_callback(token, status):
    """Consume only matching BU tokens; leave ordinary PYVoiceAgent callbacks intact."""
    if not isinstance(token, str) or not token:
        return False
    ledger = _bu_calendar_read_ledger()
    matched_key = None
    for key, entry in ledger['entries'].items():
        if isinstance(entry, dict) and isinstance(entry.get('token'), str) and hmac.compare_digest(entry['token'], token):
            matched_key = key
            break
    if matched_key is None:
        return False
    entry = ledger['entries'][matched_key]
    if entry.get('status') != 'awaiting_callback':
        print('BU 日历已记录该 token 的结果，忽略重复回调。')
        return True
    if status not in ('ok', 'failed', 'cancelled'):
        print('BU 日历回调状态无效，保持待核验。')
        return True
    try:
        delay = datetime.now().timestamp() - float(entry.get('created', 0))
    except (TypeError, ValueError):
        delay = -1
    if not 0 <= delay <= BRIDGE_TIMEOUT:
        entry['status'] = 'needs_review'
        entry['error'] = '收到过期回调，必须人工检查苹果日历，禁止自动重试'
    elif status == 'ok':
        entry['status'] = 'shortcut_reported_ok'
        entry['result'] = 'PYAgentCalendar 报告创建成功；未独立查询苹果日历核验'
    else:
        entry['status'] = 'needs_review'
        entry['result'] = '日历快捷指令报告 {}；可能已写入，请人工核验'.format(status)
    entry['callback_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
    _bu_calendar_write_ledger(ledger)
    print('BU 日历同步：{}；{}'.format(entry['status'], entry.get('result', entry.get('error',''))))
    return True


def _bu_capture_and_calendar(mode):
    """Entry for two existing timed-automation URLs. Does not touch voice state."""
    if mode not in ('day', 'night', 'test', 'test_calendar'):
        raise ValueError('BU行情采集时段无效')
    session = 'test' if mode == 'test_calendar' else mode
    snapshot = bu_capture_run(session)
    if session == 'test' and mode != 'test_calendar':
        print('测试模式不会自动写入苹果日历。')
        return snapshot
    try:
        result = _bu_calendar_publish(snapshot, require_confirmation=(mode == 'test_calendar'))
        print('【BU日历归档】' + result['message'])
    except Exception as err:
        # The quote JSON/TXT already exists and must never be rolled back.
        print('【BU日历归档】写入未确认；完整行情文件已保存。错误：' + str(err)[:260])
    return snapshot