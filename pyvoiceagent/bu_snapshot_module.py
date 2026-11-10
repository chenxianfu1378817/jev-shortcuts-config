# -*- coding: utf-8 -*-
"""BU snapshot module for PYVoiceAgent V1.9.2.

One-shot Sina quotes after night/day sessions. No Playwright, no external libs.
This module is embedded in the GitHub released core; no new iPhone file needed.
"""

import re
def _bu_cn_now(now=None):
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        raise ValueError('必须使用带时区的时间')
    return now.astimezone(tz)


def _bu_contract_codes(now):
    """Generate candidate delivery months; invalid/unlisted codes have empty responses."""
    current = now.year * 12 + now.month - 1
    codes = []
    for step in range(28):
        absolute = current + step
        year, month = divmod(absolute, 12)
        codes.append('BU{:02d}{:02d}'.format(year % 100, month + 1))
    return codes


def _bu_parse_quote_response(text):
    """Parse 'nf_BU' CF futures fields as used by Sina/AKShare.
    Index 1=time HHMMSS; 8=current_price, 13=hold, 14=volume.
    Missing/invalid prices are NOT silently replaced by zero.
    """
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
    """Sina NF often omits quote DATE: future wall-clock is suspicious.

    This is deliberately only a *warning* heuristic, not proof the quote is old.
    For example, 15:00 at a 12:51 Beijing-time test run cannot be today's
    15:00 trade, but could be a previous session's quote.
    """
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
    """Return one timestamped snapshot, never an official settlement price."""
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
        # V1.9.2: in an ad-hoc TEST, never mark a quotation whose wall-clock
        # is later than the collection time as a current effective quote.
        # Keep the raw record separately rather than erase evidence.
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
    """Triggered from unchanged entry URL; does not overwrite state/key/clipboard."""
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
    # Preserve every capture; no existing result is overwritten.
    atomic_json(json_file, snap)
    report = _bu_report(snap)
    with open(txt_file + '.tmp', 'w', encoding='utf-8') as out:
        out.write(report)
    os.replace(txt_file + '.tmp', txt_file)
    print(report)
    print('\n已归档：\n' + json_file + '\n' + txt_file)
    return snap