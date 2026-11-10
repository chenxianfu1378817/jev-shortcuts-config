# -*- coding: utf-8 -*-
"""导入《我的助手》iOS Build93 的「导出全部记录」可读 Markdown。

注意：它是摘要报告而不是完整业务备份，不能凭摘要生成可计算的投标草稿。
严格预览/指纹去重/数据库原子批量写入；不修改任何现有用户记录。
"""
import datetime as dt
import hashlib
import json
import os
import re

HEADER = '# 我的助手｜全部记录导出'
MAX_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 15000
DAY = re.compile(r'^##\s*(\d{1,2})月(\d{1,2})日\s*[·・]?\s*(?:星期[一二三四五六日天]|周[一二三四五六日天])?\s*$')
STAMP = re.compile(r'^(?:导出时间：|###\s*)(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})\s*$')
ENTRY = re.compile(r'^####\s*(\d{1,2}):(\d{2})\s*｜\s*(.+?)\s*$')
TOP = {'## 汽运费测算记录': 'freight', '## 投标报价测算': 'tender'}
TOTAL = re.compile(r'^记录总数：\s*(\d+)\s*$')
BULLET = re.compile(r'^-\s*([^：:]+)[：:]\s*(.*)$')


class IOSMarkdownError(ValueError):
    pass


def _when(raw):
    m = STAMP.fullmatch(raw.strip())
    if not m:
        return None
    try:
        return dt.datetime(*(int(x) for x in m.groups()))
    except ValueError:
        return None


def _day(month, day, exported):
    # 原生可读报告未写年份：依导出时间推断最近一个过去日期。无法推知跨多年历史的真实年份。
    try:
        d = dt.date(exported.year, int(month), int(day))
    except ValueError as exc:
        raise IOSMarkdownError('原生导出内容包含无效的月日') from exc
    if d > exported.date():
        try:
            d = d.replace(year=d.year - 1)
        except ValueError as exc:
            raise IOSMarkdownError('导出日期的年份无法推断，请改用原生 JSON 完整备份') from exc
    return d.isoformat()


def _unique(kind, source_date, title, content, extras):
    seed = {'kind': kind, 'date': source_date, 'title': title,
            'content': content, 'extra': extras}
    digest = hashlib.sha256(json.dumps(seed, ensure_ascii=False,
                                       sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return digest


def _as_candidate(kind, title, date, time, category, content, source, extra=None):
    title = str(title or 'iOS历史记录').strip()[:180]
    text = str(content or '').strip()
    if not text or not title:
        return None
    if len(text) > 300000:
        raise IOSMarkdownError('单条历史记录过大，已中止以防止不完整导入')
    extra = extra or {}
    time = time or '00:00'
    date_time = '{} {}:00'.format(date, time)
    try:
        dt.datetime.strptime(date_time, '%Y-%m-%d %H:%M:%S')
    except ValueError as exc:
        raise IOSMarkdownError('记录日期格式有误') from exc
    fingerprint = _unique(kind, date_time, title, text, {'category':category, 'source':source, **extra})
    payload = {'title': title, 'date': date, 'category': category, 'content': text,
               'source': source, '_ios_markdown_hash': fingerprint,
               '_ios_exported_original_at': date_time,
               '_ios_export_type': extra.get('source_type', 'record')}
    payload.update(extra)
    return {'kind':kind, 'title':title, 'payload':payload,
            'created_at':date_time, 'hash':fingerprint}


def _read(path):
    if not isinstance(path, (str, bytes, os.PathLike)):
        raise IOSMarkdownError('导入文件路径无效')
    if not str(path).lower().endswith(('.md','.markdown','.txt')):
        raise IOSMarkdownError('请选择 iOS 导出的 Markdown（.md）文件')
    try:
        size = os.path.getsize(path)
        if not 0 < size <= MAX_BYTES:
            raise IOSMarkdownError('文件为空或超过 10MB，请分批导出后再导入')
        with open(path, 'rb') as f:
            raw = f.read(MAX_BYTES + 1)
    except (OSError, PermissionError) as exc:
        raise IOSMarkdownError('无法读取文件，请先将 Markdown 保存到“文件”App') from exc
    if len(raw) > MAX_BYTES:
        raise IOSMarkdownError('文件超过 10MB 限制')
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise IOSMarkdownError('原生导出需要 UTF-8 编码，当前文件不能识别') from exc
    if not text.lstrip().startswith(HEADER):
        raise IOSMarkdownError('这不是《我的助手》iOS 的「导出全部记录」Markdown')
    return text.splitlines(), digest


def parse(path):
    """返回可预览、可复核的候选列表。无识别信息的片段保持原文或报错，不造字段。"""
    lines, file_digest = _read(path)
    exported = None
    declared = None
    for ln in lines[:30]:
        if ln.strip().startswith('导出时间：'):
            exported = _when(ln)
        m = TOTAL.fullmatch(ln.strip())
        if m:
            declared = int(m.group(1))
    if exported is None:
        raise IOSMarkdownError('无法读取原生导出时间，不能安全推断日期')
    result = []
    states = {'record':0, 'summary':0, 'freight':0, 'tender_summary':0}
    warnings = ['Markdown 中的日期分组没有年份，按照导出日期推断年份；跨多年记录请用 JSON 完整备份核对。']
    section, day, ai_start = None, None, None
    i = 0

    def add(candidate, counter):
        if candidate:
            result.append(candidate)
            states[counter] += 1
            if len(result) > MAX_ITEMS:
                raise IOSMarkdownError('内容记录超过安全上限，请分批导出')

    def major(line):
        if line.strip() in TOP:
            return TOP[line.strip()]
        if DAY.fullmatch(line):
            return 'day'
        return None

    while i < len(lines):
        raw = lines[i].strip()
        kind = major(raw)
        if kind:
            section = kind
            if kind == 'day':
                m = DAY.fullmatch(raw)
                day = _day(m.group(1),m.group(2),exported)
            i += 1
            continue
        if section == 'day' and day:
            if raw == '### AI每日总结':
                start = i+1
                end = start
                while end < len(lines) and lines[end].strip() != '### 原始记录' and not major(lines[end].strip()):
                    end += 1
                content = '\n'.join(lines[start:end]).strip()
                if content:
                    add(_as_candidate('record', 'AI每日总结 · '+day, day, '00:00', '其他',
                                      content, 'iOS Markdown / AI每日总结', {'source_type':'ai_daily_summary'}),'summary')
                i = end
                continue
            m=ENTRY.fullmatch(raw)
            if m:
                try:
                    hour, minute = int(m.group(1)), int(m.group(2))
                    if not (0<=hour<=23 and 0<=minute<=59):
                        raise ValueError('time')
                except ValueError:
                    raise IOSMarkdownError('原始记录包含无效时间')
                suffix=m.group(3)
                parts=suffix.split('｜来源：',1)
                category=parts[0].strip() or '其他'
                source=(parts[1].strip() if len(parts)>1 else 'iOS Markdown / 原始记录')
                stop=i+1
                while stop<len(lines) and not ENTRY.fullmatch(lines[stop].strip()) and not major(lines[stop].strip()):
                    stop+=1
                block=lines[i+1:stop]
                head=next((ix for ix,line in enumerate(block) if line.strip()),None)
                summary=''
                if head is not None and block[head].strip().startswith('摘要：'):
                    summary=block[head].strip()[3:].strip()
                    block=block[head+1:]
                body='\n'.join(block).strip()
                if not body:
                    body=summary
                title=summary or ('{}记录'.format(category))
                extra={'source_type':'raw_record','ios_summary':summary}
                add(_as_candidate('record',title,day,'{:02d}:{:02d}'.format(hour,minute),
                                  category,body,source,extra),'record')
                i=stop
                continue
        elif section == 'freight' and raw.startswith('### '):
            timestamp=_when(raw)
            if timestamp:
                stop=i+1
                while stop < len(lines) and not lines[stop].strip().startswith('### ') and not major(lines[stop].strip()):
                    stop+=1
                field_map={}
                for line in lines[i+1:stop]:
                    m=BULLET.match(line.strip())
                    if m:
                        field_map[m.group(1).strip()]=m.group(2).strip()
                origin=field_map.get('起点','')
                dest=field_map.get('终点','')
                original='\n'.join(lines[i:stop]).strip()
                title='{} → {}'.format(origin or '未填写起点',dest or '未填写终点')
                extra={'source_type':'freight_summary','origin':origin,'destination':dest,
                       'distance_source':'ios_markdown_summary','notes':'iOS Markdown 历史摘要；未包含地图坐标，不能视为完整路线。',
                       'ios_original_freight_text':original}
                distance=re.search(r'^\s*(\d+(?:\.\d+)?)\s*(?:km|公里)?\s*$',field_map.get('距离',''),re.I)
                fee=re.search(r'^\s*(\d+(?:\.\d+)?)\s*(?:元/吨)?\s*$',field_map.get('运费',''))
                if distance:
                    extra['distance_km']=distance.group(1)
                if fee:
                    extra['result']={'final_fee_per_ton':float(fee.group(1)),
                                     'source':'iOS Markdown 历史报告'}
                if field_map.get('标准'):
                    extra['original_pricing_rule']=field_map['标准']
                add(_as_candidate('freight',title,timestamp.date().isoformat(),timestamp.strftime('%H:%M'),
                                  '汽运费',original,'iOS Markdown / 汽运费摘要',extra),'freight')
                i=stop
                continue
        elif section == 'tender' and raw.startswith('### '):
            name=raw[4:].strip()
            if name:
                stop=i+1
                while stop<len(lines) and not lines[stop].strip().startswith('### ') and not major(lines[stop].strip()):
                    stop+=1
                detail='\n'.join(lines[i:stop]).strip()
                # Markdown 不含投标草稿完整信息：作为历史摘要而不是可参与计算的草稿。
                extra={'source_type':'tender_summary'}
                candidate=_as_candidate('record','[投标摘要] '+name,exported.date().isoformat(),exported.strftime('%H:%M'),
                                        '项目',detail,'iOS Markdown / 投标摘要',extra)
                # 投标报告未提供草稿创建时间：不把「导出时间」纳入去重指纹，
                # 否则同一项目每次重新导出都会被重复导入。
                candidate['hash']=hashlib.sha256(('tender-summary\n'+detail).encode('utf-8')).hexdigest()
                candidate['payload']['_ios_markdown_hash']=candidate['hash']
                add(candidate,'tender_summary')
                i=stop
                continue
        i += 1
    if declared is not None and states['record']<declared:
        warnings.append('原生报告声明原始记录 {} 条，本次识别 {} 条；请核对导出文件是否完整。'.format(declared,states['record']))
        if declared>0 and states['record']==0:
            raise IOSMarkdownError('存在原始记录但未解析出任何记录，为避免漏导入已停止')
    if not result:
        raise IOSMarkdownError('未识别出任何可导入记录，请检查 Markdown 是否为原生 App 的“导出全部记录”')
    if states['tender_summary']:
        warnings.append('投标仅导入历史摘要，不生成可计算投标草稿。')
    if states['freight']:
        warnings.append('汽运费保留当时导出的原始运费，缺失坐标与路径细节，不重新计算历史费用。')
    return {'file_sha256':file_digest,'exported_at':exported.strftime('%Y-%m-%d %H:%M:%S'),
            'declared_records':declared,'counts':states,'candidates':result,'warnings':warnings}


def preview(path, store):
    report=parse(path)
    known=store.ios_markdown_hashes()
    seen=set()
    new=[]
    duplicates=0
    for candidate in report['candidates']:
        key=candidate['hash']
        if key in seen or key in known:
            duplicates+=1
        else:
            seen.add(key)
            new.append(candidate)
    report['new_items']=new
    report['duplicates']=duplicates
    return report


def import_report(path,store,expected_sha256):
    # 二次读取核对内容不变，拒绝在用户确认后换文件；Store 事务一次完成或回滚。
    candidate=preview(path,store)
    if candidate['file_sha256']!=expected_sha256:
        raise IOSMarkdownError('文件在预览后已发生改变，请重新预览确认')
    if not candidate['new_items']:
        return {'inserted':0,'skipped':candidate['duplicates'],'by_type':{},'backup_path':None}
    backup_path=store.backup()
    outcome=store.import_ios_markdown_batch(candidate['new_items'])
    return {'inserted':outcome['inserted'],
            'skipped':candidate['duplicates']+outcome['skipped'],
            'by_type':outcome['by_type'], 'backup_path':backup_path}


def preview_lines(report):
    c=report['counts']
    lines=['原生导出时间：'+report['exported_at'],
           '原始记录：{} 条'.format(c['record']),
           'AI 每日总结：{} 条'.format(c['summary']),
           '汽运费历史摘要：{} 条'.format(c['freight']),
           '投标历史摘要：{} 条'.format(c['tender_summary']),
           '准备新增：{} 条'.format(len(report['new_items'])),
           '识别为重复：{} 条'.format(report['duplicates']),
           '', '注意事项：']
    lines += ['• '+warning for warning in report['warnings']]
    lines += ['','此操作只增加历史记录，不覆盖现有 Python 数据。导入前会自动保存 SQLite 备份。']
    return lines
