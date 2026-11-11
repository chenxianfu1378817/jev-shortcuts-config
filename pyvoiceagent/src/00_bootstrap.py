import os
import sys
import re
import json
import uuid
import hmac
import base64
import hashlib
import binascii
import traceback
import time
import tempfile
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit, unquote_to_bytes
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser
import ipaddress
import socket
VERSION = '2.3.8-deepseek-flash'
APP_FILE = 'PYVoiceAgent.py'
CALENDAR_READ_SHORTCUT = 'PYAgentCalendarRead'  # clone of existing PYAgentCalendar
BRIDGE_SHORTCUT = 'PYAgentHub'          # independent of previously verified PYBridgeEcho
LEGACY_BRIDGE = 'PYAgentBridge'
DATA_DIR = os.path.join(os.path.expanduser('~/Documents'), 'PYVoiceAgent_Data')
STATE_PATH = os.path.join(DATA_DIR, 'current_task.json')
MODULE_REGISTRY_PATH = os.path.join(DATA_DIR, 'system_modules.json')
RECOVERY_QUEUE_PATH = os.path.join(DATA_DIR, 'unresolved_writes.json')
REMINDER_LEDGER_PATH = os.path.join(DATA_DIR, 'reminder_ledger.json')
DATE_ONLY_LEDGER_PATH = os.path.join(DATA_DIR, 'date_only_reminders.json')
MODEL_PATH = os.path.join(DATA_DIR, 'deepseek_settings.json')
NOTES_DIR = os.path.join(DATA_DIR, 'notes')
REGISTRY_PATH = os.path.join(DATA_DIR, 'shortcut_registry.json')
AGENT_NOTES_INDEX = os.path.join(DATA_DIR, 'notes_created_index.json')
DEEPSEEK_ENDPOINT = 'https://api.deepseek.com/chat/completions'
DEFAULT_MODEL = 'deepseek-flash'  # DeepSeek V4.1 Flash, official current alias
KEY_SERVICE = 'PYVoiceAgent_DeepSeek'
KEY_ACCOUNT = 'main'
MAX_STEPS = 8
MAX_PLAN_ACTIONS = 5
MAX_CLARIFICATION_ROUNDS = 4
VOICE_LISTEN_LIMIT = 26.0
VOICE_WAIT_FOR_START = 7.0
VOICE_END_SILENCE = 1.15
VOICE_SAMPLE_INTERVAL = 0.12
VOICE_SESSION_ACTIVE = False
VOICE_PRIVACY_PATH = os.path.join(DATA_DIR, 'voice_privacy.json')
MAX_CLIPBOARD_CONTEXT = 4500
LOCAL_READ_ACTIONS = ('reminder.list', 'contacts.lookup', 'maps.search', 'text.respond',
                      'calendar.list', 'notes.search_agent')
LOCAL_WRITE_ACTIONS = ('reminder.complete',)
RESEARCH_ACTIONS = ('calendar.assist', 'webpage.summarize')
ONE_SHOT_TOOLS = ('app.navigate', 'apple_notes.create','calendar.create','reminder.create','local_note.save') + LOCAL_READ_ACTIONS + LOCAL_WRITE_ACTIONS + RESEARCH_ACTIONS
MAX_CLIPBOARD = 7000
MAX_AI_OUTPUT = 12000
MAX_BRIDGE_TEXT = 3500
MAX_SHORTCUTS = 12
BRIDGE_TIMEOUT = 300
TOOL_CATALOG = {
    'clipboard.read': '读取剪贴板，需同意发送给 AI',
    'local_note.save': '保存 Pythonista 本地 TXT 笔记，参数 title/text',
    'reminder.create': '创建并读回核验提醒；同标题同时间避免重复，参数 title/datetime/notes',
    'reminder.list': '查询未完成提醒，datetime/end_datetime 可选用于限定日期范围，本地返回不传 AI',
    'reminder.complete': '将唯一匹配标题的未完成提醒标记已完成，title 精确标题，二次确认',
    'contacts.lookup': '按姓名或公司查询本地联系人，优先精确姓名，其次部分匹配；title 用具体姓名/公司，联系方式留在手机',
    'calendar.list': '通过只读快捷指令 PYAgentCalendarRead 查询苹果日历，datetime/end_datetime 必须是带时区 ISO8601 范围，结果本地回传',
    'calendar.assist': '先查询指定日期内日历，再分析冲突及准备工作；可能生成待确认提醒，datetime/end_datetime 为查询范围',
    'notes.search_agent': '仅搜索自 V1.7 起经本助手成功回调创建的苹果备忘录本地索引，title 为关键词；不是苹果备忘录全文检索',
    'webpage.summarize': '读取用户明确提供的公开 HTTPS 网页后总结，title 放网址；动态网页或登录内容可能不支持；需确认再发送正文给 AI',
    'app.navigate': '跳转第三方 App 功能；amap_search 直接打开原生高德 App 搜索地点，选择地点后由用户点击导航；其他路由需要已导入 PYAgentAppRouter；shortcut_id 仅允许 wechat_scan、wxwork_docs、wxwork_messages、dingtalk_tasks、dingtalk_drive、baidu_search、baidu_nearby、baidu_route、amap_search、douyin_search、douyin_hot、xhs_search、xhs_drafts、taobao_search、taobao_orders、meituan_hotels、alipay_scan、alipay_express、bear_search、qq_scan、sina_bu、sina_sc；需要关键词/目的地则放 text 字段，其他 text 留空。无结果回调，不能声称任务已完成。',
    'maps.search': '优先打开原生苹果地图搜索目的地，title 为名称；只搜索，不自动开始导航',
    'text.respond': '仅用 text 在手机显示整理、总结或解释内容，不写入系统数据',
    'apple_notes.create': '使用已验收的 PYAgentNotes 创建备忘录，参数 title/text',
    'calendar.create': '使用已验收的 PYAgentCalendar 创建日历事件',
    'shortcut.run': '仅调用用户已登记的快捷指令，参数 shortcut_id 等',
    'shortcut.echo': '兼容旧版快捷指令回传测试',
    'shortcut.hub_echo': 'PYAgentHub 往返通信测试',
    'user.ask': '询问用户信息或确认歧义',
    'task.finish': '结束任务并总结已完成事项',
}
TOOLS = tuple(TOOL_CATALOG)
DECISION_SCHEMA = {
    'required': ['tool', 'reason', 'text', 'title', 'datetime', 'notes',
                 'end_datetime', 'shortcut_id']
}
SYSTEM_MODULES = {'apple_notes.create': 'PYAgentNotes',
                  'calendar.create': 'PYAgentCalendar'}
APP_ROUTER_SHORTCUT = 'PYAgentAppRouter'
APP_ROUTER_ENABLED_PATH = os.path.join(DATA_DIR, 'app_router_enabled.json')
APP_FEATURE_ROUTES = {
    'wechat_scan': ("微信扫一扫", "weixin://scanqrcode", None),
    'wxwork_docs': ("企业微信文档", "wxwork://jump?target=doc_tab", None),
    'wxwork_messages': ("企业微信消息", "wxwork://message", None),
    'dingtalk_tasks': ("钉钉待办", "dingtalk://dingtalkclient/action/switchtab?index=1&type=task", None),
    'dingtalk_drive': ("钉钉钉盘", "dingtalk://dingtalkclient/page/yunpan", None),
    'baidu_search': ("百度地图搜索", "baidumap://map/place/search?src=ios.pyvoiceagent.app", "query"),
    'baidu_nearby': ("百度地图附近搜索", "baidumap://map/nearbysearch?src=ios.pyvoiceagent.app", "query"),
    'baidu_route': ("百度地图驾车路线", "baidumap://map/direction?origin=我的位置&mode=driving&src=ios.pyvoiceagent.app", "destination"),
    'amap_search': ("高德地图原生地点搜索", "iosamap://poi?sourceApplication=PYVoiceAgent&dev=0", "name"),
    'douyin_search': ("抖音搜索", "snssdk1128://search", "keyword"),
    'douyin_hot': ("抖音热榜", "snssdk1128://search/trending", None),
    'xhs_search': ("小红书搜索", "xhsdiscover://search/result", "keyword"),
    'xhs_drafts': ("小红书草稿箱", "xhsdiscover://draft_list", None),
    'taobao_search': ("淘宝商品搜索", "taobao://s.taobao.com/search", "q"),
    'taobao_orders': ("淘宝订单", "taobao://go/my_orders", None),
    'meituan_hotels': ("美团酒店搜索", "imeituan://www.meituan.com/hotel/search/input", None),
    'alipay_scan': ("支付宝扫一扫", "alipay://platformapi/startapp?saId=10000007", None),
    'alipay_express': ("支付宝我的快递", "alipay://platformapi/startapp?appId=20000754", None),
    'bear_search': ("熊掌记搜索笔记", "bear://x-callback-url/search", "term"),
    'qq_scan': ("QQ扫一扫", "mqqapi://qrcode/scan_qrcode?version=1&src_type=app", None),
    'sina_bu': ("新浪财经沥青主力", "https://finance.sina.com.cn/futures/quotes/BU0.shtml", None),
    'sina_sc': ("新浪财经原油主力", "https://finance.sina.com.cn/futures/quotes/SC0.shtml", None),
}
