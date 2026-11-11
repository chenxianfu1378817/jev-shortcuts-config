def _voice_speak(message):
    try:
        import speech
        phrase = str(message or '').strip()[:220]
        if not phrase:
            return False
        speech.say(phrase, 'zh-CN', 0.48)
        time.sleep(0.18)
        deadline = time.monotonic() + 24.0
        while speech.is_speaking():
            if time.monotonic() >= deadline:
                speech.stop()
                return False
            time.sleep(0.1)
        time.sleep(0.2)
        return True
    except (Exception, KeyboardInterrupt) as exc:
        print('语音播报不可用：' + str(exc)[:120])
        return False
def _voice_level(meters):
    if not isinstance(meters, dict):
        return None
    levels = meters.get('average')
    levels = levels if isinstance(levels, (list, tuple)) else [levels]
    good = []
    for value in levels:
        try:
            number = float(value)
            if -130.0 <= number <= 0.0:
                good.append(number)
        except (TypeError, ValueError):
            pass
    return max(good) if good else None
def _voice_record_auto(path, recorder=None):
    if recorder is None:
        import sound
        recorder = sound.Recorder(path)
    start = time.monotonic()
    heard = False
    hits = 0
    baseline = -52.0
    last_voice = start
    seen = 0
    status = 'no_speech'
    try:
        recorder.record(VOICE_LISTEN_LIMIT)
        while time.monotonic() - start < VOICE_LISTEN_LIMIT:
            if not recorder.recording:
                break
            level = _voice_level(recorder.meters)
            if level is None:
                status = 'meter_unavailable'
                break
            seen += 1
            current = time.monotonic()
            elapsed = current - start
            if not heard and level <= -39.0:
                baseline = baseline * 0.85 + level * 0.15
            threshold = max(-43.0, baseline + 9.0)
            if elapsed >= 0.18 and level >= threshold:
                hits += 1
                last_voice = current
                if hits >= 2:
                    heard = True
            elif not heard:
                hits = max(0, hits - 1)
            if heard and current - last_voice >= VOICE_END_SILENCE:
                status = 'recorded'
                break
            if not heard and elapsed >= VOICE_WAIT_FOR_START:
                status = 'no_speech'
                break
            time.sleep(VOICE_SAMPLE_INTERVAL)
        if heard and status == 'no_speech':
            status = 'recorded'
        return status if seen else 'meter_unavailable'
    finally:
        try:
            recorder.stop()
        except Exception:
            pass
def _manual_voice_record(path):
    import dialogs
    import sound
    recorder = sound.Recorder(path)
    recorder.record()
    try:
        dialogs.alert('手动录音中', '说完点击「完成」停止录音', '完成', hide_cancel_button=True)
    finally:
        recorder.stop()
    return 'recorded'
def _voice_authorize_ai(state):
    if not state.get('voice_session'):
        return prompt_alert('发送给 AI 规划',
                            '下面的目标文字将发送至 DeepSeek：\n' + state['goal'][:400])
    flags = read_json(VOICE_PRIVACY_PATH, {})
    if isinstance(flags, dict) and flags.get('voice_text_auto_share') is True:
        return True
    try:
        import dialogs
        selection = dialogs.alert('语音任务联网授权',
            '识别出的语音文字将发送给 DeepSeek 规划。今后免每次确认？'
            '（剪贴板、日历内容等仍需独立授权）',
            '以后自动发送', '仅本次允许', '不发送',
            hide_cancel_button=True)
        if selection == 1:
            atomic_json(VOICE_PRIVACY_PATH,
                        {'voice_text_auto_share': True, 'approved_at': now_iso()})
            return True
        return selection == 2
    except KeyboardInterrupt:
        return False
def _voice_privacy_controls():
    import dialogs
    allowed = read_json(VOICE_PRIVACY_PATH, {}).get('voice_text_auto_share') is True
    print('语音联网自动授权：' + ('已启用' if allowed else '未启用'))
    choices = ('启用自动发送语音文字', '关闭自动发送（下次再询问）', '返回')
    selected = dialogs.list_dialog('语音文字 AI 授权', list(choices))
    if selected == choices[0]:
        if not prompt_alert('语音文字自动发送',
                '今后你主动启动语音助手后，识别出的任务文字将直接发给 DeepSeek 规划。'
                '剪贴板、日历等其他隐私内容仍需独立授权。确认启用吗？'):
            return
        atomic_json(VOICE_PRIVACY_PATH,
                    {'voice_text_auto_share': True, 'approved_at': now_iso()})
        print('已启用语音文字的自动云端规划授权。')
    elif selected == choices[1]:
        atomic_json(VOICE_PRIVACY_PATH,
                    {'voice_text_auto_share': False, 'revoked_at': now_iso()})
        print('已关闭自动发送，下次联网规划前将再次询问。')
def _voice_report(state):
    if not state.get('voice_session') or state.get('voice_report_spoken'):
        return
    state['voice_report_spoken'] = True
    put_state(state)
    events = state.get('events') or []
    if state.get('status') != 'finished':
        words = '任务已暂停，请查看屏幕提示。'
    elif any(e.get('tool') in ('app.navigate', 'maps.search') for e in events):
        words = '已向手机发出打开请求，请查看目标应用是否打开。'
    elif any(e.get('status') not in ('ok', 'blocked_duplicate') for e in events):
        words = '还有任务需要核验，请查看屏幕结果。'
    elif len(events) == 1 and events[0].get('tool') == 'text.respond':
        words = str(events[0].get('result') or '')[:160]
    else:
        words = '本次处理已结束。具体执行结果和核验状态显示在屏幕上。'
    _voice_speak(words)
