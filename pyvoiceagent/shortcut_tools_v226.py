# -*- coding: utf-8 -*-
"""V2.2.5 registered Apple Shortcuts: local whitelist and safe chat dispatch."""
_REG_PREVIOUS_CATALOG = available_tool_catalog
_REG_PREVIOUS_RUN = run_tool
_REG_PREVIOUS_APPLY = _apply_one_shot_plan
_REG_PREVIOUS_PARSE = parse_action_plan
_REG_PREVIOUS_SUBMIT = _ChatShell.submit
_REG_PREVIOUS_ADD = add_shortcut_registration
ONE_SHOT_TOOLS += ('shortcut.run',)

def local_registry():
    raw = read_json(REGISTRY_PATH, {})
    if not isinstance(raw, dict):
        return {}
    result = {}
    for ident, obj in raw.items():
        try:
            item = _reg_validate(dict(obj, id=ident), legacy=True)
            if item['enabled']:
                result[ident] = item
        except (ValueError, TypeError, AttributeError):
            continue
        if len(result) >= MAX_SHORTCUTS:
            break
    return result

def _reg_validate(item, legacy=False):
    if not isinstance(item, dict):
        raise ValueError('登记数据不是对象')
    ident = str(item.get('id','')).strip()
    name = str(item.get('name','')).strip()
    desc = str(item.get('description','')).strip()
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,31}',ident) or ident in DEFAULT_LIBRARY:
        raise ValueError('工具 ID 只能为小写英文、数字及下划线，不能使用保留 ID')
    if not 1 <= len(name) <= 70 or any(c in name for c in '\r\n'):
        raise ValueError('快捷指令名称必须与 iPhone 上的名称一致（1–70 字）')
    if name in (BRIDGE_SHORTCUT,LEGACY_BRIDGE,'PYBridgeEcho'):
        raise ValueError('不允许覆盖系统快捷指令')
    if not 1 <= len(desc) <= 160:
        raise ValueError('请输入简短用途说明（1–160 字）')
    if type(item.get('confirm',True)) is not bool or type(item.get('enabled',True)) is not bool:
        raise ValueError('确认及启用字段必须为布尔值')
    aliases=item.get('aliases', [])
    if isinstance(aliases,str):
        aliases=[x.strip() for x in aliases.replace('，',',').split(',')]
    if not isinstance(aliases,list):
        raise ValueError('触发语句必须为数组')
    aliases=[x.strip() for x in aliases if isinstance(x,str) and x.strip()]
    if legacy and not aliases:
        aliases=['运行'+name]
    if not 1 <= len(aliases) <= 8 or any(len(x)>45 or '\n' in x for x in aliases):
        raise ValueError('请设置1–8个自然语言触发语句，每条不超过45字')
    normalized=[x.casefold() for x in aliases]
    if len(set(normalized))!=len(normalized):
        raise ValueError('重复的触发语句')
    mode=item.get('mode','bridge' if legacy else 'launch')
    arg_mode=item.get('input_mode','none')
    if mode not in ('launch','bridge') or arg_mode not in ('none','suffix','full'):
        raise ValueError('调用模式或参数模式无效')
    return {'name':name,'description':desc,'aliases':aliases,'mode':mode,
            'input_mode':arg_mode,'confirm':item.get('confirm',True) is not False,
            'enabled':item.get('enabled',True) is not False}

def _reg_all():
    raw=read_json(REGISTRY_PATH,{})
    if not isinstance(raw,dict):
        return {}
    out={}
    for ident,item in raw.items():
        try: out[ident]=_reg_validate(dict(item,id=ident),legacy=True)
        except (ValueError,TypeError,AttributeError): continue
    return out

def _reg_items():
    return [dict(id=k,**v) for k,v in sorted(_reg_all().items())]

def _reg_save(data):
    if not isinstance(data,dict):
        raise ValueError('登记格式错误')
    ident=str(data.get('id','')).strip()
    candidate=_reg_validate(data)
    reg=_reg_all()
    if get_state().get('status')=='awaiting_callback':
        raise ValueError('存在待回调任务，暂不可修改工具库')
    if ident not in reg and len(reg)>=MAX_SHORTCUTS:
        raise ValueError('最多登记 {} 个快捷指令'.format(MAX_SHORTCUTS))
    for key,other in reg.items():
        if key==ident: continue
        if (other['enabled'] and candidate['enabled'] and
            set(x.casefold() for x in other['aliases']) &
            set(x.casefold() for x in candidate['aliases'])):
            raise ValueError('触发语句与已启用的其他工具重复')
    reg[ident]=candidate
    atomic_json(REGISTRY_PATH,reg)
    return ident

def _reg_change(ident,enabled=None,delete=False):
    reg=_reg_all()
    if ident not in reg:
        raise ValueError('工具未登记')
    if get_state().get('status')=='awaiting_callback':
        raise ValueError('等待快捷指令回传期间不能修改工具库')
    if delete:
        del reg[ident]
    else:
        reg[ident]['enabled']=bool(enabled)
    atomic_json(REGISTRY_PATH,reg)

def _reg_match(goal):
    if not isinstance(goal,str) or len(goal)>650 or not goal.strip():
        return None
    raw=goal.strip()
    if re.search(r'(不要|不准|别|禁止|取消|不要执行|不要打开|先别|然后|接着|同时|顺便)',raw):
        return None
    matches=[]
    for ident,item in local_registry().items():
        for alias in item['aliases']:
            for prefix in (alias, '请'+alias, '帮我'+alias):
                if raw.casefold()==prefix.casefold():
                    matches.append((len(prefix),ident,''))
                elif item['input_mode']=='suffix' and raw.casefold().startswith(prefix.casefold()):
                    extra=raw[len(prefix):].lstrip(' :：，,')
                    if extra and len(extra)<=450:
                        matches.append((len(prefix),ident,extra))
    if not matches:
        return None
    matches.sort(reverse=True)
    if len(matches)>1 and matches[0][0]==matches[1][0] and matches[0][1]!=matches[1][1]:
        return None
    ident=matches[0][1]
    item=local_registry()[ident]
    arg=raw[:450] if item['input_mode']=='full' else matches[0][2]
    return (ident,item,arg)

def available_tool_catalog():
    result=_REG_PREVIOUS_CATALOG()
    listing=public_registry()
    if listing:
        result['shortcut.run']='仅可使用本地登记的快捷指令 ID：'+str(listing)[:1800]+'；不可编造ID；仅用户明确要求才执行'
    else:
        result.pop('shortcut.run',None)
    return result

def parse_action_plan(data, allowed_tools):
    plan=_REG_PREVIOUS_PARSE(data,allowed_tools)
    actions=plan['actions']
    custom=[a for a in actions if a['tool']=='shortcut.run']
    if custom and (len(actions)!=1 or custom[0]['shortcut_id'] not in local_registry()):
        raise ValueError('自定义快捷指令必须独立执行且在本地启用')
    return plan

def _apply_one_shot_plan(state,plan):
    actions=plan.get('actions',[])
    if any(a.get('tool')=='shortcut.run' for a in actions):
        if len(actions)!=1 or actions[0]['shortcut_id'] not in local_registry():
            raise ValueError('未注册或被停用的快捷指令')
        ident=actions[0]['shortcut_id']
        item=local_registry()[ident]
        if not prompt_alert('确认执行本地快捷指令',
                            '即将请求 iOS 运行：'+item['name']):
            state.update(status='paused',error='用户取消了自定义快捷指令')
            put_state(state)
            return state
        if item['mode']=='launch':
            _reg_direct_launch(state,actions[0],item)
            return state
    return _REG_PREVIOUS_APPLY(state,plan)

def _reg_direct_launch(state,choice,item):
    import shortcuts
    payload=str(choice.get('text',''))[:450]
    url='shortcuts://run-shortcut?'+urlencode({'name':item['name'],'input':'text','text':payload})
    state['status']='finished'
    state['final']='已请求 iOS 启动「{}」，未收到执行成功证明'.format(item['name'])
    create_event(state,'shortcut.run',
                 {'shortcut_id':choice['shortcut_id'],'title':item['name'],
                  'fingerprint':action_fingerprint(choice)},
                 {'status':'handoff','verified':False,'result':state['final']})
    put_state(state)
    try:
        shortcuts.open_url(url)
        return {'status':'ok','verified':False,'result':'仅已请求启动，未验证执行结果'}
    except Exception as ex:
        state.update(status='needs_review',error='无法确认是否启动：'+str(ex)[:120])
        put_state(state)
        return {'status':'needs_review','verified':False,'result':state['error']}

def run_tool(state,choice):
    if choice.get('tool')=='shortcut.run':
        item=local_registry().get(choice.get('shortcut_id'))
        if item is None:
            return {'status':'unavailable','result':'未登记或已停用的快捷指令'}
        if item['mode']=='launch':
            return _reg_direct_launch(state,choice,item)
    return _REG_PREVIOUS_RUN(state,choice)

def _reg_invoke(shell,goal,match):
    ident,item,arg=match
    def start():
        scheduled=False
        try:
            if shell.closed: return
            old=get_state()
            if old.get('status') in ('awaiting_callback','needs_review','running','writing','paused','needs_input','replan_pending'):
                shell.message('assistant','仍有待回传或待核验任务，请先处理以免重复调用。')
                return
            try:
                previous=datetime.fromisoformat(str(old.get('created','')))
                duplicate=(old.get('routing_shortcut')==ident and
                           old.get('routing_input')==arg and
                           (datetime.now().astimezone()-previous).total_seconds()<15)
            except (ValueError,TypeError): duplicate=False
            if duplicate:
                shell.message('assistant','已拦截15秒内的重复快捷指令请求。')
                return
            if item['confirm']:
                permission=shell.approve('运行已登记的快捷指令「'+item['name']+'」？'+
                                         ('\n传入文字：'+arg[:100] if arg else ''),
                                         [('确认运行','1'),('取消','0')])
                if permission!=1:
                    shell.message('assistant','本次调用已取消，没有执行快捷指令。')
                    return
            if shell.closed: return
            def on_ui():
                if shell.closed: return
                if get_state().get('status') in ('awaiting_callback','needs_review','running','writing','paused','needs_input','replan_pending'):
                    shell.message('assistant','旧任务仍在等待或暂停中，本次未覆盖；请先处理旧任务。')
                    shell.status(False,False)
                    return
                state={'id':uuid.uuid4().hex[:12],'goal':goal,'created':now_iso(),
                       'status':'ready','events':[],'steps':0,'pending':None,
                       'final':'','error':'','routing_engine':'local_registry',
                       'routing_shortcut':ident,'routing_input':arg,
                       'voice_session':False}
                choice={'tool':'shortcut.run','shortcut_id':ident,'title':item['name'],
                        'text':arg,'reason':'本地登记的触发语句','notes':'',
                        'datetime':'','end_datetime':''}
                put_state(state)
                if item['mode']=='bridge':
                    state.update(single_plan=True,plan=[choice],plan_index=0,
                                 plan_approved=True)
                    put_state(state)
                    result=execute_planned_actions(state)
                    if result.get('status')=='awaiting_callback':
                        shell.message('assistant','已移交「'+item['name']+'」，等待有效回传；请勿重复执行。')
                    else:
                        shell.message('assistant','快捷指令状态：'+str(result.get('status')))
                else:
                    result=_reg_direct_launch(state,choice,item)
                    shell.message('assistant',str(result.get('result',''))+'；请在快捷指令中核实。')
                shell.status(False,False)
            shell.ui.delay(on_ui,0.08)
            scheduled=True
        except Exception as exc:
            shell.message('assistant','本地快捷指令调用失败：'+str(exc)[:160])
        finally:
            if not scheduled:
                shell.status(False,False)
    shell.status(True,False)
    _chat_threading.Thread(target=start,daemon=True,name='PYVA-RegisteredShortcut').start()

def _reg_submit(shell,value,from_voice=False):
    text=str(value or '').strip()[:2000]
    if shell.closed or shell.answer_event is not None or shell.busy or shell.recorder is not None:
        return _REG_PREVIOUS_SUBMIT(shell,value,from_voice)
    match=_reg_match(text)
    if not match:
        return _REG_PREVIOUS_SUBMIT(shell,value,from_voice)
    if from_voice:
        shell.recognizing=False
    shell.message('user',text)
    _reg_invoke(shell,text,match)
_ChatShell.submit=_reg_submit

_REG_OLD_ACTION=_ChatShell._handle_action
def _reg_action(shell,action,text):
    if action in ('reg_list','reg_save','reg_toggle','reg_delete'):
        if shell.busy:
            shell.post({'type':'notice','text':'请先完成正在执行的任务'})
            return
        try:
            if action=='reg_save':
                data=json.loads(text)
                ident=_reg_save(data)
                shell.post({'type':'notice','text':'工具已保存：'+ident})
            elif action=='reg_toggle':
                obj=json.loads(text)
                _reg_change(str(obj['id']),enabled=obj['enabled'] is True)
            elif action=='reg_delete':
                obj=json.loads(text)
                if obj.get('confirm') is not True:
                    raise ValueError('删除需要明确确认')
                _reg_change(str(obj['id']),delete=True)
            shell.post({'type':'reg_list','items':_reg_items()})
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            shell.post({'type':'notice','text':'工具库操作失败：'+str(exc)[:130]})
        return
    if action=='exit':
        if shell.busy and shell.answer_event is None:
            shell.post({'type':'notice','text':'任务正在执行，暂不能退出；等待结果后再退出'})
            return
        def close_after_navigation():
            shell.close()
            if shell.holder:
                shell.holder.close()
        shell.ui.delay(close_after_navigation,0.08)
        return
    return _REG_OLD_ACTION(shell,action,text)
_ChatShell._handle_action=_reg_action

def add_shortcut_registration():
    # The former prompt path wrote only enabled entries and could erase disabled
    # user tools. Always use the new local manager when WebView is available.
    shell=_CHAT_ACTIVE
    if shell is not None and not shell.closed:
        shell.post({'type':'notice','text':'请在设置中的「我的快捷指令工具库」添加或编辑。'})
        return False
    return _REG_PREVIOUS_ADD()
