def _ask_clarification(question):
    import dialogs
    print('\\n【AI 需要补充】' + question)
    try:
        choice = dialogs.alert('继续刚才的任务', question[:300],
                               '语音回答', '文字回答', '稍后继续',
                               hide_cancel_button=True)
    except KeyboardInterrupt:
        return None
    if choice == 1:
        return input_voice(hands_free=True, prompt=question)
    if choice == 2:
        return ask_text('回复 AI：' + question[:60])
    return None
def _clarification_payload(state, allowed_tools):
    payload = {
        'now_device': now_iso(), 'goal': state['goal'],
        'clarifications': state.get('clarify_history', [])[-MAX_CLARIFICATION_ROUNDS:],
        'available_tools': allowed_tools, 'max_actions': MAX_PLAN_ACTIONS,
        'instruction': '这是同一原始任务的后续答复；结合问答，直接给出可执行动作；仅在还缺必要参数时追问。'
    }
    expected = state.get('clarify_clipboard_sha256')
    if expected:
        import clipboard
        copied = clipboard.get()
        if not isinstance(copied, str) or hashlib.sha256(
                copied.encode('utf-8')).hexdigest() != expected:
            raise ValueError('用于原任务的剪贴板内容已经变化，请复制回原内容后再继续，避免误操作')
        if not prompt_alert('再次读取同一剪贴板',
                '后续分析需要原先复制的文字，是否同意再次发送给 DeepSeek？'):
            raise ValueError('未授权再次读取剪贴板；原任务保持待继续状态')
        payload['clipboard_text'] = copied
    return payload
def _request_clarification_plan(state, allowed_tools):
    try:
        payload = _clarification_payload(state, allowed_tools)
        plan = _deepseek_request([
            {'role': 'system', 'content': ONE_SHOT_POLICY},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}
        ], expect_plan=True, state=state)
        return plan
    except Exception as exc:
        state['status'] = 'replan_pending'
        state['error'] = '补充信息已保存，但 AI 重新规划失败：' + str(exc)[:250]
        put_state(state)
        print(state['error'])
        return None
def _resolve_clarifications(state, plan, allowed_tools, initial_answer=None):
    answer = initial_answer
    while plan.get('question'):
        question = plan['question'].strip()
        history = state.setdefault('clarify_history', [])
        if len(history) >= MAX_CLARIFICATION_ROUNDS:
            state['status'] = 'paused'
            state['error'] = '补充问答已达 {} 轮，已停止规划；没有执行新写入。'.format(
                MAX_CLARIFICATION_ROUNDS)
            put_state(state)
            return None
        state['status'] = 'needs_input'
        state['clarify_question'] = question
        state['error'] = ''
        put_state(state)
        supplied = answer if answer is not None else _ask_clarification(question)
        answer = None
        if supplied is None or not str(supplied).strip():
            print('对话已保存。下次打开首页第 3 项可继续回答，原任务不会被执行两次。')
            return None
        supplied = str(supplied).strip()
        if len(supplied) > 600:
            state['error'] = '回答超过600字；请缩短后重试，尚未发送到 AI。'
            put_state(state)
            return None
        history.append({'question': question, 'answer': supplied})
        state['status'] = 'replan_pending'
        state['clarify_question'] = ''
        put_state(state)
        plan = _request_clarification_plan(state, allowed_tools)
        if plan is None:
            return None
    state['clarify_question'] = ''
    state['status'] = 'ready'
    state['error'] = ''
    put_state(state)
    return plan
def resume_clarification(state=None, initial_answer=None):
    state = state if state is not None else get_state()
    if state.get('status') not in ('needs_input', 'replan_pending'):
        print('没有需要继续回答的任务。')
        return state
    if state.get('pending'):
        print('当前存在待回调的系统操作，拒绝重新规划。')
        return state
    if not api_key():
        state['error'] = 'DeepSeek API Key 未配置；原对话已保留。'
        put_state(state)
        return state
    allowed = {k:v for k,v in available_tool_catalog().items()
               if k in ONE_SHOT_TOOLS}
    if state['status'] == 'replan_pending':
        if initial_answer is not None:
            print('已有上次回答，先重试规划，不追加新指令。')
        plan = _request_clarification_plan(state, allowed)
    else:
        question = state.get('clarify_question', '')
        if not question:
            state['status'] = 'paused'
            state['error'] = '找不到先前的问题；为防止误执行，已停止。'
            put_state(state)
            return state
        plan = _resolve_clarifications(
            state, {'actions': [], 'question': question},
            allowed, initial_answer=initial_answer)
    if plan is None:
        return state
    if plan.get('question'):
        plan = _resolve_clarifications(state, plan, allowed)
        if plan is None:
            return state
    return _apply_one_shot_plan(state, plan)
def plan_once(state):
    allow = {k:v for k,v in available_tool_catalog().items() if k in ONE_SHOT_TOOLS}
    payload = {'now_device':now_iso(),'goal':state['goal'],
               'available_tools':allow,'max_actions':MAX_PLAN_ACTIONS}
    if any(word in state['goal'] for word in ('剪贴板','刚复制','刚刚复制','复制的内容','我复制的')):
        if not prompt_alert('读取剪贴板并交给 DeepSeek',
                '你要求使用刚复制的内容，是否允许将剪贴板文字发送给 DeepSeek 处理？'):
            state['status']='paused'
            state['error']='用户未授权上传剪贴板；未读取或发送'
            put_state(state)
            return state
        try:
            import clipboard
            clipboard_text=clipboard.get()
            if not isinstance(clipboard_text,str) or not clipboard_text.strip():
                raise ValueError('剪贴板没有可用的文字')
            if len(clipboard_text)>MAX_CLIPBOARD_CONTEXT:
                raise ValueError('剪贴板内容过长（上限 {} 字），请先缩短后处理'.format(MAX_CLIPBOARD_CONTEXT))
            payload['clipboard_text']=clipboard_text
            state['clarify_clipboard_sha256'] = hashlib.sha256(clipboard_text.encode('utf-8')).hexdigest()
            put_state(state)
        except Exception as ex:
            state['status']='paused'
            state['error']='无法读取已授权的剪贴板：'+str(ex)[:200]
            put_state(state)
            return state
    try:
        plan = _deepseek_request([
            {'role':'system','content':ONE_SHOT_POLICY},
            {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
            expect_plan=True,state=state)
    except Exception as ex:
        state['status'] = 'paused'
        state['error'] = 'AI 一次性规划失败：' + str(ex)[:260]
        put_state(state)
        print(state['error'])
        return state
    if plan['question']:
        plan = _resolve_clarifications(state, plan, allow)
        if plan is None:
            return state
    return _apply_one_shot_plan(state, plan)
def _apply_one_shot_plan(state, plan):
    casual_plan = _casual_dated_work_plan(state['goal'])
    unintended_write = any(
        action.get('tool') in ('calendar.create','reminder.create',
                              'apple_notes.create','local_note.save')
        for action in plan['actions'])
    if casual_plan and (plan['question'] or unintended_write):
        state.update(single_plan=True,plan=[{
            'tool':'text.respond','reason':'日期型工作目标，无写入授权',
            'text':casual_plan,'title':'','datetime':'',
            'end_datetime':'','notes':'','shortcut_id':''
        }],plan_index=0,plan_approved=True)
        put_state(state)
        return execute_planned_actions(state)
    if plan['question']:
        state['status'] = 'paused'
        state['error'] = '需要补充信息：' + plan['question']
        put_state(state)
        print(state['error'])
        return state
    if len(plan['actions'])==1 and plan['actions'][0]['tool'] in RESEARCH_ACTIONS:
        return research_then_plan(state, plan['actions'][0])
    state.update(single_plan=True,plan=plan['actions'],plan_index=0)
    put_state(state)
    summary = '\n'.join('{}. {}：{}'.format(i+1, a['tool'], a['title'])
                        for i,a in enumerate(state['plan']))
    needs_write_confirmation = any(item['tool'] in (
        'apple_notes.create','calendar.create','reminder.create','local_note.save')
        for item in state['plan'])
    if needs_write_confirmation and not prompt_alert('确认 AI 操作计划', '计划执行：\n' + summary):
        state['status'] = 'paused'
        state['error'] = '用户未批准执行计划，未进行系统写入'
        put_state(state)
        return state
    state['plan_approved'] = True
    put_state(state)
    return execute_planned_actions(state)
def execute_planned_actions(state):
    if not state.get('single_plan'):
        return drive_agent(state)
    if not state.get('plan_approved'):
        state['status'] = 'paused'
        state['error'] = 'AI 操作计划尚未获得用户确认，拒绝执行'
        put_state(state)
        return state
    if state.get('status') in ('awaiting_callback','needs_review','finished'):
        return state
    if not isinstance(state.get('plan'),list):
        raise RuntimeError('执行计划不存在，不进行操作')
    if state.get('plan_index',0) >= len(state['plan']):
        if state.get('status') == 'running':
            state['status']='finished'
            state['final']=verified_final_summary(state,'本地执行完成')
            put_state(state)
            final_report(state)
        return state
    state['status']='running'
    put_state(state)
    while state['plan_index'] < len(state['plan']):
        if state['steps'] >= MAX_STEPS:
            state['status']='paused'
            state['error']='任务次数超过上限'
            put_state(state)
            return state
        action = parse_decision(state['plan'][state['plan_index']])
        tool = action['tool']
        if tool == 'app.navigate':
            if state['plan_index'] != len(state['plan']) - 1:
                state['status']='paused'
                state['error']='App 跳转必须是最后一步'
                put_state(state)
                return state
            label=APP_FEATURE_ROUTES[action['shortcut_id']][0]
            create_event(state,tool,{'title':label,'shortcut_id':action['shortcut_id']},
                         {'status':'handoff','verified':False,
                          'result':'即将请求打开「'+label+'」；未核验'})
            state['plan_index'] += 1
            state['status']='finished'
            state['final']='已准备请求打开「'+label+'」；等待 iOS 跳转'
            put_state(state)
            final_report(state,show_dialog=False)
            try:
                actual=run_tool(state,action)
            except Exception as exc:
                actual={'status':'failed','verified':False,'result':str(exc)[:160]}
            state['events'][-1]['status']=actual.get('status','failed')
            state['events'][-1]['result']=str(actual.get('result',''))[:400]
            state['events'][-1]['verified']=False
            if actual.get('status')!='ok':
                state['status']='paused'
                state['error']=str(actual.get('result','请求失败'))[:300]
            state['final']=str(actual.get('result',''))[:400]
            put_state(state)
            return state
        if tool == 'maps.search':
            if state['plan_index'] != len(state['plan'])-1 or not action['title'].strip():
                state['status']='paused'
                state['error']='地图搜索必须是最后一步且有明确目的地'
                put_state(state)
                return state
            before={'status':'handoff','verified':False,
                    'result':'即将交给 iOS 原生地图搜索「{}」；点击结果弹窗确定后继续。'.format(
                        action['title'][:100])}
            params={'title':action['title'],'datetime':'','end_datetime':'',
                    'fingerprint':action_fingerprint(action)}
            create_event(state,tool,params,before)
            state['plan_index']+=1
            state['status']='finished'
            state['final']=verified_final_summary(state,'本地执行完成，地图待切换')
            put_state(state)
            final_report(state, show_dialog=False)
            try:
                actual=run_tool(state,action)
            except Exception as ex:
                actual={'status':'failed','verified':False,
                        'result':'地图链接提交失败：'+str(ex)[:150]}
            state['events'][-1]['status']=actual.get('status','failed')
            state['events'][-1]['result']=str(actual.get('result',''))[:500]
            state['events'][-1]['verified']=False
            if actual.get('status')!='ok':
                state['status']='paused'
                state['error']=str(actual.get('result','地图请求失败'))[:300]
            state['final']=verified_final_summary(state,'本地执行完成')
            put_state(state)
            return state
        if tool not in ONE_SHOT_TOOLS:
            state['status']='paused'
            state['error']='执行时发现未授权工具'
            put_state(state)
            return state
        try:
            result = run_tool(state,action)
        except Exception as ex:
            result = {'status':'failed','result':str(ex)[:300]}
        if result['status']=='waiting':
            return state
        params = {'title':action['title'],'datetime':action['datetime'],
                  'end_datetime':action['end_datetime'],
                  'fingerprint':action_fingerprint(action)}
        create_event(state,tool,params,result)
        if result['status'] not in ('ok','unavailable','blocked_duplicate'):
            state['status']='needs_review' if result['status']=='needs_review' else 'paused'
            state['error']=str(result.get('result',''))[:400]
            put_state(state)
            return state
        state['plan_index'] += 1
        put_state(state)
    state['status']='finished'
    state['final']=verified_final_summary(state,'本地执行完成')
    put_state(state)
    final_report(state)
    return state
def call_planner(state):
    data = {
        'now_device': now_iso(),
        'goal': state['goal'],
        'previous_actions_and_real_results': state['events'][-MAX_STEPS:],
        'remaining_steps': MAX_STEPS - state['steps'],
        'registered_shortcuts': public_registry(),
        'available_tools': available_tool_catalog(),
    }
    data['available_tools'] = {k:v for k,v in data['available_tools'].items()
                               if k not in LOCAL_READ_ACTIONS + LOCAL_WRITE_ACTIONS}
    return _deepseek_request([
        {'role': 'system', 'content': POLICY},
        {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)},
    ], state=state)
def test_deepseek_connection():
    if not prompt_alert('测试 DeepSeek', '只测试 DeepSeek Flash 模型调用，不会操作手机。'):
        return
    decision = _deepseek_request([
        {'role': 'system', 'content': POLICY + '\n这是连接测试。必须选择 task.finish，并在 text 写“连接测试通过”。'},
        {'role': 'user', 'content': '这是连接测试，不操作手机。请选择 task.finish。'},
    ])
    if decision['tool'] != 'task.finish':
        raise RuntimeError('模型已响应，但没有遵守连接测试规则；实际返回工具：{}'.format(decision['tool']))
    print('[PASSED] DeepSeek 连接正常，模型：{}'.format(DEFAULT_MODEL))
    print('模型回应：{}'.format(decision['text']))
