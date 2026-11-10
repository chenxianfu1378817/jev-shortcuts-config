# -*- coding: utf-8 -*-
"""本地 SQLite 数据库；所有用户数据仅存 Pythonista Documents/我的助手数据。"""
import sqlite3
import threading
from functools import wraps
import os
import json
import uuid
import datetime as dt
import shutil
from .calc import number

KINDS = ('quote','tender','freight','inventory','purchase','record','inbox')


def _db_guard(fn):
    """Serialize the shared SQLite connection across Pythonista UI worker threads.

    Pythonista can invoke a button callback on a different thread than the one
    that created AssistantUI. Using check_same_thread=False WITHOUT this RLock
    would be unsafe when concurrent callbacks or updates enter a transaction.
    """
    @wraps(fn)
    def guarded(self, *args, **kwargs):
        with self._db_lock:
            return fn(self, *args, **kwargs)
    return guarded


def now():
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def today():
    return dt.date.today().isoformat()


def fresh_id(): return str(uuid.uuid4())

class Store(object):
    def __init__(self, root):
        self._db_lock=threading.RLock()
        self.root=os.path.abspath(root)
        self.files=os.path.join(self.root,'招标原始文件')
        self.exports=os.path.join(self.root,'导出')
        for folder in (self.root,self.files,self.exports):
            if not os.path.isdir(folder): os.makedirs(folder)
        self.path=os.path.join(self.root,'assistant.sqlite3')
        # Pythonista's ui button handlers can run on a different thread.
        # One connection with an RLock keeps a full multi-step operation atomic.
        self.db=sqlite3.connect(self.path, timeout=8.0, check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS items(
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
            payload TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, deleted_at TEXT);
          CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind,deleted_at,created_at);
          CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, action TEXT,
            at TEXT, before_json TEXT, after_json TEXT);
          CREATE TABLE IF NOT EXISTS prefs(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        self.db.commit()

    @_db_guard
    def close(self): self.db.close()

    @_db_guard
    def save(self,kind,title,payload,item_id=None):
        if kind not in KINDS: raise ValueError('不允许的数据类型')
        if not isinstance(payload,dict): raise ValueError('payload必须是字典')
        if not title.strip(): raise ValueError('标题不能为空')
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True)
        item_id=item_id or fresh_id()
        before=self.get(item_id)
        t=now()
        with self.db:
            if before:
                self.db.execute('UPDATE items SET kind=?,title=?,payload=?,updated_at=? WHERE id=? AND deleted_at IS NULL',
                                (kind,title,encoded,t,item_id))
            else:
                self.db.execute('INSERT INTO items VALUES(?,?,?,?,?,?,NULL)',
                                (item_id,kind,title,encoded,t,t))
            self.db.execute('INSERT INTO audit(item_id,action,at,before_json,after_json) VALUES(?,?,?,?,?)',
                            (item_id,'update' if before else 'create',t,json.dumps(before,ensure_ascii=False) if before else None,encoded))
        return item_id

    @_db_guard
    def get(self,item_id,include_deleted=False):
        row=self.db.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
        if not row or (row['deleted_at'] and not include_deleted): return None
        data=dict(row)
        data['payload']=json.loads(row['payload'])
        return data

    @_db_guard
    def list(self,kind=None,limit=300):
        if kind and kind not in KINDS: raise ValueError('不允许的数据类型')
        if kind:
            rows=self.db.execute('SELECT * FROM items WHERE kind=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?', (kind,limit))
        else:
            rows=self.db.execute('SELECT * FROM items WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ?', (limit,))
        result=[]
        for row in rows:
            d=dict(row); d['payload']=json.loads(d['payload']);result.append(d)
        return result

    @_db_guard
    def delete(self,item_id):
        current=self.get(item_id)
        if not current: raise ValueError('记录不存在')
        t=now()
        with self.db:
            self.db.execute('UPDATE items SET deleted_at=?,updated_at=? WHERE id=?',(t,t,item_id))
            self.db.execute('INSERT INTO audit(item_id,action,at,before_json,after_json) VALUES(?,?,?,?,NULL)',
                            (item_id,'delete',t,json.dumps(current,ensure_ascii=False)))

    @_db_guard
    def pref(self,key,default=None):
        row=self.db.execute('SELECT value FROM prefs WHERE key=?',(key,)).fetchone()
        if not row:return default
        return json.loads(row['value'])

    @_db_guard
    def set_pref(self,key,value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO prefs VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))

    @_db_guard
    def backup(self):
        filename='我的助手备份_{}.sqlite3'.format(dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
        dst=os.path.join(self.exports,filename)
        # sqlite backup API works in Pythonista Python3; avoids a torn file
        with sqlite3.connect(dst) as conn:
            self.db.backup(conn)
        return dst

    @_db_guard
    def export_json(self):
        dst=os.path.join(self.exports,'我的助手业务数据_{}.json'.format(dt.datetime.now().strftime('%Y%m%d_%H%M%S')))
        payload={'format':'pythonista_myassistant_v1','exported_at':now(),
                 'records':self.list(limit=100000),
                 'settings':{'freight_rules':self.pref('freight_rules')}}
        with open(dst,'w',encoding='utf-8') as f: json.dump(payload,f,ensure_ascii=False,indent=2)
        return dst

    # 原生 iOS Markdown 导入：只追加记录，哈希去重；单事务保证半途失败不产生半批数据。
    @_db_guard
    def ios_markdown_hashes(self):
        known=set()
        # 连用户主动删除的历史导入行也算已导入，避免反复导入被删除的记录。
        for row in self.db.execute('SELECT payload FROM items'):
            try:
                fingerprint=json.loads(row['payload']).get('_ios_markdown_hash')
            except (ValueError, TypeError, AttributeError):
                continue
            if isinstance(fingerprint,str) and len(fingerprint)==64:
                known.add(fingerprint)
        return known

    @_db_guard
    def import_ios_markdown_batch(self,items):
        """一次性插入 iOS Markdown 历史摘要，绝不修改既有行及用户设置。"""
        if not isinstance(items,list) or len(items)>15000:
            raise ValueError('导入批次无效或过大')
        normalized=[]
        for row in items:
            if not isinstance(row,dict) or row.get('kind') not in ('record','freight'):
                raise ValueError('不允许导入的业务类别')
            title=row.get('title')
            payload=row.get('payload')
            date=row.get('created_at')
            if not isinstance(title,str) or not title.strip() or not isinstance(payload,dict):
                raise ValueError('导入记录标题或内容缺失')
            h=payload.get('_ios_markdown_hash')
            if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):
                raise ValueError('导入记录未通过唯一性校验')
            if not isinstance(date,str):
                raise ValueError('导入记录缺少原始时间')
            try: dt.datetime.strptime(date,'%Y-%m-%d %H:%M:%S')
            except ValueError: raise ValueError('导入记录原始时间无效')
            normalized.append((row['kind'],title,payload,date,h))
        known=self.ios_markdown_hashes()
        inserted=0
        skipped=0
        by_type={}
        t=now()
        with self.db:
            for kind,title,payload,original_at,h in normalized:
                if h in known:
                    skipped+=1
                    continue
                item_id=fresh_id()
                encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True)
                self.db.execute('INSERT INTO items VALUES(?,?,?,?,?,?,NULL)',
                                (item_id,kind,title,encoded,original_at,t))
                self.db.execute('INSERT INTO audit(item_id,action,at,before_json,after_json) VALUES(?,?,?,?,?)',
                                (item_id,'import_ios_markdown',t,None,encoded))
                known.add(h)
                inserted+=1
                ty=payload.get('_ios_export_type','record')
                by_type[ty]=by_type.get(ty,0)+1
        return {'inserted':inserted,'skipped':skipped,'by_type':by_type}

    # 库存：沿用 Build93 的原始流水/盘点口径，不手工修改展示汇总。
    @_db_guard
    def balances(self,entries=None):
        entries=entries if entries is not None else self.list('inventory',limit=100000)
        bal={}; histories={}
        entries=sorted(entries,key=lambda r:(r['payload'].get('date') or '',r['created_at'],r['id']))
        for record in entries:
            d=record['payload']; kind='{}|{}'.format(d.get('product',''),d.get('specification',''))
            qty=number(d.get('quantity',0))
            op=d.get('action')
            if op=='盘点':
                new=number(d.get('actual_stock'))
            elif op=='入库': new=bal.get(kind,0)+qty
            elif op=='出库': new=bal.get(kind,0)-qty
            else: raise ValueError('未知库存动作: '+str(op))
            if new < -1e-8:
                raise ValueError('库存不足：{} 在 {} 后为 {:.2f} 吨'.format(kind,record['id'],new))
            bal[kind]=max(0,new)
            histories.setdefault(kind,[]).append((record['id'],new))
        return bal

    @_db_guard
    def save_inventory(self,title,data,item_id=None):
        if data.get('action') not in ('入库','出库','盘点'): raise ValueError('库存动作必须为入库/出库/盘点')
        if not data.get('product') or not data.get('specification'): raise ValueError('必须填品种和规格')
        if number(data.get('quantity',0))<0: raise ValueError('数量不能为负')
        if data['action']=='盘点' and (data.get('actual_stock') in (None,'')):
            raise ValueError('盘点必须填写实际库存')
        if item_id:
            before=self.get(item_id)
            if not before or before['kind']!='inventory': raise ValueError('原流水不存在')
            if before['payload'].get('linked_purchase_id') and (before['payload'] != data):
                raise ValueError('已关联采购的入库流水不能直接更正，请先处理采购单')
        virtual=[r for r in self.list('inventory',limit=100000) if r['id']!=item_id]
        t=now()
        virtual.append({'id':item_id or fresh_id(),'created_at':(self.get(item_id) or {}).get('created_at',t),'payload':data})
        self.balances(virtual)
        return self.save('inventory',title,data,item_id)

    @_db_guard
    def delete_inventory(self,item_id):
        record=self.get(item_id)
        if not record or record['kind']!='inventory': raise ValueError('流水不存在')
        if record['payload'].get('linked_purchase_id'):
            raise ValueError('已关联采购的流水不能直接删除')
        rest=[r for r in self.list('inventory',limit=100000) if r['id']!=item_id]
        self.balances(rest)
        self.delete(item_id)

    @_db_guard
    def mark_purchase_arrived(self,purchase_id):
        record=self.get(purchase_id)
        if not record or record['kind']!='purchase': raise ValueError('采购单不存在')
        purchase=record['payload']
        if purchase.get('status')=='已到货': raise ValueError('不能重复入库')
        inbound={'action':'入库','date':today(),'product':purchase.get('product'),
                 'specification':purchase.get('specification'),'quantity':purchase.get('quantity'),
                 'supplier':purchase.get('supplier'), 'unit_cost':purchase.get('unit_cost'),
                 'location':purchase.get('location',''), 'linked_purchase_id':purchase_id}
        inbound_id=self.save_inventory('采购到货 · '+record['title'],inbound)
        purchase['status']='已到货';purchase['linked_inbound_id']=inbound_id
        self.save('purchase',record['title'],purchase,purchase_id)
        return inbound_id
