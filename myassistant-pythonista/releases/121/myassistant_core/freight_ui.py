# -*- coding: utf-8 -*-
"""《我的助手》卡片式汽运费测算。

主界面与 Build93 日常报价采用统一风格，不再使用 dialogs.form_dialog。
保留原始独立里程分段计价、用户的运价配置及历史记录。

重要：手动输入的是实际道路结算里程，本模块不会假装进行地图测距。
"""
import copy
from .calc import freight_quote, FREIGHT_DEFAULT_RULES, validate_freight_rules
from .ui_style import PAGE_BG, WHITE, ACCENT, ACCENT_SOFT, TEXT, MUTED, FIELD_BG, safe_top_inset

try:
    import ui
except ImportError:
    ui = None


def _confirm(title, message):
    from .ui_kit import confirm
    return confirm(title, message)


def _notice(message, success=True):
    import console
    console.hud_alert(str(message), 'success' if success else 'error', 1.5)


class FreightEditor(ui.View if ui else object):
    """一个完整界面承载测算、记录、规则管理，避免弹窗式多层菜单。"""

    def __init__(self, store, prefill=None):
        if ui is None:
            raise RuntimeError('需要在 iPhone Pythonista 3 上运行')
        super().__init__()
        self.store = store
        self.name = '汽运费测算'
        self.background_color = PAGE_BG
        self.flex = 'WH'
        self.width, self.height = ui.get_screen_size()
        self.mode = 'form'
        data = prefill or {}
        self.d = dict(origin=data.get('origin') or '',
                      destination=data.get('destination') or '',
                      distance_km=str(data.get('distance_km') or ''),
                      notes=data.get('notes') or '')
        self._fields = {}
        self._rules_fields = []
        self._result = None
        self._draw()

    def _label(self, parent, x, y, w, h, value, size=13, color=TEXT, bold=False, align=None):
        v = ui.Label(frame=(x, y, w, h))
        v.text = str(value)
        v.font = ('Helvetica-Bold' if bold else 'Helvetica', size)
        v.text_color = color
        v.number_of_lines = 0
        if align is not None:
            v.alignment = align
        parent.add_subview(v)
        return v

    def _button(self, parent, x, y, w, h, text, callback, fill=ACCENT_SOFT, color=ACCENT, size=14):
        b = ui.Button(frame=(x, y, w, h))
        b.title = str(text)
        b.background_color = fill
        b.tint_color = color
        b.font = ('Helvetica-Bold', size)
        b.corner_radius = 12
        b.action = ui.in_background(lambda sender: callback())
        parent.add_subview(b)
        return b

    def _field(self, parent, key, x, y, w, h, placeholder='', numeric=False, value=None, rule_index=None):
        f = ui.TextField(frame=(x, y, w, h))
        f.background_color = FIELD_BG
        f.corner_radius = 12
        f.text_color = TEXT
        f.font = ('Helvetica', 15)
        f.placeholder = placeholder
        f.text = str(self.d.get(key, '') if value is None else value)
        f.clear_button_mode = 'while_editing'
        f.bordered = False
        if numeric:
            f.keyboard_type = getattr(ui, 'KEYBOARD_DECIMAL_PAD', getattr(ui, 'KEYBOARD_NUMBERS', 2))
        f.delegate = self
        f.name = ('rule_' + str(rule_index)) if rule_index is not None else key
        parent.add_subview(f)
        return f

    def textfield_did_change(self, field):
        if self.mode == 'form' and field.name in self._fields:
            self.d[field.name] = field.text
            if field.name == 'distance_km':
                self._update_result()

    def textfield_did_end_editing(self, field):
        self.textfield_did_change(field)

    def textfield_should_return(self, field):
        field.end_editing()
        return True

    def _card(self, title, height):
        c = ui.View(frame=(16, self.cursor, self.width-32, height))
        c.background_color = WHITE
        c.corner_radius = 18
        self.scroll.add_subview(c)
        self._label(c, 16, 12, c.width-32, 29, title, 18, bold=True)
        self.cursor += height + 14
        return c

    def _draw(self):
        for sub in list(self.subviews):
            self.remove_subview(sub)
        w = self.width
        top_pad = safe_top_inset(self.height)
        header_height = top_pad + 64
        header = ui.View(frame=(0, 0, w, header_height))
        header.background_color = WHITE
        self.add_subview(header)
        self._button(header, 12, top_pad+10, 70, 43, '返回', self._back, fill='#f9e8d8')
        titles = {'form':'汽运费测算', 'rules':'运价分段设置', 'history':'汽运费历史'}
        self._label(header, w/2-92, top_pad+10, 184, 43, titles[self.mode], 18,
                    bold=True, align=getattr(ui, 'ALIGN_CENTER', 1))
        if self.mode in ('form', 'rules'):
            self.header_save = self._button(header, w-86, top_pad+10, 75, 43,
                         '保存', self._save if self.mode=='form' else self._save_rules,
                         fill=ACCENT, color=WHITE)
        self.scroll = ui.ScrollView(frame=(0, header_height, w, max(1, self.height-header_height)))
        self.scroll.flex = 'WH'
        self.scroll.background_color = PAGE_BG
        self.add_subview(self.scroll)
        self.cursor = 14
        if self.mode == 'form':
            self._draw_form()
        elif self.mode == 'rules':
            self._draw_rules()
        else:
            self._draw_history()
        self.scroll.content_size = (w, self.cursor + 36)

    def _draw_form(self):
        self._fields = {}
        card = self._card('起运地与目的地', 226)
        self._label(card, 16, 47, card.width-32, 22, '起运地', 12, MUTED)
        self._fields['origin'] = self._field(card, 'origin', 16, 70, card.width-32, 42, '例如：钦州港')
        self._label(card, 16, 124, card.width-32, 22, '目的地', 12, MUTED)
        self._fields['destination'] = self._field(card, 'destination', 16, 147, card.width-32, 42, '例如：南宁项目工地')
        self._label(card, 16, 196, card.width-32, 17, '地点只作记录，不会自动计算地图里程', 11, MUTED)

        card = self._card('测算距离', 150)
        self._label(card, 16, 45, card.width-32, 21, '实际结算里程（公里）', 12, MUTED)
        self._fields['distance_km'] = self._field(card, 'distance_km', 16, 68,
                                    card.width-32, 45, '请输入公里数', numeric=True)
        self._label(card, 16, 119, card.width-32, 20, '以道路实际运输里程为准，非直线距离', 11, MUTED)

        card = self._card('运费测算结果', 211)
        self.result_line = self._label(card, 16, 44, card.width-32, 45, '填写公里数后自动计算', 13, MUTED)
        self.formula_line = self._label(card, 16, 92, card.width-32, 45, '', 12, MUTED)
        self.result_number = self._label(card, 16, 142, card.width-32, 35,
                                         '— 元/吨', 22, ACCENT, True)
        self._label(card, 16, 177, card.width-32, 22, '分段单独计价；跨区间价格可能不连续', 11, MUTED)

        card = self._card('备注', 126)
        self._fields['notes'] = self._field(card, 'notes', 16, 49,
                                          card.width-32, 44, '如：运费报价有效期、车型等')
        self._label(card, 16, 101, card.width-32, 16, '历史记录会与本次运费计算结果一起保存', 11, MUTED)

        card = self._card('运价与历史', 140)
        self._label(card, 16, 46, card.width-32, 22,
                    '沿用原版六段运价；参数不会自动改变', 12, MUTED)
        half = (card.width-40)/2
        self._button(card, 16, 83, half, 40, '查看运费历史', self._go_history)
        self._button(card, 24+half, 83, half, 40, '管理分段运价', self._go_rules)

        self._button(self.scroll, 16, self.cursor, self.width-32, 50,
                     '保存本次汽运费测算', self._save, fill=ACCENT, color=WHITE, size=16)
        self.cursor += 75
        self._update_result()

    def _collect(self):
        for key, field in self._fields.items():
            self.d[key] = field.text

    def _update_result(self):
        self._result = None
        value = str(self.d.get('distance_km') or '').strip()
        if not value:
            self.result_line.text = '填写公里数后自动计算'
            self.formula_line.text = '运价规则按实际结算里程匹配'
            self.result_number.text = '— 元/吨'
            if hasattr(self, 'header_save'):
                self.header_save.enabled = False
            return
        try:
            rules = self.store.pref('freight_rules', FREIGHT_DEFAULT_RULES)
            result = freight_quote(value, rules)
            self._result = result
            self.result_line.text = ('距离：{:g} 公里\n匹配分段：{}'
                                     .format(result['distance_km'], result['segment']))
            self.formula_line.text = ('{}\n计算原值：{:.2f} 元/吨'
                                      .format(result['formula'], result['raw_fee_per_ton']))
            self.result_number.text = '{} 元/吨'.format(result['final_fee_per_ton'])
            if hasattr(self, 'header_save'):
                self.header_save.enabled = True
        except (ValueError, TypeError) as exc:
            self.result_line.text = '无法测算：' + str(exc)
            self.formula_line.text = '请检查公里数或已保存的分段规则'
            self.result_number.text = '— 元/吨'
            if hasattr(self, 'header_save'):
                self.header_save.enabled = False

    def _save(self):
        self._collect()
        self._update_result()
        if self._result is None:
            _notice('请填写有效运输距离', False)
            return
        if not _confirm('保存运费', '确认保存此次汽运费测算？'):
            return
        payload = copy.deepcopy(self.d)
        payload['result'] = copy.deepcopy(self._result)
        title = '{}→{}'.format(payload['origin'].strip() or '起点',
                               payload['destination'].strip() or '终点')
        try:
            self.store.save('freight', title, payload)
            _notice('汽运费记录已保存')
            self.close()
        except (ValueError, OSError) as exc:
            _notice('保存失败：' + str(exc), False)

    def _go_rules(self):
        self._collect()
        self.mode = 'rules'
        self._draw()

    def _go_history(self):
        self._collect()
        self.mode = 'history'
        self._draw()

    def _back(self):
        if self.mode != 'form':
            self.mode = 'form'
            self._draw()
        else:
            self.close()

    def _draw_rules(self):
        self._rules_fields = []
        try:
            rules = validate_freight_rules(self.store.pref('freight_rules', FREIGHT_DEFAULT_RULES))
        except ValueError as exc:
            self._label(self.scroll, 18, self.cursor, self.width-36, 60,
                        '当前运价规则有误：'+str(exc), 13, '#d24b4b')
            self.cursor += 76
            return
        card = self._card('六段汽运费率', 84+len(rules)*82)
        self._label(card, 16, 43, card.width-32, 24,
                    '仅修改数值，分段区间和计价方式保持不变', 12, MUTED)
        for ix, rule in enumerate(rules):
            y=70+ix*82
            last = 0 if ix==0 else rules[ix-1]['upper']
            name = ('{}—{} 公里'.format(last,rule['upper']) if rule['upper'] is not None
                    else '{} 公里以上'.format(last))
            unit = '固定元/吨' if rule['method']=='fixed' else '元/(吨·公里)'
            self._label(card, 16, y, card.width-32, 22, name+' · '+unit, 12, TEXT, True)
            f = self._field(card, 'rate', 16, y+27, card.width-32, 43,
                            '填写费率', numeric=True, value=rule['value'], rule_index=ix)
            self._rules_fields.append((f, rule))
        self._button(self.scroll, 16, self.cursor, self.width-32, 49,
                     '保存分段运价', self._save_rules, fill=ACCENT, color=WHITE)
        self.cursor += 61
        self._button(self.scroll, 16, self.cursor, self.width-32, 43,
                     '恢复原版默认运价', self._reset_rules, fill=ACCENT_SOFT)
        self.cursor += 74
        self._label(self.scroll, 18, self.cursor, self.width-36, 52,
                    '注意：历史运费记录不会因为修改分段规则而自动改价。', 12, MUTED)
        self.cursor += 62

    def _save_rules(self):
        if not self._rules_fields:
            _notice('没有可保存的运价规则', False)
            return
        rules = []
        for field, original in self._rules_fields:
            value = field.text.strip()
            r = dict(original)
            r['value'] = value
            rules.append(r)
        try:
            validated = validate_freight_rules(rules)
        except (ValueError, TypeError) as exc:
            _notice('运价规则无效：'+str(exc), False)
            return
        if not _confirm('保存分段运价', '确认更改全部汽运费率？历史记录保持原价。'):
            return
        try:
            self.store.set_pref('freight_rules', validated)
            _notice('运价规则已保存')
            self.mode = 'form'
            self._draw()
        except (ValueError, OSError) as exc:
            _notice('保存失败：'+str(exc), False)

    def _reset_rules(self):
        if not _confirm('恢复默认', '确定恢复原版六段汽运费率？'):
            return
        self.store.set_pref('freight_rules', copy.deepcopy(FREIGHT_DEFAULT_RULES))
        _notice('已恢复默认运价')
        self._draw()

    def _draw_history(self):
        records = self.store.list('freight', limit=100)
        if not records:
            card=self._card('历史运费记录', 105)
            self._label(card, 16, 48, card.width-32, 27,
                        '暂无记录。保存一次测算后会显示在这里。', 12, MUTED)
            return
        for record in records:
            payload = record.get('payload') or {}
            result = payload.get('result') or {}
            card = self._card(record.get('title','汽运费记录'), 134)
            self._label(card, 16, 42, card.width-32, 27,
                        '{} 公里 · {} 元/吨'.format(payload.get('distance_km') or '—',
                                                  result.get('final_fee_per_ton','—')), 14, ACCENT, True)
            self._label(card, 16, 73, card.width-32, 22,
                        str(record.get('created_at',''))[:16], 11, MUTED)
            half=(card.width-40)/2
            self._button(card, 16, 99, half, 28,
                         '带入重测', lambda data=copy.deepcopy(payload): self._load_record(data), size=11)
            self._button(card, 24+half, 99, half, 28,
                         '删除记录', lambda rid=record['id']: self._delete_record(rid), size=11)

    def _load_record(self, payload):
        self.d = {key:str(payload.get(key) or '') for key in ('origin','destination','distance_km','notes')}
        self.mode = 'form'
        self._draw()

    def _delete_record(self, record_id):
        if not _confirm('删除汽运费记录', '只软删除该条运费记录，确认？'):
            return
        try:
            self.store.delete(record_id)
            _notice('记录已删除')
            self._draw()
        except (ValueError, OSError) as exc:
            _notice(str(exc), False)


def open_editor(store, prefill=None, mode='form'):
    if ui is None:
        raise RuntimeError('Pythonista ui 不可用')
    editor = FreightEditor(store, prefill)
    if mode in ('form','rules','history') and mode != editor.mode:
        editor.mode = mode
        editor._draw()
    editor.present('fullscreen', hide_title_bar=True)
    return editor
