"""Single synchronous coordinator; all side effects are explicit and testable.

No UI, native thread or Apple tool is called from this module. All external
AI text requests require a separate explicit consent transition.
"""
import json

from .models import InputError, InvalidTransition, TaskResult
from ..services.llm import RemoteError
from ..services.history import HistoryService
from ..services.settings import AppearanceSettings
from ..services.shortcuts import ShortcutRegistry
from ..services.native_routes import match_native, is_unhandled_action, allowed_url

_HELP = ('V3 测试核心：输入「你好」「/帮助」「/历史」「/工具」「/设置」。'
         '其他问题须明确授权后才可发送给 DeepSeek。快捷指令只生成待确认操作，不直接执行。')


class Agent:
    def __init__(self, store, llm=None):
        self.store = store
        self.llm = llm
        self.history = HistoryService(store)
        self.appearance = AppearanceSettings(store)
        self.shortcuts = ShortcutRegistry(store)

    @staticmethod
    def _result(row, fresh=True):
        action = json.loads(row['action_json']) if row.get('action_json') else None
        return TaskResult(row['task_id'], row['status'], row['message'], fresh=fresh,
                          confirmation_required=row['status'] in (
                              'waiting_consent', 'waiting_confirmation'),
                          action=action)

    def submit(self, text, request_id=None):
        row, fresh = self.store.create_task(text, request_id)
        if not fresh:
            return self._result(row, fresh=False)
        task_id, value = row['task_id'], row['text']
        tool = self.shortcuts.match(value)
        if tool:
            action = self.shortcuts.prepare_action(tool, value)
            message = ('已找到快捷指令「{}」，但尚未执行。确认后将生成系统交接信息。'
                       .format(tool['shortcut_name']))
            return self._result(self.store.move_task(
                task_id, 'waiting_confirmation', message, action))
        # Native actions are decided locally, before any DeepSeek text request.
        # An app handoff is never a completed task until its effect is verified.
        native = match_native(value)
        if native:
            return self._result(self.store.move_task(
                task_id, 'waiting_confirmation',
                '已识别为打开高德地图；尚未发起系统跳转，也未开始导航。', native))
        if is_unhandled_action(value):
            available = [item for item in self.shortcuts.list() if item['enabled']]
            if available and self.llm is not None:
                return self._result(self.store.move_task(
                    task_id, 'waiting_consent',
                    '这是手机操作指令。将仅向 DeepSeek 发送文字和已登记工具清单用于选择；'
                    '不会让 DeepSeek 自行执行。工具选择后还需通过本地执行器确认。'))
            return self._result(self.store.move_task(
                task_id, 'failed',
                '这是手机操作指令，但当前 V3 没有可用于该命令的已登记执行工具；'
                '没有执行手机操作，也没有发送 DeepSeek。'
                '请在「快捷指令工具库」登记工具，或导入旧版直达型工具。'))
        if value in ('你好', '您好', 'hi', 'Hi', 'hello', 'Hello'):
            return self._result(self.store.move_task(
                task_id, 'completed', '你好，V3 本地引擎正常。这条问候不需要联网，也没有调用手机工具。'))
        if value in ('/帮助', '/help'):
            return self._result(self.store.move_task(task_id, 'completed', _HELP))
        if value in ('/历史', '/history'):
            rows = self.history.list(limit=8)
            message = '\n'.join('{} · {} · {}'.format(
                x['created_at'], x['status'], x['text'][:50]) for x in rows)
            return self._result(self.store.move_task(task_id, 'completed', message or '暂无历史'))
        if value in ('/工具', '/tools'):
            tools = self.shortcuts.list()
            message = '\n'.join('{}：{}{}'.format(
                x['tool_id'], x['shortcut_name'], '' if x['enabled'] else '（停用）') for x in tools)
            return self._result(self.store.move_task(task_id, 'completed', message or '暂未登记工具'))
        if value in ('/设置', '/settings'):
            settings = self.appearance.read()
            return self._result(self.store.move_task(task_id, 'completed',
                '当前主题：{}；显示模式：{}；自定义颜色：{}'.format(
                settings['theme'], settings['mode'], settings['custom_color'] or '无')))
        if value in ('/诊断', '/diagnose'):
            return self._result(self.store.move_task(task_id, 'completed',
                'V3 只读引擎可用；SQLite 可写；不启动 WebView，不使用 sound/objc_util。'))
        return self._result(self.store.move_task(task_id, 'waiting_consent',
            '这是外部 AI 问题。是否允许只把本次输入文字发送给 DeepSeek？当前尚未发送。'))

    def approve_remote(self, task_id, granted):
        if type(granted) is not bool:
            raise InputError('Consent must be an explicit boolean')
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError('No such task')
        if row['status'] != 'waiting_consent':
            return self._result(row, fresh=False)
        if not granted:
            return self._result(self.store.move_task(
                task_id, 'cancelled', '用户拒绝向外部 AI 发送文字；没有网络请求。'))
        # Claim the task in SQLite BEFORE calling the network adapter. A second
        # approve attempt cannot send the same task to the LLM twice.
        try:
            running = self.store.move_task(task_id, 'running', 'AI 请求处理中')
        except InvalidTransition:
            return self._result(self.store.get_task(task_id), fresh=False)
        try:
            if self.llm is None:
                raise RuntimeError('DeepSeek 尚未配置；未发送任何网络请求')
            if is_unhandled_action(running['text']):
                # A tool choice is only a proposal; only the registered local
                # tool is permitted. Never mark an AI choice as completion.
                available = [item for item in self.shortcuts.list() if item['enabled']]
                if not available or not hasattr(self.llm, 'select_tool'):
                    raise RuntimeError('Registered tool planner unavailable')
                tool_id = self.llm.select_tool(running['text'], available)
                tool = next((item for item in self.shortcuts.list()
                             if item['enabled'] and item['tool_id'] == tool_id), None)
                if tool is None:
                    result = self.store.move_task(
                        task_id, 'failed', 'DeepSeek 未能在已登记工具中找到匹配项；未执行任何操作。')
                else:
                    action = self.shortcuts.prepare_action(tool, running['text'])
                    result = self.store.move_task(
                        task_id, 'waiting_confirmation',
                        '已匹配本地快捷指令「{}」，尚未运行，请确认。'.format(tool['shortcut_name']),
                        action)
            else:
                answer = self.llm.answer(running['text'])
                result = self.store.move_task(task_id, 'completed', answer)
        except RemoteError as exc:
            # RemoteError messages are deliberately fixed/sanitized by the adapter.
            result = self.store.move_task(task_id, 'failed',
                'DeepSeek：{}。未调用手机系统工具。'.format(str(exc)))
        except Exception as exc:
            # Avoid writing credentials, URLs or raw request data to a trace.
            result = self.store.move_task(task_id, 'failed',
                'AI 请求未完成（{}），未调用手机系统工具。'.format(type(exc).__name__))
        return self._result(result)

    def confirm_handoff(self, task_id, granted):
        if type(granted) is not bool:
            raise InputError('Handoff confirmation must be a boolean')
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError('No such task')
        if row['status'] != 'waiting_confirmation':
            return self._result(row, fresh=False)
        if not granted:
            return self._result(self.store.move_task(task_id, 'cancelled',
                '未授权快捷指令，本次没有执行。'))
        action = json.loads(row['action_json'])
        kind = action.get('kind')
        if action.get('executed') is not False:
            raise InputError('Handoff payload has changed; refusing to execute')
        if kind == 'ios_url_handoff':
            if not allowed_url(action.get('url')):
                raise InputError('Unapproved app URL; refusing to open')
        elif kind != 'ios_shortcut_handoff':
            raise InputError('Unsupported handoff kind')
        return self._result(self.store.move_task(task_id, 'handoff_ready',
            '已生成交接信息，尚未启动苹果快捷指令。需要由用户授权的 iOS 适配器执行，并回传核验。', action))

    def mark_handoff_unverified(self, task_id):
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError('No such task')
        if row['status'] != 'handoff_ready':
            return self._result(row, fresh=False)
        return self._result(self.store.move_task(task_id, 'needs_review',
            '已移交外部操作的核验责任；本地不声称快捷指令执行成功。'))

    def cancel_review(self, task_id):
        row = self.store.get_task(task_id)
        if not row:
            raise KeyError('No such task')
        if row['status'] in ('waiting_consent', 'waiting_confirmation',
                             'handoff_ready', 'needs_review'):
            return self._result(self.store.move_task(task_id, 'cancelled',
                '已终止后续尝试；已发生的外部动作仍需自行核验。'))
        return self._result(row, fresh=False)
