def _cc_trigger(goal):
    g = str(goal or '').replace('粘贴板', '剪贴板').replace('通信录', '通讯录').strip()
    g = re.sub(r'[。！!？?\s]+$', '', g).strip()
    if not (4 <= len(g) <= 180):
        return False
    disallowed = (
        '不要','不用','别','禁止','取消','不想','不需要',
        '能不能','可不可以','怎么','如何','为什么','是否','是不是',
        '然后','并且','顺便','同时','再帮','接着','随后','下一步',
        '分析','总结','查找','查询','搜索','看看','核对',
        '删除','修改','更新','发给','发送','转发','分享','传给',
        '群发','打电话','拨打','照片','头像','截图','二维码','视频','语音',
    )
    if any(x in g for x in disallowed) or re.search(r'先.+再', g):
        return False
    not_contacts_destinations = (
        '备忘录','提醒事项','待办','表格','Excel','文件夹',
        '文本文件','PDF','邮件','邮箱','网盘','数据库',
        '微信收藏','微信笔记',
    )
    if any(x in g for x in not_contacts_destinations):
        return False
    has_person = any(x in g for x in (
        '通讯录','手机联系人','联系人','联系方式','客户联系信息',
    ))
    has_source = any(x in g for x in (
        '剪贴板','复制','微信发来','微信好友','微信里','刚收到','粘贴',
    ))
    wants_import = any(x in g for x in (
        '录入','导入','添加','新增','保存','存到','存入','存进',
        '记到','建个','新建','加到',
    ))
    return has_person and has_source and wants_import
def _cc_digits(text):
    digits = re.sub(r'\D','',str(text or ''))
    if digits.startswith('0086') and len(digits) == 15:
        digits = digits[4:]
    elif digits.startswith('86') and len(digits) == 13:
        digits = digits[2:]
    if re.fullmatch(r'1[3-9]\d{9}', digits):
        return digits
    return ''
def _cc_mask(phone):
    phone=str(phone or '')
    return phone[:3]+'****'+phone[-4:] if len(phone)>=8 else '***'
def _cc_clean(value):
    return str(value or '').strip(' \t\r\n:：;；,，。.|｜-—“”"「」()（）')
def _cc_parse_clipboard(raw):
    import unicodedata
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError('剪贴板为空；请先在微信复制姓名、单位和电话')
    if len(raw) > CLIP_CONTACT_MAX_CHARS:
        raise ValueError('剪贴板文字过长，可能复制了整段聊天；请只复制一人的联系方式（最多1800字）')
    src=unicodedata.normalize('NFKC',raw).replace('\u200b','')
    src=re.sub(r'[,，;；]\s*(?=(?:姓名|名字|联系人|单位|公司|所属单位|工作单位|手机|电话|手机号|联系电话)\s*[:：])',
               '\n',src)
    src=re.sub(r'\s+(?=(?:姓名|名字|单位|公司|手机|电话|联系电话)\s*[:：])',
               '\n',src)
    mobile_rx=r'(?<!\d)(?:(?:\+86|0086|86)[ \t-]?)?1[3-9](?:[ \t-]?\d){9}(?!\d)'
    candidates=[]
    for m in re.finditer(mobile_rx,src):
        phone=_cc_digits(m.group(0))
        if phone:
            candidates.append(phone)
    phones=list(dict.fromkeys(candidates))
    if len(phones)!=1:
        if len(phones)>1:
            raise ValueError('检测到多个不同手机号；请每次只复制一个人的联系方式')
        raise ValueError('未找到有效的中国大陆手机号；请检查是否复制了完整的11位号码')
    phone=phones[0]
    fields={'name':[],'organization':[]}
    unknown=[]
    name_rx=r'(?:姓名|名字|联系人姓名|联系人|微信姓名|真实姓名|称呼)'
    org_rx=r'(?:工作单位|所属单位|任职单位|公司名称|所在单位|单位|公司|组织|机构|企业)'
    phone_rx=r'(?:手机号码|手机号码|手机号|手机|联系电话|电话号码|电话|联系方式)'
    for line in src.splitlines():
        line=_cc_clean(line)
        if not line:
            continue
        found=False
        for key,patt in (('name',name_rx),('organization',org_rx)):
            m=re.fullmatch(r'(?:'+patt+r')\s*[:：\s]+\s*(.+)',line,flags=re.I)
            if m:
                val=_cc_clean(m.group(1))
                if val:
                    fields[key].append(val)
                found=True
                break
        if found:
            continue
        if re.match(r'^(?:'+phone_rx+r')\s*[:：\s]',line,flags=re.I):
            continue
        cleared=re.sub(mobile_rx,'',line).strip(' \t,，;；:-')
        if not cleared or re.fullmatch(r'(?:\+86|0086|86)?[\d \t-]+',cleared):
            continue
        unknown.append(cleared)
    if not fields['name'] and unknown:
        first=_cc_clean(unknown[0])
        if (re.fullmatch(r'[\u4e00-\u9fff·]{2,5}',first)
                and not first.endswith(('经理','主任','老师','书记','先生','女士','总工'))):
            fields['name'].append(first)
            unknown=unknown[1:]
        elif len(unknown)==1:
            match=re.fullmatch(r'([\u4e00-\u9fff·]{2,5})[\s,，]+(.{3,90})',first)
            if (match and match.group(1) not in ('你好','您好','请问','谢谢','我们','老板')
                    and re.search(r'公司|集团|有限|股份|工程|项目部|分公司|研究院|交通|建设|供应链|养护|材料|科技|商贸|中建|中铁|交投|北投|石化|高速|管理局|设计院',match.group(2))):
                fields['name'].append(match.group(1))
                unknown=[_cc_clean(match.group(2))]
    if not fields['organization'] and unknown:
        orgs=[v for v in unknown if (3<=len(v)<=90 and
              re.search(r'公司|集团|有限|股份|工程|项目部|分公司|研究院|交通|建设|供应链|养护|材料|科技|商贸|中建|中铁|交投|北投|石化|高速|管理局|设计院',v))]
        if len(orgs)==1 and len(unknown)==1:
            fields['organization'].append(orgs[0])
    for key in fields:
        values=list(dict.fromkeys(_cc_clean(x) for x in fields[key] if _cc_clean(x)))
        if len(values)>1:
            raise ValueError('复制内容中有多个不同{}，请每次只录入一人'.format('姓名' if key=='name' else '单位'))
        fields[key]=values
    if not fields['name']:
        raise ValueError('未能可靠识别姓名；建议使用“姓名：张三”换行“单位：XX”格式')
    name=fields['name'][0]
    org=fields['organization'][0] if fields['organization'] else ''
    if not (2<=len(name)<=30) or re.search(r'[\d@:/\\]',name):
        raise ValueError('姓名包含异常字符或长度异常，请检查')
    if len(org)>100 or re.search(r'[\r\n<>]',org):
        raise ValueError('单位名称格式异常，请检查')
    if re.search(r'\b(?:https?://|www\.)',src,re.I):
        raise ValueError('复制内容含外部链接，请仅复制联系人信息')
    return {'name':name,'organization':org,'phone':phone}
def _cc_load_ledger():
    try:
        with open(CLIP_CONTACT_LEDGER_PATH,'r',encoding='utf-8') as f:
            value=json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError,ValueError) as exc:
        raise RuntimeError('联系人防重复记录读取失败，已阻止保存：'+str(exc)[:100])
    if not isinstance(value,dict) or len(value)>3000:
        raise RuntimeError('联系人防重复记录格式异常，已阻止保存')
    return value
def _cc_persist_result(status,message,verified=False):
    summary={'status':status,'result':str(message)[:240],
             'verified':bool(verified),'timestamp':now_iso()}
    try:
        atomic_json(CLIP_CONTACT_LAST_PATH,summary)
    except Exception:
        pass
    print('=== 微信联系方式 → 苹果通讯录 ===')
    print(summary['result'])
    print('状态：{}；{}；本次没有调用 DeepSeek。'.format(
        status,'已读回核验' if verified else '未核验/未写入'))
    return summary
def _cc_existing_matches(people,name,org,phone):
    same_number=[]
    same_name=[]
    for person in people:
        person_name=str(getattr(person,'full_name','') or '').strip()
        if person_name==name:
            same_name.append(person)
        for item in (getattr(person,'phone',None) or []):
            if not isinstance(item,(list,tuple)) or len(item)<2:
                continue
            if _cc_digits(item[1])==phone:
                same_number.append(person)
                break
    return same_number,same_name
def _cc_import_clipboard():
    import clipboard
    try:
        item=_cc_parse_clipboard(clipboard.get())
    except (ValueError,TypeError) as exc:
        return _cc_persist_result('failed',str(exc))
    name,org,phone=item['name'],item['organization'],item['phone']
    masked=_cc_mask(phone)
    try:
        import contacts
        if not contacts.is_authorized():
            return _cc_persist_result('unavailable',
                '未获得通讯录访问权限；请在 iOS 设置 → Pythonista → 通讯录中授权')
        people=list(contacts.get_all_people() or [])
    except Exception as exc:
        return _cc_persist_result('failed','读取通讯录失败，请检查访问权限：'+str(exc)[:120])
    existed,same_name=_cc_existing_matches(people,name,org,phone)
    if existed:
        return _cc_persist_result('existing',
            '通讯录中已存在相同号码 {}，未重复添加或覆盖。'.format(masked),True)
    if same_name:
        return _cc_persist_result('needs_review',
            '通讯录中已存在姓名为「{}」的联系人，但号码不同；请先人工检查，不自动合并或覆盖。'.format(name))
    key=hashlib.sha256((name+'|'+phone).encode('utf-8')).hexdigest()
    try:
        ledger=_cc_load_ledger()
        if key in ledger:
            return _cc_persist_result('needs_review',
                '该姓名和号码有历史写入记录，但本次未在可访问的通讯录中读到；请先人工核验，禁止自动重试。')
    except RuntimeError as exc:
        return _cc_persist_result('needs_review',str(exc))
    preview=('姓名：{}\n单位：{}\n电话：{}\n\n仅写入本机苹果通讯录，不会发送给 DeepSeek。\n'
             '若姓名或单位识别有误，请取消，重新复制规范文本。').format(
                 name,org or '（未提供）',phone)
    if not prompt_alert('确认新增手机联系人',preview,'保存','取消'):
        return _cc_persist_result('declined','你取消了新增联系人，通讯录未修改。')
    ledger[key]={'state':'intent','at':now_iso()}
    try:
        atomic_json(CLIP_CONTACT_LEDGER_PATH,ledger)
    except Exception as exc:
        return _cc_persist_result('needs_review','保存防重复记录失败，尚未写入通讯录：'+str(exc)[:110])
    try:
        person=contacts.Person()
        person.first_name=name  # Display full Chinese name without guessing surname.
        person.organization=org
        person.phone=[(contacts.IPHONE,phone)]
        contacts.add_person(person)
        contacts.save()
    except Exception as exc:
        try:
            contacts.revert()
        except Exception:
            pass
        return _cc_persist_result('needs_review',
            '通讯录保存过程发生异常；可能已部分写入，请人工核对，程序不会重试：'+str(exc)[:120])
    try:
        verified=list(contacts.get_all_people() or [])
        by_number,_=_cc_existing_matches(verified,name,org,phone)
        exact=[p for p in by_number if
               str(getattr(p,'full_name','') or '').strip()==name and
               str(getattr(p,'organization','') or '').strip()==org]
        if len(exact)!=1:
            return _cc_persist_result('needs_review',
                '已调用通讯录保存，但未能唯一读回姓名/单位/号码，请到通讯录核对，禁止自动重试。')
        ledger[key]={'state':'verified','at':now_iso()}
        try:
            atomic_json(CLIP_CONTACT_LEDGER_PATH,ledger)
        except Exception as exc:
            return _cc_persist_result('needs_review',
                '已从通讯录读回联系人，但保存防重复凭据失败；请人工核对：'+str(exc)[:100])
    except Exception as exc:
        return _cc_persist_result('needs_review',
            '已调用保存，但读回通讯录失败；请手动检查：'+str(exc)[:100])
    return _cc_persist_result('ok',
        '已保存并读回核验：{} / {} / {}'.format(name,org or '无单位',masked),True)
_LOCAL_QUICK_STATIC = {
    'wechat_scan': ('微信扫一扫','微信扫二维码','微信扫码','微信扫扫'),
    'wxwork_docs': ('企业微信文档','企业微信的文档'),
    'wxwork_messages': ('企业微信消息','企业微信的消息'),
    'dingtalk_tasks': ('钉钉待办','钉钉的待办','钉钉待办事项'),
    'dingtalk_drive': ('钉钉钉盘','钉钉云盘'),
    'douyin_hot': ('抖音热榜','抖音热门榜单'),
    'xhs_drafts': ('小红书草稿箱','小红书草稿'),
    'taobao_orders': ('淘宝订单','淘宝我的订单'),
    'meituan_hotels': ('美团酒店搜索','美团酒店'),
    'alipay_scan': ('支付宝扫一扫','支付宝扫码','支付宝扫二维码'),
    'alipay_express': ('支付宝我的快递','支付宝快递','支付宝查快递'),
    'qq_scan': ('QQ扫一扫','QQ扫码'),
    'sina_bu': ('新浪财经沥青行情','新浪财经沥青期货','新浪沥青期货'),
    'sina_sc': ('新浪财经原油行情','新浪财经原油期货','新浪原油期货'),
}
_LOCAL_QUICK_DYNAMIC = (
    ('baidu_nearby',r'百度地图(?:查找|查询|搜索|找|查)(?:附近|周边)(?P<q>.+)'),
    ('baidu_nearby',r'百度地图(?:附近|周边)(?:查找|查询|搜索|找|查)(?P<q>.+)'),
    ('baidu_route',r'百度地图(?:导航|驾车|开车|规划路线|路线)(?:到|去|至)?(?P<q>.+)'),
    ('baidu_search',r'百度地图(?:搜索|查找|查询|搜一下|查一下|找找|搜)(?P<q>.+)'),
    ('amap_search',r'(?:高德地图|高德)(?:驾车导航|导航|驾车路线|路线规划|路线|开车)(?:到|去|至)?(?P<q>.+)'),
    ('amap_search',r'高德地图(?:搜索|查找|查询|搜一下|查一下|找找|搜)(?P<q>.+)'),
    ('douyin_search',r'抖音(?:上|里|里面)?(?:搜索|查找|查询|搜一下|查一下|找找|搜)(?P<q>.+)'),
    ('xhs_search',r'小红书(?:上|里|里面)?(?:搜索|查找|查询|搜一下|查一下|找找|搜)(?P<q>.+)'),
    ('taobao_search',r'淘宝(?:上|里|里面)?(?:搜索|查找|查询|搜一下|查一下|找找|搜)(?P<q>.+)'),
    ('bear_search',r'熊掌记(?:里|里面)?(?:搜索|查找|查询|搜一下|查一下|找找|搜)(?P<q>.+)'),
)
_LOCAL_COMPOUND_OR_UNSAFE = (
    '不要','不准','禁止','别打开','别用','别帮','取消','别再',
    '然后','之后','接着','顺便','同时','并且','再把','再帮',
    '如果','假如','若是','先查','先看','一边','另外',
    '整理','总结','分析','翻译','发给','发送','分享',
    '保存到','保存进','加入','加到','录入','创建',
    '下载','导出','删除','修改','转账','付款','发消息','发微信',
)
_LOCAL_PREFIX = re.compile(
    r'^(?:(?:请|麻烦你|麻烦|帮我|替我|给我|我想|我要|'
    r'打开|进入|调出|启动|去|到|在|用|现在|马上)\s*){0,5}')
