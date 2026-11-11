def start_new(goal, force_stepwise=False):
    goal = str(goal or '').strip()
    if not goal:
        print('没有识别到任务文字。')
        return None
    if len(goal) > 2000:
        print('任务文字过长，请先简化（最多 2000 字）。')
        return None
    old_dialogue = get_state()
    if not force_stepwise and old_dialogue.get('status') in ('needs_input','replan_pending'):
        if goal in ('继续对话','继续刚才的任务','继续上次任务','回答刚才的问题'):
            return resume_clarification(old_dialogue)
        if VOICE_SESSION_ACTIVE and old_dialogue.get('status') == 'needs_input':
            if goal in ('取消任务','取消刚才的任务','停止本次任务','暂停本次任务','稍后继续'):
                if goal == '稍后继续':
                    old_dialogue['status'] = 'needs_input'
                else:
                    old_dialogue['status'] = 'paused'
                old_dialogue['error'] = '用户语音请求暂停本次问答；无任何新系统写入。'
                put_state(old_dialogue)
                _voice_speak('已暂停当前任务。')
                return old_dialogue
            if goal.startswith(('新任务：','新任务，','开始新任务：','开始新任务，')):
                goal = goal.split('：',1)[-1] if '：' in goal else goal.split('，',1)[-1]
                if not goal.strip():
                    _voice_speak('请再说出新任务内容。')
                    return old_dialogue
            else:
                return resume_clarification(old_dialogue, initial_answer=goal)
        if old_dialogue.get('status') == 'needs_input':
            msg = ('之前的任务：' + old_dialogue.get('goal','')[:110]
                   + '\\nAI的问题：' + old_dialogue.get('clarify_question','')[:130]
                   + '\\n本次输入：' + goal[:100]
                   + '\\n将本次内容作为上个问题的回答吗？')
            if prompt_alert('继续未完成的对话', msg, ok='作为回答', cancel='开始新任务'):
                return resume_clarification(old_dialogue, initial_answer=goal)
        else:
            if prompt_alert('上次回答等待 AI 规划',
                    '上次回答已保存，但规划尚未完成。先重试原任务吗？',
                    ok='继续原任务', cancel='开始新任务'):
                return resume_clarification(old_dialogue)
    if _cc_trigger(goal):
        return _cc_import_clipboard()
    if not force_stepwise:
        build=_sb_generate_from_speech(goal)
        if build is not None:
            return build
        capture=_maybe_auto_work_plan(goal)
        if capture is not None:
            return capture
    if not force_stepwise:
        quick_result=_local_or_ai_dispatch(goal)
        if quick_result is not None:
            return quick_result
    if not api_key():
        print('尚未配置 DeepSeek API Key。请先打开菜单 → 设置 DeepSeek AI。')
        return None
    current = get_state()
    if current.get('status') in ('awaiting_callback', 'needs_review', 'writing'):
        try:
            defer_current_pending(current)
        except (ValueError, OSError, RuntimeError) as ex:
            print('无法安全归档未完成任务，保留原状：' + str(ex))
            return None
        print('未完成的旧写入已归档，不会自动重复执行，可继续其他任务。')
    if current.get('status') in ('running', 'paused'):
        if not prompt_alert('已有未完成任务', '创建新任务将结束当前未完成任务，继续吗？'):
            return None
    state = {'id': uuid.uuid4().hex[:12], 'goal': goal, 'created': now_iso(),
             'status': 'ready', 'steps': 0, 'events': [], 'pending': None,
             'voice_session': bool(VOICE_SESSION_ACTIVE),
             'final': '', 'error': ''}
    if not _voice_authorize_ai(state):
        return None
    try:
        reminder_seed_prior_state(current)
    except (OSError, RuntimeError) as ex:
        print('历史提醒的防重复记录无法保存；为避免重建重复项，新任务已取消：' + str(ex)[:150])
        return None
    put_state(state)
    return drive_agent(state) if force_stepwise else plan_once(state)
def input_voice(hands_free=False, prompt=None):
    import speech
    ensure_dirs()
    path = os.path.join(DATA_DIR,
        'voice_{}_{}.m4a'.format(datetime.now().strftime('%Y%m%d_%H%M%S'), uuid.uuid4().hex[:6]))
    try:
        print('手动录音：说完请点击「完成」停止录音。')
        status = _manual_voice_record(path)
        if status != 'recorded' or not os.path.isfile(path) or os.path.getsize(path) < 100:
            print('录音为空或无法识别；本次不执行任务。')
            return None
        langs = speech.get_recognition_languages()
        lang = next((x for x in langs if x.lower().replace('_', '-') in ('zh-cn','zh-hans-cn')), None)
        results = speech.recognize(path, lang) if lang else speech.recognize(path)
        if not results or not results[0][0].strip():
            print('没有识别出有效文字；未执行新任务。')
            return None
        spoken = results[0][0].strip()
        print('识别结果：{}'.format(spoken))
        if hands_free:
            return spoken
        edited = ask_text('核对语音（可修改错字）', spoken)
        return edited.strip() if edited is not None else None
    except (Exception, KeyboardInterrupt) as exc:
        print('语音识别失败，未执行新操作：' + str(exc)[:160])
        return None
    finally:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
def review_deferred_queue():
    queue = read_recovery_queue()
    unresolved = [(i, x) for i, x in enumerate(queue) if x.get('resolved') is not True]
    if not unresolved:
        print('没有历史待核验写入，无需处理。')
        return
    import dialogs
    options = ['{} · {}'.format(x.get('tool', ''), x.get('title', '')[:40])
               for _, x in unresolved]
    selected = dialogs.list_dialog('历史待核验项目（选择一项）', options)
    if selected not in options:
        return
    index, pending = unresolved[options.index(selected)]
    actions = ['已经打开苹果 App，确认该项目存在',
               '已经打开苹果 App，确认该项目不存在',
               '暂时无法确认']
    action = dialogs.list_dialog('请核对后选择', actions)
    if action not in actions[:2]:
        return
    if not prompt_alert('确认人工结论',
                        '仅记录你已经亲自核实的事实，不会重新创建或删除任何项目。'):
        return
    current = read_recovery_queue()
    token = str(pending.get('token', ''))
    found = False
    for row in current:
        if str(row.get('token', '')) == token and row.get('resolved') is not True:
            row['resolved'] = True
            row['status'] = 'confirmed_exists' if action == actions[0] else 'confirmed_absent'
            row['resolved_at'] = now_iso()
            found = True
            break
    if not found:
        print('记录已经处理或更新，未重复更改。')
        return
    atomic_json(RECOVERY_QUEUE_PATH, current)
    print('核验结论已保存；不会自动重复执行原操作。')
UPDATE_RELEASE_ROOT = (
    'https://raw.githubusercontent.com/chenxianfu1378817/jev-shortcuts-config/main/pyvoiceagent')
UPDATE_META_PATH = os.path.join(DATA_DIR, 'update_meta.json')
UPDATE_ENGINE_DIR = os.path.join(DATA_DIR, 'engine')
