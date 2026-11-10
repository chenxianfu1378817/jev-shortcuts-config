# -*- coding: utf-8 -*-
"""从 Swift《我的助手》完整备份 JSON 选择性迁移记录/投标/汽运。
迁移生成新ID并保留source id，重复运行不会重复导入；无法转换的信息保留原JSON在备份，不默默填造价格。
"""
import json,os
from .calc import new_tender


def _float(v,default=0):
    try:return float(v) if v is not None else default
    except (ValueError,TypeError):return default


def summary(path):
    with open(path,'r',encoding='utf-8-sig') as f:d=json.load(f)
    if not isinstance(d,dict) or 'records' not in d:
        raise ValueError('不是可识别的原生《我的助手》完整备份JSON')
    return {'records':len(d.get('records') or []),'tenders':len(d.get('tenderDrafts') or []),
            'freights':len(d.get('freightRecords') or []),
            'note':'注意：原生完整备份通常不包含日常报价和销存数据库，需在原生App另行导出。'}


def convert_tender(src):
    d=new_tender()
    project=src.get('project') or {}
    for dst,key in [('project_name','projectName'),('buyer','buyer'),('delivery_address','deliveryAddress'),
                    ('supply_period','supplyPeriod'),('payment_terms_text','paymentTerms'),('pricing_method','pricingMethod')]:
        d[dst]=project.get(key) or d.get(dst,'')
    d['source_text']=src.get('rawTenderText','')
    d['source_name']=src.get('importedFileName','')
    d['monthly_rate']=_float(src.get('monthlyFinanceRatePercent'),0.36)
    d['surcharge_rate']=_float(src.get('surchargeRatePercent'),12)
    d['payment_stages']=[{'name':x.get('name','回款'),'percentage':_float(x.get('percentage')),
                          'months':_float(x.get('delayMonths'))} for x in (src.get('paymentStages') or [])]
    d['instruments']=[{'name':str(x.get('kind') or '票据'),'percentage':_float(x.get('percentage')),
                       'months':_float(x.get('months')),'rate':_float(x.get('monthlyRatePercent'),d['monthly_rate'])}
                      for x in (src.get('paymentInstruments') or [])]
    d['finance_extras']=[{'name':x.get('name','资金占用'),'amount':_float(x.get('amountPerTon')),
                          'months':_float(x.get('months')),'rate':_float(x.get('monthlyRatePercent'),d['monthly_rate'])}
                         for x in (src.get('financeExtras') or [])]
    products=[]
    for item in (src.get('products') or []):
        kind=item.get('kind','重交道路石油沥青')
        cost_items=[]
        for it in item.get('costItems') or []:
            cost_items.append({'name':it.get('name',''),'amount':_float(it.get('amountPerTon')),
                               'tax_rate':_float(it.get('taxRatePercent'))})
        materials=[]
        sbs=item.get('sbsFormula') or {}
        if sbs:
            base=sbs.get('baseBitumenUnitPrice')
            if base:
                materials.append({'name':'基质沥青','unit_price':_float(base),
                                  'dosage_percent':max(0,100-sum(_float(a.get('dosagePercent')) for a in sbs.get('additives') or [])),
                                  'tax_rate':_float(sbs.get('baseBitumenTaxRatePercent'),13)})
            for a in sbs.get('additives') or []:
                materials.append({'name':a.get('name','添加剂'),'unit_price':_float(a.get('unitPricePerTon')),
                                  'dosage_percent':_float(a.get('dosagePercent')),
                                  'tax_rate':_float(a.get('taxRatePercent'),13)})
        em=item.get('emulsionFormula') or {}
        if em and em.get('baseBitumenUnitPrice'):
            materials.append({'name':'乳化基质','unit_price':_float(em.get('baseBitumenUnitPrice')),
                              'dosage_percent':_float(em.get('baseBitumenDosagePercent')),
                              'tax_rate':_float(em.get('baseBitumenTaxRatePercent'),13)})
        products.append({'kind':kind,'specification':item.get('specification',''),
                         'quantity':_float(item.get('quantityTon')),
                         'sale_price':_float(item.get('salePricePerTon')),
                         'sales_tax_rate':_float(item.get('salesTaxRatePercent'),13),
                         'cost_items':cost_items,'materials':materials})
    if products:d['products']=products
    d['_migration_notice']='原生报表定制字段和部分特殊材料计算应逐项复核；不要直接将迁移结果用于投标提交。'
    return d


def import_swift_backup(path,store):
    with open(path,'r',encoding='utf-8-sig') as f:data=json.load(f)
    if not isinstance(data,dict) or 'records' not in data:
        raise ValueError('无效原生备份')
    seen=set()
    for kind in ('record','tender','freight'):
        for row in store.list(kind,limit=100000):
            if row['payload'].get('_source_swift_id'):seen.add(kind+':'+str(row['payload']['_source_swift_id']))
    counts={'record':0,'tender':0,'freight':0}
    for item in data.get('records') or []:
        src=str(item.get('id') or '')
        if src and 'record:'+src in seen:continue
        p={'title':item.get('summary') or '历史记录','category':item.get('category') or '其他',
           'content':item.get('rawText') or '','source':item.get('source','原生App备份'),
           '_source_swift_id':src}
        store.save('record',p['title'],p);counts['record']+=1
    for item in data.get('tenderDrafts') or []:
        if item.get('deletedAt'):continue
        src=str(item.get('id') or '')
        if src and 'tender:'+src in seen:continue
        p=convert_tender(item);p['_source_swift_id']=src
        store.save('tender',p.get('project_name') or '历史投标',p);counts['tender']+=1
    for item in data.get('freightRecords') or []:
        src=str(item.get('id') or '')
        if src and 'freight:'+src in seen:continue
        a=item.get('origin') or {};b=item.get('destination') or {}
        p={'origin':a.get('name',''),'destination':b.get('name',''),
           'distance_km':_float(item.get('usedDistanceKm')),
           'original_final_fee_per_ton':item.get('finalFeePerTon'),
           'notes':'原生App历史测算（不会重算地图距离）',
           '_source_swift_id':src}
        store.save('freight','{} → {}'.format(p['origin'],p['destination']),p);counts['freight']+=1
    return counts
