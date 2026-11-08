# -*- coding: utf-8 -*-
"""与《我的助手》Build93关键业务算法对照的纯Python计算层。
含税口径：价格、成本输入均为含税元/吨，税额=含税金额*税率/(100+税率)。
不得以此替代真实合同及税务审查。
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math


def number(value, default=0.0):
    if value is None or value == '':
        return float(default)
    try:
        s = str(value).replace('，', '').replace(',', '').replace('％', '%').strip()
        if s.endswith('%'):
            s = s[:-1]
        x = float(Decimal(s))
        if not math.isfinite(x):
            raise ValueError('非有限数字')
        return x
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError('不能识别的数字：{}'.format(value))


def money(v):
    return float(Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def included_tax(amount, rate_percent):
    a, r = number(amount), number(rate_percent)
    return a*r/(100.0+r) if a > 0 and r > 0 else 0.0


def quote_metrics(d):
    """对照 DailyQuote.swift:metrics，年利率/365*垫资天数。"""
    sale = number(d.get('sale_price'))
    qty = number(d.get('quantity'))
    cost_items = d.get('cost_items') or []
    direct = sum(number(i.get('amount')) for i in cost_items)
    if 'direct_cost' in d and not cost_items:
        direct = number(d.get('direct_cost'))
    finance = sale * number(d.get('annual_finance_rate', 0))/100/365 * max(0, number(d.get('credit_days',0))) if d.get('payment_mode') == '短期垫资' else 0.0
    total = direct + finance
    profit = sale - total
    return {'direct_cost': money(direct), 'finance_cost': money(finance),
            'total_cost': money(total), 'profit_per_ton': money(profit),
            'gross_margin_percent': money(profit/sale*100 if sale > 0 else 0),
            'total_profit': money(profit*qty)}


FREIGHT_DEFAULT_RULES = [
    {'upper':30, 'method':'fixed', 'value':25},
    {'upper':50, 'method':'fixed', 'value':40},
    {'upper':200,'method':'coefficient','value':0.55},
    {'upper':300,'method':'coefficient','value':0.53},
    {'upper':500,'method':'coefficient','value':0.52},
    {'upper':None,'method':'coefficient','value':0.50},
]


def validate_freight_rules(rules):
    """Validate the configured *independent bands*, without changing rates.

    Do not silently modify the original Build93 rate schedule. Its segment
    boundaries can produce a lower quote at a longer distance; show that in UI.
    """
    if not isinstance(rules, list) or not rules:
        raise ValueError('运价规则不能为空')
    previous_upper = 0.0
    clean = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError('运价规则格式错误（第{}段）'.format(index+1))
        method = rule.get('method')
        if method not in ('fixed', 'coefficient'):
            raise ValueError('运价规则的计算方式无效（第{}段）'.format(index+1))
        value = number(rule.get('value'))
        if value <= 0:
            raise ValueError('运价或系数必须大于0（第{}段）'.format(index+1))
        upper = rule.get('upper')
        if upper is None:
            if index != len(rules)-1:
                raise ValueError('不限里程的分段必须排在最后')
        else:
            upper = number(upper)
            if upper <= previous_upper or index == len(rules)-1:
                raise ValueError('运价分段里程必须递增，且最后一段为不限里程')
            previous_upper = upper
        clean.append(dict(upper=upper, method=method, value=value))
    if clean[-1]['upper'] is not None:
        raise ValueError('运价规则必须设置最后一个不限里程的分段')
    return clean


def freight_quote(distance_km, rules=None):
    """按原版独立距离分段报价：输入道路公里数，并按每段分别计算。"""
    km = number(distance_km)
    if km <= 0:
        raise ValueError('距离必须大于0，且以公里为单位')
    schedule = validate_freight_rules(FREIGHT_DEFAULT_RULES if rules is None else rules)
    lower = 0.0
    for selected in schedule:
        upper = selected['upper']
        if upper is None or km <= upper:
            method = selected['method']
            raw = selected['value'] if method == 'fixed' else km*selected['value']
            rounded = int(Decimal(str(raw)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            name = '{} < 公里数 ≤ {}'.format(_fmt(lower), _fmt(upper)) if upper is not None else '公里数 > {}'.format(_fmt(lower))
            formula = ('固定运价 {} 元/吨'.format(_fmt(selected['value'])) if method=='fixed'
                       else '{} 公里 × {} 元/(吨·公里) = {:.2f} 元/吨'.format(_fmt(km),_fmt(selected['value']),raw))
            return {'distance_km':km,'raw_fee_per_ton':money(raw),'final_fee_per_ton':rounded,
                    'rule':selected.copy(),'segment':name,'formula':formula,
                    'distance_source':'手工填写的公路里程（未调用导航/地图测距）'}
        lower = upper
    raise ValueError('没有适用的运价规则')

def product_cost(product):
    """成本项可单独设置含税成本及进项税率。
    SBS / 乳化可通过 materials 设置每种原料的掺量百分比；未填写时只采用cost_items。
    """
    direct = 0.0
    input_tax = 0.0
    for item in product.get('cost_items',[]):
        amount = number(item.get('amount'))
        if amount < 0: raise ValueError('成本项不能为负')
        direct += amount
        input_tax += included_tax(amount, item.get('tax_rate',0))
    for mat in product.get('materials',[]):
        unit_price = number(mat.get('unit_price'))
        dosage = number(mat.get('dosage_percent'))
        if unit_price < 0 or dosage < 0: raise ValueError('材料价格和用量不能为负')
        amount = unit_price * dosage/100
        direct += amount
        input_tax += included_tax(amount, mat.get('tax_rate',0))
    return direct,input_tax


def tender_metrics(project, product, sale_price=None):
    """逐项复现 TenderModels.swift:rawMetrics/breakEvenPrice。
    资金占用率按项目设定，分期与票据可能叠加，完全保留 Build93 口径。
    """
    price = number(product.get('sale_price') if sale_price is None else sale_price)
    quantity = number(product.get('quantity'))
    if price < 0 or quantity < 0: raise ValueError('价格/数量不能为负')
    direct, input_tax = product_cost(product)
    output_tax = included_tax(price, product.get('sales_tax_rate',13))
    tax_surcharge = max(0, output_tax-input_tax) * (1+number(project.get('surcharge_rate',12))/100)
    monthly = number(project.get('monthly_rate',0.36))
    stages = project.get('payment_stages') or []
    instruments = project.get('instruments') or []
    extras = project.get('finance_extras') or []
    normal_finance = sum(price*number(s.get('percentage'))/100 * monthly/100 * number(s.get('months')) for s in stages)
    instrument_finance = sum(price*number(s.get('percentage'))/100 * number(s.get('rate',monthly))/100 * number(s.get('months')) for s in instruments)
    extra_finance = sum(number(s.get('amount')) * number(s.get('rate',monthly))/100 * number(s.get('months')) for s in extras)
    finance = normal_finance+instrument_finance+extra_finance
    total = direct+finance+tax_surcharge
    return {'sale_price':money(price),'quantity':quantity,'output_tax':money(output_tax),
            'input_tax':money(input_tax),'tax_surcharge':money(tax_surcharge),
            'normal_finance':money(normal_finance),'instrument_finance':money(instrument_finance),
            'extra_finance':money(extra_finance),'finance_cost':money(finance),
            'direct_cost':money(direct),'total_cost':money(total),'profit_per_ton':money(price-total),
            'total_profit':money((price-total)*quantity)}


def tender_break_even(project, product):
    """与Swift中80轮二分法同逻辑。"""
    direct,_=product_cost(product)
    if direct<=0: return 0.0
    high = max(1000., direct*2, number(product.get('sale_price') or direct)*1.5)
    n=0
    while tender_metrics(project,product,high)['profit_per_ton'] < 0 and high<1000000 and n<40:
        high*=1.5;n+=1
    low=0.
    for _ in range(80):
        mid=(low+high)/2
        if _tender_profit_exact(project,product,mid)>=0: high=mid
        else: low=mid
    return money(high)


def _tender_profit_exact(project,product,price):
    direct,input_tax=product_cost(product)
    vat=max(0,included_tax(price,product.get('sales_tax_rate',13))-input_tax)
    tax=vat*(1+number(project.get('surcharge_rate',12))/100)
    monthly=number(project.get('monthly_rate',0.36))
    finance=sum(price*number(s.get('percentage'))/100*monthly/100*number(s.get('months')) for s in project.get('payment_stages',[]))
    finance+=sum(price*number(s.get('percentage'))/100*number(s.get('rate',monthly))/100*number(s.get('months')) for s in project.get('instruments',[]))
    finance+=sum(number(s.get('amount'))*number(s.get('rate',monthly))/100*number(s.get('months')) for s in project.get('finance_extras',[]))
    return price-direct-tax-finance


def _fmt(x):
    x = number(x)
    return ('{:.10f}'.format(x)).rstrip('0').rstrip('.')


def finance_excel_formula(project, price_cell='B5'):
    """与Build93简洁Excel百分比公式保持一致；按月利率分组。"""
    groups=[]
    default_rate=number(project.get('monthly_rate',0.36))
    def add(rate,term):
        for x in groups:
            if x[0]==rate:
                x[1].append(term);return
        groups.append([rate,[term]])
    for s in project.get('payment_stages',[]):
        if number(s.get('percentage')) and number(s.get('months')):
            add(default_rate, '{}%*{}'.format(_fmt(s['percentage']),_fmt(s['months'])))
    for s in project.get('instruments',[]):
        if number(s.get('percentage')) and number(s.get('months')):
            add(number(s.get('rate',default_rate)),'{}%*{}'.format(_fmt(s['percentage']),_fmt(s['months'])))
    parts=['{}*{}%*({})'.format(price_cell,_fmt(rate),'+'.join(terms)) for rate,terms in groups]
    for s in project.get('finance_extras',[]):
        if number(s.get('amount')) and number(s.get('months')):
            parts.append('{}*{}%*{}'.format(_fmt(s['amount']),_fmt(s.get('rate',default_rate)),_fmt(s['months'])))
    return '='+'+'.join(parts) if parts else '=0'


def default_quote_costs():
    return [{'name':'基质沥青/资源成本','amount':0,'tax_rate':13},
            {'name':'码头费','amount':30,'tax_rate':6},
            {'name':'仓储费','amount':40,'tax_rate':6},
            {'name':'到工地运费','amount':0,'tax_rate':9}]


def new_tender():
    return {'project_name':'','buyer':'','delivery_address':'','supply_period':'','payment_terms_text':'',
            'deadline':'','pricing_method':'','price_limit':None,'source_file':'','source_text':'',
            'monthly_rate':0.36,'surcharge_rate':12,
            'payment_stages':[{'name':'回款1','percentage':80,'months':3},
                              {'name':'回款2','percentage':15,'months':7},
                              {'name':'质保金','percentage':5,'months':24}],
            'instruments':[], 'finance_extras':[],
            'products':[{'kind':'重交道路石油沥青','specification':'70#A','quantity':0,'sale_price':0,
                         'sales_tax_rate':13,'cost_items':default_quote_costs(), 'materials':[]}],
            'status':'草稿','uncertain_fields':[]}