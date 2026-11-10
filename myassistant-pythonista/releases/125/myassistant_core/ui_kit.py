# -*- coding: utf-8 -*-
"""《我的助手》全部业务模块统一的卡片式选择/编辑/确认/详情界面。

统一替代 dialogs.list_dialog、dialogs.form_dialog、dialogs.text_dialog 与 console 输入弹窗。
纯 Pythonista ui，无第三方依赖；以 wait_modal 等待用户提交，取消返回 None。
不访问数据库、不处理密钥、不调用网络。文件选择器、系统 Keychain 安全输入保留原生组件。
"""
from .ui_style import (PAGE_BG, WHITE, ACCENT, ACCENT_SOFT,
                       TEXT, MUTED, FIELD_BG, BORDER, DANGER, safe_top_inset)
try:
    import ui
except ImportError:
    ui = None


def _require_ui():
    if ui is None:
        raise RuntimeError('需要在 iPhone Pythonista 3 上显示界面')
    return ui


def label(parent, x, y, w, h, text, size=14, color=TEXT, bold=False, align=None):
    u = _require_ui()
    obj = u.Label(frame=(x, y, w, h))
    obj.text = '' if text is None else str(text)
    obj.text_color = color
    obj.font = ('<system-bold>' if bold else '<system>', size)
    obj.number_of_lines = 0
    if align is not None:
        obj.alignment = align
    parent.add_subview(obj)
    return obj


def button(parent, x, y, w, h, text, action, primary=False, muted=False, size=15):
    u = _require_ui()
    obj = u.Button(frame=(x, y, w, h))
    obj.title = str(text)
    obj.background_color = ACCENT if primary else (FIELD_BG if muted else ACCENT_SOFT)
    obj.tint_color = WHITE if primary else (TEXT if muted else ACCENT)
    obj.font = ('<system-bold>', size)
    obj.corner_radius = 12
    obj.action = lambda sender: action()
    parent.add_subview(obj)
    return obj


def field(parent, x, y, w, h, value='', placeholder='', numeric=False):
    u = _require_ui()
    obj = u.TextField(frame=(x, y, w, h))
    obj.text = '' if value is None else str(value)
    obj.placeholder = str(placeholder)
    obj.background_color = FIELD_BG
    obj.text_color = TEXT
    obj.font = ('<system>', 16)
    obj.corner_radius = 12
    obj.bordered = False
    obj.clear_button_mode = 'while_editing'
    if numeric:
        obj.keyboard_type = getattr(u, 'KEYBOARD_DECIMAL_PAD',
                                    getattr(u, 'KEYBOARD_NUMBERS', 2))
    parent.add_subview(obj)
    return obj


class ModalPage:
    """Compose one fullscreen scroll surface per interaction; no nested cramped system forms."""
    def __init__(self, title, action_title=None):
        u = _require_ui()
        w, h = u.get_screen_size()
        self.width = w
        self.height = h
        self.value = None
        self.view = u.View(frame=(0, 0, w, h))
        self.view.background_color = PAGE_BG
        self.view.name = str(title)
        self.view.flex = 'WH'
        top = safe_top_inset(h)
        self.head_height = top + 64
        head = u.View(frame=(0, 0, w, self.head_height))
        head.background_color = WHITE
        self.view.add_subview(head)
        button(head, 12, top+11, 72, 42, '返回', self.cancel)
        centered = label(head, 92, top+11, max(60, w-184), 42,
                         str(title), 17, bold=True, align=getattr(u, 'ALIGN_CENTER', 1))
        self.title_view = centered
        self.action_button = None
        if action_title:
            self.action_button = button(head, w-86, top+11, 74, 42,
                                        action_title, lambda: self.commit(), primary=True)
            self.title_view.frame = (89, top+11, max(60, w-178), 42)
        self.scroll = u.ScrollView(frame=(0, self.head_height, w, max(1, h-self.head_height)))
        self.scroll.background_color = PAGE_BG
        self.scroll.flex = 'WH'
        self.view.add_subview(self.scroll)
        self.cursor = 16

    def card(self, title, height):
        u = _require_ui()
        c = u.View(frame=(16, self.cursor, self.width-32, height))
        c.background_color = WHITE
        c.corner_radius = 18
        self.scroll.add_subview(c)
        if title:
            label(c, 16, 10, c.width-32, 30, title, 17, bold=True)
        self.cursor += height + 14
        return c

    def finish(self):
        self.scroll.content_size = (self.width, self.cursor+26)
        self.view.present('fullscreen', hide_title_bar=True)
        # modal waits belong to the caller's worker thread; all dashboard/quote
        # callbacks that show menus run via @ui.in_background.
        self.view.wait_modal()
        return self.value

    def cancel(self):
        self.value = None
        self.view.close()

    def commit(self):
        self.view.close()


def select(title, items):
    """滚动列表使用两行标题，长客户名、投标项目名也不压缩成小字。"""
    u = _require_ui()
    choices = list(items or [])
    if not choices:
        return None
    pg = ModalPage(title)
    c = pg.card('请选择', max(124, 60+len(choices)*66))
    for i, item in enumerate(choices):
        text = str(item)
        row = u.View(frame=(14, 45+i*66, c.width-28, 57))
        row.background_color = FIELD_BG
        row.corner_radius = 12
        c.add_subview(row)
        label(row, 14, 5, row.width-44, 48, text, 14, TEXT)
        label(row, row.width-32, 14, 20, 28, '›', 19, ACCENT)
        def pick(s=text):
            pg.value = s
            pg.view.close()
        tap = u.Button(frame=(0, 0, row.width, 57))
        tap.title = ''
        tap.background_color = (0,0,0,0)
        tap.action = lambda sender, do=pick: do()
        row.add_subview(tap)
    return pg.finish()


def edit_form(title, fields, initial=None):
    """Accept [(key,label[,type])] and return {key:text} like dialogs.form_dialog."""
    initial = dict(initial or {})
    fields = list(fields)
    pg = ModalPage(title, action_title='保存')
    c = pg.card('填写信息', max(84, 55+len(fields)*106))
    controls = {}
    for i, item in enumerate(fields):
        key, heading = item[0], item[1]
        kind = item[2] if len(item)>2 else 'text'
        y = 43+i*106
        label(c, 16, y, c.width-32, 39, heading, 13, MUTED)
        controls[key] = field(c, 16, y+43, c.width-32, 48,
                              initial.get(key,''), '请输入'+str(heading),
                              numeric=(kind=='number'))
    button(pg.scroll, 16, pg.cursor, pg.width-32, 50,
           '保存本次修改', lambda: pg.commit(), primary=True, size=16)
    pg.cursor += 65
    def commit():
        pg.value = {k: v.text for k,v in controls.items()}
        pg.view.close()
    pg.commit = commit
    # replace action callback; ModalPage created callback by reference self.commit
    return pg.finish()


def input_text(title, default=''):
    result = edit_form(title, [('value','内容')], {'value':default})
    return None if result is None else result.get('value','')


def edit_text(title, text='', editable=True):
    u = _require_ui()
    pg = ModalPage(title, action_title='完成' if editable else None)
    c = pg.card('正文' if editable else '查看内容', max(340, pg.height-pg.head_height-105))
    area = u.TextView(frame=(15, 50, c.width-30, c.height-65))
    area.text = str(text or '')
    area.font = ('<system>', 15)
    area.text_color = TEXT
    area.background_color = FIELD_BG
    area.corner_radius = 12
    area.editable = bool(editable)
    c.add_subview(area)
    if editable:
        def commit():
            pg.value=area.text
            pg.view.close()
        pg.commit=commit
    return pg.finish()


def confirm(title, question):
    pg = ModalPage(title)
    c=pg.card('请确认操作', 235)
    label(c, 16, 43, c.width-32, 116, question, 15, TEXT)
    w=(c.width-43)/2
    button(c, 16, 171, w, 47, '取消', pg.cancel, muted=True)
    def yes():
        pg.value=True
        pg.view.close()
    button(c, 27+w, 171, w, 47, '确认', yes, primary=True)
    return pg.finish() is True


def alert(message, title='我的助手'):
    pg = ModalPage(title)
    c = pg.card('操作提示', 222)
    label(c,16,43,c.width-32,107,message,15,TEXT)
    button(c,16,168,c.width-32,43,'知道了',pg.cancel,primary=True)
    pg.finish()


def information(title, lines):
    text='\n'.join(str(s) for s in lines) if isinstance(lines,(tuple,list)) else str(lines)
    edit_text(title,text,editable=False)
