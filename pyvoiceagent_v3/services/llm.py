"""DeepSeek text-only adapter; always requires an explicit caller decision.

Never stores or logs credentials; tool calls are intentionally not supported.
"""
import json
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

    def answer(self, text):
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise InputError('AI prompt must be 1-2000 characters')
        payload = {
            'model': self.model, 'stream': False,
            'thinking': {'type': 'disabled'},
            'messages': [{'role':'system','content':
                          '你是 PYVoiceAgent 的中文问答模块，手机端助手还具有独立的本地指令路由和用户登记的快捷指令工具。' 
                          '本次请求已由本地分流器判断为问答，你没有收到手机执行器或工具调用接口。' 
                          '不要声称已打开应用、已创建日历、已写入提醒或已运行快捷指令；' 
                          '也不要笼统地声称整个 PYVoiceAgent 无法调用任何 iPhone 工具。' 
                          '当用户询问使用方法时正常回答；如果遇到执行请求，只说明本次尚未执行，' 
                          '可在助手的工具库登记或选择可用工具，不要虚构执行结果。'},
                         {'role':'user','content':text}],
            'max_tokens': 800, 'temperature': 0.4,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer '+self._key,
                     'Content-Type': 'application/json'},
            method='POST')
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read(262145)
                if len(raw) > 262144:
                    raise RemoteError('AI response exceeds safe size')
                parsed = json.loads(raw.decode('utf-8'))
                choices = parsed.get('choices') if isinstance(parsed, dict) else None
                answer = choices[0]['message']['content'] if choices else None
                if not isinstance(answer, str) or not answer.strip():
                    raise RemoteError('AI response is empty or malformed')
                return answer.strip()[:5000]
        except urllib.error.HTTPError as exc:
            # HTTPError subclasses URLError: status codes are NOT offline errors.
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
