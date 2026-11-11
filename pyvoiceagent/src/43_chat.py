def _webui_safe_json(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)
            .replace('<', r'\u003c').replace('>', r'\u003e')
            .replace('&', r'\u0026').replace('\u2028', r'\u2028')
            .replace('\u2029', r'\u2029'))
_WEBUI_NATIVE_SHOW = _card_ui_show
_WEBUI_NATIVE_RESULT = _result_ui_show
import threading as _chat_threading
import time as _chat_time
from urllib.parse import urlsplit as _chat_urlsplit, parse_qs as _chat_parse_qs
_CHAT_TRANSCRIPT_PATH = os.path.join(DATA_DIR, 'chat_transcript.json')
_CHAT_ACTIVE = None
_CHAT_ORIGINAL_MENU = show_menu
_CHAT_ORIGINAL_FINAL = final_report
_CHAT_ORIGINAL_ASK = _ask_clarification
_CHAT_ORIGINAL_PROMPT = prompt_alert
_CHAT_ORIGINAL_AUTHORIZE = _voice_authorize_ai
_CHAT_ORIGINAL_MAIN = main
_CHAT_IN_TASK = _chat_threading.local()
_CHAT_CALLBACK_RESULT = None
_CHAT_BOOTSTRAP_VOICE = False
_CHAT_BOOTSTRAP_TEXT = ''
_CHAT_APP_SCHEMES = {
    'meituan': 'imeituan://',
    'meituan_waimai': 'meituanwaimai://',
}
CHAT_HTML = ''  # V2.3.9 safe UI does not load WebView markup.



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
        self.approval_event = None
        self.approval_choice = 0
        self.recorder = None
        self.record_file = None
        self.pending_audio = None
        self.audio_stop_cancel = None
        self.recognizing = False
        self._voice_session = None
        self._voice_stage = ''
        self.closed = False
        self.ready = False
        self.failed = False
        self.registry_requested = False
        self.updating = False
        self.food_context = False
        self._send_pending = False
        self._last_send_text = ''
        self._last_send_at = 0.0
        self.last_report_id = ''
        self.messages = _chat_transcript_load()

    def save(self):
        try:
            atomic_json(_CHAT_TRANSCRIPT_PATH, {'schema': 1, 'messages': self.messages[-50:]})
        except Exception:
            pass  # UI transcript must never interrupt the task engine.

    def _callback_error(self, stage, exc):
        # Keep task text, credentials and exception arguments out of diagnostics.
        frame = traceback.extract_tb(exc.__traceback__, limit=-1)
        error = {'version': VERSION.split('-')[0], 'stage': stage,
                 'type': type(exc).__name__, 'at': now_iso()}
        if frame:
            error.update(function=frame[0].name, line=frame[0].lineno)
        try:
            atomic_json(os.path.join(DATA_DIR, 'callback_last_error.json'), error)
        except Exception:
            pass
        print('【界面回调失败】{} · {}'.format(stage, error['type']))

    def _ui_later(self, stage, callback, delay):
        def guarded():
            if self.closed:
                return
            try:
                callback()
            except Exception as exc:
                self._callback_error(stage, exc)
        try:
            self.ui.delay(guarded, delay)
        except Exception as exc:
            self._callback_error(stage + '.schedule', exc)

    def post(self, payload):
        if self.closed or self.ui is None:
            return
        js = 'window.PYChatReceive(' + _webui_safe_json(payload) + ');'
        def deliver():
            if self.holder is not None and self.holder.on_screen:
                self.web.eval_js(js)
        self._ui_later('webview_reply', deliver, 0.0)

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
            session = self._voice_session
            self._voice_session = None
            self.recorder = None
            self.record_file = self.pending_audio = None
            self.recognizing = False
            if self.audio_stop_cancel is not None:
                self.audio_stop_cancel.set()
            self.answer = None
            if self.answer_event is not None:
                self.answer_event.set()
            if self.approval_event is not None:
                self.approval_choice = 0
                self.approval_event.set()
        # Never call a native sound.Recorder method from the UI thread.
        if session is not None:
            session.cancel()

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

    def approve(self, question, choices=None):
        """Secure explicit user approval inside the current WebView."""
        if choices is None:
            choices = [('确认','1'),('取消','0')]
        event = _chat_threading.Event()
        with self.lock:
            if self.closed:
                return 0
            self.approval_event = event
            self.approval_choice = 0
        self.post({'type':'approval','question':str(question)[:650],
                   'choices':[{'label':str(label),'value':str(value)}
                              for label,value in choices]})
        event.wait()
        with self.lock:
            result = self.approval_choice
            if self.approval_event is event:
                self.approval_event = None
            self.approval_choice = 0
        return result

    def submit(self, value, from_voice=False):
        text = str(value or '').strip()[:2000]
        if not text:
            self.post({'type': 'notice', 'text': '没有识别到有效文字'})
            return
        with self.lock:
            if self.closed:
                return
            if (self.recognizing or self.recorder is not None) and not from_voice:
                self.post({'type':'notice','text':'录音或识别正在进行，请先结束'})
                return
            if from_voice:
                self.recognizing = False
            if self.answer_event is not None:
                self.message('user', text)
                self.answer = None if text in ('稍后继续','暂停任务','取消任务') else text
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
        self._ui_later('open_app', launch, 0.1)

    def _worker(self, value, from_voice):
        global VOICE_SESSION_ACTIVE
        try:
            _CHAT_IN_TASK.active = True
            VOICE_SESSION_ACTIVE = bool(from_voice)
            previous = get_state()
            outcome = start_new(value)
            state = get_state()
            if not isinstance(state, dict):
                state = {}
            if (outcome is None and state.get('id') == previous.get('id')
                    and state.get('status') == previous.get('status')
                    and len(state.get('events') or []) == len(previous.get('events') or [])):
                self.message('assistant','本次没有启动新操作。请检查指令或联网配置。')
            elif state.get('status') == 'finished':
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
            _CHAT_IN_TASK.active = False
            self.status(False, False)

    def report(self, state):
        self.last_report_id = str(state.get('id') or '')
        result = _result_card_model(state)
        self.post({'type': 'result', 'result': result})

    def _voice_trace(self, phase):
        """Last audio transition for crash diagnosis; no private voice content."""
        self._voice_stage = phase
        try:
            atomic_json(os.path.join(DATA_DIR, 'voice_last_stage.json'),
                        {'version':VERSION.split('-')[0], 'stage':phase, 'at':now_iso()})
        except Exception:
            pass

    def _voice_progress(self, phase):
        if self.closed:
            return
        if phase == 'recording':
            self.post({'type':'recording','active':True})
        elif phase == 'stopped':
            with self.lock:
                self.recorder = None
                self.recognizing = True
            self.post({'type':'recording','active':False})
            self.post({'type':'busy','busy':True,'waiting':False})
        elif phase == 'idle':
            self.post({'type':'recording','active':False})

    def _voice_result(self, spoken):
        if not self.closed and self._voice_session is not None:
            self.submit(spoken, from_voice=True)

    def _voice_error(self, error_type):
        if not self.closed:
            self.message('assistant', '语音录制或识别失败（'+str(error_type)[:45]+'），未执行新任务。可以改用文字输入。')

    def _voice_done(self):
        with self.lock:
            self.recorder = None
            self.recognizing = False
            self.audio_stop_cancel = None
            self._voice_session = None
        if not self.closed and not self.busy:
            self.post({'type':'busy','busy':False,'waiting':False})

    def begin_record(self):
        """Safe fallback: never instantiate native Recorder from a chat callback.

        V2.3.6 crashed on-device immediately. iOS keyboard dictation remains
        available through the HTML input, without Pythonista sound.Recorder.
        """
        if not self.closed:
            self.post({'type':'notice',
                       'text':'已停用易闪退的原生录音。点击输入框，再点 iPhone 键盘上的麦克风听写，完成后发送。'})

    def stop_record(self, cancelled=None):
        """Legacy bridge compatibility, without touching microphone hardware."""
        self.begin_record()

    def cancel_record(self):
        """Legacy bridge compatibility; no audio resource is created."""
        if not self.closed:
            self.post({'type':'notice','text':'无需取消录音；可直接编辑或清空输入框'})

    def _legacy_action(self, action):
        """Keep prior tools reachable; system setup can use native permission dialogs."""
        def work():
            try:
                _V200_DISPATCH(action,'')
                state = get_state()
                if state.get('status') == 'awaiting_callback':
                    self.message('assistant','已请求系统模块执行，等待回调；请勿重复创建。')
                else:
                    self.post({'type':'notice','text':'设置操作已返回，请查看相关权限与结果'})
            except Exception as exc:
                self.message('assistant','设置功能未完成：'+str(exc)[:160])
        if action in ('ai_settings','voice_privacy','module_setup',
                      'review','add_shortcut','clear_state'):
            self._ui_later('legacy_settings', work, 0.1)
        else:
            _chat_threading.Thread(target=work,daemon=True).start()

    def _receive_bridge(self, action, text):
        """Never execute task logic in WebView navigation delegate.

        The native delegate must synchronously return to UIKit. Hand off text
        processing after the navigation decision has returned; keep the draft
        in JavaScript until the request is acknowledged.
        """
        if self.closed:
            return
        if action != 'send':
            self._ui_later('bridge_' + action,
                           lambda: self._handle_action(action, text), 0.02)
            return
        if not text.strip() or len(text) > 2000:
            self.post({'type':'send_ack','ok':False})
            return
        with self.lock:
            now = _chat_time.monotonic()
            if (self._send_pending or (self.busy and self.answer_event is None)
                    or (self._last_send_text == text
                        and now - self._last_send_at < 3)):
                self.post({'type':'send_ack','ok':False})
                return
            self._send_pending = True
            self._last_send_text = text
            self._last_send_at = now
        def start_worker():
            def run():
                try:
                    self._send_trace('processing')
                    self.submit(text)
                    self._send_trace('dispatched')
                except Exception as exc:
                    self._callback_error('send_dispatch', exc)
                    self.post({'type':'notice','text':'发送过程中出现错误，未确认任务是否已执行，请先查看历史'})
                finally:
                    with self.lock:
                        self._send_pending = False
            try:
                _chat_threading.Thread(target=run, daemon=True,
                                       name='PYVA-ChatSend').start()
                self.post({'type':'send_ack','ok':True})
            except Exception as exc:
                with self.lock:
                    self._send_pending = False
                self._callback_error('send_thread', exc)
                self.post({'type':'send_ack','ok':False})
                self.post({'type':'notice','text':'未能启动发送任务，请检查应用状态'})
        self._ui_later('bridge_send_schedule', start_worker, 0.03)

    def _send_trace(self, stage):
        try:
            atomic_json(os.path.join(DATA_DIR, 'send_last_stage.json'),
                        {'version':VERSION.split('-')[0], 'stage':stage, 'at':now_iso()})
        except Exception:
            pass

    def _handle_action(self, action, text):
        if action == 'ready':
            self.ready = True
            global _CHAT_BOOTSTRAP_VOICE, _CHAT_BOOTSTRAP_TEXT
            if _CHAT_BOOTSTRAP_VOICE:
                _CHAT_BOOTSTRAP_VOICE = False
                self._ui_later('voice_start_entry', self.begin_record, 0.3)
            if _CHAT_BOOTSTRAP_TEXT:
                text = _CHAT_BOOTSTRAP_TEXT
                _CHAT_BOOTSTRAP_TEXT = ''
                self._ui_later('text_entry', lambda: self.submit(text), 0.4)
        elif action == 'approve':
            with self.lock:
                if self.closed or self.approval_event is None or self.approval_event.is_set():
                    return
                self.approval_choice = int(text) if text in ('0','1','2') else 0
                self.approval_event.set()
        elif action == 'send':
            if not text.strip() or len(text) > 2000:
                self.post({'type':'notice','text':'请输入不超过2000字的任务'})
            else:
                self.submit(text)
        elif action == 'native_input':
            def ask_native():
                try:
                    import dialogs
                    value = dialogs.text_dialog('原生文字输入', '')
                    if isinstance(value, str) and value.strip() and not self.closed:
                        self._receive_bridge('send', value.strip()[:2000])
                except (KeyboardInterrupt, Exception) as exc:
                    self._callback_error('native_text_dialog', exc)
            _chat_threading.Thread(target=ask_native,daemon=True,
                                   name='PYVA-NativeText').start()
        elif action == 'voice_start':
            self.begin_record()
        elif action == 'voice_stop':
            self.stop_record()
        elif action == 'voice_cancel':
            self.cancel_record()
        elif action == 'registry':
            self._ui_later('open_registry', self.request_registry, 0.08)
        elif action == 'tools':
            try:
                self.post({'type':'tools','items':_card_tool_rows('')[:120]})
            except Exception as exc:
                self.post({'type':'notice','text':'工具库读取失败：'+str(exc)[:80]})
        elif action == 'legacy':
            allowed = frozenset(('ai_settings','voice_privacy','module_setup',
                'resume','review','ai_test','hub_echo','add_shortcut',
                'notes_test','calendar_test','clear_state','contact_import','stepwise'))
            if text not in allowed:
                self.post({'type':'notice','text':'未授权的设置功能'})
                return
            if self.busy:
                self.post({'type':'notice','text':'先结束正在执行的任务'})
                return
            self._legacy_action(text)
        elif action == 'latest':
            self.post({'type':'result','result':_result_card_model(get_state())})
        elif action == 'history_copy':
            import clipboard
            clipboard.set(_history_markdown_for_key(text))
            self.post({'type':'notice','text':'档案全文已复制'})
        elif action == 'history_share':
            try:
                import console
                path = _history_share_path(text)
                console.open_in(path)
            except Exception as exc:
                self.post({'type':'notice','text':'分享不可用：'+str(exc)[:120]})
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
            with self.lock:
                if self.closed or self.busy or self.updating:
                    self.post({'type':'notice','text':'正在执行任务或检查更新，请稍候'})
                    return
                self.updating = True
            def check_update():
                try:
                    outcome = immediate_check_and_update()
                    self.message('assistant', '在线更新：'+str(outcome.get('message') or '未知结果')[:300]+
                                 ('。请退出并重新打开固定入口使用新版。' if outcome.get('updated') else ''))
                except Exception as exc:
                    self.message('assistant', '检查更新失败：'+str(exc)[:150])
                finally:
                    with self.lock:
                        self.updating = False
            try:
                _chat_threading.Thread(target=check_update,daemon=True).start()
            except RuntimeError:
                with self.lock:
                    self.updating = False
                raise

    def request_registry(self, sender=None):
        with self.lock:
            if self.closed or self.registry_requested:
                return
            if self.busy or self.recorder is not None or self.recognizing:
                import console
                console.hud_alert('请先结束正在处理的任务或录音', 'error', 2)
                return
            self.registry_requested = True
        def manage():
            try:
                if not self.closed:
                    add_shortcut_registration()
            except Exception as exc:
                self._callback_error('shortcut_registry', exc)
                try:
                    import console
                    console.hud_alert('工具库未完成，已保留本地数据', 'error', 2)
                except Exception:
                    pass
            finally:
                with self.lock:
                    self.registry_requested = False
        try:
            _chat_threading.Thread(target=manage, daemon=True, name='PYVA-Registry').start()
        except RuntimeError:
            with self.lock:
                self.registry_requested = False
            raise

    def show(self):
        import ui
        if not hasattr(ui, 'WebView'):
            raise RuntimeError('Pythonista 缺少本地 WebView')
        self.ui = ui
        global _CHAT_CALLBACK_RESULT
        boot = {'nonce':self.nonce,'version':VERSION.split('-')[0],
                'palette':_card_palette(_card_appearance_load()),'messages':self.messages,
                'initial_result':_CHAT_CALLBACK_RESULT}
        _CHAT_CALLBACK_RESULT = None
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
                if action not in ('ready','send','approve','voice_start','voice_stop','voice_cancel',
                                  'history','detail','copy','history_copy','history_share','latest',
                                  'theme','mode','color','update','tools','legacy','registry','native_input'):
                    return False
                if len(text)>11000:
                    return False
                try:
                    outer._receive_bridge(action, text)
                except Exception as exc:
                    outer._callback_error('webview_delegate', exc)
                return False

            def webview_did_fail_load(self, view, error_code, message):
                if not outer.ready and str(error_code) not in ('-999','-1002'):
                    outer.failed = True
                    outer._ui_later('webview_failed', holder.close, 0.02)

        web.delegate = Bridge()
        holder.right_button_items = [ui.ButtonItem(title='快捷指令', action=self.request_registry)]
        # Pythonista owns the close control and dismisses the presented view.
        holder.present('full_screen', hide_title_bar=False)
        doc = doc.replace('<!--CHAT_BOOT-->', '')
        web.load_html(doc)
        def watchdog():
            if not self.ready and holder.on_screen:
                self.failed = True
                holder.close()
        self._ui_later('webview_watchdog', watchdog, 7.0)
        try:
            holder.wait_modal()
        finally:
            self.close()
        if self.failed:
            raise RuntimeError('持续对话 WebView 加载失败')
        return True


CHAT_HTML = CHAT_HTML.replace('<title>PYVoiceAgent</title>',
   '<title>PYVoiceAgent</title><script>/*CHAT_BOOT*/</script>')


def _ask_clarification(question):
    current = _CHAT_ACTIVE
    if current is not None and not current.closed:
        return current.ask(question)
    return _CHAT_ORIGINAL_ASK(question)


def prompt_alert(title, message, ok='确认', cancel='取消'):
    current = _CHAT_ACTIVE
    if current is not None and not current.closed and getattr(_CHAT_IN_TASK,'active',False):
        return current.approve(str(title)+'：\n'+str(message)[:500],
                               [(ok,'1'),(cancel,'0')]) == 1
    return _CHAT_ORIGINAL_PROMPT(title,message,ok=ok,cancel=cancel)


def _voice_authorize_ai(state):
    current = _CHAT_ACTIVE
    if current is not None and not current.closed:
        flags = read_json(VOICE_PRIVACY_PATH,{})
        if isinstance(flags,dict) and flags.get('voice_text_auto_share') is True:
            return True
        choice = current.approve('是否允许将本次任务文字发送给 DeepSeek？\n'
            '不包含未经许可的剪贴板、通讯录或日历内容。',
            [('仅本次允许','1'),('今后自动允许','2'),('取消','0')])
        if choice == 2:
            atomic_json(VOICE_PRIVACY_PATH,{
                'voice_text_auto_share':True,'approved_at':now_iso()})
        return choice in (1,2)
    return _CHAT_ORIGINAL_AUTHORIZE(state)


def final_report(state, show_dialog=True):
    global _CHAT_CALLBACK_RESULT
    current = _CHAT_ACTIVE
    if current is not None:
        if not current.closed and show_dialog:
            current.report(state)
            if state.get('voice_session'):
                _voice_report(state)
        return
    if getattr(_CHAT_IN_TASK,'active',False):
        return  # The WebView was closed while work was in flight: no console/modal.
    if len(sys.argv)>1 and sys.argv[1] in ('bridge_callback','callback'):
        if show_dialog:
            _CHAT_CALLBACK_RESULT = _result_card_model(state)
            if state.get('voice_session'):
                _voice_report(state)
        return
    return _CHAT_ORIGINAL_FINAL(state,show_dialog=show_dialog)


def show_menu():
    global _CHAT_ACTIVE
    if _CHAT_ACTIVE is not None:
        return
    shell = _ChatShell()
    _CHAT_ACTIVE = shell
    try:
        return shell.show()
    except Exception as exc:
        print('持续对话界面未能初始化，恢复旧界面：'+str(exc)[:140])
        shell.close()
        _CHAT_ACTIVE = None
        return _CHAT_ORIGINAL_MENU()
    finally:
        shell.close()
        _CHAT_ACTIVE = None


def main():
    global _CHAT_BOOTSTRAP_VOICE, _CHAT_BOOTSTRAP_TEXT
    entry = sys.argv[1] if len(sys.argv)>1 else ''
    if entry == 'voice':
        _CHAT_BOOTSTRAP_VOICE = True
        return show_menu()
    if entry == 'text' and len(sys.argv)>2:
        _CHAT_BOOTSTRAP_TEXT = str(sys.argv[2])[:2000]
        return show_menu()
    return _CHAT_ORIGINAL_MAIN()
