# -*- coding: utf-8 -*-
"""V1.9 incremental module updater. All hashes come from owner-controlled repository,
not an independent signature; trust the repository writer."""
import hashlib,importlib.util,json,os,re
NAMES=frozenset(("pynative_router","pynative_contacts","pynative_registry","pynative_vision","pynative_updater"))
LIMIT=100000
def digest(data): return hashlib.sha256(data).hexdigest()
def manifest_validate(data):
    if isinstance(data,bytes): data=data.decode("utf-8")
    obj=json.loads(data)
    if not isinstance(obj,dict) or obj.get("schema")!=1: raise ValueError("模块清单版本不合法")
    rows=obj.get("modules")
    if not isinstance(rows,list) or len(rows)!=len(NAMES): raise ValueError("模块列表不完整")
    if set(x.get("name") for x in rows if isinstance(x,dict))!=NAMES: raise ValueError("模块不在白名单")
    for x in rows:
        if (type(x.get("sequence")) is not int or x["sequence"]<1 or x["sequence"]>99999
            or type(x.get("size_bytes")) is not int or not 100<=x["size_bytes"]<=LIMIT
            or not isinstance(x.get("sha256"),str) or not re.fullmatch(r"[0-9a-f]{64}",x["sha256"])):
            raise ValueError("模块校验元数据异常")
    return rows
def atomic_write(path,data):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    tmp=path+".part"
    with open(tmp,"wb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)
def installed_state(root):
    try:
        with open(os.path.join(root,"installed.json"),encoding="utf-8") as f: return json.load(f)
    except (OSError,ValueError): return {"modules":{}}
def install(root,manifest,download):
    rows=manifest_validate(manifest)
    state=installed_state(root)
    live=os.path.join(root,"active")
    # Download and validate all necessary replacements before mutating live files.
    changes={}
    for row in rows:
        name=row["name"]; path=os.path.join(live,name+".py")
        current=state.get("modules",{}).get(name,{})
        if current.get("sequence",0)>=row["sequence"] and os.path.isfile(path):
            with open(path,"rb") as f: old=f.read()
            if digest(old)!=current.get("sha256"): raise ValueError("本地模块校验失败: "+name)
            continue
        data=download(name+".py",LIMIT)
        if len(data)!=row["size_bytes"] or digest(data)!=row["sha256"]:
            raise ValueError("下载模块哈希或长度校验失败: "+name)
        compile(data,name+".py","exec")
        changes[name]=(data,row)
    if not changes: return {"status":"current","changed":[]}
    backups={}; applied=[]
    prior=json.dumps(state,ensure_ascii=False,sort_keys=True).encode("utf-8")
    try:
        for name,(data,row) in changes.items():
            path=os.path.join(live,name+".py")
            if os.path.isfile(path):
                with open(path,"rb") as f: backups[name]=f.read()
            else: backups[name]=None
            atomic_write(path,data);applied.append(name)
            state.setdefault("modules",{})[name]={"sequence":row["sequence"],"sha256":row["sha256"]}
        atomic_write(os.path.join(root,"installed.json"),
                     json.dumps(state,sort_keys=True).encode("utf-8"))
        for name,old in backups.items():
            if old is not None: atomic_write(os.path.join(root,"previous",name+".py"),old)
        return {"status":"updated","changed":sorted(applied)}
    except Exception:
        for name in applied:
            path=os.path.join(live,name+".py")
            if backups[name] is None:
                try: os.remove(path)
                except OSError: pass
            else: atomic_write(path,backups[name])
        atomic_write(os.path.join(root,"installed.json"),prior)
        raise
def load(root,name):
    if name not in NAMES: raise ValueError("模块不在白名单")
    with open(os.path.join(root,"installed.json"),encoding="utf-8") as f:
        state=json.load(f)
    path=os.path.join(root,"active",name+".py")
    with open(path,"rb") as f: data=f.read()
    if digest(data)!=state["modules"][name]["sha256"]: raise ValueError("模块哈希异常: "+name)
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod
