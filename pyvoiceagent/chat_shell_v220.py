# -*- coding: utf-8 -*-
"""V2.2.0: persistent local WebView chat interaction. Embedded into single-file core.

No remote webpage, no automatic microphone recording, no arbitrary JS execution.
The existing V2.1.0 engine, shortcuts, update chain and user data remain intact.
"""
import threading as _chat_threading
import time as _chat_time
from urllib.parse import urlsplit as _chat_urlsplit, parse_qs as _chat_parse_qs

_CHAT_TRANSCRIPT_PATH = os.path.join(DATA_DIR, 'chat_transcript.json')
_CHAT_ACTIVE = None
_CHAT_ORIGINAL_MENU = show_menu
_CHAT_ORIGINAL_FINAL = final_report
_CHAT_ORIGINAL_ASK = _ask_clarification
_CHAT_APP_SCHEMES = {
    'meituan': 'imeituan://',
    'meituan_waimai': 'meituanwaimai://',
}

CHAT_HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'">
<title>PYVoiceAgent</title>
<style>
:root{--accent:#8a62d8;--bg:#101319;--surface:#1c222c;--raised:#252c38;--text:#f3f5fa;--muted:#abb3c1;--border:#343d4b;--light:#fff;--danger:#f57c85}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%;margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
button,input,textarea{font:inherit}button{border:0;cursor:pointer;color:inherit}button:disabled{opacity:.4}
#app{display:flex;flex-direction:column;height:100%;height:100dvh;max-width:780px;margin:auto;overflow:hidden}
.top{flex:none;padding:calc(16px + env(safe-area-inset-top,0px)) 18px 10px;background:var(--bg);border-bottom:1px solid var(--border)}
.topline{display:flex;align-items:center;justify-content:space-between;gap:8px}
.brand{font-size:21px;letter-spacing:-.5px;font-weight:800}.version{margin-top:3px;font-size:10px;color:var(--muted)}
.status{font-size:11px;color:var(--muted);border:1px solid var(--border);background:var(--surface);border-radius:99px;padding:8px 11px;white-space:nowrap}
.tabs{display:flex;gap:8px;margin-top:14px}
.tabs button{flex:1;background:transparent;border-radius:12px;color:var(--muted);font-size:13px;padding:10px 0}
.tabs button.active{background:var(--surface);color:var(--text);font-weight:700}
.screen{flex:1;min-height:0;display:none;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:16px 16px 24px}
.screen.active{display:block}
#chatview{padding-bottom:4px}
.bubble-row{display:flex;margin:0 0 13px;align-items:flex-start}
.bubble-row.user{justify-content:flex-end}.bubble{max-width:88%;font-size:15px;line-height:1.55;padding:12px 14px;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:17px;background:var(--surface)}
.bubble-row.user .bubble{background:var(--accent);color:var(--light);border-bottom-right-radius:5px}
.bubble-row.assistant .bubble{border-bottom-left-radius:5px}
.meta{font-size:10px;color:var(--muted);margin:4px 0 5px 3px}
.bubble-row.user .meta{display:none}.section-title{font-size:13px;font-weight:700;color:var(--muted);margin:0 0 12px}
.card{padding:15px;background:var(--surface);border-radius:17px;margin-bottom:12px}
.card .title{font-weight:750;margin-bottom:8px}.sub{font-size:12px;line-height:1.6;color:var(--muted)}
.quick{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 15px}
.quick button,.pill{background:var(--raised);border:1px solid var(--border);border-radius:99px;color:var(--text);padding:10px 13px;font-size:12px;min-height:39px}
.result-card{border:1px solid var(--border);padding:13px;background:var(--surface);border-radius:16px;margin:0 0 13px}
.result-card .title{font-weight:750;font-size:15px;margin-bottom:7px}
.result-card .body{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}
.result-card .note{color:var(--muted);font-size:11px;line-height:1.6;margin-top:8px}
footer{flex:none;background:var(--bg);border-top:1px solid var(--border);padding:9px 13px calc(12px + env(safe-area-inset-bottom,0px))}
.composer{display:flex;align-items:flex-end;gap:8px}.entry{flex:1;min-width:0;max-height:110px;min-height:47px;resize:none;background:var(--surface);border:1px solid var(--border);outline:none;border-radius:17px;color:var(--text);padding:13px 12px;font-size:15px;line-height:1.35}
.round{flex:none;background:var(--raised);border-radius:15px;height:47px;min-width:47px;font-size:21px;font-weight:700}
.send{background:var(--accent);color:var(--light);font-size:18px}
.recording .round.mic{background:var(--danger);color:#fff}.hint{color:var(--muted);font-size:11px;text-align:center;margin-top:8px;min-height:13px}
.field{display:block;background:var(--raised);border:1px solid var(--border);color:var(--text);border-radius:12px;padding:11px;outline:none;width:100%;margin:10px 0;font-size:14px}
.action{background:var(--accent);color:var(--light);padding:11px 14px;border-radius:12px;font-size:13px;font-weight:650;margin:4px 7px 7px 0;min-height:44px}
.secondary{background:var(--raised);color:var(--text)}
.archive-btn{text-align:left;display:block;width:100%;background:var(--surface);padding:13px;border-radius:13px;margin-bottom:9px;font-size:13px}
.colors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.color-choice{display:flex;align-items:center;gap:10px;background:var(--surface);border-radius:13px;padding:12px 9px;font-size:13px}
.dot{height:18px;width:18px;border-radius:50%;flex:none}
#toast{position:fixed;left:18px;right:18px;bottom:115px;margin:auto;max-width:520px;z-index:5;padding:11px;border-radius:12px;background:var(--raised);border:1px solid var(--border);text-align:center;font-size:12px}
[hidden]{display:none!important}
@media(max-width:350px){.top{padding-left:12px;padding-right:12px}.bubble{font-size:14px}.screen{padding-left:11px;padding-right:11px}}
</style></head>
<body><div id="app"><header class="top">
<div class="topline"><div><div class="brand">PYVoiceAgent</div><div class="version" id="version"></div></div><div id="status" class="status">准备就绪</div></div>
<div class="tabs"><button data-tab="chat" class="active">对话</button><button data-tab="history">历史</button><button data-tab="settings">设置</button></div>
</header>
<section class="screen active" id="chatview" aria-label="对话记录"></section>
<section class="screen" id="historyview" aria-label="历史档案"><div class="section-title">本机历史档案</div><input class="field" id="historyquery" placeholder="搜索任务或 BU 行情"><button class="action" id="historysearch">搜索</button><div id="historyresults"></div></section>
<section class="screen" id="settingsview" aria-label="设置"><div class="section-title">外观与主题</div><div class="card"><div class="sub">更换主题将作用于全部对话界面。设置保存在手机本地。</div><div class="colors" id="colors"></div><div style="margin-top:10px"><button class="action secondary" data-mode="跟随系统">跟随系统</button><button class="action secondary" data-mode="浅色模式">浅色</button><button class="action secondary" data-mode="深色模式">深色</button></div><input class="field" id="customcolor" placeholder="自定义颜色 #RRGGBB" maxlength="7"><button class="action secondary" id="savecolor">保存颜色</button></div><div class="section-title">程序管理</div><button class="action secondary" id="checkupdate">检查在线更新</button><div class="sub">固定入口不变。所有系统授权与写入保护继续由 Python 处理。</div></section>
<footer id="footer"><div class="composer"><textarea id="entry" class="entry" rows="1" maxlength="2000" placeholder="输入任务或继续刚才的对话"></textarea><button id="mic" class="round mic" aria-label="开始手动录音">🎙</button><button id="send" class="round send" aria-label="发送">↑</button></div><div class="hint" id="hint">点击麦克风开始录音，再点击结束；不会自动收音</div></footer></div><div id="toast" hidden></div>
<script>
(function(){
'use strict';
var B=window.PYCHAT_BOOT||{}, messages=B.messages||[], busy=false, waiting=false, recording=false, tab='chat', accents={'活力橙':'#F07828','科技蓝':'#3979E8','翡翠绿':'#159F7B','典雅紫':'#8A62D8','中国红':'#D6434B','玫瑰粉':'#D66D96','深海青':'#168E9A','石墨黑':'#444B59'};
function el(id){return document.getElementById(id)}
function node(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e}
function bridge(action,payload){if(typeof payload==='undefined')payload='';var u='pyagent-chat://dispatch?nonce='+encodeURIComponent(B.nonce)+'&action='+encodeURIComponent(action)+'&payload='+encodeURIComponent(String(payload));window.location.href=u}
function toast(msg){var x=el('toast');x.textContent=String(msg);x.hidden=false;setTimeout(function(){x.hidden=true},2500)}
function applyPalette(p){var map={accent:'--accent',background:'--bg',surface:'--surface',raised:'--raised',text:'--text',muted:'--muted',border:'--border',light:'--light',negative:'--danger'};Object.keys(map).forEach(function(k){if(p&&p[k])document.documentElement.style.setProperty(map[k],p[k])})}
function scrollBottom(){var a=el('chatview');setTimeout(function(){a.scrollTop=a.scrollHeight},25)}
function bubble(msg){var row=node('div','bubble-row '+(msg.role==='user'?'user':'assistant'));var inner=node('div','bubble');if(msg.role!=='user')row.appendChild(node('div','meta',msg.role==='system'?'系统提示':'助手'));inner.textContent=msg.text||'';row.appendChild(inner);el('chatview').appendChild(row);return row}
function addMessage(m){messages.push(m);bubble(m);scrollBottom()}
function card(r){var wrap=node('div','result-card');wrap.appendChild(node('div','title',r.title||'执行结果'));if(r.subtitle)wrap.appendChild(node('div','sub',r.subtitle));if(Array.isArray(r.items)){r.items.forEach(function(i){var x=node('div','body',(i.title||'')+'\n'+(i.time||''));x.style.marginTop='10px';wrap.appendChild(x)})}if(r.body)wrap.appendChild(node('div','body',r.body));if(r.notice)wrap.appendChild(node('div','note',r.notice));var copy=node('button','action secondary','复制结果');copy.onclick=function(){bridge('copy',r.copy||r.body||'')};wrap.appendChild(copy);el('chatview').appendChild(wrap);scrollBottom()}
function setBusy(v,w){busy=!!v;waiting=!!w;el('status').textContent=waiting?'等待你补充':busy?'正在处理':'准备就绪';el('send').disabled=busy&&!waiting;el('hint').textContent=recording?'正在录音 · 再点麦克风结束':waiting?'输入回答或点击麦克风回答；不会自动收音':busy?'正在处理任务，请勿重复提交':'手动录音 · 点击开始，再点击结束'}
function enter(t){tab=t;var screens={chat:'chatview',history:'historyview',settings:'settingsview'};Object.keys(screens).forEach(function(k){el(screens[k]).classList.toggle('active',k===t)});document.querySelectorAll('[data-tab]').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-tab')===t)});el('footer').hidden=t!=='chat';if(t==='history')bridge('history','');if(t==='chat')scrollBottom()}
function send(){var v=el('entry').value.trim();if(!v)return; if(busy&&!waiting){toast('正在执行上一项任务');return}el('entry').value='';addMessage({role:'user',text:v});setBusy(true,false);bridge('send',v)}
function themeButtons(){var x=el('colors');Object.keys(accents).forEach(function(k){var b=node('button','color-choice');var dot=node('span','dot');dot.style.background=accents[k];b.appendChild(dot);b.appendChild(node('span','',k));b.onclick=function(){bridge('theme',k)};x.appendChild(b)})}
function paintHistory(items){var p=el('historyresults');p.replaceChildren();if(!items||!items.length){p.appendChild(node('div','sub','没有匹配的记录'));return}items.forEach(function(it){var b=node('button','archive-btn',(it.title||'未命名任务')+'\n'+(it.created||'').slice(0,16));b.onclick=function(){bridge('detail',it.key||'')};p.appendChild(b)})}
window.PYChatReceive=function(m){if(!m||typeof m!=='object')return;if(m.type==='message')addMessage(m.message||{});else if(m.type==='result')card(m.result||{});else if(m.type==='busy')setBusy(m.busy,m.waiting);else if(m.type==='recording'){recording=!!m.active;document.body.classList.toggle('recording',recording);setBusy(busy,waiting)}else if(m.type==='history')paintHistory(m.items||[]);else if(m.type==='detail'){enter('chat');addMessage({role:'assistant',text:(m.title||'档案')+'\n\n'+(m.text||'')})}else if(m.type==='theme'){applyPalette(m.palette||{});toast('主题已保存')}else if(m.type==='notice')toast(m.text||'操作完成');else if(m.type==='handoff'){setBusy(false,false);toast('已向系统发出打开请求，请在目标 App 核验')}};
el('send').onclick=send;el('entry').onkeydown=function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}};
el('mic').onclick=function(){if(recording)bridge('voice_stop','');else bridge('voice_start','')};
document.querySelectorAll('[data-tab]').forEach(function(b){b.onclick=function(){enter(b.getAttribute('data-tab'))}});
el('historysearch').onclick=function(){bridge('history',el('historyquery').value.trim())};
document.querySelectorAll('[data-mode]').forEach(function(b){b.onclick=function(){bridge('mode',b.getAttribute('data-mode'))}});
el('savecolor').onclick=function(){bridge('color',el('customcolor').value.trim())};
el('checkupdate').onclick=function(){bridge('update','')};
applyPalette(B.palette||{});el('version').textContent='V'+(B.version||'2.2.0')+' · 本地 WebView';
messages.forEach(bubble);themeButtons();if(!messages.length){addMessage({role:'assistant',text:'你好，可以直接说任务，也可以输入文字。我会在这里继续追问并显示执行结果。'})}
setBusy(false,false);scrollBottom();bridge('ready','');
})();
</script></body></html>"""


def _chat_local_intent(text, food_context=False):
    """Pure intent classifier; never claims an unverified delivery/order."""
    text = re.sub(r'[\s，。！？!?.]+', '', str(text or ''))
    if text in ('我要点外卖', '我想点外卖', '点外卖', '叫外卖', '想点外卖'):
        return ('food', '想吃什么？也可以直接说「打开美团」或「打开美团外卖」。我可以打开应用，但不会替你下单。')
    if food_context and text in ('快餐', '汉堡', '米饭', '面条', '炸鸡', '早餐', '午餐', '晚餐'):
        return ('food', '好的，想找'+text+'。可以说「打开美团外卖」，进入应用后自行选择商家。')
    if text in ('打开美团', '启动美团', '进入美团', '打开美团APP', '打开美团应用'):
        return ('open', 'meituan')
    if text in ('打开美团外卖', '启动美团外卖', '进入美团外卖', '打开美团外卖APP'):
        return ('open', 'meituan_waimai')
    return None


def _chat_transcript_load():
    data = read_json(_CHAT_TRANSCRIPT_PATH, {})
    if not isinstance(data, dict) or not isinstance(data.get('messages'), list):
        return []
    clean = []
    for m in data['messages'][-50:]:
        if isinstance(m, dict) and m.get('role') in ('user', 'assistant', 'system'):
            clean.append({'role': m['role'], 'text': str(m.get('text') or '')[:4000]})
    return clean


class _ChatShell:
    """One persistent WebView, background AI worker and inline follow-up replies."""
    def __init__(self):
        self.ui = None
        self.web = None
        self.holder = None
        self.nonce = uuid.uuid4().hex
        self.lock = _chat_threading.RLock()
        self.busy = False
        self.waiting = False
        self.answer_event = None
        self.answer = None
        self.recorder = None
        self.record_file = None
        self.closed = False
        self.ready = False
        self.failed = False
        self.food_context = False
        self.last_report_id = ''
        self.messages = _chat_transcript_load()

    def save(self):
        try:
            atomic_json(_CHAT_TRANSCRIPT_PATH, {'schema': 1, 'messages': self.messages[-50:]})
        except Exception:
            pass  # UI transcript must never interrupt the task engine.

    def post(self, payload):
        if self.closed or self.ui is None:
            return
        js = 'window.PYChatReceive(' + _webui_safe_json(payload) + ');'
        def deliver():
            if self.closed or not self.holder or not self.holder.on_screen:
                return
            try:
                self.web.eval_js(js)
            except Exception:
                pass
        self.ui.delay(deliver, 0.0)

    def message(self, role, text):
        text = str(text or '')[:4000]
        if not text:
            return
        msg = {'role': role, 'text': text}
        with self.lock:
            self.messages.append(msg)
            self.messages = self.messages[-50:]
            self.save()
        self.post({'type': 'message', 'message': msg})

    def status(self, busy, waiting=False):
        with self.lock:
            self.busy = bool(busy)
            self.waiting = bool(waiting)
        self.post({'type': 'busy', 'busy': bool(busy), 'waiting': bool(waiting)})

    def close(self):
        with self.lock:
            self.closed = True
            self.answer = None
            if self.answer_event is not None:
                self.answer_event.set()
            recorder = self.recorder
            self.recorder = None
            path = self.record_file
            self.record_file = None
        if recorder is not None:
            try:
                recorder.stop()
            except Exception:
                pass
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def ask(self, question):
        """Runs in the worker; no native dialogs or automatic recording."""
        event = _chat_threading.Event()
        with self.lock:
            if self.closed:
                return None
            self.answer_event = event
            self.answer = None
            self.waiting = True
        self.message('assistant', question)
        self.status(True, True)
        event.wait()
        with self.lock:
            ans = self.answer
            self.answer = None
            if self.answer_event is event:
                self.answer_event = None
            self.waiting = False
        self.status(True, False)
        return ans

    def submit(self, value, from_voice=False):
        text = str(value or '').strip()[:2000]
        if not text:
            self.post({'type': 'notice', 'text': '没有识别到有效文字'})
            return
        with self.lock:
            if self.closed:
                return
            if self.answer_event is not None:
                self.message('user', text)
                self.answer = text
                self.answer_event.set()
                return
            if self.busy:
                self.post({'type': 'notice', 'text': '上一项任务仍在处理，请勿重复发送'})
                return
        self.message('user', text)
        intent = _chat_local_intent(text, self.food_context)
        if intent is not None:
            if intent[0] == 'food':
                self.food_context = True
                self.message('assistant', intent[1])
            elif intent[0] == 'open':
                self.food_context = False
                self._open_trusted_app(intent[1])
            return
        self.food_context = False
        self.status(True, False)
        _chat_threading.Thread(target=self._worker, args=(text, bool(from_voice)),
                               name='PYVoiceAgent-Task', daemon=True).start()

    def _open_trusted_app(self, key):
        url = _CHAT_APP_SCHEMES.get(key)
        if not url:
            self.message('assistant', '没有登记此 App 的原生直达方式。')
            return
        self.message('assistant', '正在尝试打开对应 App。此操作不代表已经选好商家或完成下单。')
        def launch():
            try:
                import shortcuts
                shortcuts.open_url(url)
                self.post({'type': 'handoff'})
            except Exception as exc:
                self.message('assistant', '未能确认 App 已打开：'+str(exc)[:100])
        # Native app launch belongs on the UI thread.
        self.ui.delay(launch, 0.1)

    def _worker(self, value, from_voice):
        global VOICE_SESSION_ACTIVE
        try:
            VOICE_SESSION_ACTIVE = bool(from_voice)
            outcome = start_new(value)
            state = get_state()
            if not isinstance(state, dict):
                state = {}
            if state.get('status') == 'finished':
                if str(state.get('id') or '') != self.last_report_id:
                    self.report(state)
            elif state.get('status') == 'awaiting_callback':
                self.message('assistant', '已移交快捷指令，正在等待系统回传；请勿重复提交相同操作。')
            elif state.get('status') in ('needs_input','replan_pending'):
                self.message('assistant', str(state.get('error') or '已保存原任务，可以继续补充或稍后恢复。')[:700])
            elif state.get('status') in ('needs_review','paused','failed'):
                self.message('assistant', str(state.get('error') or '任务未完成，原记录已保留。')[:700])
            elif outcome is None:
                self.message('assistant', '没有执行新的操作。请检查指令或设置。')
        except Exception as exc:
            self.message('assistant', '执行未完成：'+type(exc).__name__+': '+str(exc)[:180])
        finally:
            self.status(False, False)

    def report(self, state):
        self.last_report_id = str(state.get('id') or '')
        result = _result_card_model(state)
        self.post({'type': 'result', 'result': result})

    def begin_record(self):
        with self.lock:
            if self.closed or self.recorder is not None:
                return
            if self.busy and self.answer_event is None:
                self.post({'type':'notice','text':'当前任务正在处理'})
                return
        try:
            import sound
            ensure_dirs()
            path = os.path.join(DATA_DIR, 'chat_voice_'+uuid.uuid4().hex[:12]+'.m4a')
            rec = sound.Recorder(path)
            rec.record()
            with self.lock:
                self.recorder = rec
                self.record_file = path
            self.post({'type':'recording','active':True})
        except Exception as exc:
            self.message('assistant', '无法开始手动录音：'+str(exc)[:150])

    def stop_record(self):
        with self.lock:
            rec = self.recorder
            path = self.record_file
            self.recorder = None
            self.record_file = None
        if rec is None:
            return
        try:
            rec.stop()
        except Exception as exc:
            self.message('assistant', '停止录音失败：'+str(exc)[:100])
        self.post({'type':'recording','active':False})
        _chat_threading.Thread(target=self._transcribe, args=(path,),
                               name='PYVoiceAgent-Speech', daemon=True).start()

    def _transcribe(self, path):
        try:
            import speech
            if not path or not os.path.isfile(path) or os.path.getsize(path) < 100:
                raise ValueError('录音过短或无有效内容')
            langs = speech.get_recognition_languages()
            lang = next((x for x in langs
                         if x.lower().replace('_','-') in ('zh-cn','zh-hans-cn')), None)
            results = speech.recognize(path, lang) if lang else speech.recognize(path)
            spoken = str(results[0][0]).strip() if results and results[0] else ''
            if not spoken:
                raise ValueError('没有识别到有效语音')
            self.submit(spoken, from_voice=True)
        except Exception as exc:
            self.message('assistant', '语音识别未完成：'+str(exc)[:140]+'。也可以直接输入文字。')
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _handle_action(self, action, text):
        if action == 'ready':
            self.ready = True
        elif action == 'send':
            if not text.strip() or len(text) > 2000:
                self.post({'type':'notice','text':'请输入不超过2000字的任务'})
            else:
                self.submit(text)
        elif action == 'voice_start':
            self.begin_record()
        elif action == 'voice_stop':
            self.stop_record()
        elif action == 'voice_cancel':
            self.stop_record()
        elif action == 'history':
            try:
                self.post({'type':'history','items':_history_search(text[:100],60)})
            except Exception as exc:
                self.post({'type':'notice','text':'历史查询失败：'+str(exc)[:80]})
        elif action == 'detail':
            try:
                rec = _history_read(text)
                self.post({'type':'detail','title':str(rec.get('goal') or '')[:120],
                           'text':_history_md(rec)[:14000]})
            except Exception:
                self.post({'type':'notice','text':'档案读取失败或记录不存在'})
        elif action == 'copy':
            import clipboard
            clipboard.set(text[:10000])
            self.post({'type':'notice','text':'已复制结果'})
        elif action in ('theme','mode','color'):
            appearance = _card_appearance_load()
            if action == 'theme' and text in CARD_THEMES:
                appearance['theme'],appearance['custom_color'] = text,''
            elif action == 'mode' and text in DISPLAY_MODES:
                appearance['mode'] = text
            elif action == 'color' and _card_hex(text):
                appearance['custom_color'] = _card_hex(text)
            else:
                self.post({'type':'notice','text':'主题参数不合法'})
                return
            saved = _card_appearance_save(appearance)
            self.post({'type':'theme','palette':_card_palette(saved)})
        elif action == 'update':
            if self.busy:
                self.post({'type':'notice','text':'正在执行任务，暂不更新'})
                return
            def check_update():
                try:
                    outcome = immediate_check_and_update()
                    self.message('assistant', '在线更新：'+str(outcome.get('message') or '未知结果')[:300]+
                                 ('。请退出并重新打开固定入口使用新版。' if outcome.get('updated') else ''))
                except Exception as exc:
                    self.message('assistant', '检查更新失败：'+str(exc)[:150])
            _chat_threading.Thread(target=check_update,daemon=True).start()
        elif action == 'exit':
            self.holder.close()

    def show(self):
        import ui
        if not hasattr(ui, 'WebView'):
            raise RuntimeError('Pythonista 缺少本地 WebView')
        self.ui = ui
        boot = {'nonce':self.nonce,'version':VERSION.split('-')[0],
                'palette':_card_palette(_card_appearance_load()),'messages':self.messages}
        doc = CHAT_HTML.replace('/*CHAT_BOOT*/',
                  'window.PYCHAT_BOOT='+_webui_safe_json(boot)+';')
        width, height = ui.get_screen_size()
        holder = ui.View(frame=(0,0,width,height))
        self.holder = holder
        holder.name = 'PYVoiceAgent · 对话助手'
        holder.background_color = boot['palette']['background']
        holder.flex = 'WH'
        web = ui.WebView(frame=holder.bounds)
        self.web = web
        web.flex = 'WH'
        holder.add_subview(web)
        outer = self

        class Bridge:
            def webview_should_start_load(self, view, url, nav_type):
                if url in ('about:blank','about:srcdoc') or url.startswith('data:text/html'):
                    return True
                if len(url)>13500:
                    return False
                parsed = _chat_urlsplit(url)
                if parsed.scheme!='pyagent-chat' or parsed.netloc!='dispatch':
                    return False
                values = _chat_parse_qs(parsed.query,keep_blank_values=True)
                if set(values)!={'nonce','action','payload'}:
                    return False
                if any(len(items)!=1 for items in values.values()):
                    return False
                if values['nonce'][0]!=outer.nonce or outer.closed:
                    return False
                action, text = values['action'][0], values['payload'][0]
                if action not in ('ready','send','voice_start','voice_stop','voice_cancel',
                                  'history','detail','copy','theme','mode','color','update','exit'):
                    return False
                if len(text)>11000:
                    return False
                try:
                    outer._handle_action(action,text)
                except Exception as exc:
                    outer.post({'type':'notice','text':'操作未完成：'+str(exc)[:110]})
                return False

            def webview_did_fail_load(self, view, error_code, message):
                if not outer.ready and str(error_code) not in ('-999','-1002'):
                    outer.failed = True
                    ui.delay(holder.close,0.02)

        web.delegate = Bridge()
        holder.present('full_screen',hide_title_bar=True)
        doc = doc.replace('<!--CHAT_BOOT-->', '')
        web.load_html(doc)
        def watchdog():
            if not self.ready and holder.on_screen:
                self.failed = True
                holder.close()
        ui.delay(watchdog, 7.0)
        try:
            holder.wait_modal()
        finally:
            self.close()
        if self.failed:
            raise RuntimeError('持续对话 WebView 加载失败')
        return True


# Insert the boot object as an inline script, without any external asset request.
CHAT_HTML = CHAT_HTML.replace('<title>PYVoiceAgent</title>',
   '<title>PYVoiceAgent</title><script>/*CHAT_BOOT*/</script>')


def _ask_clarification(question):
    current = _CHAT_ACTIVE
    if current is not None and not current.closed:
        return current.ask(question)
    return _CHAT_ORIGINAL_ASK(question)


def final_report(state, show_dialog=True):
    current = _CHAT_ACTIVE
    if current is not None and not current.closed:
        if show_dialog:
            current.report(state)
        return
    return _CHAT_ORIGINAL_FINAL(state,show_dialog=show_dialog)


def show_menu():
    global _CHAT_ACTIVE
    if _CHAT_ACTIVE is not None and not _CHAT_ACTIVE.closed:
        return  # Another callback must not nest duplicate modal chat windows.
    shell = _ChatShell()
    _CHAT_ACTIVE = shell
    try:
        try:
            return shell.show()
        except Exception as exc:
            print('持续对话界面未能初始化，恢复已验证的旧界面：'+str(exc)[:140])
            return _CHAT_ORIGINAL_MENU()
    finally:
        shell.close()
        if _CHAT_ACTIVE is shell:
            _CHAT_ACTIVE = None
