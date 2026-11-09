# -*- coding: utf-8 -*-
"""《我的助手》统一移动端色板、导航安全区与可复用界面参数。"""
PAGE_BG = '#f3f4f8'
WHITE = '#ffffff'
ACCENT = '#eb811f'
ACCENT_SOFT = '#fdf0e3'
TEXT = '#20252c'
MUTED = '#778290'
FIELD_BG = '#f3f4f8'
BORDER = '#e6e8ec'
DANGER = '#ca4144'


def safe_top_inset(screen_height=None):
    """为刘海、灵动岛、状态栏保留空间，避免与导航栏重叠。

    UIWindow.safeAreaInsets 在 Pythonista 弹出的全屏 ui.View 中有时仍然返回前一窗口的
    20pt（截图中状态栏与返回按钮重叠）；现代长屏机最低保留 58pt。
    """
    if screen_height is None:
        try:
            import ui
            screen_height = ui.get_screen_size()[1]
        except (ImportError, AttributeError):
            screen_height = 844
    minimum = 58 if screen_height >= 780 else 26
    try:
        from objc_util import ObjCClass
        app = ObjCClass('UIApplication').sharedApplication()
        w = app.keyWindow()
        if w:
            value = float(w.safeAreaInsets().top)
            if 12 <= value <= 90:
                return max(minimum, value)
    except Exception:
        pass
    return minimum


def screen_size():
    try:
        import ui
        return ui.get_screen_size()
    except (ImportError, AttributeError):
        return (390, 844)
