# -*- coding: utf-8 -*-
"""Extracted, unchanged V1.8.3 clipboard contact parser; no system writes."""
import re
CLIP_CONTACT_MAX_CHARS=1800

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


def parse_clipboard(raw):
    """Return unambiguous single contact; refuse freeform chat guesses."""
    import unicodedata
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError('剪贴板为空；请先在微信复制姓名、单位和电话')
    if len(raw) > CLIP_CONTACT_MAX_CHARS:
        raise ValueError('剪贴板文字过长，可能复制了整段聊天；请只复制一人的联系方式（最多1800字）')
    src=unicodedata.normalize('NFKC',raw).replace('\u200b','')
    # Convert inline labeled fields to lines while preserving ordinary company names.
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
        # The phone may appear as a whole line or after a preamble.
        cleared=re.sub(mobile_rx,'',line).strip(' \t,，;；:-')
        if not cleared or re.fullmatch(r'(?:\+86|0086|86)?[\d \t-]+',cleared):
            continue
        unknown.append(cleared)
    # Safely infer from clearly separated, *short* unlabelled lines only.
    # Never guess a person's name by mining an arbitrary chat sentence.
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


