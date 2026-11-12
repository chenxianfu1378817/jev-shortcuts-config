"""DeepSeek Q&A and allowlisted tool *selection*; no iPhone execution here.

A model may select only an installed, enabled registry tool ID. All side effects
are still performed by the independent Pythonista adapter after local checks.
"""
import json
import re
import socket
import ssl
import urllib.error
import urllib.request

from ..core.models import InputError


class RemoteError(Exception):
    pass


class DeepSeekText:
    def __init__(self, api_key, opener=None, model='deepseek-flash', timeout=18,
                 endpoint='https://api.deepseek.com/chat/completions'):
        if not isinstance(api_key, str) or not api_key.strip():
            raise InputError('DeepSeek API key is missing')
        if not endpoint.startswith('https://'):
            raise InputError('Refuse non-HTTPS AI endpoint')
        if not 2 <= timeout <= 60:
            raise InputError('AI timeout must be 2-60 seconds')
        self._key = api_key
        self._opener = opener or urllib.request.urlopen
        self.model = model
        self.timeout = timeout
        self.endpoint = endpoint

    def _post(self, payload):
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self._key,
                     'Content-Type': 'application/json'},
            method='POST')
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read(262145)
                if len(raw) > 262144:
                    raise RemoteError('AI response exceeds safe size')
                parsed = json.loads(raw.decode('utf-8'))
                choices = parsed.get('choices') if isinstance(parsed, dict) else None
                message = choices[0]['message'] if choices else None
                if not isinstance(message, dict):
                    raise RemoteError('AI response is empty or malformed')
                return message
        except urllib.error.HTTPError as exc:
            status = int(exc.code) if isinstance(exc.code, int) else 0
            reason = {
                400: '请求格式被 DeepSeek 拒绝（HTTP 400）',
                401: 'DeepSeek API Key 无效或已失效（HTTP 401）',
                402: 'DeepSeek 账户余额不足（HTTP 402）',
                403: 'DeepSeek 接口访问受限（HTTP 403）',
                408: 'DeepSeek 服务器请求超时（HTTP 408）',
                429: 'DeepSeek 请求频率受限（HTTP 429）',
            }.get(status)
            if reason is None:
                reason = ('DeepSeek 服务暂时异常（HTTP {}）'.format(status)
                          if status >= 500 else
                          'DeepSeek 请求失败（HTTP {}）'.format(status))
            raise RemoteError(reason) from None
        except (TimeoutError, socket.timeout):
            raise RemoteError('DeepSeek 请求超时，请稍后再试') from None
        except urllib.error.URLError as exc:
            detail = getattr(exc, 'reason', None)
            if (isinstance(detail, ssl.SSLError) or
                    'CERTIFICATE_VERIFY_FAILED' in str(type(detail)) or
                    'CERTIFICATE_VERIFY_FAILED' in str(detail) or
                    'SSL' in type(detail).__name__):
                raise RemoteError('TLS 安全连接失败，请检查代理、证书与系统时间') from None
            raise RemoteError('网络连接失败，请检查蜂窝网络、DNS 或代理') from None
        except OSError:
            raise RemoteError('网络连接或系统 I/O 异常') from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise RemoteError('AI 返回内容无法解析') from None

    def answer(self, text):
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise InputError('AI prompt must be 1-2000 characters')
        payload = {
            'model': self.model, 'stream': False,
            'thinking': {'type': 'disabled'},
            'messages': [{'role': 'system', 'content':
                          '你是 PYVoiceAgent 的中文问答模块。助手有独立的本地工具执行器和快捷指令登记库，'
                          '本次内容被本地引擎分类为普通知识问答。'
                          '你本次没有获得手机执行权限；不能宣称任何手机系统动作已完成。'
                          '也不要笼统地说整个 PYVoiceAgent 无法操作手机。'},
                         {'role': 'user', 'content': text}],
            'max_tokens': 800, 'temperature': 0.4,
        }
        message = self._post(payload)
        answer = message.get('content')
        if not isinstance(answer, str) or not answer.strip():
            raise RemoteError('AI response is empty or malformed')
        return answer.strip()[:5000]

    def select_tool(self, text, registered_tools):
        """Return an enabled tool ID or None. Does not execute the chosen tool."""
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise InputError('AI tool request must be 1-2000 characters')
        if not isinstance(registered_tools, list):
            raise InputError('Invalid tool catalog')
        allowed = []
        for item in registered_tools:
            if not isinstance(item, dict) or not item.get('enabled'):
                continue
            ident = item.get('tool_id', '')
            if not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,31}', ident):
                raise InputError('Invalid tool catalog ID')
            label = item.get('shortcut_name', '')
            aliases = item.get('aliases', [])
            description = item.get('description', '')
            if (not isinstance(label, str) or not isinstance(aliases, list) or
                    not all(isinstance(a, str) for a in aliases) or
                    not isinstance(description, str)):
                raise InputError('Invalid tool catalog entries')
            allowed.append(item)
        if not allowed:
            return None
        if len(allowed) > 40:
            raise InputError('Tool catalog exceeds safe limit')
        ids = [item['tool_id'] for item in allowed]
        if len(set(ids)) != len(ids):
            raise InputError('Duplicate tool catalog ID')
        catalog = '\n'.join(
            '{}：快捷指令 {}；别名 {}；说明 {}'.format(
                item['tool_id'], item['shortcut_name'][:80],
                '、'.join(item['aliases'])[:300], item['description'][:200])
            for item in allowed)
        payload = {
            'model': self.model, 'stream': False,
            'thinking': {'type': 'disabled'}, 'temperature': 0,
            'max_tokens': 300, 'tool_choice': 'auto',
            'messages': [
                {'role': 'system', 'content':
                 '你是 PYVoiceAgent 的手机操作路由器。只能选择下面真实登记且已启用的本地工具。'
                 '不要编造工具、URL、功能或执行结果；你自己不会执行操作。'
                 '若用户的请求不能由所列工具完成，不调用任何工具。\n' + catalog},
                {'role': 'user', 'content': text},
            ],
            'tools': [{
                'type': 'function',
                'function': {
                    'name': 'select_registered_shortcut',
                    'description': '仅选择一个真实登记并启用的 iPhone 快捷指令，稍后由本地引擎确认执行',
                    'parameters': {
                        'type': 'object',
                        'properties': {'tool_id': {'type': 'string', 'enum': ids}},
                        'required': ['tool_id'],
                        'additionalProperties': False,
                    },
                },
            }],
        }
        message = self._post(payload)
        calls = message.get('tool_calls')
        if not calls:
            return None
        if not isinstance(calls, list) or len(calls) != 1:
            raise RemoteError('AI 返回多个或损坏的工具调用，拒绝执行')
        function = calls[0].get('function') if isinstance(calls[0], dict) else None
        if not isinstance(function, dict) or function.get('name') != 'select_registered_shortcut':
            raise RemoteError('AI 返回未登记的工具函数，拒绝执行')
        try:
            parsed = json.loads(function.get('arguments', ''))
        except (ValueError, TypeError):
            raise RemoteError('AI 工具参数不是合法 JSON，拒绝执行') from None
        if (not isinstance(parsed, dict) or set(parsed) != {'tool_id'} or
                not isinstance(parsed.get('tool_id'), str) or parsed['tool_id'] not in ids):
            raise RemoteError('AI 选择未授权工具，拒绝执行')
        return parsed['tool_id']
