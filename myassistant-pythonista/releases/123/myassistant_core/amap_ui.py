# -*- coding: utf-8 -*-
"""高德地点搜索（输入稳定版）：单任务队列、轻量防抖、页面关闭保护。"""
import time
from . import amap_service as amap
from . import ui_kit as kit
from .ui_style import PAGE_BG, WHITE, ACCENT, ACCENT_SOFT, TEXT, MUTED, FIELD_BG, safe_top_inset

try:
    import ui
except ImportError:
    ui = None


# 单次停顿才查：中文输入法合成过程不可频繁重建视图或结束键盘编辑。
_SEARCH_IDLE_SECONDS = 0.75


def _alert(message):
    return kit.alert(str(message))


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
    """避免高频搜索线程、键盘反复收起、过期回调访问已关闭视图。"""

    def __init__(self, title, on_selected, keywords='', city=''):
        if ui is None:
            raise RuntimeError('此功能需要 Pythonista UI')
        super().__init__()
        self.name = str(title)
        self.background_color = PAGE_BG
        self.flex = 'WH'
        self.width, self.height = ui.get_screen_size()
        self._on_selected = on_selected
        self._closed = False
        self._busy = False
        self._queued = None
        self._debounce_scheduled = False
        self._edit_at = 0.0
        self._request_id = 0
        self._items = []
        self._build(keywords, city)
        if len(str(keywords or '').strip()) >= 2:
            # 打开页面后首次联想，但不结束输入状态。
            self._edit_at = time.monotonic()
            self._schedule_debounce()

    def _build(self, keywords, city):
        w, h = self.width, self.height
        pad = safe_top_inset(h)
        header_h = pad + 64
        head = ui.View(frame=(0, 0, w, header_h), background_color=WHITE)
        self.add_subview(head)
        kit.button(head, 12, pad+10, 72, 42, '返回', self._close_search)
        kit.label(head, 90, pad+9, max(100, w-180), 44, self.name,
                  17, TEXT, True, getattr(ui, 'ALIGN_CENTER', 1))
        self.scroll = ui.ScrollView(frame=(0, header_h, w, max(1, h-header_h)), background_color=PAGE_BG)
        self.scroll.flex = 'WH'
        self.add_subview(self.scroll)
        card = ui.View(frame=(16, 13, w-32, 207), background_color=WHITE)
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
        self.results_holder = ui.View(frame=(16, 235, w-32, 110), background_color=WHITE)
        self.results_holder.corner_radius = 18
        self.scroll.add_subview(self.results_holder)
        self._render([], '输入关键词后点击搜索；请核对地点所在城市与详细地址。')

    def _close_search(self):
        self._closed = True
        self._request_id += 1
        self._queued = None
        self.close()

    def will_close(self):
        # 用户通过系统关闭操作退出，也不会继续呈现过期结果。
        self._closed = True
        self._request_id += 1
        self._queued = None

    def textfield_did_change(self, field):
        if self._closed or field not in (self.keyword, self.city):
            return
        # 仅记录输入变化。输入法正在拼字时，绝不结束编辑或重建卡片。
        self._request_id += 1
        self._edit_at = time.monotonic()
        self._schedule_debounce()

    def _schedule_debounce(self):
        if self._closed or self._debounce_scheduled:
            return
        self._debounce_scheduled = True
        ui.delay(self._debounce_tick, _SEARCH_IDLE_SECONDS)

    def _debounce_tick(self):
        self._debounce_scheduled = False
        if self._closed:
            return
        if time.monotonic() - self._edit_at < _SEARCH_IDLE_SECONDS - 0.025:
            self._schedule_debounce()
            return
        if len((self.keyword.text or '').strip()) < 2:
            self._queued = None
            self._render([], '请输入至少两个字符的地点关键词。')
            return
        self._request_search()

    def _launch_search(self):
        if self._closed:
            return
        # 手动点击才结束键盘编辑；自动联想始终保持键盘。
        self.keyword.end_editing()
        self.city.end_editing()
        self._request_search()

    def textfield_should_return(self, field):
        field.end_editing()
        self._request_search()
        return True

    def _request_search(self):
        if self._closed:
            return
        words = (self.keyword.text or '').strip()
        city = (self.city.text or '').strip()
        self._request_id += 1
        request = (self._request_id, words, city)
        if len(words) < 2:
            self._queued = None
            self._render([], '请输入至少两个字符的地点关键词。')
            return
        if self._busy:
            # 最多保留最后一次输入，绝不并发生成多个后台搜索任务。
            self._queued = request
            return
        self._start_request(request)

    def _start_request(self, request):
        if self._closed:
            return
        self._busy = True
        self._render([], '正在搜索匹配地址……')
        # 网络任务在 Pythonista 主解释器线程处理，不阻塞界面事件回调。
        ui.in_background(lambda sender: self._run_search(request))(None)

    def _run_search(self, request):
        token, words, city = request
        try:
            found = amap.search_places(words, city)
            message = ('点击准确地址，返回运费页面。' if found
                       else '没有有效坐标的匹配地址，请输入更具体的地点关键词。')
        except amap.AmapError as exc:
            found, message = [], str(exc)
        except Exception:
            found, message = [], '搜索暂时失败，请检查网络后重新搜索。'
        # 不直接在网络任务中修改任何控件。
        if not self._closed:
            ui.delay(lambda: self._complete(request, found, message), 0)

    def _complete(self, request, found, message):
        if self._closed:
            return
        self._busy = False
        pending = self._queued
        self._queued = None
        if pending and pending[0] == self._request_id:
            self._start_request(pending)
            return
        if request[0] != self._request_id:
            # 输入已经变了或用户取消；不显示旧关键词的结果。
            return
        self._render(found, message)

    def _render(self, found, message):
        if self._closed:
            return
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
                row = ui.View(frame=(13, y, holder.width-26, 96), background_color=FIELD_BG)
                row.corner_radius = 11
                holder.add_subview(row)
                kit.label(row, 12, 5, row.width-24, 30, item.get('name') or '无名地址', 15, TEXT, True)
                district = item.get('district') or '未知区域'
                address = item.get('address') or '请核对位置'
                kit.label(row, 12, 35, row.width-24, 51, district + '\n' + address, 12, MUTED)
                tap = ui.Button(frame=row.bounds)
                tap.title = ''
                tap.background_color = (0, 0, 0, 0)
                tap.action = lambda sender, selection=item: self._select(selection)
                row.add_subview(tap)
        self.scroll.content_size = (self.width, 248+height+30)

    def _select(self, item):
        if self._closed:
            return
        callback = self._on_selected
        selection = dict(item)
        self._close_search()
        # 先关闭搜索页，再通知上层重绘，避免嵌套展示窗口竞争。
        ui.delay(lambda: callback(selection), 0.12)


def open_place_search(title, on_selected, keywords='', city=''):
    if ui is None:
        raise RuntimeError('此功能需要 Pythonista UI')
    view = PlaceSearchView(title, on_selected, keywords, city)
    view.present('fullscreen', hide_title_bar=True)
    return view
