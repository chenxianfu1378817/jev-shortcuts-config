# -*- coding: utf-8 -*-
"""《我的助手》统一首页：与报价、运费、输入/列表菜单共享同一套界面语法。"""
from .ui_style import (PAGE_BG, WHITE, ACCENT, ACCENT_SOFT,
                       TEXT, MUTED, BORDER, safe_top_inset)
from . import ui_kit

try:
    import ui
except ImportError:
    ui = None


ACTIONS = (
    ('业务处理', (
        ('日常报价', '多品类组合报价 · 成本/资金/利润', 'quote_menu'),
        ('投标测算', '导入招标文件 · 报价 · 资金条款', 'tender_menu'),
        ('汽运费测算', '里程 · 六段运价 · 历史记录', 'freight_menu'),
        ('AI 智能处理', '智能分流 · 模型配置 · 文本导入', 'ai_menu'),
    )),
    ('经营管理', (
        ('销存管理', '库存流水 · 采购在途 · 纠错', 'inventory_menu'),
        ('工作记录', '今日记录 · 业务跟进 · 历史', 'record_menu'),
    )),
    ('数据与程序', (
        ('备份与导出', '数据备份 · 导出 · 版本回退', 'backup_menu'),
        ('检查并在线更新', '从 GitHub 更新脚本，保留本地数据', 'online_update_menu'),
    )),
)


class HomeScreen(ui.View if ui else object):
    def __init__(self, assistant, version):
        if ui is None:
            raise RuntimeError('需要 Pythonista ui')
        super().__init__()
        self.assistant = assistant
        self.name = '我的助手'
        self.background_color = PAGE_BG
        self.flex = 'WH'
        self.width, self.height = ui.get_screen_size()
        self._build(version)

    def _build(self, version):
        w, h = self.width, self.height
        safe = safe_top_inset(h)
        headh = safe+82
        header = ui.View(frame=(0,0,w,headh))
        header.background_color = WHITE
        self.add_subview(header)
        ui_kit.label(header,20,safe+8,w-40,38,'我的助手',25,TEXT,True)
        ui_kit.label(header,20,safe+44,w-40,27,
                     'Pythonista 经营助手  V{} · 本地数据'.format(version),12,MUTED)
        self.scroll = ui.ScrollView(frame=(0,headh,w,max(1,h-headh)))
        self.scroll.background_color = PAGE_BG
        self.scroll.flex = 'WH'
        self.add_subview(self.scroll)
        y=17
        for group, entries in ACTIONS:
            ui_kit.label(self.scroll,21,y,w-42,30,group,18,TEXT,True)
            y+=37
            for title,subtitle,method in entries:
                card=ui.View(frame=(16,y,w-32,78))
                card.background_color=WHITE
                card.corner_radius=17
                self.scroll.add_subview(card)
                ui_kit.label(card,17,13,card.width-55,27,title,17,ACCENT if method=='online_update_menu' else TEXT,True)
                ui_kit.label(card,17,41,card.width-58,22,subtitle,12,MUTED)
                ui_kit.label(card,card.width-32,22,20,28,'›',23,ACCENT,True)
                b=ui.Button(frame=(0,0,card.width,78))
                b.title=''
                b.background_color='clear'
                b.action=ui.in_background(self._wrap(getattr(self.assistant,method)))
                card.add_subview(b)
                y+=88
            y+=14
        ui_kit.label(self.scroll,18,y,w-36,58,
                     '保存前须确认 · 更新后重新打开程序\n当前不支持原生 LiDAR、完整 OCR 扫描等系统能力',12,MUTED,
                     align=getattr(ui,'ALIGN_CENTER',1))
        self.scroll.content_size=(w,y+94)

    def _wrap(self, action):
        def wrapped(sender):
            try:
                action()
            except KeyboardInterrupt:
                return
            except Exception as exc:
                import traceback
                traceback.print_exc()
                try:
                    ui_kit.alert(str(exc), '执行失败')
                except Exception:
                    import console
                    console.hud_alert('操作失败，请检查日志','error',1.4)
        return wrapped


def open_home(assistant, version):
    view = HomeScreen(assistant, version)
    view.present('fullscreen', hide_title_bar=True)
    return view
