"""Appearance and behavior settings, validated and stored on-device only."""
import re
from ..core.models import InputError

THEMES = {
    '活力橙': '#F28C28', '科技蓝': '#3273E8', '翡翠绿': '#159E76',
    '典雅紫': '#8057C5', '中国红': '#D94141', '玫瑰粉': '#DA6290',
    '深海青': '#198A96', '石墨黑': '#4C566A',
}
MODES = ('跟随系统', '浅色模式', '深色模式')
DEFAULT_APPEARANCE = {'theme': '活力橙', 'mode': '跟随系统', 'custom_color': ''}


class AppearanceSettings:
    def __init__(self, store):
        self.store = store

    def read(self):
        value = self.store.get_setting('appearance', DEFAULT_APPEARANCE)
        if not isinstance(value, dict):
            return dict(DEFAULT_APPEARANCE)
        out = dict(DEFAULT_APPEARANCE)
        out.update({k: value[k] for k in out if k in value})
        if out['theme'] not in THEMES or out['mode'] not in MODES or not isinstance(out['custom_color'], str):
            return dict(DEFAULT_APPEARANCE)
        if out['custom_color'] and not re.fullmatch(r'#[0-9A-Fa-f]{6}', out['custom_color']):
            out['custom_color'] = ''
        return out

    def change(self, theme=None, mode=None, custom_color=None):
        value = self.read()
        if theme is not None:
            if theme not in THEMES:
                raise InputError('Unknown color theme')
            value['theme'] = theme
        if mode is not None:
            if mode not in MODES:
                raise InputError('Unknown appearance mode')
            value['mode'] = mode
        if custom_color is not None:
            if custom_color and (not isinstance(custom_color, str) or
                                 not re.fullmatch(r'#[0-9A-Fa-f]{6}', custom_color)):
                raise InputError('Custom color must be a six digit hex value')
            value['custom_color'] = custom_color
        self.store.put_setting('appearance', value)
        return value

    def palette(self):
        value = self.read()
        return value['custom_color'] or THEMES[value['theme']]
