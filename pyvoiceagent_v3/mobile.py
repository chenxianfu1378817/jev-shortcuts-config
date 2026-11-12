"""V3 phone-first interface: Pythonista system dialogs, not a persistent UIKit/WebView.

All menus run sequentially on the Pythonista interpreter thread. No native
recording, UI worker, JS navigation or monkeypatching. Business logic is
imported from the independently tested V3 package.
"""
import datetime
import os
import sys
import traceback
import uuid
import webbrowser
from urllib.parse import urlencode

from .core.dispatcher import Agent
from .services.history import HistoryService
from .services.llm import DeepSeekText
from .services.native_routes import allowed_url
from .services.settings import THEMES, MODES
from .storage.sqlite_store import LocalStore

VERSION = '3.0.3'
KEY_SERVICE = 'PYVoiceAgent_DeepSeekV3'
KEY_ACCOUNT = 'main'
MAX_DISPLAY = 1600


def data_directory():
    return os.path.join(os.path.expanduser('~/Documents'), 'PYVoiceAgent_V3_Data')


def _key():
    try:
        import keychain
        return (keychain.get_password(KEY_SERVICE, KEY_ACCOUNT)
                or keychain.get_password('PYVoiceAgent_DeepSeek', 'main') or '')
    except (ImportError, ValueError, OSError):
        return ''


def create_agent(base=None):
    base = base or data_directory()
    store = LocalStore(os.path.join(base, 'agent_v3.sqlite3'))
    secret = _key()
    llm = DeepSeekText(secret) if secret else None
    return Agent(store, llm=llm)


def _alert(title, message):
    import console
    console.alert(title, str(message)[:MAX_DISPLAY], '确定', hide_cancel_button=True)


def _choose(title, options):
    import dialogs
    return dialogs.list_dialog(title, list(options))


def _text(title, default=''):
    import dialogs
    answer = dialogs.text_dialog(title, str(default)[:2000])
    return answer.strip() if isinstance(answer, str) else None


def _confirm(title, body, agree='确认'):
    import console
    try:
        result = console.alert(title, str(body)[:500], agree, '取消', hide_cancel_button=True)
        return result == 1
    except (KeyboardInterrupt, ValueError):
        return False


def _message(result):
    _alert('助手 · '+str(result.status), result.message)
    if result.status == 'waiting_consent':
        return 'consent'
    if result.status == 'waiting_confirmation':
        return 'handoff'
    return None


def _handoff(agent, task_id, confirmed, opener=None):
    """Only a launch request; never claim an app or Shortcut finished."""
    if opener is None:
        opener = webbrowser.open
    outcome = agent.confirm_handoff(task_id, bool(confirmed))
    if not confirmed or not outcome.fresh or outcome.status != 'handoff_ready':
        return outcome
    action = outcome.action or {}
    if action.get('kind') == 'ios_url_handoff':
        uri = action.get('url', '')
        if not allowed_url(uri):
            agent.mark_handoff_unverified(task_id)
            raise ValueError('未授权的应用地址，拒绝打开')
    else:
        name = action.get('shortcut_name', '')
        if not isinstance(name, str) or not name or len(name) > 80:
            agent.mark_handoff_unverified(task_id)
            raise ValueError('快捷指令名称无效，未尝试打开')
        text = action.get('input_text', '')
        if not isinstance(text, str) or len(text) > 2000:
            agent.mark_handoff_unverified(task_id)
            raise ValueError('快捷指令参数格式无效')
        params = {'name': name}
        if text:
            params.update({'input': 'text', 'text': text})
        uri = 'shortcuts://run-shortcut?' + urlencode(params)
    try:
        opened = opener(uri)
    except Exception:
        agent.mark_handoff_unverified(task_id)
        raise
    if opened is False:
        agent.mark_handoff_rejected(task_id)
        raise RuntimeError('iOS 拒绝打开外部地址')
    # A URL open request is not proof that the app or Shortcut completed.
    agent.mark_handoff_unverified(task_id)
    return outcome


def _send(agent, value):
    value = str(value or '').strip()
    if not value:
        return
    if len(value) > 2000:
        _alert('输入过长', '本版每次最多发送 2000 字，不会截断并执行。')
        return
    try:
        result = agent.submit(value, request_id=uuid.uuid4().hex)
        if result.status == 'waiting_consent':
            # Pressing Send authorizes sending this *text* to configured DeepSeek.
            # System tools still require a separate explicit confirmation.
            if agent.llm is None:
                _alert('DeepSeek 尚未配置',
                       '未从 Pythonista Keychain 读取到 API Key。请进入「设置 → DeepSeek API Key」。本次文字未联网。')
                agent.approve_remote(result.task_id, True)
                return
            # A DeepSeek response may select an allowed shortcut rather than
            # return text; handle that proposed handoff below.
            result = agent.approve_remote(result.task_id, True)
        if result.status == 'waiting_confirmation' and (result.action or {}).get('kind') == 'ios_url_handoff':
            outcome = _handoff(agent, result.task_id, True)
            if not outcome.fresh or outcome.status != 'handoff_ready':
                _message(outcome)
                return
            # A low-risk app launch follows the explicit user command, with no
            # extra approval tap. Do not mark it as completed.
            _alert('已尝试打开高德地图',
                   '已向 iOS 发出高德地图跳转请求，尚未开始路线导航。'
                   '若没有切换到地图 App，请核实是否已安装高德地图。')
            return
        if result.status == 'waiting_confirmation':
            action = result.action or {}
            info = ('快捷指令：{}\n参数：{}\n仅打开苹果快捷指令，不保证执行成功。'
                    .format(action.get('shortcut_name', ''),
                            str(action.get('input_text', ''))[:130]))
            approved = _confirm('系统工具授权', info, '打开快捷指令')
            outcome = _handoff(agent, result.task_id, approved)
            if approved and outcome.fresh and outcome.status == 'handoff_ready':
                _alert('等待核验', '已尝试转交苹果快捷指令。是否实际完成，请在快捷指令或对应 App 核对；不会自动重试。')
            elif approved:
                _message(outcome)
            return
        _message(result)
    except Exception as exc:
        # Do not include private prompt, URL, credentials or exception message.
        _alert('本次操作未确认', '操作未完成：'+type(exc).__name__+'。请在历史中核验后再尝试，避免重复系统写入。')


def _history(agent):
    rows = agent.history.list(limit=30)
    if not rows:
        _alert('历史记录', 'V3 暂无任务历史。可以在下方选择「旧版历史预览」。')
    labels = ['{} · {} · {}'.format(row['created_at'][:16],
                                   row['status'][:20], row['text'][:35]) for row in rows]
    labels.append('旧版历史预览（只读，不迁移）')
    selected = _choose('V3 历史记录（只读）', labels)
    if selected == '旧版历史预览（只读，不迁移）':
        legacy = os.path.join(os.path.expanduser('~/Documents'), 'PYVoiceAgent_Data')
        preview = HistoryService.preview_legacy(legacy, limit=25)
        entries = preview['entries']
        if entries:
            chosen = _choose('旧版历史（只读）',
                             ['{} · {}'.format(x['created'][:16], x['goal'][:45])
                              for x in entries])
            if chosen:
                _alert('旧版历史预览', chosen)
        else:
            _alert('旧版历史', '未发现可读取的旧版历史档案。')
        return
    if selected in labels:
        row = rows[labels.index(selected)]
        _alert('任务历史', '输入：{}\n状态：{}\n回复：{}'.format(
            row['text'][:300], row['status'], row['message'][:1100]))


def _tools(agent):
    while True:
        selected = _choose('快捷指令工具库', (
            '已登记工具', '登记一个快捷指令', '导入旧版快捷指令', '返回'))
        if not selected or selected == '返回':
            return
        if selected == '已登记工具':
            rows = agent.shortcuts.list()
            if not rows:
                _alert('工具库', '尚未登记工具。')
                continue
            labels = ['{} · {}{}'.format(x['tool_id'],x['shortcut_name'],
                                         '' if x['enabled'] else '（已停用）') for x in rows]
            selected_row = _choose('已登记工具', labels)
            if selected_row in labels:
                item = rows[labels.index(selected_row)]
                _alert('工具说明', '快捷指令：{}\n触发词：{}\n状态：{}\n系统执行必须二次确认。'.format(
                    item['shortcut_name'], '、'.join(item['aliases']),
                    '启用' if item['enabled'] else '停用'))
        elif selected == '导入旧版快捷指令':
            from .services.legacy_import import (preview_legacy_registry,
                                                 import_legacy_registry)
            legacy = os.path.join(os.path.expanduser('~/Documents'), 'PYVoiceAgent_Data')
            preview = preview_legacy_registry(legacy)
            count = len(preview['ready'])
            if not count:
                _alert('旧版快捷指令', '没有可安全导入的直达型快捷指令。'
                       '需要旧 PYAgentHub 桥接的工具不会自动迁移。')
                continue
            if _confirm('导入旧版快捷指令',
                        '找到 {} 项直达型工具，另有 {} 项不兼容而跳过。'
                        '只复制配置到 V3，绝不改动 V2 原文件。'
                        .format(count,preview['skipped']), '确认复制'):
                result = import_legacy_registry(agent.shortcuts, legacy)
                _alert('导入结果', '新增 {} 项，跳过 {} 项。'
                       '旧版配置完整保留；实际执行仍须每次授权。'
                       .format(len(result['imported']), result['skipped']))
        elif selected == '登记一个快捷指令':
            ident = _text('工具 ID（英文字母开头、下划线）')
            if not ident:
                continue
            name = _text('苹果快捷指令的精确名称')
            if not name:
                continue
            alias = _text('触发说法（例如：打开付款码）')
            if not alias:
                continue
            try:
                result = agent.shortcuts.register(
                    ident, name, [alias], description='通过用户确认后打开',
                    enabled=True, input_mode='none')
                _alert('登记完成', '登记成功：'+result['shortcut_name']+
                       '\n下次在输入框说「'+alias+'」可以选择打开。')
            except (ValueError, TypeError) as exc:
                _alert('登记未完成', type(exc).__name__+'：请检查 ID、名称和触发词。')


def _settings(agent):
    while True:
        current = agent.appearance.read()
        selected = _choose('设置 · V3', (
            '外观与主题 · '+current['theme'],
            '显示模式 · '+current['mode'],
            'DeepSeek API Key',
            '检查在线更新',
            '回退到升级前版本',
            '数据备份（V3 独立数据库）',
            '运行诊断与版本',
            '返回'))
        if not selected or selected == '返回':
            return
        if selected.startswith('外观与主题'):
            theme = _choose('选择主题（设置持久保存）', list(THEMES))
            if theme:
                agent.appearance.change(theme=theme)
                _alert('已保存', '主题：'+theme+'。系统原生弹窗颜色仍跟随 iOS；卡片主题将在独立 UI 验收后启用。')
        elif selected.startswith('显示模式'):
            mode = _choose('选择显示模式', MODES)
            if mode:
                agent.appearance.change(mode=mode)
        elif selected == 'DeepSeek API Key':
            _credentials()
            secret = _key()
            agent.llm = DeepSeekText(secret) if secret else None
        elif selected == '检查在线更新':
            from .mobile_update import check_for_update
            report = check_for_update()
            _alert('在线更新', report['message'])
            if report.get('updated'):
                _alert('更新成功', '请退出 V3，然后从原来的 PYVoiceAgent.py 入口重新打开。')
                return True
        elif selected == '回退到升级前版本':
            if _confirm('版本回退',
                        '将尝试恢复升级前经过 SHA-256 校验的引擎。'
                        'V3 个人数据仍然保留，不会自动重装当前版本。', '确认回退'):
                from .mobile_update import rollback_to_previous
                result = rollback_to_previous()
                _alert('回退结果', result['message'])
                if result.get('rolled_back'):
                    return True
        elif selected == '数据备份（V3 独立数据库）':
            destination = os.path.join(data_directory(), 'backups',
                 'v3_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite3')
            try:
                path = agent.store.backup(destination)
                _alert('备份已保存', path)
            except (OSError, ValueError) as exc:
                _alert('备份失败', type(exc).__name__)
        elif selected == '运行诊断与版本':
            _alert('版本与诊断',
                'V3.0.3 · 独立模块\nSQLite：已初始化\nWebView：未使用\n'
                'Pythonista 原生录音：未启用\n旧数据：未修改\n'
                'DeepSeek Keychain：{}\n本机稳定性仍需真机验证。'.format(
                    '已读取' if _key() else '未检测到'))


def _credentials():
    import dialogs
    # Password-type field; never echo or store the key in SQLite.
    fields = [{'title':'DeepSeek Key','key':'key','type':'password',
               'value':''}]
    result = dialogs.form_dialog('设置 DeepSeek API Key', fields, done_button_title='保存')
    if not result or not result.get('key'):
        return
    secret = str(result['key']).strip()
    if len(secret) > 300:
        _alert('设置失败', 'Key 过长，没有保存。')
        return
    import keychain
    keychain.set_password(KEY_SERVICE, KEY_ACCOUNT, secret)
    _alert('保存成功', '密钥保存在 Pythonista Keychain 中，不写入数据库或 GitHub。')


def run(argv=None):
    """Directly usable on the phone after the original launcher installs V3."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        import dialogs
    except ImportError:
        print('V3 iPhone interface requires the Pythonista dialogs module.')
        return 2
    try:
        agent = create_agent()
    except Exception as exc:
        _alert('V3 启动失败', '数据库初始化未完成：'+type(exc).__name__+'。旧版数据未修改。')
        return 2
    if args and args[0] in ('bridge_callback', 'callback'):
        _alert('旧版快捷指令回调', 'V3 不会执行 V2 未确认的回调；请到旧版记录核验，防止重复写入。')
        return 0
    if args and args[0] == 'text' and len(args) > 1:
        _send(agent, args[1])
        return 0
    if args and args[0] == 'voice':
        _send(agent, _text('系统键盘听写：点击键盘上的麦克风'))
        return 0
    while True:
        item = _choose('PYVoiceAgent V3 · 稳定入口', (
            '输入任务 / AI 对话', '使用剪贴板文字',
            '历史记录', '快捷指令工具库', '设置',
            '系统听写（键盘麦克风）', '退出'))
        if item is None or item == '退出':
            return 0
        try:
            if item == '输入任务 / AI 对话':
                _send(agent, _text('输入任务 · 文字对话'))
            elif item == '使用剪贴板文字':
                import clipboard
                clip = clipboard.get()
                if isinstance(clip, str) and clip.strip():
                    _send(agent, clip.strip())
                else:
                    _alert('剪贴板', '没有文字内容')
            elif item == '历史记录':
                _history(agent)
            elif item == '快捷指令工具库':
                _tools(agent)
            elif item == '设置':
                if _settings(agent):
                    return 0
            elif item.startswith('系统听写'):
                _send(agent, _text('请用系统键盘麦克风听写'))
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            _alert('本次操作失败', type(exc).__name__+'；未自动重试。')


if __name__ == '__main__':
    sys.exit(run())
