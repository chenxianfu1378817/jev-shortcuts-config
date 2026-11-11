"""Pythonista-native chat surface and crash-isolation entry (V2.3.9).

No WebView or URL-scheme send bridge is instantiated.  All UI callbacks are
short and return to UIKit; task dispatch stays on worker threads.
"""
class _NativeChatShell(_ChatShell):
    def __init__(self):
        super().__init__()
        self._native_root = None
        self._native_pending = False
        self._native_feed = ''
        self._native_probe_count = 0
        self._native_appearance = _card_appearance_load()
        self._native_palette = _card_palette(self._native_appearance)

    def _native_trace(self, phase):
        try:
            atomic_json(os.path.join(DATA_DIR, 'native_chat_stage.json'),
                        {'version': VERSION.split('-')[0], 'stage': phase,
                         'at': now_iso()})
        except Exception:
            pass

    def _native_append(self, role, text):
        text = str(text or '')[:1200]
        if not text or self.closed:
            return
        label = '我' if role == 'user' else ('系统' if role == 'system' else '助手')
        self._native_feed = (self._native_feed + '\n\n' + label + '：\n' + text)[-15000:]
        root = self._native_root
        if root is not None:
            root.log.text = self._native_feed
            try:
                root.log.content_offset = (0, max(0, root.log.content_size[1] - root.log.height))
            except Exception:
                pass

    def _native_approve(self, payload):
        def choose():
            selected = 0
            try:
                import dialogs
                options = [str(x.get('label', '')) for x in payload.get('choices', [])]
                picked = dialogs.list_dialog(
                    str(payload.get('question') or '需要确认')[:190], options)
                if picked in options:
                    selected = int(payload['choices'][options.index(picked)]['value'])
            except (Exception, KeyboardInterrupt):
                pass
            with self.lock:
                self.approval_choice = selected
                if self.approval_event is not None:
                    self.approval_event.set()
        _chat_threading.Thread(target=choose, daemon=True,
                               name='PYVA-NativeApprove').start()

    def post(self, payload):
        if self.closed or self.ui is None or self._native_root is None:
            return
        def paint():
            if self.closed or self._native_root is None:
                return
            kind = payload.get('type')
            root = self._native_root
            if kind == 'message':
                item = payload.get('message') or {}
                self._native_append(item.get('role', 'assistant'), item.get('text', ''))
            elif kind == 'notice':
                self._native_append('system', payload.get('text', ''))
            elif kind == 'result':
                result = payload.get('result') or {}
                fragments = [str(result.get('title') or '执行结果')]
                for key in ('subtitle', 'body', 'notice'):
                    if result.get(key):
                        fragments.append(str(result[key]))
                for item in (result.get('items') or [])[:20]:
                    fragments.append(str(item.get('title') or '') + ' ' +
                                     str(item.get('time') or ''))
                self._native_append('assistant', '\n'.join(fragments))
            elif kind == 'busy':
                busy, waiting = bool(payload.get('busy')), bool(payload.get('waiting'))
                root.status.text = ('等待补充' if waiting else
                                    '正在执行' if busy else '准备就绪') + ' · 原生稳定模式'
                root.send.enabled = not self._native_pending and (not busy or waiting)
            elif kind == 'approval':
                self._native_approve(payload)
            elif kind == 'handoff':
                self._native_append('system', '已请求打开目标 App，实际完成情况仍需人工核验')
        self._ui_later('native_render', paint, 0)

    def _native_unlock(self, accepted, text):
        def finish():
            self._native_pending = False
            root = self._native_root
            if self.closed or root is None:
                return
            if accepted and root.entry.text.strip() == text:
                root.entry.text = ''
            root.send.enabled = not self.busy or self.waiting
            if not accepted:
                root.status.text = '发送未完成 · 原文已保留'
        if self.ui is not None:
            self._ui_later('native_unlock', finish, 0)

    def _native_send(self, sender=None, diagnostic=False):
        """Invoked by UIKit action: never perform file I/O or agent work here."""
        root = self._native_root
        if self.closed or root is None or self._native_pending:
            return
        value = str(root.entry.text or '').strip()[:2000]
        if not value:
            root.status.text = '先输入文字，或点击键盘麦克风听写'
            return
        if diagnostic:
            self._native_probe_count += 1
            root.status.text = '本地发送测试通过 · 没有执行任何 AI 或系统操作'
            return
        with self.lock:
            if self.busy and self.answer_event is None:
                root.status.text = '上一项任务仍在执行 · 文字已保留'
                return
            self._native_pending = True
        root.send.enabled = False
        def process():
            accepted = False
            try:
                self._native_trace('native_send_received')
                self.submit(value)
                accepted = True
                self._native_trace('native_submit_returned')
            except Exception as exc:
                self._callback_error('native_send', exc)
                self.post({'type':'notice',
                           'text':'发送异常，请核验历史后再尝试，不要重复真实系统写入'})
            finally:
                self._native_unlock(accepted, value)
        try:
            _chat_threading.Thread(target=process, daemon=True,
                                   name='PYVA-NativeChatSend').start()
        except Exception as exc:
            self._native_pending = False
            root.send.enabled = True
            self._callback_error('native_send_thread', exc)

    def _native_theme(self, sender=None):
        themes = list(CARD_THEMES)
        old = self._native_appearance.get('theme', '活力橙')
        index = (themes.index(old) + 1) % len(themes) if old in themes else 0
        appearance = dict(self._native_appearance)
        appearance.update(theme=themes[index], custom_color='')
        self._native_appearance = _card_appearance_save(appearance)
        self._native_palette = _card_palette(self._native_appearance)
        if self._native_root is not None:
            self._native_root.apply_palette(self._native_palette)
            self._native_root.theme.title = themes[index]

    def _native_mode(self, sender=None):
        modes = list(DISPLAY_MODES)
        previous = self._native_appearance.get('mode', modes[0])
        next_index = (modes.index(previous) + 1) % len(modes) if previous in modes else 0
        appearance = dict(self._native_appearance, mode=modes[next_index])
        self._native_appearance = _card_appearance_save(appearance)
        self._native_palette = _card_palette(self._native_appearance)
        if self._native_root is not None:
            self._native_root.apply_palette(self._native_palette)
            self._native_root.mode.title = modes[next_index]

    def _native_recent(self, sender=None):
        def read():
            try:
                items = _history_search('', 5)
                for item in items:
                    self.post({'type':'notice',
                               'text':str(item.get('title') or '历史任务')[:120]})
                if not items:
                    self.post({'type':'notice','text':'没有历史记录'})
            except Exception:
                self.post({'type':'notice','text':'历史暂时无法读取；原始记录未修改'})
        _chat_threading.Thread(target=read, daemon=True,
                               name='PYVA-Recent').start()

    def show(self):
        import ui
        self.ui = ui
        shell = self
        width, height = ui.get_screen_size()

        class NativeRoot(ui.View):
            def __init__(self):
                super().__init__(frame=(0, 0, width, height))
                self.keyboard_top = 0
                self.name = 'PYVoiceAgent · 原生稳定模式'
                self.title = ui.Label(text='PYVoiceAgent', font=('<System-Bold>', 21))
                self.version = ui.Label(text='V'+VERSION.split('-')[0]+' · 原生界面',
                                        font=('<System>', 11))
                self.status = ui.Label(text='准备就绪 · 原生稳定模式',
                                       font=('<System>', 12))
                self.log = ui.TextView()
                self.log.editable = False
                self.log.font = ('<System>', 15)
                self.log.corner_radius = 15
                self.entry = ui.TextView()
                self.entry.font = ('<System>', 16)
                self.entry.corner_radius = 12
                self.entry.border_width = 1
                self.send = ui.Button(title='发送')
                self.probe = ui.Button(title='仅测试')
                self.dictate = ui.Button(title='🎙')
                self.theme = ui.Button(title=shell._native_appearance.get('theme', '活力橙'))
                self.mode = ui.Button(title=shell._native_appearance.get('mode', '跟随系统'))
                self.tools = ui.Button(title='快捷指令')
                self.recent = ui.Button(title='历史')
                self.close_button = ui.Button(title='退出')
                self.elements = [self.title, self.version, self.status, self.log,
                                 self.entry, self.send, self.probe, self.dictate,
                                 self.theme, self.mode, self.tools, self.recent,
                                 self.close_button]
                for element in self.elements:
                    self.add_subview(element)
                self.send.action = shell._native_send
                self.probe.action = lambda sender: shell._native_send(sender, diagnostic=True)
                self.dictate.action = lambda sender: self.entry.begin_editing()
                self.theme.action = shell._native_theme
                self.mode.action = shell._native_mode
                self.tools.action = shell.request_registry
                self.recent.action = shell._native_recent
                self.close_button.action = lambda sender: self.close()
                self.apply_palette(shell._native_palette)

            def apply_palette(self, palette):
                self.background_color = palette['background']
                self.title.text_color = palette['text']
                for label in (self.version, self.status):
                    label.text_color = palette['muted']
                self.log.background_color = palette['surface']
                self.log.text_color = palette['text']
                self.entry.background_color = palette['raised']
                self.entry.text_color = palette['text']
                self.entry.border_color = palette['border']
                for button in (self.probe, self.dictate, self.theme, self.mode,
                               self.tools, self.recent):
                    button.background_color = palette['raised']
                    button.tint_color = palette['text']
                    button.corner_radius = 11
                for button in (self.send, self.close_button):
                    button.background_color = palette['accent']
                    button.tint_color = palette['light']
                    button.corner_radius = 11

            def keyboard_frame_did_change(self, frame):
                try:
                    rectangle = ui.convert_rect(frame, None, self)
                    top = float(rectangle[1])
                    self.keyboard_top = top if 120 < top < self.height else 0
                    self.layout()
                except Exception:
                    self.keyboard_top = 0

            def layout(self):
                w = max(280, self.width)
                h = self.keyboard_top if self.keyboard_top else self.height
                h = max(220, min(h, self.height))
                compact = h < 350  # keyboard may cover most of a small iPhone
                self.title.hidden = compact
                self.version.hidden = compact
                self.title.frame = (16, 8, w-180, 30)
                self.version.frame = (16, 40, w-30, 19)
                self.status.frame = (16, 5 if compact else 62, w-30, 22)
                row = [('theme', 0), ('mode', 1), ('tools', 2), ('recent', 3)]
                tw = max(54, (w-42)/4)
                for name, index in row:
                    item = getattr(self, name)
                    item.hidden = compact
                    item.frame = (12 + index*(tw+6), 92, tw, 36)
                input_height = 68 if h < 420 else 88
                top = 34 if compact else 137
                bottom = h - input_height - 50
                self.log.frame = (12, top, w-24, max(30, bottom-top-7))
                self.entry.frame = (12, bottom, w-24, input_height)
                bw = (w-44)/4
                for index, button in enumerate((self.dictate, self.probe, self.send,
                                                self.close_button)):
                    button.frame = (12+index*(bw+7), bottom+input_height+8,
                                    bw, 39)
                self.close_button.title = '退出'

        root = NativeRoot()
        self.holder = root
        self._native_root = root
        self.web = None
        self._native_feed = ''
        for msg in self.messages[-20:]:
            self._native_append(msg.get('role'), msg.get('text'))
        root.present('full_screen', hide_title_bar=False)
        global _CHAT_BOOTSTRAP_TEXT, _CHAT_BOOTSTRAP_VOICE
        if _CHAT_BOOTSTRAP_VOICE:
            _CHAT_BOOTSTRAP_VOICE = False
            self.post({'type':'notice',
                       'text':'点击 🎙 后请使用 iPhone 键盘麦克风听写，再点击发送'})
        if _CHAT_BOOTSTRAP_TEXT:
            root.entry.text = str(_CHAT_BOOTSTRAP_TEXT)[:2000]
            _CHAT_BOOTSTRAP_TEXT = ''
        try:
            root.wait_modal()
        finally:
            self.close()
            self._native_root = None
        return True


def show_menu():
    """V2.3.9 default: do not create a WebView, even for plain text."""
    global _CHAT_ACTIVE
    if _CHAT_ACTIVE is not None:
        return
    shell = _NativeChatShell()
    _CHAT_ACTIVE = shell
    try:
        return shell.show()
    except Exception as exc:
        # Never silently execute the old crash-prone WebView as fallback.
        print('原生对话界面初始化失败：'+type(exc).__name__)
        shell.close()
        return None
    finally:
        shell.close()
        _CHAT_ACTIVE = None
