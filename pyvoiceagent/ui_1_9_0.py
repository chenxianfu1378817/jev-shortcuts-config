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


