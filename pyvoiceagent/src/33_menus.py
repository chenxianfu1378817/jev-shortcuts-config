def waiting_for_shortcut():
    if get_state().get('status') == 'awaiting_callback':
        print('已移交快捷指令，菜单退出以允许回调运行。')
        return True
    return False
def show_text_menu():
    import dialogs
    while True:
        choice = dialogs.list_dialog('输入方式', list(TEXT_MENU))
        if not choice or choice.startswith('4.'):
            return
        if choice.startswith('1.'):
            text = ask_text('输入任务')
            if text:
                start_new(text)
                return True
        elif choice.startswith('2.'):
            import clipboard
            text = clipboard.get()
            if not text:
                print('剪贴板没有可用文字。')
            else:
                start_new(text)
                return True
        elif choice.startswith('3.'):
            _cc_import_clipboard()
            return True
        if waiting_for_shortcut():
            return True
def show_tool_status():
    print('系统工具：')
    for key, tool in DEFAULT_LIBRARY.items():
        if tool['tool'] in SYSTEM_MODULES:
            status = ('已验收启用' if verified_system_module(tool['tool'])
                      else '未启用（在“更多与设置”完成首次验证）')
        else:
            status = '兼容工具'
        print('  {} → {} [{}]'.format(key, tool['description'], status))
    print('自定义工具：')
    for key, tool in local_registry().items():
        print('  {} → {}：{}'.format(key, tool['name'], tool['description']))
def resume_old_task():
    old = get_state()
    if old.get('status') in ('needs_input','replan_pending'):
        return resume_clarification(old)
    if old.get('status') == 'paused':
        execute_planned_actions(old) if old.get('single_plan') else drive_agent(old)
    elif old.get('status') == 'awaiting_callback':
        print('正在等待快捷指令回传；请返回快捷指令完成操作。')
    elif old.get('status') == 'needs_review':
        print('存在待核验事项。请先使用“查看待核验项目”，不要重复执行。')
    else:
        print('没有暂停的任务。')
def show_advanced_menu():
    import dialogs
    while True:
        choice = dialogs.list_dialog('高级操作 · 非日常使用', list(ADVANCED_MENU))
        if not choice or choice.startswith('10.'):
            return
        if choice.startswith('1.'):
            resume_old_task()
        elif choice.startswith('2.'):
            old = get_state()
            if old.get('status') in ('awaiting_callback', 'needs_review') and old.get('pending'):
                review_pending()
            else:
                review_deferred_queue()
        elif choice.startswith('3.'):
            add_shortcut_registration()
        elif choice.startswith('4.'):
            txt = ask_text('复杂任务：逐步 AI（耗费更多 Token）')
            if txt:
                start_new(txt, force_stepwise=True)
        elif choice.startswith('5.'):
            test_deepseek_connection()
        elif choice.startswith('6.'):
            start_bridge_diagnostic('shortcut.hub_echo')
        elif choice.startswith('7.'):
            start_bridge_diagnostic('apple_notes.create')
        elif choice.startswith('8.'):
            print('系统快捷指令：{}；旧版：{}'.format(BRIDGE_SHORTCUT, LEGACY_BRIDGE))
            print('匹配 token 的回传入口：')
            print('pythonista3://iCloud/PYVoiceAgent.py?action=run&argv=bridge_callback&argv=')
            print('回传 token 必须与参数一致；status 仅允许 ok/failed/cancelled。')
        elif choice.startswith('9.'):
            state = get_state()
            if state.get('pending') and state.get('status') in (
                    'awaiting_callback', 'needs_review', 'writing'):
                print('待核验操作不能清除，请先到苹果 App 检查。')
            elif prompt_alert('清除当前任务',
                    '仅清除任务状态/执行记录，不删除笔记、录音和 Key。确认？'):
                if os.path.isfile(STATE_PATH):
                    os.remove(STATE_PATH)
                print('当前任务已清除。')
        if waiting_for_shortcut():
            return
def show_settings_menu():
    import dialogs
    while True:
        choice = dialogs.list_dialog('更多与设置', list(SETTINGS_MENU))
        if not choice or choice.startswith('7.'):
            return
        if choice.startswith('1.'):
            show_tool_status()
        elif choice.startswith('2.'):
            set_ai_credentials()
        elif choice.startswith('3.'):
            print_update_status()
        elif choice.startswith('4.'):
            install_system_module()
        elif choice.startswith('5.'):
            show_advanced_menu()
        elif choice.startswith('6.'):
            _voice_privacy_controls()
        if waiting_for_shortcut():
            return
def show_menu():
    import dialogs
    while True:
        try:
            choice = dialogs.list_dialog(
                'PYVoiceAgent V{} · DeepSeek Flash'.format(VERSION.split('-')[0]), list(MAIN_MENU))
            if not choice:
                return
            if choice.startswith('1.'):
                global VOICE_SESSION_ACTIVE
                VOICE_SESSION_ACTIVE = True
                txt = input_voice(hands_free=True)
                if txt:
                    start_new(txt)
                    return
            elif choice.startswith('2.'):
                if show_text_menu():
                    return  # A submitted task owns execution; do not reopen menus.
            elif choice.startswith('3.'):
                saved=get_state()
                pretty_status(saved)
                if saved.get('status') in ('needs_input','replan_pending'):
                    if prompt_alert('继续刚才的对话', '原任务未执行完毕。是否继续补充回答？', ok='继续', cancel='稍后'):
                        resume_clarification(saved)
                    return
                if retry_last_readonly_calendar(saved):
                    return  # The read-only callback now owns this task.
            elif choice.startswith('4.'):
                if update_from_menu():
                    return  # Do not keep the old engine alive after installing another.
            elif choice.startswith('5.'):
                show_settings_menu()
        except KeyboardInterrupt:
            print('用户取消了当前操作。')
        except Exception as ex:
            print('发生错误：{}: {}'.format(type(ex).__name__, ex))
            traceback.print_exc()
        if waiting_for_shortcut():
            return
import re
