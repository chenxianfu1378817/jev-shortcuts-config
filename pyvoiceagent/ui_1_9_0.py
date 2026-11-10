# --- PYVoiceAgent V1.9.0: modern unified card UI extension ---
# This is embedded in the released single-file engine by the publisher.
# The verified V1.8.5 native/AI/Shortcuts backend remains unchanged.

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


def _card_hex(value):
    if not isinstance(value, str):
        return ''
    value = value.strip().upper()
    return value if re.fullmatch(r'#[0-9A-F]{6}', value) else ''


def _card_appearance_load():
    raw = read_json(APPEARANCE_PATH, {})
    result = dict(_CARD_DEFAULTS)
    if isinstance(raw, dict):
        if raw.get('theme') in CARD_THEMES:
            result['theme'] = raw['theme']
        if raw.get('mode') in DISPLAY_MODES:
            result['mode'] = raw['mode']
        result['custom_color'] = _card_hex(raw.get('custom_color', ''))
    return result


def _card_appearance_save(appearance):
    data = dict(_CARD_DEFAULTS)
    if appearance.get('theme') in CARD_THEMES:
        data['theme'] = appearance['theme']
    if appearance.get('mode') in DISPLAY_MODES:
        data['mode'] = appearance['mode']
    data['custom_color'] = _card_hex(appearance.get('custom_color', ''))
    atomic_json(APPEARANCE_PATH, data)
    return data


def _card_system_dark():
    try:
        from objc_util import ObjCClass
        app = ObjCClass('UIApplication').sharedApplication()
        window = app.keyWindow()
        return int(window.traitCollection().userInterfaceStyle()) == 2
    except Exception:
        return False


def _card_palette(appearance, system_dark=None):
    if system_dark is None:
        system_dark = _card_system_dark()
    dark = appearance.get('mode') == '深色模式' or (appearance.get('mode') == '跟随系统' and system_dark)
    accent = _card_hex(appearance.get('custom_color')) or CARD_THEMES.get(
        appearance.get('theme'), CARD_THEMES['活力橙'])
    if dark:
        return dict(accent=accent, background='#101319', surface='#1C222C',
                    raised='#252C38', text='#F3F5FA', muted='#ABB3C1',
                    border='#343D4B', negative='#F57C85', light='#FFFFFF', dark=True)
    return dict(accent=accent, background='#F5F6FA', surface='#FFFFFF',
                raised='#EFF2F7', text='#172032', muted='#647084',
                border='#E3E8EF', negative='#D34550', light='#FFFFFF', dark=False)


def _card_task_snapshot():
    try:
        s = get_state()
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def _card_tool_rows(filter_text=''):
    rows = []
    try:
        for key, description in TOOL_CATALOG.items():
            rows.append((key, str(description)))
        for key, item in local_registry().items():
            rows.append((str(key), str(item.get('description', '已登记快捷指令'))))
    except Exception:
        pass
    needle = filter_text.strip().lower()
    if needle:
        rows = [r for r in rows if needle in (r[0] + ' ' + r[1]).lower()]
    return rows


def _card_nav_items(page):
    if page == 'home':
        return [
            ('voice', '语音执行', '一句话交代工作与生活任务', '主要入口'),
            ('input', '文字任务', '输入指令并让 AI 规划执行', ''),
            ('clipboard', '处理剪贴板', '整理复制的公告、文字和资料', ''),
            ('status', '执行结果', '查看状态、历史及待处理事项', ''),
            ('update', '检查在线更新', '从 GitHub 校验并获取新版本', ''),
            ('settings_page', '设置与工具', '主题、模型、模块及高级设置', ''),
        ]
    if page == 'settings':
        return [
            ('appearance_page', '外观与主题', '八种配色、系统/浅色/深色', ''),
            ('ai_settings', 'DeepSeek AI 配置', '安全管理 API Key', ''),
            ('voice_privacy', '语音隐私与授权', '设置是否将语音文本送给 AI', ''),
            ('tools_page', '工具库', '搜索与查看已登记操作', ''),
            ('module_setup', '系统模块首次验收', '验证需要授权的快捷指令', ''),
            ('advanced_page', '高级与故障排查', '诊断、恢复及安全记录', ''),
        ]
    if page == 'advanced':
        return [
            ('resume', '继续暂停任务', '不重放已经写入的操作', ''),
            ('review', '核验待处理任务', '人工处理可能已执行的操作', ''),
            ('add_shortcut', '登记快捷指令', '仅允许已授权的工具', ''),
            ('stepwise', 'AI 逐步执行模式', '较复杂任务使用更多 Token', ''),
            ('ai_test', '测试 AI 连接', '检查模型和网络调用', ''),
            ('hub_echo', '快捷指令回传自测', '只检测往返通信', ''),
            ('notes_test', '测试创建备忘录', '可能写入一条真实测试备忘', ''),
            ('calendar_test', '测试创建日程', '可能写入一条真实测试日程', ''),
            ('clear_state', '清除当前任务状态', '不会删除个人资料或密钥', ''),
        ]
    return []


def _card_dispatch(action, payload=''):
    # Existing confirmed actions are reused to prevent functional regressions.
    if action == 'voice':
        globals()['VOICE_SESSION_ACTIVE'] = True
        text = input_voice(hands_free=True)
        if text:
            start_new(text)
        return 'handoff'
    if action == 'input':
        if payload.strip():
            start_new(payload.strip())
        return 'handoff'
    if action == 'clipboard':
        import clipboard
        text = clipboard.get()
        if text:
            start_new(text)
        else:
            print('剪贴板暂无文字。')
        return 'handoff'
    if action == 'status':
        state = _card_task_snapshot()
        pretty_status(state)
        if state.get('status') in ('needs_input', 'replan_pending'):
            if prompt_alert('继续原任务', '是否补充信息并继续？'):
                resume_clarification(state)
        elif state.get('tool') == 'calendar.list':
            retry_last_readonly_calendar(state)
        return 'stay'
    if action == 'update':
        if update_from_menu():
            return 'handoff'
    elif action == 'ai_settings':
        set_ai_credentials()
    elif action == 'voice_privacy':
        _voice_privacy_controls()
    elif action == 'module_setup':
        install_system_module()
    elif action == 'resume':
        resume_old_task()
    elif action == 'review':
        state = _card_task_snapshot()
        if state.get('pending') and state.get('status') in ('awaiting_callback', 'needs_review', 'writing'):
            review_pending()
        else:
            review_deferred_queue()
    elif action == 'add_shortcut':
        add_shortcut_registration()
    elif action == 'stepwise':
        text = ask_text('输入复杂任务')
        if text:
            start_new(text, force_stepwise=True)
            return 'handoff'
    elif action == 'ai_test':
        test_deepseek_connection()
    elif action == 'hub_echo':
        start_bridge_diagnostic('shortcut.hub_echo')
    elif action == 'notes_test':
        start_bridge_diagnostic('apple_notes.create')
    elif action == 'calendar_test':
        start_bridge_diagnostic('calendar.create')
    elif action == 'clear_state':
        state = _card_task_snapshot()
        if state.get('pending') and state.get('status') in ('awaiting_callback','needs_review','writing'):
            print('当前有待核验操作，禁止清理状态。')
        elif prompt_alert('清除当前任务', '只清除任务状态，不删除笔记、录音、联系人或密钥，确定吗？'):
            if os.path.isfile(STATE_PATH):
                os.remove(STATE_PATH)
    elif action == 'contact_import':
        _cc_import_clipboard()
        return 'handoff'
    elif action == 'check_update_status':
        print_update_status()
    if waiting_for_shortcut():
        return 'handoff'
    return 'stay'


    elif action == 'resume':
        resume_old_task()
    elif action == 'review':
        state = _card_task_snapshot()
        if state.get('pending') and state.get('status') in ('awaiting_callback', 'needs_review', 'writing'):
            review_pending()
        else:
            review_deferred_queue()
    elif action == 'add_shortcut':
        add_shortcut_registration()
    elif action == 'stepwise':
        text = ask_text('输入复杂任务')
        if text:
            start_new(text, force_stepwise=True)
            return 'handoff'
    elif action == 'ai_test':
        test_deepseek_connection()
    elif action == 'hub_echo':
        start_bridge_diagnostic('shortcut.hub_echo')
    elif action == 'notes_test':
        start_bridge_diagnostic('apple_notes.create')
    elif action == 'calendar_test':
        start_bridge_diagnostic('calendar.create')
    elif action == 'clear_state':
        state = _card_task_snapshot()
        if state.get('pending') and state.get('status') in ('awaiting_callback','needs_review','writing'):
            print('当前有待核验操作，禁止清理状态。')
        elif prompt_alert('清除当前任务', '只清除任务状态，不删除笔记、录音、联系人或密钥，确定吗？'):
            if os.path.isfile(STATE_PATH):
                os.remove(STATE_PATH)
    elif action == 'contact_import':
        _cc_import_clipboard()
        return 'handoff'
    elif action == 'check_update_status':
        print_update_status()
    if waiting_for_shortcut():
        return 'handoff'
    return 'stay'


def _card_ui_show():
    try:
        import ui
    except ImportError:
        return None

    class AgentCardView(ui.View):
        def __init__(self):
            super(AgentCardView, self).__init__()
            self.name = 'PYVoiceAgent · DeepSeek Flash'
            self.background_color = '#F5F6FA'
            self.page = 'home'
            self.search_text = ''
            self.appearance = _card_appearance_load()
            self.result = None
            self._last_dims = (0, 0)
            self.flex = 'WH'

        def layout(self):
            dimensions = (int(self.width), int(self.height))
            if dimensions != self._last_dims and all(dimensions):
                self._last_dims = dimensions
                self._render()

        def _label(self, parent, text, x, y, width, height, size=14,
                   weight=False, color=None, align=ui.ALIGN_LEFT, lines=1):
            label = ui.Label(frame=(x, y, max(1, width), height))
            label.text = str(text)
            label.text_color = color or self.palette['text']
            label.font = ('HelveticaNeue-Bold' if weight else 'HelveticaNeue', size)
            label.alignment = align
            label.number_of_lines = lines
            label.background_color = 'clear'
            parent.add_subview(label)
            return label

        def _button(self, parent, title, x, y, width, height, handler,
                    emphasis=False, color=None, size=14):
            b = ui.Button(frame=(x, y, max(1, width), height))
            b.title = title
            b.font = ('HelveticaNeue-Bold', size)
            b.background_color = color or (self.palette['accent'] if emphasis else self.palette['raised'])
            b.tint_color = self.palette['light'] if emphasis else self.palette['text']
            b.corner_radius = 13
            b.action = handler
            parent.add_subview(b)
            return b

        def _panel(self, parent, x, y, w, h, alternate=False):
            surface = ui.View(frame=(x, y, w, h))
            surface.background_color = self.palette['raised'] if alternate else self.palette['surface']
            surface.corner_radius = 18
            surface.flex = 'W'
            parent.add_subview(surface)
            return surface

        def _link(self, action, payload=''):
            def handler(sender):
                self.result = (action, payload)
                self.close()
            return handler

        def _navigate(self, page):
            def handler(sender):
                self.page = page
                self._render()
            return handler

        def _choose_theme(self, name):
            def handler(sender):
                self.appearance['theme'] = name
                self.appearance['custom_color'] = ''
                _card_appearance_save(self.appearance)
                self._render()
            return handler

        def _choose_mode(self, name):
            def handler(sender):
                self.appearance['mode'] = name
                _card_appearance_save(self.appearance)
                self._render()
            return handler

        def _custom_color(self, sender):
            try:
                import dialogs
                raw = dialogs.text_dialog('自定义主题色', self.appearance.get('custom_color') or '#F07828')
                if raw is None:
                    return
                color = _card_hex(raw)
                if not color:
                    dialogs.alert('颜色无效', '请输入 #RRGGBB，例如 #E66B28。', '确定', hide_cancel_button=True)
                    return
                self.appearance['custom_color'] = color
                _card_appearance_save(self.appearance)
                self._render()
            except Exception as error:
                print('保存主题色失败：{}'.format(error))

        def _search_changed(self, sender):
            self.search_text = sender.text or ''
            # Do not reconstruct a currently editing TextField (keyboard lifecycle).

        def _search_apply(self, sender):
            field = getattr(self, "search_field", None)
            if field is not None:
                self.search_text = field.text or ""
            self._render()

        def _submit_text(self, sender):
            text = (self.input_view.text or '').strip()
            if not text:
                return
            self.result = ('input', text)
            self.close()

        def _render(self):
            if self.width < 100 or self.height < 200:
                return
            for sub in list(self.subviews):
                self.remove_subview(sub)
            self.palette = _card_palette(self.appearance)
            P = self.palette
            self.background_color = P['background']
            width = float(self.width)
            side = 18 if width < 560 else min(46, width * 0.07)
            content_width = width - side * 2
            top = 50  # preserve space for iOS notch/status bar on fullscreen

            self._label(self, 'PYVoiceAgent', side, top, content_width - 64, 34,
                        size=26, weight=True)
            self._label(self, 'V1.9.0 · DeepSeek Flash', side, top + 33,
                        content_width, 20, size=12, color=P['muted'])
            self._button(self, '关闭', width-side-64, top+2, 64, 36, self._link('exit'))
            y = top + 74
            if self.page != 'home':
                self._button(self, '‹ 返回', side, y, 82, 38, self._navigate('home'))
                self._label(self, {'settings': '设置中心', 'appearance': '外观与主题',
                     'tools': '工具库', 'advanced': '高级操作', 'history': '执行记录',
                     'input': '文字任务'}.get(self.page, self.page), side+96,
                     y, content_width-105, 38, size=21, weight=True)
                y += 56

            viewport = max(160, self.height-y-24)
            scroll = ui.ScrollView(frame=(side, y, content_width, viewport))
            scroll.background_color = P['background']
            scroll.shows_vertical_scroll_indicator = True
            scroll.flex = 'WH'
            self.add_subview(scroll)
            cursor = 2

            def desc_block(title, desc, height=96, action=None, badge=''):
                nonlocal cursor
                block = self._panel(scroll, 0, cursor, content_width, height)
                self._label(block, title, 17, 13, content_width-34, 29,
                            size=17, weight=True)
                self._label(block, desc, 17, 45, content_width-34,
                            max(29, height-51), size=12, color=P['muted'], lines=2)
                if badge:
                    self._label(block, badge, content_width-78, 14, 60, 24,
                                size=11, color=P['accent'], align=ui.ALIGN_RIGHT)
                if action:
                    btn = ui.Button(frame=(0, 0, content_width, height))
                    btn.background_color = 'clear'
                    btn.action = action
                    block.add_subview(btn)
                cursor += height + 11

            if self.page == 'home':
                state = _card_task_snapshot()
                status = str(state.get('status', '未开始'))
                block = self._panel(scroll, 0, cursor, content_width, 102, alternate=True)
                self._label(block, '一句话，执行多个任务', 16, 12,
                            content_width-32, 32, size=19, weight=True)
                self._label(block, '语音识别 · AI 规划 · 逐步执行 · 状态核验',
                            16, 50, content_width-32, 23, size=12, color=P['muted'])
                self._label(block, '当前任务：' + status[:18], 16, 76,
                            content_width-32, 20, size=11, color=P['accent'])
                cursor += 116
                for key, title, desc, badge in _card_nav_items('home'):
                    destination = {'input':'input', 'status':'history',
                                   'settings_page':'settings'}.get(key)
                    desc_block(title, desc, action=(self._navigate(destination) if destination
                               else self._link(key)), badge=badge)
            elif self.page == 'input':
                desc_block('输入任务', '例如：读取剪贴板里的招标公告，提取截止日期并创建提醒', height=96)
                block = self._panel(scroll, 0, cursor, content_width, 218)
                view = ui.TextView(frame=(14, 12, content_width-28, 142))
                view.text = ''
                view.font = ('HelveticaNeue', 16)
                view.background_color = P['raised']
                view.text_color = P['text']
                view.corner_radius = 12
                block.add_subview(view)
                self.input_view = view
                self._button(block, '交给 AI 处理', 14, 168, content_width-28,
                             40, self._submit_text, emphasis=True)
                cursor += 232
                desc_block('其他文字输入', '可直接读取剪贴板，或把剪贴板里的联系人资料导入通讯录', height=85)
                self._button(scroll, '分析剪贴板', 0, cursor, content_width*.48, 45,
                             self._link('clipboard'))
                self._button(scroll, '导入联系人', content_width*.52, cursor,
                             content_width*.48, 45, self._link('contact_import'))
                cursor += 59
            elif self.page == 'history':
                state = _card_task_snapshot()
                title = str(state.get('goal', '尚无记录'))
                desc_block('任务状态：'+str(state.get('status', '未开始')),
                           title[:120], height=106)
                for event in list(state.get('events') or [])[-12:]:
                    if isinstance(event, dict):
                        desc_block(str(event.get('tool', '工具')) + ' · ' +
                                   str(event.get('status', '未知')),
                                   str(event.get('result', event.get('message', '')))[:140], height=82)
                self._button(scroll, '继续暂停任务', 0, cursor, content_width*.48, 46,
                             self._link('resume'), emphasis=True)
                self._button(scroll, '核验待处理项', content_width*.52, cursor,
                             content_width*.48, 46, self._link('review'))
                cursor += 60
                self._button(scroll, '详细执行报告', 0, cursor, content_width, 46,
                             self._link('status'))
                cursor += 58
            elif self.page == 'settings':
                for key, title, desc, badge in _card_nav_items('settings'):
                    destination = {'appearance_page': 'appearance',
                                   'tools_page': 'tools',
                                   'advanced_page': 'advanced'}.get(key)
                    desc_block(title, desc,
                               action=(self._navigate(destination) if destination
                                       else self._link(key)))
            elif self.page == 'appearance':
                desc_block('统一主题', '修改后首页、子页面、输入框和卡片即时同步换色', height=84)
                for i, (name, color) in enumerate(CARD_THEMES.items()):
                    row = i//2
                    col = i%2
                    h = 61
                    yy = cursor+row*(h+8)
                    x = col*(content_width*.5)
                    pad = 4
                    w = content_width*.5-8
                    card = self._panel(scroll, x+pad, yy, w, h)
                    circle = ui.View(frame=(12, 15, 28, 28))
                    circle.corner_radius = 14
                    circle.background_color = color
                    card.add_subview(circle)
                    label_width = w-55
                    self._label(card, name, 48, 14, label_width, 30,
                                size=13, weight=(self.appearance['theme']==name))
                    b = ui.Button(frame=(0, 0, w, h))
                    b.background_color = 'clear'
                    b.action = self._choose_theme(name)
                    card.add_subview(b)
                cursor += 4*(61+8)+11
                desc_block('显示模式', '选择系统同步或手动锁定深浅色', height=78)
                for i, mode in enumerate(DISPLAY_MODES):
                    w = (content_width-12)/3
                    self._button(scroll, mode, i*(w+6), cursor, w, 43,
                                 self._choose_mode(mode),
                                 emphasis=(self.appearance['mode']==mode), size=11)
                cursor += 59
                self._button(scroll, '自定义主题色 #RRGGBB', 0, cursor,
                             content_width, 44, self._custom_color)
                cursor += 55
                desc_block('当前效果', '颜色选择已保存在本地，程序在线更新不会覆盖。', height=80)
            elif self.page == 'tools':
                block = self._panel(scroll, 0, cursor, content_width, 99)
                field = ui.TextField(frame=(14, 12, content_width-112, 41))
                field.placeholder = '输入工具名称 / 功能关键词'
                field.background_color = P['raised']
                field.text_color = P['text']
                field.font = ('HelveticaNeue', 13)
                field.corner_radius = 10
                field.text = self.search_text
                field.action = self._search_changed
                block.add_subview(field)
                self.search_field = field
                self._button(block, '搜索', content_width-91, 12, 77, 41,
                             self._search_apply, emphasis=True)
                self._label(block, '已启用及已登记的工具（仅白名单允许调用）',
                            14, 64, content_width-25, 24, size=11, color=P['muted'])
                cursor += 111
                for key, desc in _card_tool_rows(self.search_text):
                    desc_block(key, desc[:130], height=76)
                self._button(scroll, '登记新快捷指令', 0, cursor,
                             content_width, 44, self._link('add_shortcut'), emphasis=True)
                cursor += 54
            elif self.page == 'advanced':
                for key, title, desc, badge in _card_nav_items('advanced'):
                    desc_block(title, desc, height=87, action=self._link(key))
            scroll.content_size = (content_width, max(viewport+2, cursor+16))

    width, height = ui.get_screen_size()
    root = AgentCardView()
    root.frame = (0, 0, width, height)
    root.present('fullscreen', hide_title_bar=True)
    root.wait_modal()
    return root.result or ('exit', '')


# Keep the original five-entry menu for environments where the iOS ui module
# cannot initialize. This never changes callback or fixed-entry semantics.
_V185_SHOW_MENU = show_menu


def show_menu():
    try:
        import ui
    except ImportError:
        return _V185_SHOW_MENU()
    while True:
        try:
            result = _card_ui_show()
            if result is None:
                return _V185_SHOW_MENU()
            action, payload = result
            if action == 'exit':
                return
            outcome = _card_dispatch(action, payload)
            if outcome == 'handoff' or waiting_for_shortcut():
                return
        except KeyboardInterrupt:
            print('用户取消。')
        except Exception as error:
            print('界面操作失败：{}: {}'.format(type(error).__name__, error))
            traceback.print_exc()
            try:
                import dialogs
                dialogs.alert('操作未完成', str(error)[:250], '确定', hide_cancel_button=True)
            except Exception:
                return
# --- End UI extension ---
