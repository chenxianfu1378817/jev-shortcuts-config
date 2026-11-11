def _spoken_work_plan(raw, today=None):
    text = re.sub(r'\s+', '', str(raw or '')).strip('，。！!；; ')
    if not (4 <= len(text) <= 220) or any(x in text for x in _AUTO_BLOCK):
        return None
    now = today or datetime.now().date()
    day = ''
    m = re.match(r'^(?:我|我们)?(今天|明天|后天)(.+)$',text)
    if m:
        day = (now+timedelta(days={'今天':0,'明天':1,'后天':2}[m.group(1)])).isoformat()
        text=m.group(2)
    else:
        m = re.match(r'^(?:我|我们)?(?:(本周|下周)|周|星期)([一二三四五六日天])(.+)$',text)
        if m:
            weekday='一二三四五六日'.index('日' if m.group(2)=='天' else m.group(2))
            target=now-timedelta(days=now.weekday())+timedelta(
                days=weekday+(7 if m.group(1)=='下周' else 0))
            if m.group(1)!='本周' and target<now:
                target+=timedelta(days=7)
            if target<now:
                return None
            day=target.isoformat()
            text=m.group(3)
        else:
            m = re.match(r'^(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日(.+)$',text)
            if m:
                yy=int(m.group(1) or now.year)
                try:
                    dt=datetime(yy,int(m.group(2)),int(m.group(3))).date()
                    if not m.group(1) and dt<now:
                        dt=datetime(yy+1,int(m.group(2)),int(m.group(3))).date()
                except ValueError:
                    return None
                day=dt.isoformat()
                text=m.group(4)
    if day and not 0 <= (datetime.strptime(day,'%Y-%m-%d').date()-now).days <= 365*3:
        return None
    if re.search(r'\d{1,2}[:：点时]\d{0,2}',text):
        return None
    if any(x in text for x in ('今天','明天','后天','本周','下周')):
        return None
    if any(x in text for x in ('顺便','另外','然后','分别','两件事','，再','，还要','；',';')):
        return None
    if not day and not any(x in text for x in _AUTO_INTENT):
        return None
    text=re.sub(r'^(?:我(?:们)?|要|得|需要|想|打算|计划|准备|争取|力争|尽快|抓紧|务必)+','',text)
    if not 4 <= len(text) <= 125 or not any(v in text for v in _AUTO_WORK):
        return None
    return {'title':text,'day':day,'spoken':str(raw).strip()[:200]}
def _dayonly_key(title,day):
    clean=re.sub(r'[\s，。！!；;,.、：:（）()\-—_]+','',title.casefold())
    for a,b in (('剩下的','剩余'),('剩余的','剩余'),('大概',''),('约',''),('抓紧',''),('争取','')):
        clean=clean.replace(a,b)
    return hashlib.sha256((day+'|'+clean).encode('utf-8')).hexdigest()[:32]
def _dayonly_load():
    j=read_json(DATE_ONLY_LEDGER_PATH,{'entries':{}})
    if not isinstance(j,dict) or not isinstance(j.get('entries'),dict):
        raise ValueError('仅日期待办防重复台账无效')
    return j
def _dayonly_existing(reminders_module,title,day,key):
    rows=list(reminders_module.get_reminders(completed=None) or [])
    result=[]
    for item in rows:
        notes=str(getattr(item,'notes','') or '')
        due=getattr(item,'due_date',None)
        if isinstance(due,datetime):
            actual=(due.astimezone() if due.tzinfo else due).date().isoformat()
        elif hasattr(due,'isoformat'):
            actual=str(due.isoformat())[:10]
        else:
            actual=''
        has_marker=('[PYVoiceAgent dayonly:'+key+']') in notes
        same_name=(_dayonly_key(str(getattr(item,'title','') or ''),day)==key)
        if (has_marker or same_name) and actual==day:
            result.append(item)
    return result
def _eventkit_date_only_save(title,day,notes):
    from objc_util import ObjCClass
    event_store=ObjCClass('EKEventStore')
    if int(event_store.authorizationStatusForEntityType_(1)) not in (3,4):
        raise PermissionError('Pythonista 未获得苹果提醒事项权限')
    store=event_store.alloc().init()
    calendar=store.defaultCalendarForNewReminders()
    if not calendar:
        raise RuntimeError('没有可写的默认提醒事项列表')
    item=ObjCClass('EKReminder').reminderWithEventStore_(store)
    item.setCalendar_(calendar)
    item.setTitle_(title)
    item.setNotes_('')
    if day:
        dt=datetime.strptime(day,'%Y-%m-%d')
        cal=ObjCClass('NSCalendar').calendarWithIdentifier_('gregorian')
        if not cal:
            raise RuntimeError('无法使用公历日期组件')
        components=ObjCClass('NSDateComponents').alloc().init()
        components.setCalendar_(cal)
        components.setYear_(dt.year)
        components.setMonth_(dt.month)
        components.setDay_(dt.day)
        item.setStartDateComponents_(components)
        item.setDueDateComponents_(components)
    if not store.saveReminder_commit_error_(item,True,None):
        raise RuntimeError('EventKit 未确认写入')
    return True
def _dayonly_save(state, plan):
    import reminders
    title,day=plan['title'],plan['day']
    key=_dayonly_key(title,day)
    marker='[PYVoiceAgent dayonly:'+key+']'
    notes=''
    try:
        j=_dayonly_load()
        prior=j['entries'].get(key)
        if prior:
            if prior.get('status') in ('verified','existing'):
                return {'status':'ok','verified':False,'outcome':'existing',
                        'result':'同一工作待办已登记，跳过重复创建：'+title}
            return {'status':'blocked_duplicate','result':'此前写入待核验，禁止重复创建：'+title}
        from objc_util import ObjCClass
        if int(ObjCClass('EKEventStore').authorizationStatusForEntityType_(1)) not in (3,4):
            return {'status':'unavailable','result':'提醒事项权限未授权，未写入'}
        if _dayonly_existing(reminders,title,day,key):
            j['entries'][key]={'day':day,'title':title,'status':'existing'}
            atomic_json(DATE_ONLY_LEDGER_PATH,j)
            return {'status':'ok','verified':True,'outcome':'existing',
                    'result':'提醒事项中已存在同一日期同一工作目标，未重复创建：'+title}
    except Exception as ex:
        return {'status':'failed','result':'写入前检查失败，未创建：'+str(ex)[:140]}
    j['entries'][key]={'title':title,'day':day,'marker':marker,
                        'created':now_iso(),'status':'intent'}
    try:
        atomic_json(DATE_ONLY_LEDGER_PATH,j)
    except Exception as ex:
        return {'status':'failed','result':'写入防重记录失败，未创建：'+str(ex)[:120]}
    state['pending']={'tool':'reminder.create_day','title':title,'day':day,
                      'marker':marker,'token':uuid.uuid4().hex,'fingerprint':key,
                      'created':datetime.now().timestamp()}
    state['status']='needs_review'
    put_state(state)
    try:
        _eventkit_date_only_save(title,day,notes)
        found=False
        for k in range(3):
            matches=_dayonly_existing(reminders,title,day,key)
            if len(matches)==1 and len(list(getattr(matches[0],'alarms',[]) or []))==0:
                found=True
                break
            if k<2:
                time.sleep(0.4)
        if not found:
            return {'status':'needs_review','result':'已请求系统保存，但未能完整读回核验；禁止自动重试。'}
        j=_dayonly_load()
        j['entries'][key]['status']='verified'
        j['entries'][key]['verified_at']=now_iso()
        atomic_json(DATE_ONLY_LEDGER_PATH,j)
        state['pending']=None
        state['status']='running'
        put_state(state)
        return {'status':'ok','verified':True,'outcome':'created',
                'result':'已保存工作待办：{}（{}，不设具体钟点）'.format(title,day or '无到期日期')}
    except Exception as ex:
        return {'status':'needs_review','result':'写入或读回结果不确定，请人工核实；不自动重试：'+str(ex)[:140]}
def _maybe_auto_work_plan(goal):
    plan=_spoken_work_plan(goal)
    if plan is None:
        return None
    current=get_state()
    if current.get('status') in ('awaiting_callback','needs_review','writing'):
        defer_current_pending(current)
    reminder_seed_prior_state(current)
    state={'id':uuid.uuid4().hex[:12],'goal':goal,'created':now_iso(),
           'status':'ready','steps':0,'events':[],'pending':None,'final':'','error':'',
           'voice_session':bool(VOICE_SESSION_ACTIVE)}
    put_state(state)
    result=_dayonly_save(state,plan)
    params={'title':plan['title'],'datetime':plan['day'],
            'fingerprint':_dayonly_key(plan['title'],plan['day'])}
    create_event(state,'reminder.create_day',params,result)
    state['final']=str(result.get('result',''))
    if result['status']=='needs_review':
        state['status']='needs_review'
        state['error']=state['final']
    elif result['status'] in ('failed','unavailable','blocked_duplicate'):
        state['status']='paused'
        state['error']=state['final']
    else:
        state['status']='finished'
    put_state(state)
    print('\n=== 语音工作待办 ===\n'+state['final'])
    print('日期：{}；不添加钟点；没有调用 DeepSeek。'.format(plan['day'] or '未指定'))
    if state.get('voice_session'):
        _voice_report(state)
    return state
def _casual_dated_work_plan(goal):
    goal = str(goal or '').strip()
    if not 4 <= len(goal) <= 250 or '?' in goal or '？' in goal:
        return ''
    if not any(x in goal for x in ('今天','明天','后天','本周','下周','周末','星期','周一','周二','周三','周四','周五','周六','周日')):
        return ''
    if not any(x in goal for x in ('争取','打算','计划','准备','力争','尽快','抓紧','希望','务必','需要把','得把','要把','打算把')):
        return ''
    if any(x in goal for x in ('提醒我','提醒一下','设置提醒','建提醒','提醒事项','创建日历','添加日历','记到日历','放到日历',
                              '创建日程','安排日程','保存备忘录','记到备忘录','帮我记','请记录','存起来','闹钟','通知我',
                              '查询日历','查日历','查看日程','分析日程','查提醒','查备忘录','几点','具体时间')):
        return ''
    if goal.startswith(('请问','怎么','如何','为什么','能不能','可不可以')):
        return ''
    return ('已理解为工作计划（尚未写入提醒事项或日历）：\n'
            + goal[:200]
            + '\n建议先核实实际待处理事项与可用资源，再明确对接对象及执行进度。'
            + '\n如果要系统提醒，请另说“明天上午9点提醒我跟进这件事”等包含提醒时刻的指令。')
