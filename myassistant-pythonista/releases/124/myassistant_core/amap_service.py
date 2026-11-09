# -*- coding: utf-8 -*-
"""高德 Web 服务地址候选与驾车里程。仅访问高德 HTTPS API。

API Key 储存在 Pythonista 的 Keychain，不记录到 sqlite、日志或更新包。
返回的路径是普通驾车方案，不能当作货车许可通行/结算里程。
"""
import json
import math
import re
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

_KEYCHAIN_SERVICE = 'com.penchen.myassistant.amap-webservice'
_KEYCHAIN_ACCOUNT = 'api_key'
_TIPS_URL = 'https://restapi.amap.com/v3/assistant/inputtips'
_ROUTE_URL = 'https://restapi.amap.com/v5/direction/driving'
_COORD = re.compile(r'^\s*(-?\d{1,3}(?:\.\d{1,8})?)\s*,\s*(-?\d{1,3}(?:\.\d{1,8})?)\s*$')
_RESPONSE_LIMIT = 1024 * 1024


class AmapError(ValueError):
    """可显示给用户的错误，不包含带有 Key 的 URL。"""


def get_api_key():
    try:
        import keychain
        return (keychain.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT) or '').strip()
    except ImportError:
        return ''
    except Exception:
        return ''


def save_api_key(value):
    value = (value or '').strip()
    if not 8 <= len(value) <= 128 or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise AmapError('API Key 格式不正确，请复制高德 Web 服务 Key')
    try:
        import keychain
        keychain.set_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT, value)
    except ImportError:
        raise AmapError('当前环境缺少 Pythonista Keychain')
    except Exception:
        raise AmapError('Keychain 保存失败，请检查 Pythonista 权限')


def remove_api_key():
    try:
        import keychain
        keychain.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
    except ImportError:
        raise AmapError('当前环境缺少 Pythonista Keychain')
    except Exception:
        raise AmapError('无法从 Keychain 删除高德 Key')


def _key(value):
    value = (value if value is not None else get_api_key()) or ''
    if not value.strip():
        raise AmapError('尚未配置高德 Web 服务 API Key，请先点「配置高德 Key」')
    return value.strip()


def _request(url, params, timeout=9):
    """对外统一调用点，测试时可替换。禁止把含 Key 的 URL 输出到异常中。"""
    address = url + '?' + urlencode(params)
    try:
        request = Request(address, headers={'User-Agent': 'MyAssistant-Pythonista/1.2', 'Accept': 'application/json'})
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(_RESPONSE_LIMIT + 1)
        if len(raw) > _RESPONSE_LIMIT:
            raise AmapError('高德响应内容过大，已停止解析')
        data = json.loads(raw.decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, OSError):
        raise AmapError('连接高德失败，请检查网络、配额和 API Key')
    except (ValueError, UnicodeError):
        raise AmapError('高德返回的数据格式异常')
    if not isinstance(data, dict):
        raise AmapError('高德返回的数据格式异常')
    if str(data.get('status')) != '1':
        code = str(data.get('infocode') or '')[:12]
        info = str(data.get('info') or '调用失败')[:80]
        info = info.replace(str(params.get('key') or ''), '***')
        # 不回显请求 URL，避免将 Key 暴露到错误界面或截图中
        raise AmapError('高德接口异常：{} {}'.format(code, info))
    return data


def validate_location(value):
    if not isinstance(value, str):
        raise AmapError('地点缺少可用于算路的坐标，请换一个候选地址')
    match = _COORD.fullmatch(value)
    if not match:
        raise AmapError('地点缺少可用于算路的坐标，请换一个候选地址')
    lon, lat = (float(match.group(1)), float(match.group(2)))
    if not (-180 <= lon <= 180 and -90 <= lat <= 90) or not (math.isfinite(lon) and math.isfinite(lat)):
        raise AmapError('地点经纬度超出有效范围')
    return '{:.6f},{:.6f}'.format(lon, lat)


def search_places(keywords, city='', api_key=None, limit=12):
    """返回可选 POI，剔除没有合法经纬度的输入提示。"""
    term = str(keywords or '').strip()
    if len(term) < 2:
        raise AmapError('请输入至少两个字符的地点关键词')
    if len(term) > 80:
        raise AmapError('关键词请不要超过 80 个字符')
    params = {'key': _key(api_key), 'keywords': term, 'datatype': 'poi', 'output': 'JSON'}
    city = str(city or '').strip()
    if city:
        if len(city) > 36:
            raise AmapError('城市名称过长')
        params['city'] = city
        params['citylimit'] = 'false'
    data = _request(_TIPS_URL, params)
    tips = data.get('tips')
    if not isinstance(tips, list):
        return []
    items = []
    seen = set()
    for item in tips:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        if not name:
            continue
        try:
            point = validate_location(item.get('location'))
        except AmapError:
            continue
        district = str(item.get('district') or '').strip()
        address = item.get('address')
        if not isinstance(address, str):
            address = ''
        address = address.strip()
        identifier = item.get('id')
        identifier = str(identifier).strip() if isinstance(identifier, str) else ''
        identity = (identifier or name, point)
        if identity in seen:
            continue
        seen.add(identity)
        items.append({'name': name, 'district': district, 'address': address,
                      'location': point, 'id': identifier, 'adcode':str(item.get('adcode') or '')})
        if len(items) >= min(max(int(limit), 1), 20):
            break
    return items


def plan_driving(origin, destination, api_key=None):
    """返回高德方案列表；米转公里。不提供虚假的货车专用道路保证。"""
    if not isinstance(origin, dict) or not isinstance(destination, dict):
        raise AmapError('请先搜索并选定起运地和目的地')
    src = validate_location(origin.get('location'))
    dst = validate_location(destination.get('location'))
    if src == dst:
        raise AmapError('起点终点相同，请核对位置')
    params = {'key': _key(api_key), 'origin':src, 'destination':dst,
              'strategy':'32', 'alternative_route':'3', 'show_fields':'cost', 'output':'json'}
    if origin.get('id'):
        params['origin_id'] = str(origin['id'])
    if destination.get('id'):
        params['destination_id'] = str(destination['id'])
    response = _request(_ROUTE_URL, params, timeout=12)
    route = response.get('route') or {}
    paths = route.get('paths') if isinstance(route, dict) else None
    if not isinstance(paths, list) or not paths:
        raise AmapError('未查到可用驾车路线，请调整地点或手工输入里程')
    results=[]
    for path in paths[:3]:
        if not isinstance(path,dict):continue
        try:
            metres = float(path.get('distance'))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(metres) or metres <= 0 or metres > 100000000:
            continue
        cost = path.get('cost') if isinstance(path.get('cost'),dict) else {}
        duration = cost.get('duration') or path.get('duration')
        try:
            seconds = int(float(duration))
            seconds = seconds if 0 < seconds < 10000000 else None
        except (TypeError,ValueError):
            seconds=None
        results.append({'distance_m':int(round(metres)), 'distance_km':round(metres/1000, 2),
                        'duration_minutes':round(seconds/60) if seconds else None,
                        'strategy':32, 'route_index':len(results),
                        'restriction':str(path.get('restriction') or ''),
                        'fetched_at':datetime.now().astimezone().isoformat(timespec='seconds')})
    if not results:
        raise AmapError('高德路线没有有效里程，请手工填写实际公里数')
    return results
