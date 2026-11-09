# -*- coding: utf-8 -*-
"""Build 93 DailyQuote.swift business model port (Pythonista, no UI dependency).

All input costs/prices are tax-inclusive RMB/t. The DAILY quote profit is
sale - sum(direct costs and formula materials) - sale*rate/100/365*days.
Input VAT is informational only: it is not subtracted again from daily profit.
User records remain in the existing SQLite 'quote' table, no migration write.
"""
from __future__ import division
import copy
from decimal import Decimal, ROUND_HALF_UP

KINDS = ('道路石油沥青', 'SBS改性沥青', '乳化沥青', '改性乳化沥青')
SPECIFICATIONS = {'道路石油沥青': ('70#A','90#A'),
                  'SBS改性沥青': ('I-D','I-C'),
                  '乳化沥青': ('PC-2','PC-3'),
                  '改性乳化沥青': ('PCR','BCR')}
COST_DEFAULTS = {
  '道路石油沥青': [('道路石油沥青/到岸价',0,13),('码头费',30,6),('仓储费',40,6),('到工地运费',0,9),('其他费用',0,6)],
  'SBS改性沥青': [('改性加工费',0,13),('码头费',30,6),('仓储费',40,6),('到工地运费',0,9),('其他费用',0,6)],
  '乳化沥青': [('乳化材料综合成本',0,13),('乳化加工费',0,13),('包装/装车等费用',0,13),('到工地运费',0,9),('其他费用',0,6)],
  '改性乳化沥青': [('乳化材料综合成本',0,13),('改性材料综合成本',0,13),('乳化改性加工费',0,13),('包装/装车等费用',0,13),('到工地运费',0,9),('其他费用',0,6)],
}
DEFAULT_TEMPLATE = '{{产品}}，{{交货方式文本}}，报价{{报价}}元/吨，{{付款方式}}，价格以当日确认为准。'
PLACEHOLDERS = ('{{客户}}','{{联系人}}','{{产品}}','{{规格}}','{{报价}}','{{数量}}','{{交货方式}}','{{交货方式文本}}','{{收货地点}}','{{付款方式}}','{{报价方式}}','{{日期}}','{{备注}}')


def num(v, fallback=0.0):
    if v is None or str(v).strip()=='' : return float(fallback)
    try:
        v = float(str(v).replace('，','').replace(',','').strip().rstrip('%'))
        import math
        if not math.isfinite(v): raise ValueError()
        return v
    except (ValueError, TypeError):
        raise ValueError('请输入有效数字：{}'.format(v))


def cents(v):
    return float(Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _nonnegative(v, desc):
    x=num(v)
    if x<0: raise ValueError(desc+'不能为负数')
    return x


def vat_inc(v, r):
    r=_nonnegative(r,'税率')
    if r>100:raise ValueError('税率不能超过100%')
    v=_nonnegative(v,'成本')
    return v*r/(100+r) if r else 0


def cost_item(name,amount=0,rate=13,note=''):
    return {'name':name,'amount':amount,'tax_rate':rate,'note':note}


def initial_line(kind):
    if kind not in KINDS: raise ValueError('未知品类')
    line={'included':kind==KINDS[0],'specification':SPECIFICATIONS[kind][0],
          'quantity':'','sale_price':'',
          'cost_items':[cost_item(*row) for row in COST_DEFAULTS[kind]]}
    if kind=='SBS改性沥青':
        line['formula']={'base_price':'','base_tax_rate':13,
                         'materials':[{'name':name,'unit_price':'','dosage_percent':'','tax_rate':13}
                                      for name in ('SBS改性剂','稳定剂','其他添加剂')]}
    elif kind in ('乳化沥青','改性乳化沥青'):
        line['formula']={'base_price':'','base_dosage_percent':'','base_tax_rate':13}
    return line


def new_draft(default_annual_rate=3):
    return {'quote_schema':2,'customer':'','contact':'','channel':'微信',
            'delivery_mode':'配送','delivery_address':'','payment_mode':'先款后货',
            'credit_days':30,'annual_finance_rate':default_annual_rate,
            'notes':'','status':'跟进中','selected_kind':KINDS[0],
            'lines':{kind:initial_line(kind) for kind in KINDS}}


def normalize(d):
    """Old 1.1.x single quote is only *viewed* through a compatibility wrapper.
    Never discard legacy custom fields or overwrite old records on read.
    """
    if not isinstance(d,dict): raise ValueError('报价数据不是字典')
    if d.get('quote_schema')==2 and isinstance(d.get('lines'),dict):
        result=copy.deepcopy(d)
        for kind in KINDS:
            if not isinstance(result['lines'].get(kind),dict): result['lines'][kind]=initial_line(kind)
            result['lines'][kind].setdefault('cost_items',[])
            result['lines'][kind].setdefault('included',False)
        if result.get('selected_kind') not in KINDS:result['selected_kind']=KINDS[0]
        return result
    result=new_draft(num(d.get('annual_finance_rate'),3))
    for name in ('customer','contact','channel','delivery_mode','delivery_address','payment_mode','credit_days','annual_finance_rate','notes','status'):
        if name in d:result[name]=d[name]
    inferred=str(d.get('product') or KINDS[0])
    kind=next((kind for kind in KINDS if kind in inferred),KINDS[0])
    result['selected_kind']=kind
    for k in KINDS:result['lines'][k]['included']=(k==kind)
    line=result['lines'][kind]
    line['specification']=d.get('specification') or line['specification']
    line['quantity']=d.get('quantity','')
    line['sale_price']=d.get('sale_price','')
    # Legacy single direct cost cannot be safely split among tax categories.
    if d.get('cost_items') and isinstance(d['cost_items'],list):
        line['cost_items']=copy.deepcopy(d['cost_items'])
    else:
        line['cost_items']=[cost_item('旧版直接成本（待拆分）',d.get('direct_cost',0),0,
                                      '原记录未提供分项税率，升级时未推断税额')]
    result['legacy_original']=copy.deepcopy(d)
    return result


def included_kinds(d):
    return [k for k in KINDS if d['lines'].get(k,{}).get('included')]


def validate(d):
    if d.get('payment_mode') not in ('先款后货','短期垫资'): raise ValueError('付款方式无效')
    if d.get('delivery_mode') not in ('自提','配送'): raise ValueError('交货方式无效')
    if d.get('channel') not in ('微信','电话','现场','其他'): raise ValueError('报价方式无效')
    if d.get('status') not in ('跟进中','已成交','未成交'): raise ValueError('报价状态无效')
    if not included_kinds(d): raise ValueError('请至少加入一个产品')
    _nonnegative(d.get('credit_days',0),'垫资天数')
    rate=_nonnegative(d.get('annual_finance_rate',0),'资金成本率')
    if rate>100: raise ValueError('年资金成本率不得超过100%')
    for kind in included_kinds(d):metrics(d,kind)
    return True


def metrics(d,kind=None):
    kind=kind or d.get('selected_kind') or KINDS[0]
    if kind not in KINDS:raise ValueError('未知品类')
    line=d['lines'][kind]
    price=_nonnegative(line.get('sale_price'),'报价')
    qty=_nonnegative(line.get('quantity'),'数量')
    direct=vat=0.0
    for item in line.get('cost_items',[]):
        v=_nonnegative(item.get('amount'),'成本项')
        # Swift's pickup rule zeros freight costs across ALL product lines.
        if d.get('delivery_mode')=='自提' and '运费' in str(item.get('name','')):v=0.0
        direct+=v;vat+=vat_inc(v,item.get('tax_rate',0))
    formula=line.get('formula') or {}
    if kind=='SBS改性沥青':
        materials=formula.get('materials',[])
        added=sum(_nonnegative(m.get('dosage_percent'),'掺量') for m in materials)
        if added>100.000001:raise ValueError('SBS及添加剂总掺量超过100%')
        base_price=_nonnegative(formula.get('base_price'),'基质价')
        base=base_price*(100-added)/100
        direct+=base;vat+=vat_inc(base,formula.get('base_tax_rate',13))
        for material in materials:
            val=_nonnegative(material.get('unit_price'),'材料单价')*_nonnegative(material.get('dosage_percent'),'掺量')/100
            direct+=val;vat+=vat_inc(val,material.get('tax_rate',13))
    elif kind in ('乳化沥青','改性乳化沥青'):
        pct=_nonnegative(formula.get('base_dosage_percent'),'基质占比')
        if pct>100: raise ValueError('基质占比超过100%')
        val=_nonnegative(formula.get('base_price'),'基质价')*pct/100
        direct+=val;vat+=vat_inc(val,formula.get('base_tax_rate',13))
    finance=(price*_nonnegative(d.get('annual_finance_rate',0),'资金成本率')/100/365*
             _nonnegative(d.get('credit_days',0),'垫资天数')) if d.get('payment_mode')=='短期垫资' else 0
    profit=price-direct-finance
    return {'sale_price':cents(price),'quantity':qty if str(line.get('quantity','')).strip() else None,
            'direct_cost':cents(direct),'input_tax_reference':cents(vat),
            'finance_cost':cents(finance),'total_cost':cents(direct+finance),
            'profit_per_ton':cents(profit),
            'gross_margin_percent':cents(profit/price*100 if price else 0),
            'estimated_total_profit':cents(profit*qty) if qty>0 else None}


def apply_pickup(d):
    d['delivery_mode']='自提'
    for line in d['lines'].values():
        for item in line.get('cost_items',[]):
            if '运费' in str(item.get('name','')):item['amount']=0


def set_freight(d,kind,fee):
    fee=_nonnegative(fee,'运费')
    for item in d['lines'][kind].get('cost_items',[]):
        if '运费' in item.get('name',''):
            item['amount']=fee;return
    d['lines'][kind]['cost_items'].append(cost_item('到工地运费',fee,9))


def render_text(d,template=None,date=None):
    template=template or DEFAULT_TEMPLATE
    date=date or __import__('datetime').date.today().isoformat()
    result=[]
    for kind in included_kinds(d):
        line=d['lines'][kind]
        sale=num(line.get('sale_price'))
        qty=num(line.get('quantity'))
        spec=line.get('specification') or ''
        name=kind+('（'+spec+'）' if spec else '')
        addr=str(d.get('delivery_address') or '').strip()
        delivery='自提' if d.get('delivery_mode')=='自提' else ('送达'+addr if addr else '配送到工地')
        replacements={'{{客户}}':d.get('customer',''),'{{联系人}}':d.get('contact',''),'{{产品}}':name,
                      '{{规格}}':spec,'{{报价}}':format(sale,'g'),'{{数量}}':format(qty,'g')+'吨' if qty else '',
                      '{{交货方式}}':d.get('delivery_mode',''),'{{交货方式文本}}':delivery,
                      '{{收货地点}}':addr,'{{付款方式}}':d.get('payment_mode',''),
                      '{{报价方式}}':d.get('channel',''),'{{日期}}':date,'{{备注}}':d.get('notes','')}
        text=template
        for k,v in replacements.items():text=text.replace(k,str(v))
        result.append(text)
    return '\n'.join(result)


def combined_metrics(d):
    return {kind:metrics(d,kind) for kind in included_kinds(d)}
