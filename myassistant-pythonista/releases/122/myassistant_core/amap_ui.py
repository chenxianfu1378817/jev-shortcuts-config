# -*- coding: utf-8 -*-
"""高德地点搜索与 Key 配置：同《我的助手》卡片式界面。"""
from . import amap_service as amap
from . import ui_kit as kit
from .ui_style import PAGE_BG, WHITE, ACCENT, ACCENT_SOFT, TEXT, MUTED, FIELD_BG, safe_top_inset

try:
    import ui
except ImportError:
    ui = None


def _alert(message):
    # 已在 Pythonista 后台按钮回调中时允许 modal 等待。
    return kit.alert(str(message))


def configure_api_key():
    """密码输入框不回显，保存到 Keychain，绝不写入数据库。"""
    if ui is None:
        raise RuntimeError('请在 Pythonista 中配置高德 API Key')
    pg = kit.ModalPage('高德地图 API 配置', action_title='保存')
    card = pg.card('Web 服务 API Key', 230)
    kit.label(card, 15, 43, card.width-30, 55,
              '在高德开放平台申请「Web服务」类型 Key。\n仅保存在本机 Keychain，不上传云盘。', 13, MUTED)
    key_field = kit.field(card, 15, 104, card.width-30, 47,
                          '', '输入新的高德 Web 服务 API Key')
    key_field.secure = True
    kit.label(card, 15, 159, card.width-30, 45,
              '状态：' + ('已配置（可直接重新输入替换）' if amap.get_api_key() else '尚未配置'),
              12, MUTED)

    def commit():
        key = (key_field.text or '').strip()
        if not key:
            _alert('请先输入新 Key；已配置的 Key 不会自动覆盖。')
            return
        try:
            amap.save_api_key(key)
        except amap.AmapError as exc:
            _alert(exc)
            return
        key_field.text = ''
        pg.value = True
        pg.view.close()

    # 系统 Keychain 与错误提示在后台执行，不能阻塞主 UI 线程。
    pg.commit = lambda: ui.in_background(lambda sender: commit())(None)

    def clear():
        if not kit.confirm('清除 Key', '确定删除本机 Keychain 中保存的高德 Key？'):
            return
        try:
            amap.remove_api_key()
        except amap.AmapError as exc:
            _alert(exc)
            return
        pg.value = True
        pg.view.close()

    kit.button(pg.scroll, 16, pg.cursor, pg.width-32, 50, '保存 / 更换高德 Key', pg.commit, primary=True)
    pg.cursor += 64
    kit.button(pg.scroll, 16, pg.cursor, pg.width-32, 44, '清除已保存 Key',
               lambda: ui.in_background(lambda sender: clear())(None), muted=True)
    pg.cursor += 70
    return pg.finish() is True


class PlaceSearchView(ui.View if ui else object):
    def __init__(self, title, on_selected, keywords='', city=''):
        if ui is None:
            raise RuntimeError('此功能需要 Pythonista UI')
        super().__init__()
        self.name = str(title)
        self.background_color = PAGE_BG
        self.flex = 'WH'
        self.width, self.height = ui.get_screen_size()
        self._on_selected = on_selected
        self._request_token = 0
        self._items = []
        self._build(keywords, city)

    def _build(self, keywords, city):
        w, h = self.width, self.height
        pad = safe_top_inset(h)
        header_h = pad+64
        head = ui.View(frame=(0,0,w,header_h),background_color=WHITE)
        self.add_subview(head)
        kit.button(head, 12, pad+10, 72, 42, '返回', self.close)
        kit.label(head, 90, pad+9, max(100,w-180), 44, self.name,
                  17, TEXT, True, getattr(ui,'ALIGN_CENTER',1))
        self.scroll = ui.ScrollView(frame=(0,header_h,w,max(1,h-header_h)),background_color=PAGE_BG)
        self.scroll.flex = 'WH'
        self.add_subview(self.scroll)
        card = ui.View(frame=(16,13,w-32,207),background_color=WHITE)
        card.corner_radius = 18
        self.scroll.add_subview(card)
        kit.label(card, 16, 11, card.width-32, 26, '搜索地图地点', 17, TEXT, True)
        self.keyword = kit.field(card, 16, 44, card.width-32, 47,
                                 keywords, '输入地点名称、道路、仓库或项目')
        self.keyword.delegate = self
        self.city = kit.field(card, 16, 98, card.width-32, 42,
                              city, '城市筛选（可空，如南宁、钦州）')
        self.city.delegate = self
        kit.button(card, 16, 150, card.width-32, 43,
                   '搜索匹配地址', self._launch_search, primary=True)
        self.results_holder = ui.View(frame=(16,235,w-32,110),background_color=WHITE)
        self.results_holder.corner_radius=18
        self.scroll.add_subview(self.results_holder)
        self._render([], '输入关键词后点击搜索；请核对地点所在城市与详细地址。')

    def _launch_search(self):
        # 所有 TextField 读取与键盘操作都放在主 UI 线程；只让 HTTP 在后台执行。
        self.keyword.end_editing()
        self.city.end_editing()
        keywords = (self.keyword.text or '').strip()
        city = (self.city.text or '').strip()
        self._request_token += 1
        token = self._request_token
        self._render([], '正在向高德搜索地址……')
        ui.in_background(lambda sender: self._run_search(token, keywords, city))(None)

    def textfield_did_change(self, field):
        # 输入停止约半秒后自动弹出候选；每次编辑取消旧请求的展示资格。
        if field is not self.keyword:
            return
        self._request_token += 1
        token = self._request_token
        if len((field.text or '').strip()) < 2:
            self._render([], '请输入至少两个字符的地点关键词。')
            return
        ui.delay(lambda: self._launch_if_current(token), 0.55)

    def _launch_if_current(self, token):
        if token == self._request_token:
            self._launch_search()

    def textfield_should_return(self, field):
        field.end_editing()
        self._launch_search()
        return True

    def _run_search(self, token, keywords, city):
        try:
            found = amap.search_places(keywords, city)
        except amap.AmapError as exc:
            message = str(exc)
            self._apply_on_ui(lambda: self._show_if_current(token, [], message))
            return
        except Exception:
            self._apply_on_ui(lambda: self._show_if_current(token, [], '搜索失败，请检查网络并重试'))
            return
        self._apply_on_ui(lambda: self._show_if_current(token, found,
                          '没有有效坐标的匹配地址，请增加城市或更具体的关键词。' if not found else '点击准确地址，返回运费页面。'))

    def _apply_on_ui(self, action):
        # Pythonista 的 ui.delay 在主 UI 队列运行，网络请求仍位于后台线程。
        ui.delay(action, 0)

    def _show_if_current(self, token, found, message):
        if token != self._request_token:
            return
        self._render(found, message)

    def _render(self, found, message):
        self._items = list(found)
        holder = self.results_holder
        for child in list(holder.subviews):
            holder.remove_subview(child)
        height = max(116, 75+len(self._items)*106)
        holder.height = height
        kit.label(holder, 16, 12, holder.width-32, 26,
                  '搜索结果（{}）'.format(len(self._items)), 17, TEXT, True)
        if not self._items:
            kit.label(holder, 16, 46, holder.width-32, 54, message, 13, MUTED)
        else:
            for index, item in enumerate(self._items):
                y = 48 + index*106
                row = ui.View(frame=(13,y,holder.width-26,96),background_color=FIELD_BG)
                row.corner_radius=11
                holder.add_subview(row)
                kit.label(row, 12, 5, row.width-24, 30, item.get('name') or '无名地址', 15, TEXT, True)
                district = item.get('district') or '未知区域'
                address = item.get('address') or '请核对位置'
                kit.label(row, 12, 35, row.width-24, 51,
                          district + '\n' + address, 12, MUTED)
                tap = ui.Button(frame=row.bounds)
                tap.title=''
                tap.background_color=(0,0,0,0)
                tap.action=lambda sender, selection=item:self._select(selection)
                row.add_subview(tap)
        self.scroll.content_size=(self.width, 248+height+30)

    def _select(self, item):
        self._request_token += 1
        self._on_selected(dict(item))
        self.close()


def open_place_search(title, on_selected, keywords='', city=''):
    if ui is None:
        raise RuntimeError('此功能需要 Pythonista UI')
    view=PlaceSearchView(title,on_selected,keywords,city)
    view.present('fullscreen',hide_title_bar=True)
    return view
