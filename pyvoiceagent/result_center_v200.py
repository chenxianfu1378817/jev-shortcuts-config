# -*- coding: utf-8 -*-
"""V2.0.0 native result cards for Pythonista; no network or state mutations.

Embedded into the fixed PYVoiceAgent.py engine. Pure model-building helpers are
safe to test without Pythonista. Only _result_ui_show imports iOS modules.
"""
_RESULT_CALENDAR_DATE = re.compile(
    r'^\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*'
    r'(\d{1,2}:\d{2})\s*(?:[—–~～\-至]\s*)?'
    r'(\d{1,2}:\d{2})\s*(.*)$')
_RESULT_CALENDAR_COUNT = re.compile(r'查询到\s*(\d+)\s*[条项]日程')
_RESULT_EVENT_LIMIT = 30


def _result_clean_calendar_payload(raw):
    """Remove transport-only prefixes; never infer an event that was not read."""
    value = str(raw or '').strip()
    for prefix in ('只读快捷指令返回（未做独立系统核验）：',
                   '只读快捷指令返回（未做独立系统核验）:',
                   'CALREAD1\n'):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
    return value


def _result_parse_calendar(raw):
    """Recognize the user's existing PYAgentCalendarRead textual response."""
    body = _result_clean_calendar_payload(raw)
    matches = []
    for line in body.splitlines():
        match = _RESULT_CALENDAR_DATE.match(line.strip())
        if not match:
            continue
        year, month, day, start, end, name = match.groups()
        # Validate the date and times; never manufacture an event time.
        try:
            datetime(int(year), int(month), int(day))
            for clock in (start, end):
                hour, minute = [int(x) for x in clock.split(':')]
                if hour > 23 or minute > 59:
                    raise ValueError('invalid time')
        except (ValueError, TypeError):
            continue
        name = name.strip(' \t:：-—')
        if not name:
            name = '未命名日程'
        matches.append({
            'title': name[:200],
            'time': '{}月{}日 · {}—{}'.format(int(month), int(day), start, end),
            'year': str(year),
        })
    advertised = _RESULT_CALENDAR_COUNT.search(body)
    count = int(advertised.group(1)) if advertised else None
    # Keep unparsed data visible, instead of claiming no events.
    unparsed = not matches and bool(body) and not (
        count == 0 or '没有日程' in body or '无日程' in body or '未查询到' in body)
    return {'rows': matches, 'declared_count': count, 'raw': body,
            'unparsed': unparsed}


def _result_safe_text(value, max_chars=9000):
    if value is None:
        return ''
    if isinstance(value, str):
        return value[:max_chars]
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:max_chars]
    except (TypeError, ValueError):
        return str(value)[:max_chars]


def _result_card_model(state):
    """Only end-user information; technical execution details stay in history."""
    if not isinstance(state, dict):
        state = {}
    status = str(state.get('status') or '')
    events = [e for e in state.get('events', []) if isinstance(e, dict)] if isinstance(state.get('events'), list) else []
    calendar = next((e for e in reversed(events) if e.get('tool') == 'calendar.list'), None)
    # Calendar-assisted analysis can contain further work/insights. Do not
    # replace its final analysis with only the raw event-list preview.
    if state.get('research_origin') == 'calendar.assist' and status == 'finished':
        result = _result_safe_text(state.get('final'), 11000) or '日程分析已结束。'
        return {'kind':'analysis', 'title':'日程分析结果',
                'subtitle':'已完成日历查询后的分析',
                'items':[], 'body':result,
                'notice':'日历内容来自只读快捷指令；操作效果需另行核验。',
                'copy':result, 'status':status, 'more':0}
    if calendar is not None and calendar.get('status') == 'ok' and status == 'finished':
        data = _result_parse_calendar(calendar.get('result'))
        count = len(data['rows'])
        declared = data['declared_count']
        if data['unparsed']:
            subtitle = '已收到日历查询结果'
        elif declared is not None and declared != count:
            subtitle = '日程返回数量与解析数量不同，请查看原始内容'
        else:
            subtitle = '查询到 {} 项日程'.format(count)
        return {
            'kind': 'calendar', 'title': '日历查询完成', 'subtitle': subtitle,
            'items': data['rows'][:_RESULT_EVENT_LIMIT],
            'body': data['raw'] if (data['unparsed'] or declared is not None and declared != count) else '',
            'notice': '来自日历只读快捷指令，尚未独立核验。',
            'copy': ('\n\n'.join('{}\n{}'.format(i['title'],i['time'])
                                  for i in data['rows'])
                     if data['rows'] and not data['unparsed'] and
                        (declared is None or declared == count) else data['raw']),
            'status': 'ok',
            'more': max(0, len(data['rows']) - _RESULT_EVENT_LIMIT),
        }
    errors = any(e.get('status') in ('failed','needs_review','error') for e in events)
    if status in ('needs_review', 'failed', 'paused', 'needs_input', 'replan_pending') or errors:
        kind, heading = 'warning', '需要检查任务'
    elif status == 'awaiting_callback':
        kind, heading = 'pending', '等待系统操作返回'
    else:
        kind, heading = 'success', '任务处理完成'
    text_event = next((e for e in reversed(events) if e.get('tool') == 'text.respond'
                       and e.get('status') == 'ok'), None)
    if text_event is not None:
        body = _result_safe_text(text_event.get('result'), 11000)
    else:
        body = _result_safe_text(state.get('final') or state.get('error'), 11000)
    if not body:
        body = '暂无可显示的结果。请到「执行结果」查看任务状态。'
    uncertain = any(e.get('status') in ('handoff', 'waiting', 'awaiting_callback') or
                    (e.get('tool') in ('calendar.create','apple_notes.create',
                                      'shortcut.run','app.navigate','maps.search') and
                     e.get('verified') is not True)
                    for e in events)
    return {
        'kind': kind, 'title': heading,
        'subtitle': ('操作已发起，实际结果尚待核验' if uncertain else
                     '以下是本次任务结果'),
        'items': [], 'body': body,
        'notice': ('跨 App 操作需到目标应用核对。' if uncertain else
                   '完整执行记录保存在本机「历史档案」。'),
        'copy': body, 'status': status, 'more': 0,
    }


def _result_ui_show(state):
    """Present a native, theme-matched result sheet, not a console dump."""
    model = _result_card_model(state)
    try:
        import ui
    except ImportError:
        # Pythonista native UI is mandatory for the card; fallback below is
        # intentionally still user-readable rather than a technical log.
        import dialogs
        dialogs.alert(model['title'], model['copy'][:650] or model['subtitle'],
                      '完成', hide_cancel_button=True)
        return model

    appearance = _card_appearance_load()
    palette = _card_palette(appearance)
    width, height = ui.get_screen_size()
    margin = 18 if width < 560 else min(48, width * 0.07)
    body_width = max(250, width - margin * 2)

    class ResultView(ui.View):
        def __init__(self):
            ui.View.__init__(self, frame=(0, 0, width, height))
            self.background_color = palette['background']
            self.flex = 'WH'
            self.last_size = None
            self._build()

        def label(self, host, content, frame, size=14, color=None, bold=False, lines=1):
            widget = ui.Label(frame=frame)
            widget.text = str(content)
            widget.font = ('HelveticaNeue-Bold' if bold else 'HelveticaNeue', size)
            widget.text_color = color or palette['text']
            widget.number_of_lines = lines
            widget.background_color = (0, 0, 0, 0)
            host.add_subview(widget)
            return widget

        def panel(self, host, y, height, fill=None):
            v = ui.View(frame=(0, y, host.width, height))
            v.background_color = fill or palette['surface']
            v.corner_radius = 16
            host.add_subview(v)
            return v

        def button(self, title, frame, func, prominent=False):
            button = ui.Button(frame=frame)
            button.title = title
            button.font = ('HelveticaNeue-Bold', 15)
            button.corner_radius = 12
            button.tint_color = palette['light'] if prominent else palette['text']
            button.background_color = palette['accent'] if prominent else palette['raised']
            button.action = func
            self.add_subview(button)
            return button

        def dismiss(self, sender):
            self.close()

        def copy_text(self, sender):
            try:
                import clipboard
                clipboard.set(model['copy'])
                import console
                console.hud_alert('结果已复制', 'success', 1.2)
            except Exception:
                self.label(self, '复制不可用，请使用历史档案。',
                           (margin, height-142, body_width, 25), 12, palette['negative'])

        def _build(self):
            w, h = float(self.width), float(self.height)
            side = 18 if w < 560 else min(48, w * 0.07)
            content_w = w - side * 2
            # Result view follows the existing full-screen card design.
            self.label(self, 'PYVoiceAgent', (side, 54, content_w-90, 26),
                       17, palette['muted'], bold=True)
            self.label(self, model['title'], (side, 94, content_w, 38),
                       25, palette['text'], bold=True)
            self.label(self, model['subtitle'], (side, 137, content_w, 29),
                       13, palette['muted'])
            scroll_y = 181
            footer_h = 111
            viewport = max(160, h-scroll_y-footer_h)
            scroll = ui.ScrollView(frame=(side, scroll_y, content_w, viewport))
            scroll.flex = 'WH'
            scroll.background_color = palette['background']
            scroll.shows_vertical_scroll_indicator = True
            self.add_subview(scroll)
            y = 0
            if model['kind'] == 'calendar' and model['items']:
                for item in model['items']:
                    cell = self.panel(scroll, y, 105)
                    self.label(cell, item['title'], (15, 11, content_w-30, 49),
                               17, palette['text'], bold=True, lines=2)
                    self.label(cell, item['time'], (15, 68, content_w-30, 24),
                               14, palette['muted'])
                    y += 117
                if model['more']:
                    self.label(scroll, '另有 {} 项，请复制查看完整内容'.format(model['more']),
                               (4, y+4, content_w-8, 30), 12, palette['muted'])
                    y += 41
            else:
                # Long results have their own scrolling text view; do not
                # duplicate the same report in multiple panels.
                text = model['body'] or '没有日程。'
                pane_h = min(450, max(142, viewport-78))
                panel = self.panel(scroll, y, pane_h)
                reader = ui.TextView(frame=(10, 10, content_w-20, pane_h-20))
                reader.text = text
                reader.editable = False
                reader.text_color = palette['text']
                reader.background_color = palette['surface']
                reader.font = ('HelveticaNeue', 15)
                panel.add_subview(reader)
                y += pane_h+13
            self.label(scroll, model['notice'], (4, y+8, content_w-8, 53),
                       12, palette['muted'], lines=2)
            scroll.content_size = (content_w, max(viewport+1, y+76))
            button_y = h-100
            self.button('复制结果', (side, button_y, content_w*.45, 46), self.copy_text)
            self.button('完成', (side+content_w*.49, button_y, content_w*.51, 46),
                        self.dismiss, prominent=True)

    view = ResultView()
    view.present('full_screen', hide_title_bar=True)
    view.wait_modal()
    return model


_V199_FINAL_REPORT = final_report


def final_report(state, show_dialog=True):
    """Use app-style card for completed callbacks; keep debug info in history."""
    if not show_dialog:
        # Navigation handoffs must not block the target App with a result modal.
        return
    try:
        _result_ui_show(state)
    except Exception as error:
        # Safe, readable fallback; original technical report remains accessible
        # from history rather than spilling a long stack into the main console.
        print('结果卡片未能显示：{}: {}'.format(type(error).__name__, str(error)[:140]))
        try:
            import dialogs
            model = _result_card_model(state)
            dialogs.alert(model['title'], model['copy'][:650] or model['subtitle'],
                          '完成', hide_cancel_button=True)
        except Exception:
            pass
    if state.get('voice_session'):
        _voice_report(state)