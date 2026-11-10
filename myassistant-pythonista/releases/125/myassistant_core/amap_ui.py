# -*- coding: utf-8 -*-
"""高德地址搜索：仅手动提交查询；HTTP 工作线程绝不直接触碰 UIKit。

V1.2.4 focused crash isolation. UI always manipulated on UIKit main thread.
The Amap Key remains in Pythonista's Keychain via amap_service.
"""
import threading
import time
from . import amap_service as amap
from . import ui_kit as kit
from .ui_style import PAGE_BG, WHITE, ACCENT, ACCENT_SOFT, TEXT, MUTED, FIELD_BG, safe_top_inset

try:
    import ui
except ImportError:
    ui = None
try:
    from objc_util import on_main_thread
except ImportError:
    def on_main_thread(func):
        return func


def configure_api_key():
    """原 Keychain 存储方式保持不变；不在界面/日志显示已保存密钥。"""
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
    """All UIKit work on main; at most one HTTP request and no implicit search."""
    MAX_ROWS = 6

    def __init__(self, title, on_selected, keywords='', city=''):
        if ui is None:
            raise RuntimeError('此功能需要 Pythonista 3')
        super().__init__()
        self.name = str(title)
        self.background_color = PAGE_BG
        self.flex = 'WH'
        self.width, self.height = ui.get_screen_size()
        self._on_selected = on_selected
        self._closed = False
        self._busy = False
        self._token = 0
        self._items = []
        self._page = 0
        self._build(keywords, city)

    @on_main_thread
    def _build(self, keywords, city):
        w, h = self.width, self.height
        pad = safe_top_inset(h)
        hh = pad + 64
        header = ui.View(frame=(0, 0, w, hh), background_color=WHITE)
        self.add_subview(header)
        kit.button(header, 12, pad+10, 72, 42, '返回', self._close_search)
        kit.label(header, 90, pad+9, max(100, w-180), 44,
                  self.name, 17, TEXT, True, getattr(ui, 'ALIGN_CENTER', 1))
        self.scroll = ui.ScrollView(frame=(0, hh, w, max(1, h-hh)), background_color=PAGE_BG)
        self.scroll.flex = 'WH'
        self.add_subview(self.scroll)
        card = ui.View(frame=(16, 13, w-32, 205), background_color=WHITE)
        card.corner_radius = 18
        self.scroll.add_subview(card)
        kit.label(card, 16, 11, card.width-32, 27, '搜索地图地点', 17, TEXT, True)
        self.keyword = kit.field(card, 16, 44, card.width-32, 46,
                                 keywords, '输入起点、仓库或项目关键词')
        self.city = kit.field(card, 16, 98, card.width-32, 42,
                              city, '限定城市（可不填）')
        self.keyword.delegate = self
        self.city.delegate = self
        self.search_button = kit.button(card, 16, 150, card.width-32, 44,
                                        '搜索匹配地址', self._search_pressed, primary=True)
        self.results_holder = ui.View(frame=(16, 233, w-32, 118), background_color=WHITE)
        self.results_holder.corner_radius = 18
        self.scroll.add_subview(self.results_holder)
        self._render([], '输入关键词后点「搜索匹配地址」，选择正确地点。')

    @on_main_thread
    def _close_search(self):
        self._closed = True
        self._token += 1
        self.close()

    def will_close(self):
        self._closed = True
        self._token += 1

    def textfield_should_return(self, field):
        # Do not recursively resign first responder and launch a search in this delegate.
        return True

    def textfield_did_change(self, field):
        # No network calls or rebuilds while Chinese IME is composing text.
        return

    @on_main_thread
    def _search_pressed(self):
        if self._closed or self._busy:
            return
        keywords = (self.keyword.text or '').strip()
        city = (self.city.text or '').strip()
        if len(keywords) < 2:
            self._render([], '请先输入至少两个字符的关键词。')
            return
        if len(keywords) > 80 or len(city) > 36:
            self._render([], '关键词或城市名称过长，请简化后重试。')
            return
        # Finish IME composition on the UI thread, do not mutate view hierarchy
        # until the click handler returns to UIKit's run loop.
        self.keyword.end_editing()
        self.city.end_editing()
        self._busy = True
        self.search_button.enabled = False
        self._token += 1
        token = self._token
        # Do not rebuild results while UITextField resigns first-responder.
        self.search_button.title = '搜索中……'
        worker = threading.Thread(target=self._search_worker,
                                  args=(token, keywords, city), daemon=True,
                                  name='myassistant-amap-search')
        try:
            worker.start()
        except RuntimeError:
            self._busy = False
            self.search_button.enabled = True
            self.search_button.title = '搜索匹配地址'
            self._render([], '无法启动搜索任务，请重新点击搜索。')

    def _search_worker(self, token, keywords, city):
        try:
            items = amap.search_places(keywords, city, limit=12)
            message = '请选择符合地点和城市的结果。' if items else '没有找到带坐标的地点，请换关键词。'
        except amap.AmapError as exc:
            items, message = [], str(exc)
        except Exception:
            items, message = [], '搜索失败，请检查网络，稍后重试。'
        # Crucial: send results back to UIKit main thread. The worker never calls
        # ui.delay, creates UI objects, calls view.present, or edits controls.
        self._finish_search(token, items, message)

    @on_main_thread
    def _finish_search(self, token, items, message):
        if self._closed or token != self._token:
            return
        self._busy = False
        self.search_button.enabled = True
        self.search_button.title = '搜索匹配地址'
        # Allow IME keyboard dismissal to settle before replacing its sibling views.
        # ui.delay is called on the UIKit main thread, never from the worker.
        ui.delay(lambda: self._show_response(token, items, message), 0.20)

    @on_main_thread
    def _show_response(self, token, items, message):
        if not self._closed and token == self._token:
            self._render(items, message)

    @on_main_thread
    def _render(self, found, message):
        if self._closed:
            return
        self._items = list(found)
        self._page = 0
        self._render_page(message)

    @on_main_thread
    def _render_page(self, message='请选择正确地址。'):
        if self._closed:
            return
        holder = self.results_holder
        for child in list(holder.subviews):
            holder.remove_subview(child)
        page_items = self._items[self._page*self.MAX_ROWS:(self._page+1)*self.MAX_ROWS]
        height = max(114, 68+len(page_items)*106+(53 if len(self._items)>self.MAX_ROWS else 0))
        holder.height = height
        kit.label(holder, 16, 12, holder.width-32, 27,
                  '搜索结果（{}）'.format(len(self._items)), 17, TEXT, True)
        if not page_items:
            kit.label(holder, 16, 46, holder.width-32, 55, message, 13, MUTED)
        else:
            for index, item in enumerate(page_items):
                y = 47+index*106
                row = ui.View(frame=(13, y, holder.width-26, 96), background_color=FIELD_BG)
                row.corner_radius = 11
                holder.add_subview(row)
                kit.label(row, 12, 5, row.width-24, 30, item.get('name') or '无名地址', 15, TEXT, True)
                district = str(item.get('district') or '未知区域')
                address = str(item.get('address') or '请核对位置')
                kit.label(row, 12, 35, row.width-24, 51,
                          district + '\n' + address, 12, MUTED)
                tap = ui.Button(frame=row.bounds)
                tap.title = ''
                tap.background_color = (0, 0, 0, 0)
                tap.action = lambda sender, selected=item: self._select(selected)
                row.add_subview(tap)
            if len(self._items) > self.MAX_ROWS:
                pages = (len(self._items)+self.MAX_ROWS-1)//self.MAX_ROWS
                at = 52+len(page_items)*106
                kit.button(holder, 13, at, holder.width-26, 40,
                           '第 {}/{} 页 · {}'.format(self._page+1,pages,
                           '下一页' if self._page+1<pages else '上一页'), self._next_page)
        self.scroll.content_size = (self.width, 248+height+36)

    @on_main_thread
    def _next_page(self):
        pages = (len(self._items)+self.MAX_ROWS-1)//self.MAX_ROWS
        self._page = (self._page+1) % pages if pages>1 else 0
        self._render_page()

    @on_main_thread
    def _select(self, item):
        if self._closed:
            return
        result = dict(item)
        callback = self._on_selected
        self._close_search()
        # Give UIKit one turn to dismiss the search window before repainting
        # the parent freight page. ui.delay is called exclusively on main.
        ui.delay(lambda: callback(result), 0.20)


def open_place_search(title, on_selected, keywords='', city=''):
    if ui is None:
        raise RuntimeError('此功能需要 Pythonista UI')
    @on_main_thread
    def present():
        view = PlaceSearchView(title, on_selected, keywords, city)
        view.present('fullscreen', hide_title_bar=True)
        return view
    return present()
