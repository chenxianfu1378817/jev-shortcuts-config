"""DeepSeek text-only adapter; always requires an explicit caller decision.

Never stores or logs credentials; tool calls are intentionally not supported.
"""
import json
import urllib.error
import urllib.request

from ..core.models import InputError


class RemoteError(Exception):
    pass


class DeepSeekText:
    def __init__(self, api_key, opener=None, model='deepseek-chat', timeout=18,
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
            'messages': [{'role':'system','content':
                          '你是个人只读问答助手。不要声称执行了任何日历、付款、快捷指令或系统操作。'},
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
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RemoteError('网络不可用、超时或 TLS/连接异常') from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise RemoteError('AI 返回内容无法解析') from None
