# -*- coding: utf-8 -*-
"""V1.9 Pythonista direct app navigation; never execute model-provided URLs."""
from urllib.parse import urlsplit
_ALLOWED_CUSTOM = frozenset(("weixin","wxwork","dingtalk","baidumap","snssdk1128","xhsdiscover","taobao","imeituan","alipay","bear","mqqapi"))
_ALLOWED_HOSTS = frozenset(("uri.amap.com","finance.sina.com.cn"))
def validate_target(url):
    if not isinstance(url,str) or not (1 <= len(url) <= 650) or any(ord(c)<32 or ord(c)==127 for c in url):
        raise ValueError("目标网址格式不合法")
    p=urlsplit(url)
    if p.username or p.password: raise ValueError("不允许 URL 内嵌凭据")
    if p.scheme.lower()=="https":
        if p.hostname not in _ALLOWED_HOSTS or p.port is not None: raise ValueError("目标网址不在白名单")
    elif p.scheme.lower() in _ALLOWED_CUSTOM:
        if not url.lower().startswith(p.scheme.lower()+"://"): raise ValueError("应用链接格式不正确")
    else: raise ValueError("未知应用链接")
    return url
def open_target(url,open_func=None,background=None):
    validate_target(url)
    if background is None:
        try:
            import shortcuts
            background=bool(shortcuts.is_running_shortcut())
        except ImportError: background=False
    if background: return {"status":"unavailable","verified":False,"result":"后台扩展不能打开其他 App"}
    if open_func is None:
        try:
            import shortcuts
            open_func=shortcuts.open_url
        except ImportError:
            return {"status":"unavailable","verified":False,"result":"缺少原生打开 URL 接口"}
    try: open_func(url)
    except Exception as e:
        return {"status":"failed","verified":False,"result":"iOS 打开链接异常："+str(e)[:140]}
    return {"status":"ok","verified":False,"result":"已请求 iOS 打开链接，目标页面是否成功打开尚未核验"}
