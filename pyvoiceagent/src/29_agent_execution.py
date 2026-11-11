def run_tool(state, choice):
    tool = choice['tool']
    if tool == 'app.navigate':
        return _app_route_handoff(state, choice)
    if tool in SYSTEM_MODULES and not verified_system_module(tool):
        return {'status': 'unavailable',
                'result': '系统模块尚未安装并验收，未发送任务：' + tool}
    if tool in ('reminder.create', 'apple_notes.create', 'calendar.create', 'shortcut.run'):
        queue = read_recovery_queue()
        if deferred_duplicate(queue, tool, choice.get('title'), action_fingerprint(choice)):
            return {'status': 'blocked_duplicate',
                    'result': '有同功能同标题的待核验写入；为避免重复，已跳过该项但其他任务可继续。'}
    if tool in ('local_note.save','apple_notes.create','calendar.create','shortcut.run'):
        fp = action_fingerprint(choice)
        if any(e.get('params',{}).get('fingerprint') == fp and
               e.get('status') == 'ok' for e in state.get('events', [])):
            return {'status':'ok', 'verified': False, 'result': '此前已经执行相同参数；本次未重复写入，未重新核验系统结果。'}
    if tool == 'text.respond':
        return {'status':'ok','verified':False,'result':choice['text'][:3500]}
    if tool == 'calendar.list':
        return start_bridge_tool(state,choice,'calendar.list',CALENDAR_READ_SHORTCUT)
    if tool == 'notes.search_agent':
        return _local_agent_notes_search(choice)
    if tool == 'reminder.list':
        return _local_reminder_list(choice)
    if tool == 'reminder.complete':
        return _local_reminder_complete(choice)
    if tool == 'contacts.lookup':
        return _local_contacts_lookup(choice)
    if tool == 'maps.search':
        return _local_maps_search(choice)
    if tool == 'clipboard.read':
        import clipboard
        if not prompt_alert('读取剪贴板', '将读取剪贴板文字并发送到 DeepSeek 官方 API 进行分析，可能涉及隐私。是否允许？'):
            return {'status': 'declined', 'result': '用户拒绝读取/上传剪贴板'}
        content = clipboard.get()
        if not isinstance(content, str) or not content.strip():
            return {'status': 'failed', 'result': '剪贴板为空或不是文字'}
        original_len = len(content)
        content = content[:MAX_CLIPBOARD]
        return {'status': 'ok', 'result': {'content': content,
                'truncated': original_len > MAX_CLIPBOARD, 'original_chars': original_len}}
    if tool == 'local_note.save':
        title = choice['title'].strip()
        body = choice['text'].strip()
        if not body:
            return {'status': 'failed', 'result': '笔记正文为空'}
        sample = (title + '\n\n' + body)[:650]
        if not (state.get('single_plan') and state.get('plan_approved')) and not prompt_alert('保存本地笔记', '仅保存在 Pythonista 的 txt 文件（不是苹果备忘录）：\n' + sample):
            return {'status': 'declined', 'result': '用户取消保存笔记'}
        clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', title).strip(' .')[:45] or '笔记'
        os.makedirs(NOTES_DIR, exist_ok=True)
        fname = '{}_{}_{}.txt'.format(datetime.now().strftime('%Y%m%d_%H%M%S'), clean, uuid.uuid4().hex[:6])
        path = os.path.join(NOTES_DIR, fname)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(title + '\n\n' + body + '\n')
        with open(path, 'r', encoding='utf-8') as f:
            if f.read() != title + '\n\n' + body + '\n':
                return {'status': 'failed', 'result': '笔记写入后复核不一致'}
        return {'status': 'ok', 'result': '本地文件已保存并读回核验：' + path}
    if tool == 'reminder.create':
        import reminders
        title = choice['title'].strip()
        timestr = choice['datetime'].strip()
        try:
            date = parse_local_dt(timestr, '提醒时间')
            if date <= datetime.now():
                return {'status': 'failed', 'result': '提醒时间已过去，请重新确定日期'}
            if date > datetime.now() + timedelta(days=365 * 5):
                return {'status': 'failed', 'result': '提醒时间超过五年，拒绝创建'}
        except (TypeError, ValueError):
            return {'status': 'failed', 'result': '提醒时间应为带时区的 ISO 8601：' + timestr[:80]}
        marker = '[PYVoiceAgent:{}:{}]'.format(state['id'], state['steps'])
        key = reminder_key(title, date)
        try:
            ledger = reminder_ledger_load()
            old_success = reminder_legacy_success(key)
        except (OSError, ValueError, RuntimeError) as ex:
            return {'status': 'failed', 'result': str(ex)[:240]}
        try:
            existing = list(reminders.get_reminders(completed=False) or [])
        except Exception as ex:
            return {'status': 'failed', 'result': '读取苹果提醒事项失败，未尝试创建：' + str(ex)[:150]}
        exact = [r for r in existing if reminder_exact_match(r, title, date)]
        if exact:
            try:
                reminder_ledger_set(key, title, date,
                                    str(getattr(exact[0], 'notes', '') or '')[-90:], 'verified')
            except (OSError, RuntimeError) as ex:
                return {'status': 'failed', 'result': '已发现提醒，但记录防重复凭据失败：' + str(ex)[:150]}
            return {'status': 'ok', 'verified': True, 'outcome': 'existing',
                    'result': '已在苹果提醒事项中读到相同标题、日期和闹铃，跳过重复创建：{}，{}'.format(
                        title, date.strftime('%Y-%m-%d %H:%M'))}
        suspect = [r for r in existing if (
            marker in (getattr(r, 'notes', '') or '') or
            (reminder_same_title(r, title) and reminder_same_minute(
                getattr(r, 'due_date', None), date)))]
        if key in ledger or old_success or suspect:
            state['pending'] = reminder_pending(state, choice, marker, date)
            state['status'] = 'needs_review'
            put_state(state)
            reason = ('防重复记录显示这个提醒先前已创建/尝试创建，'
                      '但本次系统查询未返回完全匹配项' if key in ledger or old_success
                      else '找到同标题同时间提醒，但到期/闹铃字段不匹配')
            return {'status': 'needs_review', 'result': reason +
                    '；已拦截再次创建，请到苹果提醒事项中核对，必要时使用菜单第11项人工核验'}
        if not (state.get('single_plan') and state.get('plan_approved')) and not prompt_alert('确认创建提醒', '{}\n时间：{}\n备注：{}'.format(
                title, date.strftime('%Y-%m-%d %H:%M'), choice['notes'][:220])):
            return {'status': 'declined', 'result': '用户取消创建提醒'}
        state['pending'] = reminder_pending(state, choice, marker, date)
        state['status'] = 'needs_review'
        put_state(state)
        try:
            reminder_ledger_set(key, title, date, marker, 'intent')
        except (OSError, RuntimeError) as ex:
            return {'status': 'needs_review', 'result':
                    '防重复记录写入失败，已阻止创建：' + str(ex)[:150]}
        try:
            r = reminders.Reminder()
            r.title = title
            r.notes = choice['notes'].strip()[:1400]
            r.due_date = date
            alarm = reminders.Alarm()
            alarm.date = date
            r.alarms = [alarm]
            r.save()
        except Exception as ex:
            return {'status': 'needs_review', 'result':
                    '系统保存时出现异常，结果可能已写入，请先打开提醒事项检查：' + str(ex)[:150]}
        for attempt in range(3):
            try:
                found = list(reminders.get_reminders(completed=False) or [])
                if sum(1 for x in found if reminder_exact_match(x, title, date)
                       and str(getattr(x, 'notes', '') or '').strip() == choice['notes'].strip()[:1400]) == 1:
                    try:
                        reminder_ledger_set(key, title, date, marker, 'verified')
                    except (OSError, RuntimeError) as ex:
                        return {'status': 'needs_review', 'result':
                                '系统提醒已读回，但防重复记录无法保存：' + str(ex)[:150]}
                    state['pending'] = None
                    state['status'] = 'running'
                    put_state(state)
                    return {'status': 'ok', 'verified': True, 'outcome': 'created',
                            'result': '已保存并从苹果提醒事项读回核验标题、到期时间和闹铃：{}，{}'.format(
                                title, date.strftime('%Y-%m-%d %H:%M'))}
            except Exception:
                pass
            if attempt < 2:
                time.sleep(0.4)
        return {'status': 'needs_review', 'result':
                '已请求保存，但未能核验标题/时间/闹铃；已经锁定防重记录，禁止自动重试'}
    if tool in ('apple_notes.create', 'calendar.create', 'shortcut.run'):
        if tool == 'shortcut.run':
            lib = local_registry()
            ident = choice['shortcut_id']
            if ident not in lib:
                return {'status':'failed', 'result': '工具 ID 未登记：' + ident[:40]}
            dest = lib[ident]['name']
        else:
            dest = verified_system_module(tool)
            if not dest:
                return {'status': 'unavailable', 'result': '模块不可用，未发送：' + tool}
        try:
            return start_bridge_tool(state, choice, tool, dest)
        except (ValueError, RuntimeError) as ex:
            return {'status':'failed', 'result': str(ex)}
    if tool == 'user.ask':
        response = _ask_clarification(choice['text'][:180] or '请补充信息')
        if response is None or not response.strip():
            return {'status': 'declined', 'result': '用户未提供补充信息'}
        return {'status': 'ok', 'result': '用户回答：' + response.strip()[:2000]}
    if tool == 'task.finish':
        return {'status': 'finished', 'result': choice['text'] or '任务已结束'}
    if tool == 'shortcut.hub_echo':
        return start_bridge_tool(state, choice, tool, BRIDGE_SHORTCUT)
    if tool == 'shortcut.echo':
        import shortcuts
        if not prompt_alert('V1.2 跨 App 测试', '将调用旧版的 {}。请确认它已存在。'.format(LEGACY_BRIDGE)):
            return {'status': 'declined', 'result': '用户未允许跳转旧版快捷指令'}
        token = 'agent_' + uuid.uuid4().hex[:16]
        state['pending'] = {'tool': tool, 'token': token,
                            'expected': 'DONE_' + token.upper(),
                            'created': datetime.now().timestamp()}
        state['status'] = 'awaiting_callback'
        put_state(state)
        url = 'shortcuts://run-shortcut?' + urlencode({'name': LEGACY_BRIDGE,
                   'input': 'text', 'text': token})
        shortcuts.open_url(url)
        return {'status': 'waiting', 'result': '已跳转旧版诊断快捷指令，等待回传'}
    raise ValueError('未授权的工具名：' + str(tool))
def verified_final_summary(state, ai_text=''):
    writes = ('reminder.create', 'reminder.create_day', 'reminder.complete','local_note.save', 'apple_notes.create',
              'calendar.create', 'shortcut.run')
    events = [x for x in state.get('events', []) if x.get('tool') in writes]
    if state.get('research_origin') == 'calendar.assist' and not events:
        answers = [str(x.get('result','')) for x in state.get('events', [])
                   if x.get('tool') == 'text.respond' and x.get('status') == 'ok']
        if answers:
            return '\n'.join(answers)[:3500]
        return str(state.get('calendar_insights', ai_text or '日程读取完成'))[:3500]
    if not events:
        readings = [str(item.get('result','')) for item in state.get('events', [])
                    if item.get('tool') in LOCAL_READ_ACTIONS]
        return ('\n'.join(readings) if readings else str(ai_text or '任务已结束'))[:1000]
    lines = []
    labels = {'reminder.create': '提醒', 'reminder.create_day':'仅日期工作待办', 'local_note.save': '本地笔记',
              'apple_notes.create': '苹果备忘录', 'calendar.create': '日历',
              'shortcut.run': '快捷指令', 'reminder.complete':'标记提醒完成'}
    for e in events:
        tool, status = e.get('tool'), e.get('status')
        label = labels.get(tool, tool)
        title = str(e.get('params', {}).get('title', '') or '')[:50]
        when = str(e.get('params', {}).get('datetime', '') or '')[:30]
        if status == 'ok':
            if e.get('verified'):
                word = '已核验' if e.get('outcome') != 'existing' else '已存在，未重复创建'
            else:
                word = '仅收到工具成功报告，未独立核验'
        elif status == 'needs_review':
            word = '待人工核验'
        elif status == 'failed':
            word = '失败'
        elif status == 'unavailable':
            word = '功能未就绪，未执行'
        elif status == 'blocked_duplicate':
            word = '已拦截未核验的重复请求'
        elif status == 'declined':
            word = '已取消'
        else:
            word = '未确认(' + str(status) + ')'
        lines.append('• {} {} {} {}'.format(word, label, title, when).strip())
    if any(e.get('status') != 'ok' for e in events):
        lines.insert(0, '任务存在未成功或未核验的操作，请逐项核对：')
    else:
        lines.insert(0, '逐项执行结果：')
    for item in state.get('events', []):
        if item.get('tool') in LOCAL_READ_ACTIONS:
            lines.append(str(item.get('result',''))[:350])
    return '\n'.join(lines)[:1000]
def _brief_result_text(result, limit=120):
    data=str(result or '')
    if not data:
        return ''
    lines=data.splitlines()
    if len(lines)<=3 and len(data)<=limit:
        return data
    head=lines[0]
    if head.startswith('本地查询到') and len(lines)>1:
        head+=' / '+('、'.join(line.strip().lstrip('• ')[:34] for line in lines[1:3]))
    elif (head.startswith('本地通讯录精确匹配') or head.startswith('本地通讯录找到')) and len(lines)>2:
        head+=' / '+lines[1].strip().lstrip('• ')[:30]
        if lines[2].lstrip().startswith(('电话','邮箱')):
            head+=' '+lines[2].strip()[:38]
    return head[:limit].rstrip() + ('…' if len(head)>limit else '')
def concise_execution_summary(state):
    if state.get('research_origin') == 'calendar.assist':
        status = '分析已完成' if state.get('status') == 'finished' else str(state.get('status',''))
        return ('日历已读取（快捷指令回调），{}。\n\n{}\n{}'.format(
            status, str(state.get('final',''))[:670], token_usage_report(state)))[:950]
    events=state.get('events', [])
    ok=sum(item.get('status')=='ok' for item in events)
    total=len(events)
    waiting=sum(item.get('status')=='handoff' for item in events)
    lines=['操作结果：{} / {} 项报告成功{}'.format(
        ok,total,'（{} 项待系统跳转）'.format(waiting) if waiting else '')]
    labels={'reminder.list':'提醒查询','contacts.lookup':'联系人','maps.search':'地图',
            'calendar.list':'日历查询','notes.search_agent':'助手备忘索引',
            'webpage.summarize':'网页分析','calendar.assist':'日程分析',
            'apple_notes.create':'备忘录','calendar.create':'日历',
            'reminder.create':'新提醒','reminder.complete':'完成提醒',
            'local_note.save':'本地笔记','text.respond':'AI 内容'}
    for item in events:
        tool=item.get('tool','')
        label=labels.get(tool,tool)
        status=item.get('status')
        if status=='handoff' and tool=='app.navigate':
            msg='已请求 iOS 跳转（目标 App 尚未核验）'
        elif status=='handoff' and tool=='maps.search':
            msg='点击确定后将跳转苹果地图；尚未核验'
        elif status!='ok':
            msg='未成功：'+_brief_result_text(item.get('result'),110)
        elif tool in ('apple_notes.create','calendar.create','shortcut.run'):
            msg='快捷指令回调成功，待到苹果 App 核验'
        elif tool=='maps.search':
            msg='已请求打开原生地图（未核验 App）'
        elif tool in ('reminder.list','contacts.lookup','text.respond','calendar.list','notes.search_agent'):
            msg=_brief_result_text(item.get('result'),160)
        elif item.get('verified'):
            msg='已从系统读回核验'
        else:
            msg='操作已报告成功，未独立核验'
        lines.append('• {}：{}'.format(label,msg))
    if state.get('status') not in ('finished',):
        lines.append('当前状态：'+str(state.get('status',''))[:30])
    lines.append(token_usage_report(state))
    return '\n'.join(lines)[:950]
def final_report(state, show_dialog=True):
    if state.get('research_origin') == 'calendar.assist':
        print('\n========= 日历分析结果 =========')
        print(str(state.get('final', '未生成分析报告'))[:3500])
        for event in state.get('events', []):
            if event.get('tool') in ('reminder.create','apple_notes.create','local_note.save'):
                print('• {} [{}] {}'.format(event.get('tool'), event.get('status'),
                      str(event.get('result',''))[:120]))
        print('日历读取通道：PYAgentCalendarRead（单次只读回调）')
        print(token_usage_report(state))
        print('============================')
        if state.get('voice_session'):
            _voice_report(state)
        elif show_dialog:
            try:
                import dialogs
                dialogs.alert('PYVoiceAgent 日历分析', concise_execution_summary(state),
                              '确定', hide_cancel_button=True)
            except Exception:
                pass
        return
    print('\n========= 执行结果 =========')
    print('本地执行总结（以逐项执行记录为准）：' + str(state.get('final', '任务已结束')))
    for event in state.get('events', []):
        limit = 2200 if event.get('tool') in LOCAL_READ_ACTIONS + LOCAL_WRITE_ACTIONS else 120
        print('• {}  [{}] {}'.format(event.get('tool'), event.get('status'),
               str(event.get('result', ''))[:limit]))
    print(token_usage_report(state))
    print('=============================')
    if state.get('voice_session'):
        _voice_report(state)
        return
    if not show_dialog:
        return
    try:
        import dialogs
        dialogs.alert('PYVoiceAgent 执行结果', concise_execution_summary(state),
                      '确定', hide_cancel_button=True)
    except Exception:
        pass
def drive_agent(state, planner=None, executor=None):
    planner = planner or call_planner
    executor = executor or run_tool
    if state.get('status') in ('awaiting_callback', 'needs_review'):
        return state
    state['status'] = 'running'
    put_state(state)
    while state['steps'] < MAX_STEPS:
        try:
            decision = parse_decision(planner(state))
        except Exception as ex:
            state['status'] = 'paused'
            state['error'] = str(ex)
            put_state(state)
            print('AI 规划暂停：' + str(ex))
            return state
        tool = decision['tool']
        if tool in LOCAL_READ_ACTIONS + LOCAL_WRITE_ACTIONS + ('app.navigate',):
            state['status'] = 'paused'
            state['error'] = '这类本地隐私查询/修改请使用首页语音或文字的一次规划模式'
            put_state(state)
            return state
        print('\nAI 下一步：{} | {}'.format(tool, decision['reason'][:150]))
        try:
            result = executor(state, decision)
        except Exception as ex:
            print('工具执行异常：{}'.format(ex))
            result = {'status': 'failed', 'result': '{}: {}'.format(type(ex).__name__, str(ex)[:300])}
        if result['status'] == 'waiting':
            return state
        args = {'title': decision['title'][:100], 'datetime': decision['datetime'][:100],
                'end_datetime': decision['end_datetime'][:100],
                'shortcut_id': decision['shortcut_id'][:50]}
        if tool in ('local_note.save','reminder.create','apple_notes.create','calendar.create','shortcut.run'):
            args['fingerprint'] = action_fingerprint(decision)
        if tool == 'user.ask':
            args['question'] = decision['text'][:160]
        create_event(state, tool, args, result)
        if result['status'] == 'finished':
            state['status'] = 'finished'
            state['final'] = verified_final_summary(state, result.get('result', ''))
            put_state(state)
            final_report(state)
            return state
        if result['status'] == 'needs_review':
            state['status'] = 'needs_review'
            state['error'] = str(result.get('result', ''))[:400]
            put_state(state)
            print('【待人工核验】' + state['error'])
            return state
        if result['status'] in ('unavailable', 'blocked_duplicate'):
            recent = [x for x in state['events'][-3:]
                      if x['tool'] == tool and x['status'] in ('unavailable', 'blocked_duplicate')]
            if len(recent) >= 2:
                state['status'] = 'paused'
                state['error'] = '连续调用不可执行的工具，停止规划；未产生新的系统写入。'
                put_state(state)
                return state
            continue
        if result['status'] == 'declined':
            state['status'] = 'paused'
            state['error'] = '用户取消了操作；没有自动重试。'
            put_state(state)
            return state
        if result['status'] == 'failed':
            recent = [x for x in state['events'][-3:] if x['tool'] == tool and x['status'] == 'failed']
            if len(recent) >= 2:
                state['status'] = 'paused'
                state['error'] = '同一个工具连续出错，已停止以防重复执行。'
                put_state(state)
                return state
    state['status'] = 'paused'
    state['error'] = '达到每次最多 {} 步的安全限制，已暂停；请查看报告，必要时新建任务。'.format(MAX_STEPS)
    put_state(state)
    return state
def callback(answer):
    state = get_state()
    p = state.get('pending') or {}
    if state.get('status') != 'awaiting_callback' or not p or p.get('tool') != 'shortcut.echo':
        print('没有旧版等待中的诊断任务，旧回调被忽略。')
        return False
    elapsed = datetime.now().timestamp() - p.get('created', 0)
    expected = str(p.get('expected', ''))
    if elapsed < 0 or elapsed > 300 or not hmac.compare_digest(str(answer), expected):
        state['status'] = 'paused'
        state['error'] = '快捷指令回传超时或编号不匹配；不计为成功。'
        put_state(state)
        print(state['error'])
        return False
    state['pending'] = None
    state['status'] = 'running'
    create_event(state, 'shortcut.echo', {}, {'status': 'ok', 'result': '快捷指令回传编号一致：' + expected})
    print('[PASSED] PYAgentBridge 双向回传成功')
    drive_agent(state)
    return True
import hashlib as _sb_hashlib
import ipaddress as _sb_ipaddress
import json as _sb_json
import os as _sb_os
import plistlib as _sb_plistlib
import re as _sb_re
import uuid as _sb_uuid
from urllib.parse import urlsplit as _sb_urlsplit
_SB_ROOT = "PYVoiceAgent_Data/GeneratedShortcuts"
_SB_ALLOWED = frozenset((
    "is.workflow.actions.showresult",
    "is.workflow.actions.url",
    "is.workflow.actions.openurl",
    "is.workflow.actions.urlencode",
))
_SB_TEMPLATES = ("show_input","show_text","open_web","apple_map_search")
_SB_MAX_ACTIONS = 5
_SB_CMD = _sb_re.compile(r"^(?:请|请你|帮我|给我)?(?:创建|生成|制作|新建)(?:一个|一条|个)?(?:苹果)?快捷指令(?:，|,|：|:|\s)*",_sb_re.I)
