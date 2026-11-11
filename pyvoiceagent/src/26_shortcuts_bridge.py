def create_event(state, tool, args, result):
    state['steps'] += 1
    state.setdefault('events', []).append({
        'tool': tool,
        'params': args,
        'status': result.get('status', 'unknown'),
        'result': result.get('result', ''),
        'at': now_iso(),
        'verified': result.get('verified', False),
        'outcome': result.get('outcome', ''),
    })
    put_state(state)
def local_registry():
    reg = read_json(REGISTRY_PATH, {})
    if not isinstance(reg, dict):
        return {}
    output = {}
    for key, item in reg.items():
        if (not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,31}', key)
                or not isinstance(item, dict)):
            continue
        name = item.get('name', '')
        description = item.get('description', '')
        if (not isinstance(name, str) or not (1 <= len(name) <= 70)
                or not isinstance(description, str)):
            continue
        if key in DEFAULT_LIBRARY or name in (BRIDGE_SHORTCUT, LEGACY_BRIDGE, 'PYBridgeEcho'):
            continue
        output[key] = {'name': name, 'description': description[:160]}
        if len(output) >= MAX_SHORTCUTS:
            break
    return output
def public_registry():
    return [{'id': k, 'description': v['description']}
            for k, v in local_registry().items()]
def add_shortcut_registration():
    name = ask_text('苹果快捷指令真实名称')
    if not name or not name.strip() or len(name.strip()) > 70:
        return False
    ident = ask_text('工具 ID（小写英文数字下划线，如 my_safe_action）')
    if not ident or not re.fullmatch(r'[a-z][a-z0-9_]{1,31}', ident):
        print('ID 不符合规则：必须以小写字母开头，只能包含小写字母数字下划线。')
        return False
    if ident in DEFAULT_LIBRARY:
        print('此 ID 为保留值。')
        return False
    desc = ask_text('让 AI 理解这个指令用途（简短描述）')
    if not desc or not desc.strip():
        return False
    reg = local_registry()
    if ident not in reg and len(reg) >= MAX_SHORTCUTS:
        print('达到自定义快捷指令数量上限。')
        return False
    if not prompt_alert('登记授权工具', '只有你已检查安全性的快捷指令才应登记。\nID：{}\n名称：{}\n用途：{}'.format(ident, name, desc[:140])):
        return False
    reg[ident] = {'name': name.strip(), 'description': desc.strip()[:160]}
    atomic_json(REGISTRY_PATH, reg)
    print('工具已登记：{} → {}'.format(ident, name))
    return True
def parse_local_dt(timestr, label='时间'):
    if not isinstance(timestr, str) or not timestr.strip():
        raise ValueError('{}缺少日期'.format(label))
    dt = datetime.fromisoformat(timestr.strip().replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('{}必须提供时区，例如 +08:00'.format(label))
    return dt.astimezone().replace(tzinfo=None)
def action_fingerprint(choice):
    keys = ('tool','title','text','datetime','end_datetime','notes','shortcut_id')
    values = {k: choice.get(k,'') for k in keys}
    return hashlib.sha256(json.dumps(values, ensure_ascii=False,
                 sort_keys=True).encode('utf-8')).hexdigest()[:24]
def bridge_payload(state, choice, route, shortcut_name):
    title, body = choice['title'].strip(), choice['text'].strip()
    notes = choice['notes'].strip()
    start, end = choice['datetime'].strip(), choice['end_datetime'].strip()
    if route == 'apple_notes.create' and not body:
        raise ValueError('苹果备忘录正文为空')
    if route == 'calendar.list':
        dt_start, dt_end = parse_local_dt(start, '日程查询开始'), parse_local_dt(end, '日程查询结束')
        if dt_end <= dt_start or dt_end - dt_start > timedelta(days=31):
            raise ValueError('日历查询时间区间必须大于0且不超过31天')
    if route == 'calendar.create':
        dt_start, dt_end = parse_local_dt(start, '日程开始'), parse_local_dt(end, '日程结束')
        if dt_start <= datetime.now() - timedelta(days=1):
            raise ValueError('日程开始时间早于昨天，不自动创建')
        if dt_start >= dt_end or dt_end - dt_start > timedelta(days=7):
            raise ValueError('日程起止时间不合法或跨度超过 7 天')
    if route == 'shortcut.run':
        if choice['shortcut_id'] not in local_registry():
            raise ValueError('自定义快捷指令未在本地工具库登记')
    if max(len(title), len(body), len(notes)) > MAX_BRIDGE_TEXT:
        raise ValueError('传给快捷指令的文本过长，最多 {} 字'.format(MAX_BRIDGE_TEXT))
    token = uuid.uuid4().hex
    marker = '[PYVoiceAgent:{}:{}]'.format(state['id'], state['steps'])
    payload = {
        'version': 13, 'token': token, 'route': route,
        'shortcut_id': choice['shortcut_id'] if route == 'shortcut.run' else '',
        'title': title, 'text': body,
        'notes': notes, 'start': start, 'end': end, 'marker': marker,
    }
    if route == 'apple_notes.create':
        payload['note_body'] = clean_apple_note(title, body)
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    packed = base64.b64encode(raw).decode('ascii')
    if len(packed) > 8500:
        raise ValueError('快捷指令 URL 传参超过安全限制，请缩短文本')
    return payload, packed, token
def start_bridge_tool(state, choice, route, target_shortcut):
    enrolling = (state.get('module_enroll') == route and
                 SYSTEM_MODULES.get(route) == target_shortcut)
    if route in SYSTEM_MODULES and not enrolling and verified_system_module(route) != target_shortcut:
        return {'status': 'unavailable',
                'result': '系统模块未经过安装验证，未发出创建操作：' + route}
    import shortcuts
    payload, encoded, token = bridge_payload(state, choice, route, target_shortcut)
    summary = ('快捷指令：{}\n工具：{}\n标题：{}\n{}'.format(
        target_shortcut, route, payload['title'],
        (payload['text'] or payload['notes'])[:250]))
    if route != 'calendar.list' and not (state.get('single_plan') and state.get('plan_approved')) and not prompt_alert('确认跨 App 操作', summary):
        return {'status': 'declined', 'result': '用户拒绝跨 App 操作'}
    state['pending'] = {
        'tool': route, 'token': token, 'created': datetime.now().timestamp(),
        'marker': payload['marker'], 'name': target_shortcut,
        'title': payload['title'], 'shortcut_id': payload.get('shortcut_id',''),
        'origin_step': state['steps'], 'fingerprint': action_fingerprint(choice),
    }
    state['status'] = 'awaiting_callback'
    put_state(state)
    url = 'shortcuts://run-shortcut?' + urlencode({
        'name': target_shortcut, 'input': 'text', 'text': encoded})
    try:
        shortcuts.open_url(url)
    except Exception as ex:
        state['status'] = 'needs_review'
        state['error'] = '跳转异常，无法确定快捷指令是否已执行：{}'.format(ex)
        put_state(state)
        return {'status': 'waiting', 'result': state['error']}
    return {'status': 'waiting', 'result': '已请求快捷指令，等待带相同 token 的回调'}
def decode_shortcuts_result_b64(raw):
    if not isinstance(raw, str) or len(raw) > 4000:
        raise ValueError('回传数据长度或类型不合法')
    if re.search(r'%(?![0-9a-fA-F]{2})', raw):
        raise ValueError('URL 编码包含不完整的百分号转义')
    ascii_text = unquote_to_bytes(raw).decode('ascii')
    ascii_text = ''.join(ch for ch in ascii_text if ch not in (chr(13), chr(10), chr(9)))
    ascii_text = ascii_text.replace(' ', '+')
    decoded = base64.b64decode(ascii_text, validate=True).decode('utf-8')
    if len(decoded) > 1800:
        raise ValueError('解码内容过长')
    return decoded
def can_retry_readonly_calendar(state):
    p=state.get('pending') or {}
    plan=state.get('plan')
    return bool(
        state.get('status')=='needs_review'
        and isinstance(p,dict) and p.get('tool')=='calendar.list'
        and state.get('single_plan') and state.get('plan_approved')
        and isinstance(plan,list) and len(plan)==1
        and isinstance(plan[0],dict) and plan[0].get('tool')=='calendar.list'
        and state.get('plan_index')==0 and not state.get('events')
        and int(state.get('calendar_read_retry_count',0))<1
        and any(term in str(state.get('error','')) for term in (
            '数据编码异常','CALREAD1','查询回调正文为空')))
def retry_last_readonly_calendar(state):
    if not can_retry_readonly_calendar(state):
        return False
    if not prompt_alert('重新读取日历（不用 AI）',
            '只重新查询上次的日期，不创建或修改事项，不消耗 DeepSeek Token。确认继续？'):
        return False
    state['calendar_read_retry_count']=1
    state['pending']=None
    state['status']='ready'
    state['error']=''
    put_state(state)
    execute_planned_actions(state)
    return True
def bridge_callback(token, status, result_b64=''):
    state = get_state()
    p = state.get('pending') or {}
    if state.get('status') != 'awaiting_callback' or not p:
        if deferred_callback(token, status):
            return True
        print('当前没有等待中的快捷指令，忽略回调。')
        return False
    if not isinstance(token, str) or not hmac.compare_digest(token, str(p.get('token',''))):
        if isinstance(token, str) and status in ('ok', 'failed', 'cancelled') and deferred_callback(token, status):
            return True
        print('回调编号不匹配，忽略；未修改正在等待的任务。')
        return False
    if not isinstance(status, str) or status not in ('ok', 'failed', 'cancelled'):
        print('回调状态无效，忽略；未修改正在等待的任务。')
        return False
    returned_text = ''
    if result_b64:
        try:
            returned_text = decode_shortcuts_result_b64(result_b64)
        except (ValueError, UnicodeDecodeError, binascii.Error) as ex:
            state['status'] = 'needs_review'
            state['error'] = '快捷指令返回的数据编码异常，待人工核验：{}'.format(ex)
            put_state(state)
            return False
    delay = datetime.now().timestamp() - p.get('created', 0)
    if delay < 0 or delay > BRIDGE_TIMEOUT:
        state['status'] = 'needs_review'
        state['error'] = '回调过期。必须手工检查苹果应用中的项目是否已创建，不能自动重试。'
        put_state(state)
        print(state['error'])
        return False
    tool = p['tool']
    calendar_result = None
    if tool == 'calendar.list' and status == 'ok':
        prefix = 'CALREAD1' + chr(10)
        if not returned_text.startswith(prefix):
            state['pending']['reported_status'] = 'invalid_calendar_read_response'
            state['status'] = 'needs_review'
            state['error'] = ('日历只读快捷指令回调没有携带 CALREAD1 格式的查询结果；'
                              '已拒绝将空结果当作没有日程。请检查 PYAgentCalendarRead 的回传正文。')
            put_state(state)
            return False
        calendar_result = returned_text[len(prefix):].strip()
        if not calendar_result:
            state['status'] = 'needs_review'
            state['error'] = '日历查询回调正文为空，拒绝报告查询成功。'
            put_state(state)
            return False
    desc = ('快捷指令 {} 回报：{}。标记 {}。' .format(p['name'], status, p['marker']))
    if status == 'ok':
        result = ({'status': 'ok', 'verified': False,
                   'result': '只读快捷指令返回（未做独立系统核验）：\n'+calendar_result}
                  if tool == 'calendar.list' else
                  {'status': 'ok', 'result': desc + '这是快捷指令报告，并非 Pythonista 二次查询核验。' +
                   (' 工具返回数据：' + returned_text if returned_text else '')})
    elif status == 'cancelled':
        result = {'status': 'declined', 'result': desc}
    else:
        result = {'status': 'failed', 'result': desc}
    if status != 'ok':
        state['pending']['reported_status'] = status
        state['status'] = 'needs_review'
        state['error'] = '快捷指令未报告成功。请人工核实是否已经创建，禁止自动重试。'
        put_state(state)
        print(state['error'])
        return False
    if tool == 'apple_notes.create':
        try:
            _index_agent_note_after_callback(state, p)
        except Exception as index_error:
            print('备忘录本地索引保存失败，备忘录快捷指令回调仍单独记录：'+str(index_error)[:130])
    state['pending'] = None
    state['status'] = 'running'
    create_event(state, tool, {'title': p['title'], 'marker': p['marker'],
                              'fingerprint': p.get('fingerprint','')}, result)
    if state.get('diagnostic'):
        print('[CALLBACK OK] {}（匹配回传）'.format(tool))
    if state.get('diagnostic'):
        state['status'] = 'finished'
        enroll = state.get('module_enroll')
        if enroll in SYSTEM_MODULES:
            if confirm_module_install(state, enroll):
                state['final'] = '已确认系统测试项目存在，模块 {} 已启用。'.format(SYSTEM_MODULES[enroll])
            else:
                state['final'] = '仅收到快捷指令回调，尚未完成苹果 App 核验；模块未启用。'
        else:
            state['final'] = '离线诊断已收到快捷指令 OK 回调；请进入苹果 App 检查实体是否真的创建。'
        put_state(state)
        pretty_status(state)
        return True
    if tool=='calendar.list' and state.get('research_origin')=='calendar.assist':
        if state.get('research_phase')!='awaiting_calendar':
            state['status']='needs_review'
            state['error']='日历连续任务阶段不匹配，拒绝自动继续'
            put_state(state)
            return False
        state['calendar_read_text']=calendar_result
        state['research_phase']='calendar_read_complete'
        state['plan_index']=1
        put_state(state)
        finish_calendar_assist(state)
        return True
    if state.get('single_plan'):
        state['plan_index'] = int(state.get('plan_index',0)) + 1
        put_state(state)
        execute_planned_actions(state)
    else:
        drive_agent(state)
    return True
def review_pending():
    state = get_state()
    p = state.get('pending') or {}
    if not p or state.get('status') not in ('awaiting_callback','needs_review'):
        print('无待人工核验的跨 App 操作。')
        return
    print('工具：{}\n标题：{}\n标记：{}\n快捷指令：{}'.format(
        p.get('tool'), p.get('title'), p.get('marker'), p.get('name')))
    import dialogs
    options = [
        '已经在苹果 App 中亲自确认创建成功',
        '亲自确认没有创建，可重新规划但不自动重试',
        '尚未确认，继续保持暂停',
    ]
    answer = dialogs.list_dialog('跨 App 操作人工核验', options)
    if answer == options[2] or not answer:
        print('仍处于待核验状态。')
        return
    if not prompt_alert('请再次确认', '你已经打开苹果 App 核对了标题、日期和标记吗？此操作仅记录你的核验结论。'):
        return
    status = 'ok' if answer == options[0] else 'failed'
    event = {'status': status, 'result': '用户在苹果 App 中人工确认：' + answer}
    create_event(state, p.get('tool','shortcut.run'),
                 {'title':p.get('title',''), 'marker':p.get('marker',''),
                  'fingerprint':p.get('fingerprint','')}, event)
    state['pending'] = None
    state['error'] = ''
    if p.get('tool') == 'reminder.create_day':
        try:
            record=_dayonly_load()
            key=p.get('fingerprint')
            if key in record['entries']:
                record['entries'][key]['status']='verified' if status=='ok' else 'confirmed_absent'
                record['entries'][key]['reviewed_at']=now_iso()
                atomic_json(DATE_ONLY_LEDGER_PATH,record)
        except Exception as ex:
            state['status']='needs_review'
            state['pending']=p
            state['error']='待办核验记录失败：'+str(ex)[:140]
            put_state(state)
            return
        state['status']='finished' if status=='ok' else 'paused'
        state['final']='人工核验已记录；原事项不会自动重试。'
        put_state(state)
        print(state['final'])
        return
    if p.get('tool') == 'reminder.create':
        try:
            key = p.get('ledger_key')
            when = datetime.fromisoformat(p.get('datetime', ''))
            when = reminder_local_datetime(when)
            key = key or reminder_key(p.get('title'), when)
            if status == 'ok':
                reminder_ledger_set(key, p.get('title',''), when, p.get('marker',''), 'verified')
            else:
                reminder_ledger_delete(key)
        except (OSError, ValueError, RuntimeError) as ex:
            state['status'] = 'needs_review'
            state['pending'] = p
            state['error'] = '更新防重复记录失败：' + str(ex)[:150]
            put_state(state)
            print(state['error'])
            return
    if status == 'ok':
        state['status'] = 'paused'
        put_state(state)
        if prompt_alert('继续任务', '已记录人工核验通过，是否继续让 AI 规划后续步骤？'):
            drive_agent(state)
    else:
        state['status'] = 'paused'
        state['error'] = '人工确认未创建，已记录失败。需明确指示才能重新创建。'
        put_state(state)
def install_system_module():
    import dialogs
    options = ['苹果备忘录 PYAgentNotes', '苹果日历 PYAgentCalendar']
    chosen = dialogs.list_dialog('首次安装与核验系统模块', options)
    if chosen not in options:
        return None
    route = 'apple_notes.create' if chosen == options[0] else 'calendar.create'
    target = SYSTEM_MODULES[route]
    if verified_system_module(route) == target:
        print('系统模块 {} 已完成验收，不重复创建测试事项。'.format(target))
        return None
    previous = get_state()
    if previous.get('status') in ('awaiting_callback', 'needs_review', 'writing'):
        try:
            defer_current_pending(previous)
        except (OSError, ValueError, RuntimeError) as ex:
            print('旧任务无法安全归档：' + str(ex))
            return None
    if not prompt_alert('首次模块验证',
                        '请确认快捷指令“{}”已按安装说明配置。\n'
                        '即将实际创建一条可删除的测试项目，必须亲自检查苹果 App 后才能启用模块。'.format(target)):
        return None
    state = {'id': uuid.uuid4().hex[:12], 'goal': '模块首次验收：' + route,
             'created': now_iso(), 'status': 'ready', 'steps': 0,
             'events': [], 'pending': None, 'final': '', 'error': '',
             'diagnostic': True, 'module_enroll': route}
    choice = {k:'' for k in DECISION_SCHEMA['required']}
    choice.update(tool=route, reason='首次安装验证', title='PYVoiceAgent模块验收测试')
    if route == 'apple_notes.create':
        choice['text'] = '这是一条首次安装验证备忘录，可以在完成验收后删除。'
    else:
        when = (datetime.now().astimezone() + timedelta(days=4)).replace(
            hour=14, minute=0, second=0, microsecond=0)
        choice['datetime'] = when.isoformat()
        choice['end_datetime'] = (when + timedelta(minutes=30)).isoformat()
        choice['notes'] = '首次安装日历模块的验证事件，可删除'
    put_state(state)
    result = start_bridge_tool(state, choice, route, target)
    if result.get('status') != 'waiting':
        state['status'] = 'paused'
        state['error'] = str(result.get('result', ''))
        put_state(state)
    return state
def confirm_module_install(state, route):
    import dialogs
    labels = ['我已经亲自确认测试项目存在', '尚未确认或项目不存在']
    choice = dialogs.list_dialog('模块安装验收', labels)
    if choice != labels[0]:
        return False
    target = SYSTEM_MODULES.get(route)
    if not target:
        return False
    cfg = read_json(MODULE_REGISTRY_PATH, {})
    if not isinstance(cfg, dict):
        raise RuntimeError('模块登记信息格式错误')
    modules = cfg.get('modules', {})
    if not isinstance(modules, dict):
        raise RuntimeError('模块登记表格式错误')
    modules[route] = {'name': target, 'verified': True,
                      'verified_at': now_iso(), 'method': 'user-checked-test-item'}
    cfg['modules'] = modules
    atomic_json(MODULE_REGISTRY_PATH, cfg)
    return True
def start_bridge_diagnostic(kind='shortcut.hub_echo'):
    old = get_state()
    if old.get('status') in ('awaiting_callback','needs_review','writing') and old.get('pending'):
        try:
            defer_current_pending(old)
        except (OSError, RuntimeError, ValueError) as ex:
            print('无法安全归档旧任务：' + str(ex))
            return None
    if old.get('status') in ('running','paused') and not prompt_alert(
            '已有历史任务', '本次诊断会覆盖未完成任务状态，是否继续？'):
        return None
    state = {'id': uuid.uuid4().hex[:12], 'goal':'离线诊断：' + kind,
             'created': now_iso(), 'status':'ready', 'steps':0,
             'events':[], 'pending':None, 'final':'', 'error':'',
             'diagnostic':True}
    put_state(state)
    choice = {k:'' for k in DECISION_SCHEMA['required']}
    choice.update(tool=kind, reason='人工发起的离线桥接诊断')
    if kind == 'apple_notes.create':
        choice.update(title='PYVoiceAgent V1.4 测试备忘',
                      text='这是一条由 Pythonista 发起的测试备忘，可在验收后删除。')
    elif kind == 'calendar.create':
        start = (datetime.now().astimezone()+timedelta(days=3)).replace(
            hour=14,minute=0,second=0,microsecond=0)
        choice.update(title='PYVoiceAgent V1.4 测试日程',
                      datetime=start.isoformat(),
                      end_datetime=(start+timedelta(minutes=30)).isoformat(),
                      notes='测试结束后请手动删除。')
    else:
        choice.update(text='hub-ping')
    result = run_tool(state, choice)
    if result.get('status') != 'waiting':
        state['status'] = 'paused'
        state['error'] = str(result.get('result'))
        put_state(state)
    return state
