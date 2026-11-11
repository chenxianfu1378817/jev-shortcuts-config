def _app_router_enabled():
    try:
        with open(APP_ROUTER_ENABLED_PATH, 'r', encoding='utf-8') as f:
            value = json.load(f)
        return (isinstance(value, dict) and value.get('enabled') is True
                and value.get('user_confirmed') is True
                and value.get('shortcut_name') == APP_ROUTER_SHORTCUT)
    except (OSError, ValueError, TypeError):
        return False
def _app_route_target(choice):
    route_id = str(choice.get('shortcut_id', '')).strip()
    if route_id not in APP_FEATURE_ROUTES:
        raise ValueError('未知或未授权的 App 功能 ID：' + route_id[:36])
    label, base, param = APP_FEATURE_ROUTES[route_id]
    raw_query = str(choice.get('text', ''))
    if re.search(r'[\x00-\x1f\x7f]', raw_query):
        raise ValueError('搜索参数不得包含换行或控制字符')
    query = raw_query.strip()
    if param:
        if not (1 <= len(query) <= 90) or re.search(r'[\x00-\x1f\x7f]', query):
            raise ValueError('搜索词/目的地必须明确，长度 1～90 字，放在 text 字段')
        target = base + ('&' if '?' in base else '?') + urlencode({param:query})
    else:
        if query:
            raise ValueError('此功能不支持额外搜索参数')
        target = base
    if len(target) > 650:
        raise ValueError('目标链接超出安全长度')
    return label, target
def _app_route_handoff(state, choice):
    route_id = str(choice.get('shortcut_id', '')).strip()
    if route_id != 'amap_search' and not _app_router_enabled():
        return {'status':'unavailable', 'verified':False,
                'result':'请先在 iPhone Pythonista 确认安装并启用 PYAgentAppRouter'}
    try:
        label, target = _app_route_target(choice)
    except (TypeError, ValueError) as exc:
        return {'status':'failed','verified':False,'result':str(exc)[:170]}
    import shortcuts
    try:
        if route_id == 'amap_search':
            shortcuts.open_url(target)
        else:
            url = 'shortcuts://run-shortcut?' + urlencode({
                'name':APP_ROUTER_SHORTCUT, 'input':'text', 'text':target})
            shortcuts.open_url(url)
    except Exception as exc:
        return {'status':'failed','verified':False,
                'result':'请求打开 App 失败（不自动重试）：'+str(exc)[:140]}
    if route_id == 'amap_search':
        return {'status':'ok','verified':False,
                'result':'已请求唤起高德地图 App 并搜索目的地；请选择正确地点再点击「导航」，尚未核验 App 是否打开'}
    return {'status':'ok','verified':False,
            'result':'已请求打开「'+label+'」；实际目标页面是否打开仍需手机确认'}
CLIP_CONTACT_LEDGER_PATH = os.path.join(DATA_DIR, 'clipboard_contact_ledger.json')
CLIP_CONTACT_LAST_PATH = os.path.join(DATA_DIR, 'clipboard_contact_last.json')
CLIP_CONTACT_MAX_CHARS = 1800
