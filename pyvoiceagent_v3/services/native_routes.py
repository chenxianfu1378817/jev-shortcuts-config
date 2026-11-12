"""Safe local action recognition before the text-only AI fallback.

An external App URL is an unverified handoff, never a completed task.
Only exact, documented URLs are allowed. No dynamic URL from the LLM.
"""
import re

AMAP_URI = 'iosamap://myLocation?sourceApplication=PYVoiceAgent'

_AMAP_COMMANDS = frozenset((
    '打开高德', '打开高德地图', '打开高德导航', '启动高德地图',
    '启动高德导航', '打开高德地图导航', '打开高德地图app',
))

_ACTION_PREFIX = re.compile(
    r'^(?:请|请你|帮我|给我|麻烦你|麻烦)?'
    r'(?:打开|启动|运行|执行|导航去|导航到|带我去|'
    r'创建提醒|添加提醒|设置提醒|新建提醒|'
    r'创建日程|添加日程|新建日程|'
    r'新建备忘录|创建备忘录|添加备忘录|'
    r'拨打电话|发送短信|发短信|保存联系人|新增联系人|'
    r'完成提醒|删除提醒|修改日程)'
)


def match_native(text):
    """Return an allowed handoff, or None; no network or side effects."""
    compact = re.sub(r'\s+', '', str(text or '')).lower()
    compact = compact.rstrip('。.!！')
    if compact in _AMAP_COMMANDS:
        return {
            'kind': 'ios_url_handoff',
            'app_name': '高德地图',
            'url': AMAP_URI,
            'executed': False,
            'requires_user_action': False,
        }
    return None


def is_unhandled_action(text):
    """Do not mislabel an unimplemented iPhone operation as completed AI chat."""
    value = str(text or '').strip()
    if value.endswith(('？', '?')) or value.startswith(('如何', '怎么', '为什么', '能否', '介绍')):
        return False
    return bool(_ACTION_PREFIX.match(value))


def allowed_url(url):
    return url == AMAP_URI
