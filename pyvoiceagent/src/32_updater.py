UPDATE_ENGINE_PATH = os.path.join(UPDATE_ENGINE_DIR, 'current.py')
UPDATE_BACKUP_PATH = os.path.join(UPDATE_ENGINE_DIR, 'previous.py')
MAX_UPDATE_BYTES = 350000
FIXED_ENTRY_URL = 'pythonista3://iCloud/PYVoiceAgent.py?action=run'
def _release_download(path, limit):
    if not isinstance(path, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.json|\.py)', path):
        raise ValueError('更新文件名不安全')
    address = UPDATE_RELEASE_ROOT + '/' + path
    req = Request(address, headers={
        'User-Agent': 'PYVoiceAgent/1.5.2',
        'Cache-Control': 'no-cache',
    })
    with urlopen(req, timeout=15) as resp:
        body = resp.read(limit + 1)
    if len(body) > limit:
        raise ValueError('更新文件超过允许大小')
    return body
def _update_sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()
def _update_atomic_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    staging = path + '.part'
    with open(staging, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(staging, path)
def immediate_check_and_update():
    state = get_state()
    if (state.get('pending') and state.get('status') in (
            'awaiting_callback','needs_review','writing')
            and (state.get('pending') or {}).get('tool') != 'calendar.list'):
        return {'updated': False,
                'message': '存在待核验的系统写入，已禁止自动更新；请先人工核实'}
    meta = read_json(UPDATE_META_PATH, {})
    if not isinstance(meta, dict):
        return {'updated':False,'message':'更新状态文件格式异常，未修改'}
    meta['last_checked'] = time.time()
    try:
        release = json.loads(_release_download('manifest.json',16384).decode('utf-8'))
        if not isinstance(release,dict):
            raise ValueError('版本清单格式错误')
        sequence = release.get('sequence')
        version = release.get('version')
        sha = release.get('sha256')
        size = release.get('size_bytes')
        name = release.get('path')
        if (not isinstance(sequence,int) or isinstance(sequence,bool)
                or not 100<=sequence<=99999
                or not isinstance(version,str)
                or not re.fullmatch(r'\d+\.\d+\.\d+',version)
                or not isinstance(sha,str)
                or not re.fullmatch(r'[0-9a-f]{64}',sha)
                or not isinstance(size,int) or isinstance(size,bool)
                or not 1000<=size<=MAX_UPDATE_BYTES
                or not isinstance(name,str)
                or not re.fullmatch(r'[a-zA-Z0-9_-]+\.py',name)):
            raise ValueError('版本清单未通过安全校验')
        installed_seq = int(meta.get('installed_seq',0))
        if sequence <= max(140,installed_seq):
            result = '已是最新版本：{}'.format(meta.get('installed_version',VERSION))
            meta['last_result'] = result
            atomic_json(UPDATE_META_PATH,meta)
            return {'updated':False,'message':result}
        if meta.get('broken_version') == version:
            result = '版本 {} 曾在此设备运行失败，为保护数据不自动重装'.format(version)
            meta['last_result'] = result
            atomic_json(UPDATE_META_PATH,meta)
            return {'updated':False,'message':result}
        data = _release_download(name,size+1)
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:
            raise ValueError('下载文件大小或 SHA256 与发布清单不一致')
        compile(data,name,'exec')
        if os.path.isfile(UPDATE_ENGINE_PATH):
            if not meta.get('sha256') or _update_sha(UPDATE_ENGINE_PATH)!=meta['sha256']:
                raise ValueError('当前缓存引擎校验异常，拒绝覆盖')
            with open(UPDATE_ENGINE_PATH,'rb') as f:
                previous=f.read()
            _update_atomic_bytes(UPDATE_BACKUP_PATH,previous)
            meta['previous_sha256']=hashlib.sha256(previous).hexdigest()
        _update_atomic_bytes(UPDATE_ENGINE_PATH,data)
        meta['sha256']=sha
        meta['installed_seq']=sequence
        meta['installed_version']=version
        meta['last_result']='已安装 '+version
        atomic_json(UPDATE_META_PATH,meta)
        return {'updated':True,'version':version,'message':'已安装 {}'.format(version)}
    except Exception as ex:
        meta['last_result']='立即更新失败：'+str(ex)[:160]
        atomic_json(UPDATE_META_PATH,meta)
        return {'updated':False,'message':meta['last_result']}
def update_from_menu():
    print('正在连接 GitHub，检查并安装最新版本…')
    result=immediate_check_and_update()
    print('[程序更新] '+result['message'])
    if not result.get('updated'):
        try:
            import dialogs
            dialogs.alert('程序更新',result['message'][:500],
                          '确定',hide_cancel_button=True)
        except Exception:
            pass
        return False
    restart=prompt_alert('更新完成',
        '{}。\n是否立即运行新版？如跳转未生效，手动再运行一次 PYVoiceAgent.py。'.format(
            result['message']),ok='立即启动',cancel='稍后')
    if restart:
        try:
            import webbrowser
            webbrowser.open(FIXED_ENTRY_URL)
        except Exception as ex:
            print('自动启动未成功，请手动重新运行固定入口：'+str(ex)[:130])
    return True
def print_update_status():
    info = read_json(os.path.join(DATA_DIR, 'update_meta.json'), {})
    print('当前执行引擎：{}'.format(VERSION))
    print('已安装的版本：{}'.format(info.get('installed_version', '未知')))
    print('最近更新状态：{}'.format(info.get('last_result', '尚未检查')))
    print('固定入口 PYVoiceAgent.py 在非回调启动时检查更新。')
    print('已验收启用的系统模块：')
    for route, name in SYSTEM_MODULES.items():
        print('  {}：{}'.format(name, '可用' if verified_system_module(route) else '尚未验收'))
MAIN_MENU = (
    '1. 语音执行任务',
    '2. 文字／剪贴板任务',
    '3. 查看上次执行结果',
    '4. 立即更新版本',
    '5. 更多与设置',
)
TEXT_MENU = (
    '1. 手动输入任务',
    '2. 使用剪贴板内容',
    '3. 剪贴板→新增通讯录联系人',
    '4. 返回首页',
)
SETTINGS_MENU = (
    '1. 查看已启用工具',
    '2. DeepSeek API 设置',
    '3. 查看当前版本',
    '4. 首次安装／验证系统模块',
    '5. 高级操作与故障排查',
    '6. 语音 AI 自动发送授权',
    '7. 返回首页',
)
ADVANCED_MENU = (
    '1. 继续暂停的任务',
    '2. 查看待核验项目',
    '3. 登记新快捷指令',
    '4. 复杂任务逐步 AI 模式',
    '5. 测试 DeepSeek 连接',
    '6. PYAgentHub 往返自测',
    '7. 测试苹果备忘录',
    '8. PYAgentHub 配置说明',
    '9. 清除当前任务记录',
    '10. 返回设置',
)
