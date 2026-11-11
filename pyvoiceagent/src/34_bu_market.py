def _bu_cn_now(now=None):
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        raise ValueError('必须使用带时区的时间')
    return now.astimezone(tz)
def _bu_contract_codes(now):
    current = now.year * 12 + now.month - 1
    codes = []
    for step in range(28):
        absolute = current + step
        year, month = divmod(absolute, 12)
        codes.append('BU{:02d}{:02d}'.format(year % 100, month + 1))
    return codes
def _bu_parse_quote_response(text):
    result = {}
    pattern = r'var\s+hq_str_nf_(BU\d{4})\s*=\s*"([^"]*)"\s*;?'
    for match in re.finditer(pattern, text, flags=re.I):
        symbol = match.group(1).upper()
        fields = match.group(2).split(',')
        if len(fields) < 15:
            continue
        clock = fields[1].strip().replace(':', '')
        if not re.fullmatch(r'\d{6}', clock):
            continue
        try:
            price = float(fields[8].strip())
        except (ValueError, TypeError):
            continue
        if not 500 <= price <= 20000:
            continue
        def numeric_field(index):
            try:
                val = float(fields[index].strip())
                return max(0, int(val)) if val >= 0 else None
            except (ValueError, IndexError, OverflowError):
                return None
        result[symbol] = {
            'contract': symbol, 'last_price': price, 'quote_clock': clock,
            'volume': numeric_field(14), 'open_interest': numeric_field(13),
            'source': 'sina_finance_nf_snapshot',
        }
    return result
def _bu_accept_quote_clock(clock, session):
    try:
        h = int(clock[0:2]); m = int(clock[2:4]); s = int(clock[4:6])
        seconds = h * 3600 + m * 60 + s
        if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
            return False
    except (ValueError, TypeError, IndexError):
        return False
    if session == 'night':
        return 21 * 3600 <= seconds <= 23 * 3600 + 59
    if session == 'day':
        return 13 * 3600 + 30 * 60 <= seconds <= 15 * 3600 + 59
    return False
def _bu_clock_future(clock, captured, margin_seconds=120):
    try:
        h, m, sec = int(clock[:2]), int(clock[2:4]), int(clock[4:6])
        if not 0 <= h < 24 or not 0 <= m < 60 or not 0 <= sec < 60:
            return True
        quote_seconds = h * 3600 + m * 60 + sec
        captured_seconds = captured.hour * 3600 + captured.minute * 60 + captured.second
        return quote_seconds > captured_seconds + margin_seconds
    except (TypeError, ValueError, IndexError):
        return True
def _bu_fetch_quotes(codes, fetcher=None):
    from urllib.request import Request, urlopen
    all_rows = {}
    for offset in range(0, len(codes), 15):
        batch = codes[offset:offset + 15]
        url = ('https://hq.sinajs.cn/list=' +
               ','.join('nf_' + code for code in batch))
        if fetcher is not None:
            body = fetcher(url)
        else:
            request = Request(url, headers={
                'Referer': 'https://vip.stock.finance.sina.com.cn/',
                'User-Agent': 'Mozilla/5.0 (iPhone; PYVoiceAgent 1.9.2)',
                'Accept': '*/*', 'Cache-Control': 'no-cache',
            })
            with urlopen(request, timeout=12) as response:
                body = response.read(100000)
        if isinstance(body, bytes):
            text = body.decode('gbk', errors='replace')
        else:
            text = str(body)
        all_rows.update(_bu_parse_quote_response(text))
    return all_rows
def _bu_build_snapshot(session, now=None, fetcher=None):
    current = _bu_cn_now(now)
    if session not in ('night', 'day', 'test'):
        raise ValueError('时段只允许 night、day、test')
    if session != 'test':
        if current.weekday() >= 5:
            raise ValueError('周末不采集收盘快照；节假日请核对交易日历')
        time_min = current.hour * 60 + current.minute
        lo, hi = ((23 * 60, 23 * 60 + 17) if session == 'night'
                  else (15 * 60, 15 * 60 + 17))
        if not lo <= time_min <= hi:
            raise ValueError('不在{}收盘后采集窗口，不使用盘中价格冒充收盘'.format(session))
    codes = _bu_contract_codes(current)
    raw = _bu_fetch_quotes(codes, fetcher)
    rows = []
    suspected = []
    for symbol in codes:
        quote = raw.get(symbol)
        if not quote:
            continue
        clock = quote['quote_clock']
        if session in ('night', 'day') and not _bu_accept_quote_clock(clock, session):
            continue
        quote = dict(quote)
        quote['price_kind'] = '时点末价参考，不等于交易所官方收盘或结算价'
        quote['verification'] = ('仅核对时分秒；新浪接口不提供完整交易日，'
                                 '节假日及无成交合约需人工复核')
        if session == 'test' and _bu_clock_future(clock, current):
            quote['quality'] = 'suspect_previous_session_or_time_unknown'
            quote['quality_reason'] = '报价时刻晚于本次采集时间，可能沿用上一交易时段报价'
            suspected.append(quote)
            continue
        quote['quality'] = 'clock_only_unverified_date'
        rows.append(quote)
    if not rows and not suspected:
        raise RuntimeError('没有取得有效 BU 行情字段；未保存任何收盘数字')
    rows.sort(key=lambda item: item['contract'])
    suspected.sort(key=lambda item: item['contract'])
    return {
        'version': 1, 'exchange': 'SHFE', 'product': 'BU',
        'session': session, 'session_calendar_date_bj': current.date().isoformat(),
        'captured_at_bj': current.isoformat(timespec='seconds'),
        'data_source': 'https://hq.sinajs.cn/',
        'requested_candidate_count': len(codes),
        'valid_quote_count': len(rows),
        'suspect_quote_count': len(suspected),
        'received_quote_count': len(rows) + len(suspected),
        'suspect_records': suspected,
        'kind': '收盘时点快照' if session != 'test' else '实时测试快照',
        'disclaimer': ('行情源未提供完整交易日日期；只能作为时点参考。'
                       '不能保证所有上市合约均有有效报价；不等于官方结算价。'),
        'records': rows,
    }
def _bu_report(snapshot):
    label = {'night':'夜盘','day':'日盘','test':'测试'}[snapshot['session']]
    lines = ['BU 沥青期货{}行情快照'.format(label),
             '采集日期（北京时间）：' + snapshot['captured_at_bj'],
             '来源：新浪财经（非官方结算数据）',
             '时刻未见异常报价：{} 条（日期仍未核验）'.format(snapshot['valid_quote_count']),
             '时刻可疑报价：{} 条'.format(snapshot.get('suspect_quote_count', 0)), '']
    for row in snapshot['records']:
        lines.append('{}  {:g} 元/吨  行情时间 {}  成交量 {}'.format(
            row['contract'], row['last_price'], row['quote_clock'],
            row['volume'] if row['volume'] is not None else '未知'))
    if snapshot.get('suspect_records'):
        lines += ['', '以下报价不计入本次有效参考（保留供人工核对）：']
        for row in snapshot['suspect_records']:
            lines.append('{}  {:g} 元/吨  行情时间 {}  [时刻可疑]'.format(
                row['contract'], row['last_price'], row['quote_clock']))
    lines += ['', snapshot['disclaimer']]
    return '\n'.join(lines)
def bu_capture_run(session='test', now=None, fetcher=None, output_dir=None):
    import os
    import uuid
    from datetime import datetime
    snap = _bu_build_snapshot(session, now, fetcher)
    folder = output_dir or os.path.join(DATA_DIR, 'bu_futures')
    os.makedirs(folder, exist_ok=True)
    stamp = _bu_cn_now(now).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:5]
    stem = 'bu_{}_{}'.format(stamp, session)
    json_file = os.path.join(folder, stem + '.json')
    txt_file = os.path.join(folder, stem + '.txt')
    atomic_json(json_file, snap)
    report = _bu_report(snap)
    with open(txt_file + '.tmp', 'w', encoding='utf-8') as out:
        out.write(report)
    os.replace(txt_file + '.tmp', txt_file)
    print(report)
    print('\n已归档：\n' + json_file + '\n' + txt_file)
    return snap
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
    import json
    if os.path.exists(BU_CALENDAR_LEDGER_PATH):
        try:
            with open(BU_CALENDAR_LEDGER_PATH, 'r', encoding='utf-8') as stream:
                data = json.load(stream)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ValueError('BU 日历同步日志无法读取，已停止写入以保护记录：' + str(error)[:120]) from error
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
def _bu_calendar_compact_notes(snapshot):
    from datetime import datetime, timezone, timedelta
    captured = datetime.fromisoformat(snapshot['captured_at_bj'])
    if captured.tzinfo is None:
        raise ValueError('BU 采集日期没有时区')
    cn = captured.astimezone(timezone(timedelta(hours=8)))
    session = snapshot.get('session')
    night = session == 'night' or (session == 'test' and 21 <= cn.hour <= 23)
    day = session == 'day' or (session == 'test' and 9 <= cn.hour < 21)
    lines = []
    marked = False
    seen = set()
    for group, suspect in ((snapshot.get('records') or [], False),
                           (snapshot.get('suspect_records') or [], True)):
        for row in group:
            contract = str(row.get('contract', '')).strip().upper()
            price = row.get('last_price')
            if not re.fullmatch(r'BU\d{4}', contract):
                continue
            try:
                price = float(price)
            except (ValueError, TypeError):
                continue
            if not (0 < price < 100000):
                continue
            if contract in seen:
                continue
            seen.add(contract)
            clock = str(row.get('quote_clock', '')).zfill(6)
            out_of_period = False
            if not re.fullmatch(r'\d{6}', clock):
                out_of_period = True
            elif night:
                out_of_period = not ('210000' <= clock <= '230000')
            elif day:
                out_of_period = not (
                    ('090000' <= clock <= '113000') or
                    ('133000' <= clock <= '150000'))
            flag = suspect or out_of_period
            lines.append('{}  {:g}{}'.format(contract, price, ' *' if flag else ''))
            marked = marked or flag
    if not lines:
        raise ValueError('BU 报价为空，无法生成日历备注')
    notes = ['单位：元/吨'] + lines
    notes.append('注：{}日期未核验，非结算价。'.format('*为非本时段或可疑报价；' if marked else ''))
    return '\n'.join(notes)
def _bu_calendar_event_fields(snapshot):
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
    content = _bu_calendar_compact_notes(snapshot)
    if len(content) > BU_CALENDAR_MAX_NOTE:
        raise ValueError('BU 报价过长，未自动写日历；完整报告仍已本地归档')
    return {'key': key, 'title': title, 'notes': content, 'start': start.isoformat(timespec='seconds'),
            'end': end.isoformat(timespec='seconds')}
def _bu_calendar_publish(snapshot, launcher=None, require_confirmation=False):
    if snapshot.get('session') == 'test' and not require_confirmation:
        return {'status': 'skipped', 'message': '测试快照不会自动创建苹果日程'}
    if snapshot.get('session') not in ('day', 'night', 'test'):
        return {'status': 'skipped', 'message': '未知时段，未写日程'}
    fields = _bu_calendar_event_fields(snapshot)
    key = fields['key']
    ledger = _bu_calendar_read_ledger()
    if require_confirmation and not prompt_alert('创建测试日历',
            '将创建一条真实的苹果日历测试事件（可手动删除），是否继续？'):
        return {'status': 'cancelled', 'message': '已取消测试日历写入'}
    attempt_id = uuid.uuid4().hex
    state = {'id': 'bu_' + attempt_id[:12], 'steps': 0}
    choice = {'tool': 'calendar.create', 'reason': 'BU行情归档', 'title': fields['title'],
              'text': '', 'notes': fields['notes'], 'datetime': fields['start'],
              'end_datetime': fields['end'], 'shortcut_id': ''}
    payload, encoded, token = bridge_payload(state, choice, 'calendar.create', BU_CALENDAR_SHORTCUT)
    internal_marker = payload.get('marker', '')
    payload['marker'] = ''
    encoded = base64.b64encode(json.dumps(
        payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).decode('ascii')
    journal_key = 'attempt_' + attempt_id
    ledger['entries'][journal_key] = {
        'key': key, 'attempt_id': attempt_id,
        'status': 'awaiting_callback', 'token': token,
        'created': datetime.now().timestamp(), 'title': fields['title'],
        'start': fields['start'], 'end': fields['end'], 'marker': internal_marker,
        'snapshot_captured_at_bj': snapshot['captured_at_bj'],
        'note': '苹果日历操作结果可能未核验；新一次用户发起的执行会另建日程',
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
        entry = ledger['entries'].get(journal_key, {})
        if entry.get('token') == token:
            entry['status'] = 'needs_review'
            entry['error'] = '快捷指令跳转异常，可能已经启动：' + str(exc)[:150]
            _bu_calendar_write_ledger(ledger)
        return {'status': 'needs_review', 'message': '系统跳转不确定；请检查苹果日历后再处理：' + str(exc)[:130]}
    return {'status': 'awaiting_callback', 'message': '每次执行均已独立请求 PYAgentCalendar 新建日程，等待回传（实际写入未独立核验）'}
def _bu_calendar_handle_callback(token, status):
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
        print('【BU日历归档】写入未确认；完整行情文件已保存。错误：' + str(err)[:260])
    return snapshot
def main():
    global VOICE_SESSION_ACTIVE
    if len(sys.argv) > 1:
        if sys.argv[1] == 'bu_close':
            mode = sys.argv[2] if len(sys.argv) > 2 else 'test'
            try:
                _bu_capture_and_calendar(mode)
            except Exception as ex:
                print('【BU行情快照】未成功归档：' + str(ex)[:250])
            return
        if sys.argv[1] == 'bridge_callback':
            _token = sys.argv[2] if len(sys.argv)>2 else ''
            _status = sys.argv[3] if len(sys.argv)>3 else ''
            _result = sys.argv[4] if len(sys.argv)>4 else ''
            try:
                _bu_handled = _bu_calendar_handle_callback(_token, _status)
            except Exception as _bu_callback_error:
                print('BU日历回调状态读取异常：' + str(_bu_callback_error)[:200])
                _bu_handled = False
            if not _bu_handled:
                bridge_callback(_token, _status, _result)
            return
        if sys.argv[1] == 'callback':
            callback(sys.argv[2] if len(sys.argv) > 2 else '')
            return
        if sys.argv[1] == 'voice':
            VOICE_SESSION_ACTIVE = True
            txt = input_voice(hands_free=True)
            if txt:
                start_new(txt)
            return
        if sys.argv[1] == 'text' and len(sys.argv) > 2:
            start_new(sys.argv[2])
            return
    show_menu()
APPEARANCE_PATH = os.path.join(DATA_DIR, 'appearance.json')
CARD_THEMES = {
    '活力橙': '#F07828',
    '科技蓝': '#3979E8',
    '翡翠绿': '#159F7B',
    '典雅紫': '#8A62D8',
    '中国红': '#D6434B',
    '玫瑰粉': '#D66D96',
    '深海青': '#168E9A',
    '石墨黑': '#444B59',
}
DISPLAY_MODES = ('跟随系统', '浅色模式', '深色模式')
_CARD_DEFAULTS = {'theme': '活力橙', 'mode': '跟随系统', 'custom_color': ''}
