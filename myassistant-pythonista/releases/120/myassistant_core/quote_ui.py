# -*- coding: utf-8 -*-
"""Pythonista native card editor for Build93 DailyQuote features.
No SwiftUI dependency. No database writes until explicit Save confirmation.
"""
import copy
import datetime as _dt
from . import quote_full as q
try:
    import ui
except ImportError:
    ui = None

_BG='#f3f4f8'
_ORANGE='#eb811f'
_MUTED='#778290'
_WHITE='#ffffff'


def _dialog(title,fields,values):
    import dialogs
    descriptors=[]
    for k,label,kind in fields:
        v=values.get(k)
        descriptors.append({'type':'number' if kind=='number' else 'text','key':k,'title':label,
                            'value':'' if v is None else str(v)})
    return dialogs.form_dialog(title=title,fields=descriptors)


def _pick(title,options):
    import dialogs
    return dialogs.list_dialog(title=title,items=list(options))


def _alert(message):
    import console
    console.alert('我的助手',str(message),'确定',hide_cancel_button=True)


def _confirm(message):
    import console
    try:return console.alert('请确认',message,'确认','取消',hide_cancel_button=True)==1
    except KeyboardInterrupt:return False


class QuoteEditor(ui.View if ui else object):
    def __init__(self,store,record=None,prefill=None):
        if ui is None:raise RuntimeError('此界面只能在 iPhone Pythonista 3 上运行')
        super().__init__()
        self.store=store
        self.record=record
        self.d=q.normalize(record['payload']) if record else q.new_draft(self.store.pref('quote_annual_rate_default',3))
        if prefill:
            for old,new in (('customer','customer'),('contact','contact'),('delivery_address','delivery_address')):
                if prefill.get(old):self.d[new]=prefill[old]
            if prefill.get('specification'):self.d['lines'][self.d['selected_kind']]['specification']=prefill['specification']
        self.background_color=_BG
        self.name='新建日常报价' if record is None else '编辑日常报价'
        self.flex='WH'
        self._build()

    def _text(self,parent,x,y,w,h,value,size=13,color='#20252c',bold=False):
        v=ui.Label(frame=(x,y,w,h));v.text=str(value);v.font=('Helvetica-Bold' if bold else 'Helvetica',size)
        v.text_color=color;v.number_of_lines=0;parent.add_subview(v);return v

    def _btn(self,parent,x,y,w,h,title,action,fill='#fdf0e3',color=_ORANGE,size=13):
        b=ui.Button(frame=(x,y,w,h));b.title=title;b.background_color=fill;b.tint_color=color
        b.font=('Helvetica-Bold',size);b.corner_radius=12;b.action=lambda sender:action()
        parent.add_subview(b);return b

    def _card(self,heading,height):
        card=ui.View(frame=(16,self.cursor,self.width-32,height));card.background_color=_WHITE;card.corner_radius=18
        self.scroll.add_subview(card)
        self._text(card,14,10,card.width-28,29,heading,18,bold=True)
        self.cursor+=height+14
        return card

    def _summary(self,card,y,value,size=13,color=_MUTED):
        return self._text(card,14,y,card.width-28,46,value,size,color)

    def _build(self):
        self.width = ui.get_screen_size()[0]
        screen_h = ui.get_screen_size()[1]
        self.height = screen_h
        self._populate()

    def _populate(self):
        pos=getattr(getattr(self,'scroll',None),'content_offset',(0,0))
        for child in list(self.subviews):self.remove_subview(child)
        w=self.width
        top=ui.View(frame=(0,0,w,65));top.background_color=_WHITE;self.add_subview(top)
        self._btn(top,12,11,68,42,'返回',lambda:self.close(),fill='#f9e8d8')
        self._text(top,w/2-86,10,172,42,self.name,18,bold=True)
        self._btn(top,w-88,11,76,42,'保存',self._save,fill=_ORANGE,color=_WHITE)
        self.scroll=ui.ScrollView(frame=(0,65,w,self.height-65));self.scroll.flex='WH';self.scroll.background_color=_BG
        self.add_subview(self.scroll)
        self.cursor=14
        d=self.d;kind=d['selected_kind'];line=d['lines'][kind]
        card=self._card('客户与询价',138)
        self._summary(card,43,'客户：{}\n联系人：{}  ·  报价方式：{}'.format(d['customer'] or '未填写',d['contact'] or '未填写',d['channel']))
        self._btn(card,14,96,card.width-28,32,'编辑客户 / 联系人 / 报价方式',self._customer)

        card=self._card('本次报价产品  ·  已选{}项'.format(len(q.included_kinds(d))),193)
        self._text(card,14,40,card.width-28,32,'各品类独立保存价格、成本及配方；切换不会清空',11,_MUTED)
        chip_w=(card.width-32)/2
        for i,k in enumerate(q.KINDS):
            selected=kind==k
            self._btn(card,12+(i%2)*chip_w,74+(i//2)*34,chip_w-4,30,
                      ('✓' if d['lines'][k].get('included') else '○')+k,
                      lambda key=k:self._kind(key),fill=_ORANGE if selected else '#f3f4f8',
                      color=_WHITE if selected else '#404752',size=11)
        self._btn(card,14,151,card.width-28,30,
                  ('移出本次组合报价' if line.get('included') else '加入本次组合报价'),self._toggle)

        card=self._card('规格与数量',136)
        self._summary(card,42,'规格：{}     数量：{} 吨\n拟报价：{} 元/吨'.format(line.get('specification'),line.get('quantity') or '未填',line.get('sale_price') or '未填'))
        self._btn(card,14,96,card.width-28,30,'编辑规格 / 数量 / 单吨报价',self._product)

        card=self._card('交货方式',148)
        self._summary(card,42,'{} · {}\n{}'.format(d['delivery_mode'],d['delivery_address'] or '未填写收货地点',
                                          '自提：所有品类的运费归零' if d['delivery_mode']=='自提' else '配送：可使用最近汽运费'))
        self._btn(card,14,95,(card.width-34)/2,34,'修改交货方式',self._delivery)
        self._btn(card,18+(card.width-34)/2,95,(card.width-34)/2,34,'最近汽运费',self._latest_freight)

        costs=line.get('cost_items',[])
        card=self._card('成本测算  ·  元/吨（含税）',103+len(costs)*44)
        self._text(card,14,38,card.width-28,26,'逐项金额、税率、备注；税额仅作进项税参考',11,_MUTED)
        for i,item in enumerate(costs):
            name=item.get('name','成本项');amount=item.get('amount',0);rate=item.get('tax_rate',0)
            self._btn(card,12,65+i*44,card.width-24,39,'{}    {}元    税{}%'.format(name,amount or 0,rate),
                      lambda ix=i:self._edit_cost(ix),fill='#f4f5f8',color='#344055',size=12)
        self._btn(card,14,66+len(costs)*44,card.width-28,29,'＋ 新增成本项目',self._add_cost)

        if kind in ('SBS改性沥青','乳化沥青','改性乳化沥青'):
            f=line.get('formula') or {}
            count=len(f.get('materials',[])) if kind=='SBS改性沥青' else 0
            card=self._card('配方材料折算',116+count*40)
            base='基质单价：{} 元/吨'.format(f.get('base_price') or '未填写')
            if kind in ('乳化沥青','改性乳化沥青'):base+='  ·  基质掺量 {}%'.format(f.get('base_dosage_percent') or 0)
            self._text(card,14,42,card.width-28,26,base,12,_MUTED)
            self._btn(card,14,70,card.width-28,32,'编辑基质材料 / 税率',self._edit_formula_base)
            for i,material in enumerate(f.get('materials',[])):
                self._btn(card,14,106+40*i,card.width-28,35,
                          '{}  {}元/吨 × {}%'.format(material.get('name'),material.get('unit_price') or 0,material.get('dosage_percent') or 0),
                          lambda ix=i:self._edit_formula_material(ix),fill='#f4f5f8',color='#344055',size=12)

        card=self._card('资金条件',142)
        self._summary(card,40,'{}   ·   {}天   ·   年资金率 {}%\n资金成本 = 报价 × 年利率 ÷ 365 × 垫资天数'.format(
             d['payment_mode'],d.get('credit_days',30),d.get('annual_finance_rate',3)))
        self._btn(card,14,99,card.width-28,31,'修改付款方式及资金参数',self._finance)

        card=self._card('当前产品报价结果',253)
        try:
            m=q.metrics(d,kind)
            vals=[('直接成本',m['direct_cost']),('资金成本',m['finance_cost']),
                  ('综合成本',m['total_cost']),('利润/吨',m['profit_per_ton']),
                  ('毛利率',str(m['gross_margin_percent'])+'%')]
            for i,(label,val) in enumerate(vals):
                self._text(card,15,46+i*28,150,25,label,13,_MUTED)
                self._text(card,card.width-154,46+i*28,138,25,str(val),14,
                           '#ce3f41' if label=='利润/吨' and m['profit_per_ton']<0 else '#22232a',True)
            if m['estimated_total_profit'] is not None:
                self._text(card,15,188,card.width-30,24,'预计总利润：{}元'.format(m['estimated_total_profit']),14,_ORANGE,True)
            if m['profit_per_ton']<50 and numprice(line.get('sale_price'))>0:
                self._text(card,15,210,card.width-30,20,'注意：利润低于50元/吨，请核实报价。',11,'#cf484a')
        except ValueError as exc:self._summary(card,45,'计算暂停：'+str(exc),12,'#c63f40')
        values=[(-20,'-20'),(-10,'-10'),(10,'+10'),(20,'+20')]
        for i,(amount,label) in enumerate(values):
            bw=(card.width-32)/4
            self._btn(card,12+i*bw,218,bw-5,26,label,lambda delta=amount:self._adjust(delta),size=11)

        card=self._card('本次组合报价 · {}项'.format(len(q.included_kinds(d))),58+len(q.included_kinds(d))*54)
        for i,k in enumerate(q.included_kinds(d)):
            try:
                m=q.metrics(d,k)
                caption='{}（{}）  报价{}，利润{}元/吨'.format(k,d['lines'][k].get('specification',''),m['sale_price'],m['profit_per_ton'])
            except ValueError as exc:caption=k+'  ·  '+str(exc)
            self._text(card,14,43+i*54,card.width-28,46,caption,12,'#303744')

        card=self._card('报价文字模板',142)
        t=self._template()
        self._text(card,14,39,card.width-28,48,q.render_text(d,t)[:180],12,_MUTED)
        self._btn(card,14,100,(card.width-34)/2,32,'管理模板',self._template_menu)
        self._btn(card,18+(card.width-34)/2,100,(card.width-34)/2,32,'复制报价文本',self._copy)

        card=self._card('记录',136)
        self._summary(card,42,'状态：{}\n备注：{}'.format(d['status'],d.get('notes') or '未填写'))
        self._btn(card,14,95,card.width-28,31,'编辑状态及备注',self._notes)
        self._btn(self.scroll,16,self.cursor,w-32,52,'保存本次报价记录',self._save,fill=_ORANGE,color=_WHITE,size=16)
        self.cursor+=78
        self.scroll.content_size=(w,self.cursor)
        try:self.scroll.content_offset=pos
        except Exception:pass

    def _customer(self):
        res=_dialog('客户与询价',[('customer','客户名称','text'),('contact','联系人（可选）','text')],self.d)
        if res is None:return
        self.d.update(res)
        options=['微信','电话','现场','其他']
        chosen=_pick('报价方式（当前：{}）'.format(self.d['channel']),options)
        if chosen:self.d['channel']=chosen
        self._populate()

    def _kind(self,kind):
        self.d['selected_kind']=kind
        self.d['lines'][kind]['included']=True
        self._populate()

    def _toggle(self):
        k=self.d['selected_kind'];self.d['lines'][k]['included']=not self.d['lines'][k].get('included')
        self._populate()

    def _product(self):
        k=self.d['selected_kind'];line=self.d['lines'][k]
        specs=q.SPECIFICATIONS[k]
        res=_dialog('产品规格与报价',[('specification','规格（如'+specs[0]+'）','text'),
                             ('quantity','询价数量（吨，可空）','number'),('sale_price','拟报价（含税元/吨）','number')],line)
        if res is None:return
        line.update(res);self._populate()

    def _delivery(self):
        d=self.d
        chosen=_pick('交货方式',['自提','配送'])
        if not chosen:return
        d['delivery_mode']=chosen
        if chosen=='自提':q.apply_pickup(d)
        else:
            res=_dialog('配送地址',[('delivery_address','收货地点','text')],d)
            if res is not None:d.update(res)
        self._populate()

    def _latest_freight(self):
        if self.d.get('delivery_mode')=='自提':_alert('自提无需运费；如需配送请先切换交货方式。');return
        records=self.store.list('freight')
        if not records:_alert('暂无汽运费记录，请先使用汽运费测算保存一次。');return
        last=records[0]['payload'];details=last.get('result') or {}
        fee=details.get('final_fee_per_ton')
        if fee is None:_alert('最近记录缺少已核验的运费结果，未填入。');return
        if not _confirm('最近运费 {}元/吨。仅用于当前品类，是否填入？'.format(fee)):return
        q.set_freight(self.d,self.d['selected_kind'],fee)
        self.d['delivery_address']=last.get('destination') or self.d['delivery_address']
        self._populate()

    def _edit_cost(self,ix):
        item=self.d['lines'][self.d['selected_kind']]['cost_items'][ix]
        if self.d['delivery_mode']=='自提' and '运费' in item.get('name',''):
            _alert('自提运费固定为0，需配送请先调整交货方式');return
        res=_dialog('成本明细',[('name','项目名称','text'),('amount','金额（含税元/吨）','number'),
                           ('tax_rate','税率（%）','number'),('note','备注（可选）','text')],item)
        if res is None:return
        item.update(res)
        try:q.metrics(self.d)
        except ValueError as exc:_alert(exc)
        self._populate()

    def _add_cost(self):
        item=q.cost_item('新增成本项',0,6)
        self.d['lines'][self.d['selected_kind']]['cost_items'].append(item)
        self._edit_cost(len(self.d['lines'][self.d['selected_kind']]['cost_items'])-1)

    def _edit_formula_base(self):
        k=self.d['selected_kind'];f=self.d['lines'][k]['formula']
        fields=[('base_price','基质沥青单价（元/吨）','number'),('base_tax_rate','基质沥青税率（%）','number')]
        if k in ('乳化沥青','改性乳化沥青'):fields.append(('base_dosage_percent','基质掺量（%）','number'))
        res=_dialog('材料配方',fields,f)
        if res is not None:f.update(res)
        self._populate()

    def _edit_formula_material(self,ix):
        mat=self.d['lines'][self.d['selected_kind']]['formula']['materials'][ix]
        res=_dialog('SBS添加剂配方',[('name','材料名称','text'),('unit_price','单价（元/吨）','number'),
                                ('dosage_percent','掺量（%）','number'),('tax_rate','税率（%）','number')],mat)
        if res is not None:mat.update(res)
        self._populate()

    def _finance(self):
        d=self.d;mode=_pick('资金条件',['先款后货','短期垫资'])
        if not mode:return
        d['payment_mode']=mode
        if mode=='短期垫资':
            res=_dialog('垫资与年利率',[('credit_days','垫资天数','number'),('annual_finance_rate','年资金成本率（%）','number')],d)
            if res is not None:d.update(res)
        self._populate()

    def _adjust(self,delta):
        line=self.d['lines'][self.d['selected_kind']]
        line['sale_price']=max(0,q.num(line.get('sale_price'))+delta)
        self._populate()

    def _notes(self):
        d=self.d;s=_pick('报价状态',['跟进中','已成交','未成交'])
        if s:d['status']=s
        res=_dialog('备注',[('notes','备注','text')],d)
        if res is not None:d.update(res)
        self._populate()

    def _template(self):
        return self.store.pref('daily_quote_template',q.DEFAULT_TEMPLATE) or q.DEFAULT_TEMPLATE

    def _template_menu(self):
        res=_dialog('报价文字模板',[('template','文字模板（使用{{报价}}等变量）','text')],{'template':self._template()})
        if res and res.get('template'):
            if _confirm('保存此模板为默认模板？'):
                self.store.set_pref('daily_quote_template',res['template'])
        self._populate()

    def _copy(self):
        try:
            import clipboard
            clipboard.set(q.render_text(self.d,self._template()));_alert('报价文本已复制，可以粘贴到微信。')
        except (ValueError,ImportError) as exc:_alert(str(exc))

    def _save(self):
        try:
            q.validate(self.d)
            if not self.d.get('customer','').strip():raise ValueError('客户名称不能为空')
            for kind in q.included_kinds(self.d):
                if q.num(self.d['lines'][kind].get('sale_price'))<=0:
                    raise ValueError('已选品类必须填写有效报价：'+kind)
            if self.d['delivery_mode']=='自提':q.apply_pickup(self.d)
        except ValueError as exc:_alert(exc);return
        if not _confirm('确定保存本次报价？不会自动建立库存流水。'):return
        title='{} · {}项报价'.format(self.d['customer'].strip(),len(q.included_kinds(self.d)))
        ident=self.store.save('quote',title,copy.deepcopy(self.d),self.record['id'] if self.record else None)
        self.record=self.store.get(ident)
        _alert('报价已保存，现有数据库记录保持完整。')
        self.close()


def numprice(v):
    try:return q.num(v)
    except ValueError:return 0


def open_editor(store,record=None,prefill=None):
    if ui is None:raise RuntimeError('Pythonista ui 未找到')
    editor=QuoteEditor(store,record,prefill)
    editor.present('fullscreen',hide_title_bar=True)
    return editor
