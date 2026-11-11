def now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')
def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(NOTES_DIR, exist_ok=True)
def atomic_json(path, obj):
    ensure_dirs()
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.',
                                suffix='.tmp', dir=parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return {} if default is None else default
def get_state():
    return read_json(STATE_PATH, {})
def put_state(state):
    atomic_json(STATE_PATH, state)
def settings():
    value = read_json(MODEL_PATH, {})
    return {'provider': 'deepseek', 'model': DEFAULT_MODEL, 'endpoint': DEEPSEEK_ENDPOINT,
            'configured': value.get('provider') == 'deepseek'}
def api_key():
    import keychain
    return keychain.get_password(KEY_SERVICE, KEY_ACCOUNT)
def set_ai_credentials():
    import dialogs
    import keychain
    print('当前服务：DeepSeek 官方 API，模型：{}（V4.1 Flash）'.format(DEFAULT_MODEL))
    print('接口：{}'.format(DEEPSEEK_ENDPOINT))
    key = dialogs.password_alert('DeepSeek API Key',
            '请输入从 DeepSeek 开放平台取得的 API Key；留空则保留已有密钥。', '', '保存')
    if key is None:
        return
    key = key.strip()
    if key:
        keychain.set_password(KEY_SERVICE, KEY_ACCOUNT, key)
    if not api_key():
        dialogs.alert('尚未设置密钥', '请填写 DeepSeek 开放平台的 API Key 才能联网调用模型。',
                      '确定', hide_cancel_button=True)
        return
    atomic_json(MODEL_PATH, {'provider': 'deepseek', 'model': DEFAULT_MODEL,
                             'endpoint': DEEPSEEK_ENDPOINT})
    print('已保存 DeepSeek 配置，密钥仅保存在 Pythonista Keychain。')
def prompt_alert(title, message, ok='确认', cancel='取消'):
    import dialogs
    try:
        return dialogs.alert(title, str(message)[:700], ok, cancel, hide_cancel_button=False) == 1
    except KeyboardInterrupt:
        return False
def ask_text(title, initial=''):
    import dialogs
    return dialogs.text_dialog(title, initial)
def pretty_status(state):
    print('\n=== PYVoiceAgent {} ==='.format(VERSION))
    print('任务编号：{}'.format(state.get('id', '')))
    print('任务状态：{}'.format(state.get('status', '')))
    print('用户目标：{}'.format(state.get('goal', '')))
    print('已执行工具：')
    for e in state.get('events', []):
        print('- {}：{}'.format(e.get('tool'), e.get('status')))
        if e.get('tool') in LOCAL_READ_ACTIONS + LOCAL_WRITE_ACTIONS:
            print(str(e.get('result',''))[:2200])
    if state.get('final'):
        print('最后结果：{}'.format(state['final']))
    if state.get('error'):
        print('错误信息：{}'.format(state['error']))
    if state.get('status') == 'needs_input':
        print('等待回答：{}'.format(state.get('clarify_question','')))
    if state.get('pending'):
        print('待回传：{}（标记 {}）'.format(state['pending'].get('tool'), state['pending'].get('marker')))
        print('这不表示系统事项已创建；不确定时选择“人工核验”')
    print(token_usage_report(state))
    print('数据文件：{}'.format(STATE_PATH))
