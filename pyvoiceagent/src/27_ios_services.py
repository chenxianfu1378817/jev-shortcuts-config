def reminder_key(title, when):
    local = reminder_local_datetime(when)
    if local is None:
        raise ValueError('无效的提醒时间')
    canonical = ' '.join(str(title or '').strip().split()).casefold()
    identity = canonical + '\n' + local.strftime('%Y-%m-%dT%H:%M')
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
def reminder_ledger_load():
    try:
        with open(REMINDER_LEDGER_PATH, 'r', encoding='utf-8') as f:
            records = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as ex:
        raise RuntimeError('防重复记录无法读取，请先人工核对：' + str(ex)[:100])
    if not isinstance(records, dict):
        raise RuntimeError('防重复记录格式异常，请先人工核对')
    return records
def reminder_ledger_set(key, title, when, marker, status):
    ledger = reminder_ledger_load()
    ledger[key] = {'title': title, 'datetime': when.strftime('%Y-%m-%dT%H:%M'),
                   'marker': marker, 'status': status, 'updated': now_iso()}
    atomic_json(REMINDER_LEDGER_PATH, ledger)
def reminder_ledger_delete(key):
    ledger = reminder_ledger_load()
    if key in ledger:
        del ledger[key]
        atomic_json(REMINDER_LEDGER_PATH, ledger)
def reminder_legacy_success(key):
    previous = get_state()
    for event in previous.get('events', []):
        if (event.get('tool') != 'reminder.create' or event.get('status') != 'ok'
                or event.get('verified') is not True):
            continue
        params = event.get('params', {})
        try:
            if reminder_key(params.get('title'), parse_local_dt(params.get('datetime'))) == key:
                return True
        except (TypeError, ValueError):
            pass
    return False
def reminder_seed_prior_state(previous):
    for event in previous.get('events', []):
        if (event.get('tool') != 'reminder.create' or
            event.get('status') != 'ok' or event.get('verified') is not True):
            continue
        params = event.get('params', {})
        try:
            title = params.get('title', '').strip()
            when = parse_local_dt(params.get('datetime', ''))
            key = reminder_key(title, when)
        except (TypeError, ValueError, AttributeError):
            continue
        ledger = reminder_ledger_load()
        if key not in ledger:
            reminder_ledger_set(key, title, when, '', 'verified')
def reminder_local_datetime(value):
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value
def reminder_same_minute(actual, expected):
    first = reminder_local_datetime(actual)
    second = reminder_local_datetime(expected)
    if first is None or second is None:
        return False
    return first.replace(second=0, microsecond=0) == second.replace(second=0, microsecond=0)
def reminder_same_title(item, title):
    return str(getattr(item, 'title', '') or '').strip() == title.strip()
def reminder_exact_match(item, title, date):
    if not reminder_same_title(item, title):
        return False
    if not reminder_same_minute(getattr(item, 'due_date', None), date):
        return False
    return any(reminder_same_minute(getattr(alarm, 'date', None), date)
               for alarm in (getattr(item, 'alarms', None) or []))
def reminder_pending(state, choice, marker, date):
    return {'tool': 'reminder.create', 'marker': marker,
            'title': choice['title'].strip(), 'datetime': date.isoformat(),
            'name': 'Pythonista Reminders', 'fingerprint': action_fingerprint(choice),
            'origin_step': state['steps'],
            'ledger_key': reminder_key(choice['title'], date)}
def _local_reminder_list(choice):
    import reminders
    try:
        raw=list(reminders.get_reminders(completed=False) or [])
    except Exception as ex:
        return {'status':'failed','result':'读取提醒事项失败：'+str(ex)[:150]}
    start = parse_local_dt(choice['datetime'],'查询开始') if choice['datetime'] else None
    end = parse_local_dt(choice['end_datetime'],'查询结束') if choice['end_datetime'] else None
    if bool(start) != bool(end):
        return {'status':'failed','result':'日期范围必须同时提供开始与结束'}
    found=[]
    for entry in raw:
        name=str(getattr(entry,'title','') or '').strip()
        if not name:
            continue
        due=getattr(entry,'due_date',None)
        date_only_source='[PYVoiceAgent dayonly:' in str(getattr(entry,'notes','') or '')
        if start is not None:
            if not isinstance(due,datetime):
                continue
            local=due.astimezone().replace(tzinfo=None) if due.tzinfo else due
            if not (local<end):
                continue
        else:
            local=due.astimezone().replace(tzinfo=None) if isinstance(due,datetime) and due.tzinfo else due
        found.append((local,name,date_only_source))
    found.sort(key=lambda item:(item[0] is None,item[0] or datetime.max,item[1]))
    if not found:
        return {'status':'ok','verified':True,'result':'未查询到符合条件的未完成提醒事项。'}
    lines=[]
    for when,title,date_only_source in found[:25]:
        if isinstance(when,datetime):
            day=when.strftime('%m-%d')+'（仅日期）' if date_only_source else when.strftime('%m-%d %H:%M')
        else:
            day='无到期日'
        lines.append('• {}  {}'.format(day,title[:90]))
    tail='；另有 {} 项未展示'.format(len(found)-25) if len(found)>25 else ''
    return {'status':'ok','verified':True,'result':'本地查询到 {} 项未完成提醒{}：\n{}'.format(len(found),tail,'\n'.join(lines))}
def _local_reminder_complete(choice):
    import reminders
    target=choice['title'].strip()
    if not target:
        return {'status':'failed','result':'缺少提醒标题'}
    try:
        incomplete=list(reminders.get_reminders(completed=False) or [])
    except Exception as ex:
        return {'status':'failed','result':'读取未完成事项失败：'+str(ex)[:140]}
    exact=[x for x in incomplete if str(getattr(x,'title','') or '').strip().casefold()==target.casefold()]
    if len(exact)!=1:
        return {'status':'failed','result':('未找到精确匹配的未完成提醒，未修改任何事项' if not exact
                else '找到 {} 个同名待办，为避免误操作已拒绝修改'.format(len(exact)) + '；请先在提醒事项中区分标题')}
    if not prompt_alert('确认标记提醒为已完成','将以下提醒标记为已完成：\n'+target):
        return {'status':'declined','result':'用户取消标记完成'}
    try:
        before=sum(str(getattr(x,'title','') or '').strip().casefold()==target.casefold()
                   for x in reminders.get_reminders(completed=True) or [])
        exact[0].completed=True
        exact[0].save()
        updated=list(reminders.get_reminders(completed=True) or [])
        count=sum(str(getattr(x,'title','') or '').strip().casefold()==target.casefold() for x in updated)
        if count<=before:
            return {'status':'needs_review','result':'系统保存后未能独立确认完成状态；请打开苹果提醒事项核验'}
        return {'status':'ok','verified':True,'result':'已在苹果提醒事项中读回确认完成：'+target}
    except Exception as ex:
        return {'status':'needs_review','result':'标记完成期间出错，不能断定是否已更新，请在提醒事项核验：'+str(ex)[:140]}
def _contact_text(value):
    return ''.join(str(value or '').casefold().split())
def _local_contacts_lookup(choice):
    import contacts
    original=choice['title'].strip()
    term=_contact_text(original)
    if not term or len(original)>80:
        return {'status':'failed','result':'需要明确的姓名或公司关键词'}
    try:
        people=list(contacts.get_all_people() or [])
    except Exception as ex:
        return {'status':'failed','result':'读取联系人失败，请检查系统权限：'+str(ex)[:140]}
    hits=[]
    for person in people:
        name=str(getattr(person,'full_name','') or '').strip()
        company=str(getattr(person,'organization','') or '').strip()
        nn,cc=_contact_text(name),_contact_text(company)
        if nn==term and nn:
            score=0
        elif nn.startswith(term) and nn:
            score=1
        elif term in nn:
            score=2
        elif cc==term and cc:
            score=3
        elif cc.startswith(term) and cc:
            score=4
        elif term in cc:
            score=5
        else:
            continue
        fields=[]
        for field in ('phone','email'):
            for item in (getattr(person,field,None) or [])[:3]:
                if not isinstance(item,(tuple,list)) or len(item)<2:
                    continue
                value=str(item[1] or '').strip()
                if value:
                    fields.append(('电话' if field=='phone' else '邮箱')+': '+value[:110])
        fields=list(dict.fromkeys(fields))[:5]
        hits.append((score,nn,cc,name,company,fields))
    if not hits:
        return {'status':'ok','verified':True,
                'result':'本地通讯录未找到「{}」。如未授权访问，请检查 iOS 设置中的 Pythonista 通讯录权限。'.format(original[:40])}
    exact=[item for item in hits if item[0]==0]
    results=exact if exact else hits
    results.sort(key=lambda item:(item[0],len(item[1]) if item[0]<=2 else len(item[2]),item[1],item[2]))
    chunks=[]
    for score,_,__,name,org,details in results[:8]:
        chunks.append('• '+(name[:90] or '未命名联系人')+(' / '+org[:50] if org else '')+
                      ('\n    '+'；'.join(details) if details else '\n    无电话或邮箱'))
    total=len(results)
    suffix='（另有 {} 人未展示，请补充姓名或公司缩小范围）'.format(total-8) if total>8 else ''
    lead='本地通讯录精确匹配 {} 人'.format(total) if exact else '本地通讯录找到 {} 人'.format(total)
    return {'status':'ok','verified':True,
            'result':'{}{}：\n{}'.format(lead,suffix,'\n'.join(chunks))}
def _open_native_maps(url):
    from objc_util import ObjCClass, nsurl, on_main_thread
    @on_main_thread
    def send():
        app = ObjCClass('UIApplication').sharedApplication()
        return bool(app.openURL_(nsurl(url)))
    return send()
def _local_maps_search(choice):
    query=choice['title'].strip()
    if not query or len(query)>160:
        return {'status':'failed','result':'需要明确的地图目的地'}
    url='maps://?'+urlencode({'q':query})
    try:
        if not _open_native_maps(url):
            return {'status':'failed',
                    'result':'iOS 未接受原生地图链接，已停止；没有打开网页作为替代，请检查苹果地图是否可用。'}
    except Exception as ex:
        return {'status':'failed',
                'result':'调用 iOS 原生地图失败：'+str(ex)[:180]+'；没有改用内置网页。'}
    return {'status':'ok','verified':False,
            'result':'已向 iOS 发送原生苹果地图搜索请求：「{}」。请核对 App 是否切换成功。'.format(query)}
def _ios_calendar_events(start, end):
    from objc_util import ObjCClass
    event_store_class=ObjCClass('EKEventStore')
    authorization=int(event_store_class.authorizationStatusForEntityType_(0))
    if authorization not in (3,4):
        raise PermissionError('Pythonista 未获得“日历完整访问”权限；当前不读取日程。请先检查 iOS 设置中的 Pythonista 日历权限；如没有完整访问选项，本机需另接只读快捷指令。')
    store=event_store_class.alloc().init()
    NSDate=ObjCClass('NSDate')
    start_obj=NSDate.dateWithTimeIntervalSince1970_(start.timestamp())
    end_obj=NSDate.dateWithTimeIntervalSince1970_(end.timestamp())
    predicate=store.predicateForEventsWithStartDate_endDate_calendars_(start_obj,end_obj,None)
    events=store.eventsMatchingPredicate_(predicate)
    out=[]
    for ev in list(events or []):
        try:
            title=str(ev.title() or '未命名日程').strip()
            begin=datetime.fromtimestamp(float(ev.startDate().timeIntervalSince1970())).astimezone()
            finish=datetime.fromtimestamp(float(ev.endDate().timeIntervalSince1970())).astimezone()
            location=str(ev.location() or '').strip()
            out.append({'title':title[:120],'start':begin.isoformat(timespec='minutes'),
                        'end':finish.isoformat(timespec='minutes'),'location':location[:90]})
        except Exception:
            continue
    out.sort(key=lambda item:(item['start'],item['title']))
    return out[:100]
def _calendar_read(choice):
    parse_local_dt(choice['datetime'],'查询开始')
    parse_local_dt(choice['end_datetime'],'查询结束')
    start=datetime.fromisoformat(choice['datetime'].replace('Z','+00:00')).astimezone()
    end=datetime.fromisoformat(choice['end_datetime'].replace('Z','+00:00')).astimezone()
    if end <= start or end-start>timedelta(days=31):
        raise ValueError('日期范围必须大于0且不超过31天')
    return _ios_calendar_events(start,end)
def _local_calendar_list(choice):
    try:
        rows=_calendar_read(choice)
    except PermissionError as ex:
        return {'status':'unavailable','result':str(ex)}
    except Exception as ex:
        return {'status':'failed','result':'无法读取苹果日历：'+str(ex)[:180]}
    if not rows:
        return {'status':'ok','verified':True,'result':'已查询有权限读取的苹果日历，该时间段未找到日程（不代表其他未授权日历也为空）。'}
    lines=[]
    for row in rows[:25]:
        lines.append('• {} — {}  {}{}'.format(
            row['start'][5:16],row['end'][11:16],row['title'],
            ' · '+row['location'] if row['location'] else ''))
    extra='；另有 {} 项未展示'.format(len(rows)-25) if len(rows)>25 else ''
    return {'status':'ok','verified':True,
            'result':'本地日历查询到 {} 项{}：\n{}'.format(len(rows),extra,'\n'.join(lines))}
def _agent_notes_index_load():
    records=read_json(AGENT_NOTES_INDEX, {'items': []})
    if not isinstance(records,dict) or not isinstance(records.get('items'),list):
        raise ValueError('本地备忘录索引文件异常')
    return records['items']
def _index_agent_note_after_callback(state,pending):
    if not state.get('single_plan') or not isinstance(state.get('plan'),list):
        return
    index=int(state.get('plan_index',-1))
    if index < 0 or index >= len(state['plan']):
        return
    note=state['plan'][index]
    if note.get('tool')!='apple_notes.create':
        return
    marker=str(pending.get('marker') or '')
    if not marker:
        return
    records=_agent_notes_index_load()
    if any(item.get('marker')==marker for item in records if isinstance(item,dict)):
        return
    records.append({'marker':marker,'created':now_iso(),
                    'title':str(note.get('title',''))[:150],
                    'text':str(note.get('text',''))[:2500],
                    'source':'PYAgentNotes callback OK (not independent Notes readback)'})
    atomic_json(AGENT_NOTES_INDEX,{'items':records[-200:]})
def _local_agent_notes_search(choice):
    keyword=str(choice['title'] or '').strip().casefold()
    if not keyword or len(keyword)>100:
        return {'status':'failed','result':'请提供1~100字的备忘录关键词'}
    try:
        records=_agent_notes_index_load()
    except Exception as ex:
        return {'status':'failed','result':'本地索引无法读取：'+str(ex)[:150]}
    matches=[x for x in records if isinstance(x,dict) and (
        keyword in str(x.get('title','')).casefold() or
        keyword in str(x.get('text','')).casefold())]
    if not matches:
        return {'status':'ok','verified':False,
                'result':'本助手的本地索引没有找到「{}」。仅覆盖 V1.7 起经成功回调创建的备忘录，并非苹果备忘录全库搜索。'.format(choice['title'][:70])}
    lines=[]
    for item in reversed(matches[-10:]):
        lines.append('• {}  {}\n  {}'.format(
            str(item.get('created',''))[:16],
            str(item.get('title',''))[:65],
            str(item.get('text','')).replace('\n',' ')[:120]))
    return {'status':'ok','verified':False,'result':
            '本助手本地索引匹配 {} 条（非 Apple Notes 独立核验）：\n{}'.format(
                len(matches),'\n'.join(lines))}
