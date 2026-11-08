# -*- coding: utf-8 -*-
"""Pythonista 3 手机 UI（ui + dialogs）与业务操作入口。
通过原生表单减少维护；正式写入一律用户确认。"""
import os,sys,datetime as dt,copy,csv
from .store import Store,today
from .calc import (number,quote_metrics,freight_quote,tender_metrics,tender_break_even,
                   FREIGHT_DEFAULT_RULES,new_tender,finance_excel_formula)
from .tender_import import read_tender,copy_original,parse_tender_locally,DocumentError
from .xlsx import export_tender
from .ai import route,extract_tender,get_key,set_key,AIError


def _ui():
    import ui,dialogs,console
    return ui,dialogs,console


def form(title,fields,initial=None):
    _,dialogs,_=_ui()
    initial=initial or {}
    specs=[]
    for item in fields:
        if len(item)==2:k,label=item;type_='text'
        else:k,label,type_=item
        value=initial.get(k)
        specs.append({'type':type_,'key':k,'title':label,
                      'value':str(value) if value is not None else ''})
    return dialogs.form_dialog(title=title,fields=specs)


def choice(title,choices):
    _,dialogs,_=_ui()
    return dialogs.list_dialog(title=title,items=choices)


def ask(title,default=''):
    _,_,console=_ui()
    try:return console.input_alert(title,'',str(default))
    except KeyboardInterrupt:return None


def confirm(title,question):
    _,_,console=_ui()
    try:return console.alert(title,question,'确认','返回',hide_cancel_button=True)==1
    except KeyboardInterrupt:return False


def notice(message,success=True):
    _,_,console=_ui()
    console.hud_alert(message,'success' if success else 'error',1.3)


def read_text(title,text):
    # Pythonista text_dialog 支持长篇多行显示，编辑内容不会自动覆盖数据
    _,dialogs,_=_ui()
    dialogs.text_dialog(title=title,text=str(text or ''))


def n(value):
    return number(value or 0)


def title_row(item):
    return '{} · {}'.format(item['title'][:37],item['created_at'][:16])


class AssistantUI(object):
    def __init__(self,root):
        self.store=Store(root)

    def get_ai(self):
        provider=self.store.pref('ai_provider','ollama')
        model=self.store.pref('ai_model','gpt-oss:120b')
        key=get_key(provider)
        return provider,model,key

    def choose_item(self,kind):
        rows=self.store.list(kind)
        if not rows:notice('暂无记录',False);return None
        labels=['{:02d}  {}'.format(i+1,title_row(r)) for i,r in enumerate(rows)]
        selection=choice('选择记录',labels)
        return rows[labels.index(selection)] if selection in labels else None

    def preview(self,label,lines):read_text(label,'\n'.join(str(x) for x in lines))

    # ── 日常报价 ──
    def quote_menu(self):
        while True:
            s=choice('日常报价',['新建报价','报价历史/编辑','返回'])
            if s=='新建报价':self.quote_edit()
            elif s=='报价历史/编辑':
                r=self.choose_item('quote')
                if r:self.quote_record_menu(r)
            else:break

    def quote_edit(self,old=None,prefill=None):
        d=copy.deepcopy(old or {})
        d.update(prefill or {})
        fields=[('customer','客户'),('contact','联系人'),('product','品种'),('specification','规格'),
                ('quantity','数量(吨)','number'),('sale_price','含税售价(元/吨)','number'),
                ('direct_cost','直接成本(含税元/吨)','number'),('delivery_mode','交货方式(自提/配送)'),
                ('delivery_address','交货地点'),('payment_mode','先款后货/短期垫资'),
                ('credit_days','垫资天数','number'),('annual_finance_rate','年资金成本率(%)','number'),('notes','备注')]
        d.setdefault('product','道路石油沥青');d.setdefault('specification','70#A')
        d.setdefault('delivery_mode','配送');d.setdefault('payment_mode','先款后货')
        d.setdefault('annual_finance_rate',3);d.setdefault('credit_days',30)
        r=form('报价编辑',fields,d)
        if r is None:return
        d.update(r)
        if d.get('payment_mode') not in ('先款后货','短期垫资'):
            notice('资金条件须为先款后货或短期垫资',False);return
        try:m=quote_metrics(d)
        except ValueError as e:notice(str(e),False);return
        lines=['客户：'+d.get('customer',''),'产品：{} / {}'.format(d.get('product'),d.get('specification')),
               '数量：{}吨；销售价：{}元/吨'.format(d.get('quantity'),d.get('sale_price')),
               '直接成本：{}元/吨'.format(m['direct_cost']),
               '资金占用：{}元/吨'.format(m['finance_cost']),
               '利润：{}元/吨；预计总利润：{}元'.format(m['profit_per_ton'],m['total_profit'])]
        self.preview('报价测算结果',lines)
        if confirm('保存报价','确认保存报价草稿吗？（不自动生成库存流水）'):
            self.store.save('quote','{} · {}'.format(d.get('customer') or '未填客户',d.get('specification') or '报价'),d,
                            (old or {}).get('_id'))
            notice('报价已保存')

    def quote_record_menu(self,r):
        while True:
            d=r['payload'];s=choice('报价 · '+r['title'],['查看利润','修改报价','复制报价文本','删除记录','返回'])
            if s=='查看利润':
                try:self.preview('报价指标',[str(k)+'：'+str(v) for k,v in quote_metrics(d).items()])
                except Exception as e:notice(str(e),False)
            elif s=='修改报价':
                self.quote_edit(dict(d,_id=r['id']));return
            elif s=='复制报价文本':
                import clipboard
                t='客户：{}\n品种：{} {}\n数量：{} 吨\n含税报价：{} 元/吨\n交货：{} {}'.format(d.get('customer',''),d.get('product',''),d.get('specification',''),d.get('quantity',''),d.get('sale_price',''),d.get('delivery_mode',''),d.get('delivery_address',''))
                clipboard.set(t);notice('报价文本已复制')
            elif s=='删除记录':
                if confirm('删除报价','删除后只保留在审计历史中，继续？'):
                    self.store.delete(r['id']);notice('已删除');return
            else:return

    # ── 汽运费 ──
    def freight_menu(self):
        while True:
            s=choice('汽运费测算',['新测算','查看历史','编辑距离分段系数','返回'])
            if s=='新测算':self.freight_edit()
            elif s=='查看历史':
                r=self.choose_item('freight')
                if r:
                    self.preview(r['title'],[str(k)+': '+str(v) for k,v in r['payload'].items()])
                    if confirm('删除运费记录','确定删除此记录？'):self.store.delete(r['id'])
            elif s=='编辑距离分段系数':self.edit_freight_rules()
            else:return

    def edit_freight_rules(self):
        rs=copy.deepcopy(self.store.pref('freight_rules',FREIGHT_DEFAULT_RULES))
        s=choice('编辑费率',['{}km内：{} {}'.format(x['upper'] if x['upper'] else '不限',x['method'],x['value']) for x in rs]+['恢复原版默认','返回'])
        if s=='恢复原版默认':
            if confirm('恢复默认','恢复 Build93 6段运价规则？'):
                self.store.set_pref('freight_rules',FREIGHT_DEFAULT_RULES);notice('已恢复')
            return
        index=next((i for i,x in enumerate(rs) if s=='{}km内：{} {}'.format(x['upper'] if x['upper'] else '不限',x['method'],x['value'])),None)
        if index is None:return
        val=ask('新运价系数/固定价',rs[index]['value'])
        if val is None:return
        try:
            if n(val)<0:raise ValueError('不得为负')
            rs[index]['value']=n(val)
            from .calc import validate_freight_rules
            validate_freight_rules(rs)
            self.store.set_pref('freight_rules',rs);notice('已更新')
        except ValueError as e:notice(str(e),False)

    def freight_edit(self,prefill=None):
        d=dict(prefill or {})
        r=form('汽运费测算',[('origin','起运地'),('destination','目的地'),('distance_km','测算距离(公里)','number'),('notes','备注')],d)
        if r is None:return
        d.update(r)
        try:
            m=freight_quote(d.get('distance_km'),self.store.pref('freight_rules',FREIGHT_DEFAULT_RULES))
        except ValueError as e:notice(str(e),False);return
        self.preview('运费结果',[d.get('origin','')+' → '+d.get('destination',''),
                            '人工输入里程：{} 公里'.format(m['distance_km']),
                            '匹配运价分段：'+m['segment'],m['formula'],
                            '计算原值：{:.2f} 元/吨'.format(m['raw_fee_per_ton']),
                            '四舍五入后：{} 元/吨'.format(m['final_fee_per_ton']),
                            '提示：此功能不自动查询地图距离。运价采用原版分段独立计算，跨段可能出现运价下降，请核对规则。'])
        if confirm('保存运费','保存此次测算？'):
            d['result']=m
            self.store.save('freight','{}→{}'.format(d.get('origin') or '起点',d.get('destination') or '终点'),d)
            notice('运费已保存')

    # ── 投标测算 ──
    def tender_menu(self):
        while True:
            s=choice('投标测算',['导入招标文件（PDF/DOCX/TXT）','新建空白投标','项目草稿列表','返回'])
            if s=='导入招标文件（PDF/DOCX/TXT）':
                _,dialogs,_=_ui()
                path=dialogs.pick_document(types=['public.data'])
                if path:self.import_tender_file(path)
            elif s=='新建空白投标':
                d=new_tender();ident=self.store.save('tender','未命名投标',d)
                self.tender_edit(ident)
            elif s=='项目草稿列表':
                r=self.choose_item('tender')
                if r:self.tender_edit(r['id'])
            else:return

    def import_tender_file(self,path):
        try:
            text=read_tender(path)
            provider,model,key=self.get_ai()
            try:
                info=extract_tender(text,provider,model,key) if key and model else parse_tender_locally(text)
            except AIError as e:
                # AI异常不应阻止导入招标文件；本地确定性提取作为回退。
                notice('在线提取失败，使用本地提取',False)
                info=parse_tender_locally(text)
            original=copy_original(path,self.store.files)
        except (DocumentError,AIError,ValueError) as e:
            notice(str(e),False);return
        draft=new_tender()
        for k in ('project_name','buyer','delivery_address','supply_period','payment_terms_text','deadline','pricing_method','price_limit'):
            if info.get(k) is not None:draft[k]=info[k]
        if info.get('quantity'):draft['products'][0]['quantity']=info['quantity']
        if info.get('suggested_kind'):draft['products'][0]['kind']=info['suggested_kind']
        draft['source_file']=original
        draft['source_name']=os.path.basename(path)
        draft['source_text']=text
        draft['extraction_evidence']=info.get('evidence',{})
        draft['uncertain_fields']=info.get('uncertain_fields',[])
        self.preview('招标文件提取预览（待核对）',[
            '源文件：'+os.path.basename(path),'字符数：'+str(len(text)),
            '项目：'+str(draft.get('project_name','未提取')),
            '采购人：'+str(draft.get('buyer','未提取')),
            '数量：'+str(draft['products'][0].get('quantity',0))+' 吨',
            '最高单价：'+str(draft.get('price_limit') or '未提取')+' 元/吨',
            '投标截止：'+str(draft.get('deadline') or '未提取'),
            '付款：'+str(draft.get('payment_terms_text') or '未提取'),
            '请核对招标文件原文；未提取字段需手工补全。'])
        if confirm('创建投标草稿','保存以上识别信息为候选项目，稍后核对报价？'):
            ident=self.store.save('tender',draft.get('project_name') or os.path.basename(path),draft)
            notice('已创建投标草稿')
            self.tender_edit(ident)

    def tender_edit(self,ident):
        while True:
            row=self.store.get(ident)
            if not row:return
            d=row['payload']
            s=choice('投标 · '+row['title'][:22],[
                '项目基本信息','编辑产品与报价','新增一个品种','分期回款比例/月数',
                '票据比例/月数/利率','固定资金占用','查看测算结果',
                '导出 Excel','查看原招标文件','删除项目','返回'])
            if s=='项目基本信息':
                fields=[('project_name','项目名称'),('buyer','采购单位'),('delivery_address','交货地点'),
                        ('supply_period','供货期'),('payment_terms_text','付款条款'),('deadline','投标截止'),
                        ('price_limit','最高单价(元/吨)','number'),('monthly_rate','月资金利率(%)','number'),
                        ('surcharge_rate','附加税费率(%)','number')]
                ret=form('项目条款',fields,d)
                if ret is None:continue
                d.update(ret)
                self.store.save('tender',d.get('project_name') or row['title'],d,ident)
            elif s=='编辑产品与报价':
                ps=d.get('products') or []
                names=['{} {} | {}吨'.format(p.get('kind'),p.get('specification'),p.get('quantity')) for p in ps]
                pick=choice('选择品种',names)
                if pick in names:
                    self.tender_product_edit(d,ps[names.index(pick)])
                    self.store.save('tender',row['title'],d,ident)
            elif s=='新增一个品种':
                p={'kind':'重交道路石油沥青','specification':'70#A','quantity':0,'sale_price':0,'sales_tax_rate':13,'cost_items':[],'materials':[]}
                d.setdefault('products',[]).append(p)
                self.tender_product_edit(d,p)
                self.store.save('tender',row['title'],d,ident)
            elif s=='分期回款比例/月数':
                old=','.join('{}@{}'.format(x.get('percentage'),x.get('months')) for x in d.get('payment_stages',[]))
                val=ask('分期比例%@月数, 用逗号分隔',old)
                if val is not None:
                    try:
                        stages=[]
                        for i,term in enumerate(val.split(',')):
                            if not term.strip():continue
                            perc,months=term.strip().split('@')
                            if n(perc)<0 or n(months)<0:raise ValueError('不得为负')
                            stages.append({'name':'回款'+str(i+1),'percentage':n(perc),'months':n(months)})
                        if sum(x['percentage'] for x in stages)>100.00001:raise ValueError('分期回款比例合计不能超过100%')
                        d['payment_stages']=stages
                        self.store.save('tender',row['title'],d,ident)
                    except (ValueError,TypeError) as e:notice('格式错误：'+str(e),False)
            elif s=='票据比例/月数/利率':
                old=','.join('{}@{}@{}'.format(x.get('percentage'),x.get('months'),x.get('rate')) for x in d.get('instruments',[]))
                val=ask('商票: 比例%@月数@月利率%',old)
                if val is not None:
                    try:
                        out=[]
                        for term in val.split(','):
                            if not term.strip():continue
                            a,b,c=term.split('@')
                            if any(n(v)<0 for v in (a,b,c)):raise ValueError('不得为负')
                            out.append({'name':'非现金工具','percentage':n(a),'months':n(b),'rate':n(c)})
                        d['instruments']=out;self.store.save('tender',row['title'],d,ident)
                    except ValueError as e:notice(str(e),False)
            elif s=='固定资金占用':
                old=','.join('{}@{}@{}'.format(x.get('amount'),x.get('months'),x.get('rate')) for x in d.get('finance_extras',[]))
                val=ask('金额元/吨@月数@月利率%',old)
                if val is not None:
                    try:
                        out=[]
                        for term in val.split(','):
                            if not term.strip():continue
                            a,b,c=term.split('@')
                            if any(n(v)<0 for v in (a,b,c)):raise ValueError('不得为负')
                            out.append({'name':'固定资金占用','amount':n(a),'months':n(b),'rate':n(c)})
                        d['finance_extras']=out;self.store.save('tender',row['title'],d,ident)
                    except ValueError as e:notice(str(e),False)
            elif s=='查看测算结果':self.tender_report(d)
            elif s=='导出 Excel':
                filename='投标测算_{}_{}.xlsx'.format(''.join(x for x in row['title'] if x.isalnum())[:22],dt.datetime.now().strftime('%Y%m%d_%H%M'))
                path=os.path.join(self.store.exports,filename)
                try:
                    export_tender(d,path)
                    _,_,console=_ui();console.quicklook(path)
                except Exception as e:notice('导出失败：'+str(e),False)
            elif s=='查看原招标文件':
                path=d.get('source_file')
                if path and os.path.isfile(path):
                    _,_,console=_ui();console.quicklook(path)
                else:notice('没有原始附件',False)
            elif s=='删除项目':
                if confirm('删除项目','确定删除投标草稿？原附件会保留以便审计。'):
                    self.store.delete(ident);notice('已删除');return
            else:return

    def tender_product_edit(self,d,p):
        while True:
            s=choice('品种测算 · '+str(p.get('specification','')),['编辑规格/售价/数量','编辑成本项','添加材料掺量','删除品种','返回'])
            if s=='编辑规格/售价/数量':
                r=form('品种参数',[('kind','品类'),('specification','规格'),('quantity','吨数','number'),('sale_price','含税售价/吨','number'),('sales_tax_rate','销售税率(%)','number')],p)
                if r is not None:p.update(r)
            elif s=='编辑成本项':
                items=p.setdefault('cost_items',[])
                names=['{}  {}元/吨 (税率{}%)'.format(x.get('name'),x.get('amount'),x.get('tax_rate')) for x in items]
                chosen=choice('成本项',['新增成本项']+names+['返回'])
                if chosen=='新增成本项':
                    ret=form('新增成本项',[('name','成本名称'),('amount','含税元/吨','number'),('tax_rate','进项税率(%)','number')],{'name':'其他成本','tax_rate':13})
                    if ret:items.append(ret)
                elif chosen in names:
                    i=names.index(chosen)
                    cmd=choice('成本处理',['修改','删除','返回'])
                    if cmd=='修改':
                        ret=form('修改成本项',[('name','成本名称'),('amount','含税元/吨','number'),('tax_rate','税率(%)','number')],items[i])
                        if ret:items[i]=ret
                    elif cmd=='删除' and confirm('删除成本','确实删除这条成本项？'):items.pop(i)
            elif s=='添加材料掺量':
                mats=p.setdefault('materials',[])
                chosen=choice('材料掺量',['新增材料']+['{} {}元×{}%'.format(x.get('name'),x.get('unit_price'),x.get('dosage_percent')) for x in mats]+['返回'])
                if chosen=='新增材料':
                    ret=form('材料掺量',[('name','材料名称'),('unit_price','原材料单价元/吨','number'),('dosage_percent','占成品比例(%)','number'),('tax_rate','进项税率(%)','number')],{'tax_rate':13})
                    if ret:mats.append(ret)
                else:
                    matches=['{} {}元×{}%'.format(x.get('name'),x.get('unit_price'),x.get('dosage_percent')) for x in mats]
                    if chosen in matches:
                        i=matches.index(chosen)
                        if confirm('删除材料','删除材料项？'):mats.pop(i)
            elif s=='删除品种':
                if len(d.get('products',[]))<=1:notice('至少保留一个品种',False);continue
                if confirm('删除品种','仅删除此项目中的该产品？'):
                    d['products'].remove(p);return
            else:return

    def tender_report(self,d):
        lines=['项目：'+str(d.get('project_name','')),'资金成本公式样式：'+finance_excel_formula(d,'C19')]
        lines.append('注意：对不同付款节点分别计息，票据占用可叠加。')
        total=0
        for p in d.get('products',[]):
            try:
                m=tender_metrics(d,p)
                total+=m['total_profit']
                lines.extend(['','【{} {}】'.format(p.get('kind'),p.get('specification')),
                   '数量 {} 吨；销售价 {} 元/吨'.format(m['quantity'],m['sale_price']),
                   '直接成本：{} 元/吨；资金成本：{} 元/吨'.format(m['direct_cost'],m['finance_cost']),
                   '税费：{} 元/吨；总成本：{} 元/吨'.format(m['tax_surcharge'],m['total_cost']),
                   '利润：{} 元/吨；总利润：{} 元'.format(m['profit_per_ton'],m['total_profit']),
                   '保本价：{} 元/吨'.format(tender_break_even(d,p))])
            except ValueError as e:lines.append('计算错误：'+str(e))
        lines.append('项目预计总利润：{:.2f}元'.format(total))
        self.preview('投标测算',lines)

    # ── 销存 ──
    def inventory_menu(self):
        while True:
            s=choice('销存管理',['分品种库存','新增入库/出库/盘点','更正/删除库存流水',
                            '录入采购/在途','采购单到货','查看采购单','返回'])
            if s=='分品种库存':
                try:
                    balances=self.store.balances()
                    self.preview('分品种库存',['{}：{:.2f}吨'.format(k,v) for k,v in sorted(balances.items())] or ['暂无库存流水'])
                except ValueError as e:notice(str(e),False)
            elif s=='新增入库/出库/盘点':self.inventory_edit()
            elif s=='更正/删除库存流水':
                row=self.choose_item('inventory')
                if row:
                    cmd=choice('纠错 · '+row['title'],['更正流水','删除流水','返回'])
                    if cmd=='更正流水':self.inventory_edit(row)
                    elif cmd=='删除流水' and confirm('删除库存流水','将重新检查所有库存是否出现负数，确定继续？'):
                        if confirm('再次确认','不可直接撤销，确定删除这条原始流水？'):
                            try:self.store.delete_inventory(row['id']);notice('已删除并重新计算库存')
                            except ValueError as e:notice(str(e),False)
            elif s=='录入采购/在途':self.purchase_edit()
            elif s=='采购单到货':
                r=self.choose_item('purchase')
                if r and confirm('确认到货','采购单到货将生成一笔关联入库流水，确定？'):
                    try:self.store.mark_purchase_arrived(r['id']);notice('到货入库已登记')
                    except ValueError as e:notice(str(e),False)
            elif s=='查看采购单':
                r=self.choose_item('purchase')
                if r:self.preview('采购详情',[str(k)+'：'+str(v) for k,v in r['payload'].items()])
            else:return

    def inventory_edit(self,old=None,prefill=None):
        d=copy.deepcopy((old or {}).get('payload') or {})
        d.update(prefill or {})
        d.setdefault('action','入库');d.setdefault('date',today())
        r=form('出入库/盘点',[('action','动作：入库/出库/盘点'),('date','日期 YYYY-MM-DD'),('product','品类'),('specification','规格'),
                          ('quantity','入出库吨数','number'),('actual_stock','盘点实存(吨)','number'),
                          ('customer','客户'),('project_name','项目'),('supplier','供应方'),('unit_cost','采购成本/吨','number'),
                          ('location','仓库'),('notes','备注')],d)
        if r is None:return
        d.update(r)
        if not confirm('核对库存','{} {} {} 吨，确定登记/更正？'.format(d.get('product'),d.get('specification'),d.get('quantity'))):return
        try:
            self.store.save_inventory('{} · {} · {}'.format(d.get('action'),d.get('product'),d.get('specification')),d,(old or {}).get('id'))
            notice('库存流水已保存')
        except ValueError as e:notice(str(e),False)

    def purchase_edit(self,prefill=None):
        d=dict(prefill or {});d.setdefault('date',today());d.setdefault('status','在途')
        ret=form('采购/在途记录',[('date','订货日期'),('supplier','供应商'),('product','品类'),('specification','规格'),
                          ('quantity','数量(吨)','number'),('unit_cost','采购价元/吨','number'),('expected_arrival','预计到货日期'),
                          ('status','状态：在途/已确认'),('location','到货仓库'),('notes','备注')],d)
        if ret is None:return
        d.update(ret)
        if confirm('保存采购草稿','仅保存采购和在途，不立即增加库存？'):
            self.store.save('purchase','{} · {}{}'.format(d.get('supplier',''),d.get('product',''),d.get('specification','')),d)
            notice('采购草稿已保存')

    # ── 工作记录 ──
    def record_menu(self):
        while True:
            s=choice('工作记录',['新建记录','历史记录','今日工作','返回'])
            if s=='新建记录':self.record_edit()
            elif s=='历史记录':
                r=self.choose_item('record')
                if r:
                    cmd=choice('记录 '+r['title'],['查看','编辑','删除','返回'])
                    if cmd=='查看':self.preview(r['title'],[r['payload'].get('content','')])
                    elif cmd=='编辑':self.record_edit(r)
                    elif cmd=='删除' and confirm('删除','确定删除此记录？'):self.store.delete(r['id'])
            elif s=='今日工作':
                rows=[x for x in self.store.list('record') if x['payload'].get('date',x['created_at'][:10])==today()]
                self.preview('今日工作 · '+today(),['{} · {}'.format(x['title'],x['payload'].get('content','')[:300]) for x in rows] or ['今日尚无记录'])
            else:return

    def record_edit(self,old=None,prefill=None):
        d=copy.deepcopy((old or {}).get('payload') or {})
        d.update(prefill or {})
        d.setdefault('date',today());d.setdefault('category','项目')
        ret=form('工作记录',[('date','日期 YYYY-MM-DD'),('title','标题'),('category','分类：市场/新闻/项目/跟进/日程/生活/其他')],d)
        if ret is None:return
        _,dialogs,_=_ui()
        content=dialogs.text_dialog(title='工作记录正文',text=d.get('content',''))
        if content is None:return
        d.update(ret);d['content']=content
        if confirm('保存工作记录','确认保存整理后的记录，不自动写入日历？'):
            self.store.save('record',d.get('title') or '工作记录',d,(old or {}).get('id'));notice('已保存')

    # ── AI初判与导入 ──
    def ai_menu(self,text=None):
        if text is None:
            s=choice('AI智能处理',['粘贴板内容','手工输入文字','导入招标文件','模型配置','返回'])
            if s=='粘贴板内容':
                import clipboard
                text=clipboard.get()
            elif s=='手工输入文字':
                _,dialogs,_=_ui();text=dialogs.text_dialog(title='输入待处理内容',text='')
            elif s=='导入招标文件':
                _,dialogs,_=_ui();p=dialogs.pick_document(types=['public.data'])
                if p:self.import_tender_file(p)
                return
            elif s=='模型配置':self.model_settings();return
            else:return
        if not text or not text.strip():notice('没有输入内容',False);return
        provider,model,key=self.get_ai()
        try:r=route(text,provider,model,key)
        except (AIError,ValueError) as e:
            notice('在线初判失败，改用本地规则：'+str(e),False)
            from .ai import local_route
            r=local_route(text)
        self.preview('智能分流结果',[r['title'],'目标板块：'+r['module'],
                    '判断依据：'+r.get('reason',''),
                    '提取字段：'+str(r.get('fields',{})),
                    '不确定字段：'+str(r.get('uncertain_fields',[])),
                    '原文仅作背景，不直接保存成正式业务数据。'])
        self.store.save('inbox',r['title'],{'input_text':text[:12000],'routing':r,'created_at':today()})
        if not confirm('进入专业模块','继续进入目标板块，核对字段后再保存？'):return
        fields=r.get('fields') or {}
        module=r['module']
        if module=='quote':self.quote_edit(prefill=fields)
        elif module=='inventory':self.inventory_edit(prefill=fields)
        elif module=='purchase':self.purchase_edit(prefill=fields)
        elif module=='freight':self.freight_edit(prefill=fields)
        elif module=='record':
            info={'title':r['title'],'category':'项目','content':fields.get('content') or text[:8000]}
            self.record_edit(prefill=info)
        elif module=='tender':
            d=new_tender()
            d.update({k:v for k,v in fields.items() if k in d})
            if 'quantity' in fields:d['products'][0]['quantity']=fields['quantity']
            if 'suggested_kind' in fields:d['products'][0]['kind']=fields['suggested_kind']
            ident=self.store.save('tender',d.get('project_name') or r['title'],d)
            self.tender_edit(ident)
        else:self.preview('分析输入', [text,'\n如需完整经营分析，请将此内容交给ChatGPT或配置对应AI模型。'])

    def model_settings(self):
        """Separate selection and input screens to avoid Pythonista form row overlap.

        The current provider/model keys remain backward compatible with V1.1.3.
        Switching providers keeps a separate model ID for each provider, and
        the credential is stored only in the Pythonista Keychain.
        """
        labels = {'ollama': 'Ollama', 'deepseek': 'DeepSeek',
                  'openrouter': 'OpenRouter'}
        model_defaults = {'ollama': 'gpt-oss:120b',
                          'deepseek': 'deepseek-chat', 'openrouter': ''}
        while True:
            provider, model, key = self.get_ai()
            display = labels.get(provider, provider)
            selected = choice('AI 接口配置', [
                '选择服务商',
                '设置模型名称',
                '设置或更换 API Key',
                '查看当前配置',
                '测试 AI 连接',
                '返回',
            ])
            if selected in (None, '返回'):
                return
            if selected == '选择服务商':
                name = choice('选择 AI 服务商', ['Ollama', 'DeepSeek', 'OpenRouter', '返回'])
                selected_provider = next((k for k, v in labels.items() if v == name), None)
                if not selected_provider:
                    continue
                if selected_provider != provider:
                    if provider in labels and model:
                        self.store.set_pref('ai_model_' + provider, model)
                    saved_model = self.store.pref('ai_model_' + selected_provider,
                                                  model_defaults[selected_provider])
                    self.store.set_pref('ai_provider', selected_provider)
                    self.store.set_pref('ai_model', saved_model)
                notice('已选择 ' + labels[selected_provider])
            elif selected == '设置模型名称':
                value = ask('模型名称 / ID', model or model_defaults.get(provider, ''))
                if value is None:
                    continue
                value = value.strip()
                if not value or len(value) > 160 or any(c in value for c in '\r\n\x00'):
                    notice('模型名称必须是有效的非空单行文字', False)
                    continue
                self.store.set_pref('ai_model', value)
                if provider in labels:
                    self.store.set_pref('ai_model_' + provider, value)
                notice('模型名称已保存')
            elif selected == '设置或更换 API Key':
                _, _, console = _ui()
                try:
                    value = console.password_alert('API Key', '仅保存在 Pythonista Keychain')
                except KeyboardInterrupt:
                    continue
                if not value or not value.strip():
                    notice('未输入密钥，原配置保持不变', False)
                    continue
                try:
                    set_key(provider, value.strip())
                except AIError as exc:
                    notice(str(exc), False)
                else:
                    notice('API Key 已保存')
            elif selected == '查看当前配置':
                self.preview('AI 当前配置', [
                    '服务商：' + display,
                    '模型名称：' + (model or '未设置'),
                    'API Key：' + ('已配置' if key else '未配置'),
                    '',
                    'Ollama、DeepSeek 和 OpenRouter 各自保存独立密钥。',
                    '切换服务商时会恢复上次为该服务商使用的模型名称。',
                    'API Key 不会在页面中明文显示。',
                ])
            elif selected == '测试 AI 连接':
                if not model:
                    notice('请先设置模型名称', False)
                    continue
                if not key:
                    notice('请先设置 API Key', False)
                    continue
                if not confirm('测试 AI 连接', '将发送简短测试请求，可能产生 API 费用，继续？'):
                    continue
                from .ai import chat
                try:
                    result = chat(provider, model, key,
                                  [{'role': 'user', 'content': '请简短回复：连接成功'}])
                except AIError as exc:
                    self.preview('AI 连接失败', [str(exc), '请核对服务商、模型名称、密钥及网络。'])
                else:
                    self.preview('AI 连接结果', [
                        '服务商：' + display,
                        '模型名称：' + model,
                        '返回：' + str(result or '(空响应)')[:400],
                    ])

    # ── 在线更新（用户点击后才执行，不自动修改业务脚本） ──
    def online_update_menu(self):
        from .online_update import check_and_install, UpdateError
        root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            result=check_and_install(root)
        except (UpdateError,OSError,ValueError) as exc:
            self.preview('在线更新没有完成',[
                '原来的业务程序保持不变。',
                '原因：'+str(exc),
                '请检查网络连接及 GitHub 是否可访问，再点击首页按钮重试。'])
            return
        if result.get('status')=='updated':
            message=[result['message'],'',
                     '更新的脚本：']+list(result.get('files',[]))+[
                     '', '你的报价、投标、库存、工作记录与附件不会因脚本更新被清空。']
            self.preview('在线更新成功',message)
        else:
            notice('已经是最新版本')
            self.preview('在线更新', [result.get('message','已经是最新版本')])

    def rollback_menu(self):
        from .online_update import rollback_last, UpdateError
        root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not confirm('恢复上一版脚本','仅恢复最近一次在线更新的程序代码；不会修改业务记录，确定继续？'):
            return
        try:
            if rollback_last(root):
                self.preview('脚本恢复成功',['已恢复在线更新前的脚本。',
                    '请关闭本次程序，再重新运行「启动_我的助手.py」。',
                    '原有 SQLite、附件、导出文件未修改。'])
            else:notice('没有可恢复的历史脚本版本',False)
        except (UpdateError,OSError) as exc:
            self.preview('恢复失败',['请保留现有文件，不要覆盖程序。',str(exc)])

    # ── 备份和导出 ──
    def backup_menu(self):
        s=choice('备份导出',['备份 SQLite 数据库','导出 JSON 数据','导入原生App完整备份JSON','查看历史导出文件','恢复上一版脚本','返回'])
        if s=='备份 SQLite 数据库':
            path=self.store.backup();self.share_file(path)
        elif s=='导出 JSON 数据':
            path=self.store.export_json();self.share_file(path)
        elif s=='导入原生App完整备份JSON':
            _,dialogs,_=_ui()
            path=dialogs.pick_document(types=['public.data'])
            if path:
                from .migrate import summary,import_swift_backup
                try:
                    details=summary(path)
                    if confirm('迁移原生数据','原生备份中：工作记录{}条、投标{}个、运费{}笔。此操作不会覆盖Pythonista数据，但需要逐项核对。确定迁移？'.format(details['records'],details['tenders'],details['freights'])):
                        result=import_swift_backup(path,self.store)
                        self.preview('迁移完成',[str(result),details['note']])
                except (ValueError,KeyError) as e:notice('导入失败：'+str(e),False)
        elif s=='恢复上一版脚本':self.rollback_menu()
        elif s=='查看历史导出文件':
            files=sorted(os.listdir(self.store.exports),reverse=True)
            val=choice('选择文件',files)
            if val:self.share_file(os.path.join(self.store.exports,val))

    def share_file(self,path):
        _,_,console=_ui()
        if confirm('导出已完成','文件已写入Pythonista，是否使用系统共享菜单导出到“文件”？'):
            console.open_in(path)

    def main(self):
        ui,_,console=_ui()
        from .online_update import current_version
        app_root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version=current_version(app_root)
        width=390
        root=ui.View(name='我的助手 · Pythonista',background_color='#F6F8FA',frame=(0,0,width,730))
        scroll=ui.ScrollView(frame=root.bounds,flex='WH',background_color='#F6F8FA')
        root.add_subview(scroll)
        title=ui.Label(frame=(20,22,350,42),text='我的助手 · Pythonista',font=('<system-bold>',23),text_color='#173D48',flex='W')
        scroll.add_subview(title)
        subtitle=ui.Label(frame=(20,68,350,26),text='经营业务版 V{}  •  数据本地保存'.format(version),font=('<system>',13),text_color='#65777E',flex='W')
        scroll.add_subview(subtitle)
        actions=[('检查并在线更新',self.online_update_menu),
                 ('AI智能处理',self.ai_menu),('日常报价',self.quote_menu),
                 ('投标测算 · 导入招标文件',self.tender_menu),
                 ('汽运费测算',self.freight_menu),('销存管理',self.inventory_menu),
                 ('工作记录',self.record_menu),('备份与导出',self.backup_menu)]
        for index,(name,callback) in enumerate(actions):
            is_update=(name=='检查并在线更新')
            b=ui.Button(title=name,frame=(20,108+index*68,350,56),
                        background_color=('#E3F2EE' if is_update else '#FFFFFF'),
                        tint_color=('#006C63' if is_update else '#194D58'),
                        corner_radius=11,font=('<system-bold>' if is_update else '<system>',17),flex='W')
            b.border_color='#B5D5CD' if is_update else '#DFE7E8'
            b.border_width=1
            def perform(sender,fun=callback):
                try:fun()
                except KeyboardInterrupt:return
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    console.alert('执行失败',str(e),'返回',hide_cancel_button=True)
            # 网络连接和文件写入放在 Pythonista 的后台执行线程，避免界面假死。
            b.action=ui.in_background(perform) if is_update else perform
            scroll.add_subview(b)
        note=ui.Label(frame=(20,660,350,55),text='更新后重新打开程序即可使用新版本\n正式保存均需确认；扫描件暂不支持OCR',
                      number_of_lines=2,alignment=ui.ALIGN_CENTER,
                      font=('<system>',12),text_color='#69797C',flex='W')
        scroll.add_subview(note)
        scroll.content_size=(width,740)
        root.present('fullscreen')
        return root

    def share_entry(self):
        try:import appex
        except ImportError:return False
        if not appex.is_running_extension():return False
        try:
            paths=appex.get_file_paths()
            if paths:
                path=paths[0]
                ext=os.path.splitext(path)[1].lower()
                if ext in ('.pdf','.docx','.txt','.md','.csv'):
                    self.import_tender_file(path)
                else:notice('当前只支持文字版PDF/DOCX等招标文件',False)
            else:
                text=appex.get_text() or appex.get_url() or ''
                if text:self.ai_menu(text)
                else:notice('共享内容为空',False)
        finally:
            appex.finish()
        return True
