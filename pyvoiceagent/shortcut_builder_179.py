# -*- coding: utf-8 -*-
"""PYVoiceAgent Shortcut Builder 1.7.9.
Safe pure-Python Shortcuts compiler (plistlib); unsigned files only.
Standalone for review/tests; the updater embeds this module into the engine.
No AI-generated executable Python or arbitrary third-party App Intent IDs.
"""
import hashlib as _sb_hashlib
import ipaddress as _sb_ipaddress
import json as _sb_json
import os as _sb_os
import plistlib as _sb_plistlib
import re as _sb_re
import uuid as _sb_uuid
from urllib.parse import urlsplit as _sb_urlsplit

_SB_ROOT = "PYVoiceAgent_Data/GeneratedShortcuts"
_SB_ALLOWED = frozenset((
    "is.workflow.actions.showresult",
    "is.workflow.actions.url",
    "is.workflow.actions.openurl",
    "is.workflow.actions.urlencode",
))
_SB_TEMPLATES = ("show_input","show_text","open_web","apple_map_search")
_SB_MAX_ACTIONS = 5
_SB_CMD = _sb_re.compile(r"^(?:请|请你|帮我|给我)?(?:创建|生成|制作|新建)(?:一个|一条|个)?(?:苹果)?快捷指令(?:，|,|：|:|\s)*",_sb_re.I)


def _sb_secure_https(url):
    """Limit generated web URL actions to non-local HTTPS destinations."""
    if not isinstance(url,str) or not (8 <= len(url) <= 600):
        return False
    if any(c.isspace() or ord(c)<32 for c in url):
        return False
    try:
        p=_sb_urlsplit(url)
        if p.scheme.lower()!="https" or not p.netloc or p.username or p.password:
            return False
        if p.port is not None and p.port != 443:
            return False
        h=(p.hostname or "").lower().rstrip(".")
        if h in ("localhost",) or h.endswith((".local",".internal",".localhost")):
            return False
        try:
            _sb_ipaddress.ip_address(h)
            return False  # no direct IP / loopback / private addresses
        except ValueError:
            pass
        if not _sb_re.fullmatch(r"[a-z0-9.-]+",h) or "." not in h or ".." in h:
            return False
        return True
    except (ValueError, TypeError):
        return False


def _sb_plan_from_voice(goal):
    """Return None for non-creation intent, plan or explicit unsupported message."""
    if not isinstance(goal,str) or len(goal)>350:
        return None
    match=_SB_CMD.match(goal.strip())
    if not match:
        return None
    q=goal.strip()[match.end():].strip("：:,，。 ")
    if not q:
        return {"error":"请说出要生成的功能，例如“创建快捷指令：显示传入内容”。"}
    if any(x in q for x in ("删除","卸载","转账","付款","支付","发微信","发短信","发送消息","修改设置","执行代码")):
        return {"error":"当前自动生成器只支持显示文字、打开安全网页和苹果地图搜索，不生成具有系统写入或支付能力的动作。"}
    if any(x in q for x in ("显示传入","显示输入","回显输入","回显文字","回显传入","显示快捷指令输入")):
        return {"template":"show_input","name":"PYGen_ShowInput","value":""}
    if any(x in q for x in ("地图搜索","搜索地点","地图查找","地图搜索输入")):
        return {"template":"apple_map_search","name":"PYGen_AppleMapSearch","value":""}
    m=_sb_re.search(r"(https://[^\s，,。]+)",q,_sb_re.I)
    if m and ("打开" in q or "访问" in q):
        url=m.group(1)
        if not _sb_secure_https(url):
            return {"error":"为防止误打开本地服务或不安全地址，仅接受公开的 HTTPS 网站。"}
        hash6=_sb_hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        return {"template":"open_web","name":"PYGen_Web_"+hash6,"value":url}
    for word,url in (("百度地图","https://map.baidu.com/"),
                     ("高德地图","https://ditu.amap.com/"),
                     ("GitHub","https://github.com/")):
        if ("打开"+word) in q or ("访问"+word) in q:
            return {"template":"open_web",
                    "name":"PYGen_Web_"+_sb_hashlib.sha256(url.encode()).hexdigest()[:8],"value":url}
    m=_sb_re.match(r"^(?:显示文字|显示提示|显示内容|显示|弹出文字|弹出提示)[：:\s]*(.+)$",q)
    if m:
        message=m.group(1).strip()
        if not 1 <= len(message) <= 240:
            return {"error":"显示文字长度必须在 1～240 字之间。"}
        return {"template":"show_text",
                "name":"PYGen_Text_"+_sb_hashlib.sha256(message.encode()).hexdigest()[:8],
                "value":message}
    return {"error":"暂不支持该快捷指令动作。当前可说：显示输入内容、显示一段文字、打开 HTTPS 网站、用苹果地图搜索输入地点。第三方 App 动作需先核实参数。"}


def _sb_text(*parts):
    """Use the engine's UTF-16 token offsets, including embedded references."""
    s=""; refs={}
    for part in parts:
        if isinstance(part,dict) and part.get("Type"):
            i=len(s.encode("utf-16-le"))//2
            refs["{%d, 1}"%i]=part
            s+="\ufffc"
        else:
            s+=str(part)
    return {"WFSerializationType":"WFTextTokenString",
            "Value":{"string":s,"attachmentsByRange":refs}}


def _sb_action(identifier,**params):
    if identifier not in _SB_ALLOWED:
        raise ValueError("未授权的快捷指令动作 "+identifier)
    return {"WFWorkflowActionIdentifier":identifier,
            "WFWorkflowActionParameters":{"UUID":str(_sb_uuid.uuid4()).upper(),**params}}


def _sb_workflow(plan):
    if not isinstance(plan,dict) or plan.get("template") not in _SB_TEMPLATES:
        raise ValueError("不受支持的模板")
    if not _sb_re.fullmatch(r"PYGen_[A-Za-z0-9_]{3,80}",plan.get("name","")):
        raise ValueError("生成的名称不安全")
    typ=plan["template"];val=plan.get("value","")
    if typ=="show_input":
        actions=[_sb_action("is.workflow.actions.showresult",
                            Text=_sb_text("收到：",{"Type":"ExtensionInput"}))]
    elif typ=="show_text":
        if not isinstance(val,str) or not 1 <= len(val) <= 240:
            raise ValueError("文字格式不合法")
        actions=[_sb_action("is.workflow.actions.showresult",Text=_sb_text(val))]
    elif typ=="open_web":
        if not _sb_secure_https(val):
            raise ValueError("目标网址不安全")
        a=_sb_action("is.workflow.actions.url",WFURLActionURL=val)
        actions=[a,_sb_action("is.workflow.actions.openurl",
                  WFInput=_sb_text({"Type":"ActionOutput","OutputUUID":a["WFWorkflowActionParameters"]["UUID"],
                                    "OutputName":"URL"}))]
    else:  # Dynamically search a location passed from Pythonista using Apple Maps.
        a=_sb_action("is.workflow.actions.urlencode",
                     WFEncodeMode="Encode", WFInput=_sb_text({"Type":"ExtensionInput"}))
        b=_sb_action("is.workflow.actions.url",
                     WFURLActionURL=_sb_text("https://maps.apple.com/?q=",
                         {"Type":"ActionOutput","OutputUUID":a["WFWorkflowActionParameters"]["UUID"],
                          "OutputName":"URL Encoded Text"}))
        actions=[a,b,_sb_action("is.workflow.actions.openurl",
                       WFInput=_sb_text({"Type":"ActionOutput",
                         "OutputUUID":b["WFWorkflowActionParameters"]["UUID"],"OutputName":"URL"}))]
    if len(actions)>_SB_MAX_ACTIONS:
        raise ValueError("生成动作过多")
    references=set()
    for a in actions:
        if a["WFWorkflowActionIdentifier"] not in _SB_ALLOWED:
            raise ValueError("未批准的动作")
        for v in a["WFWorkflowActionParameters"].values():
            if isinstance(v,dict) and v.get("WFSerializationType")=="WFTextTokenString":
                refs=v["Value"].get("attachmentsByRange",{})
                if "\ufffc" not in v["Value"]["string"] and refs:
                    raise ValueError("变量编码异常")
                for r in refs.values():
                    if r.get("Type")=="ActionOutput":
                        if r.get("OutputUUID") not in references:
                            raise ValueError("变量引用无效")
        references.add(a["WFWorkflowActionParameters"]["UUID"])
    return {"WFWorkflowClientVersion":"4018.0.4",
            "WFWorkflowMinimumClientVersion":900,
            "WFWorkflowMinimumClientVersionString":"900",
            "WFWorkflowIcon":{"WFWorkflowIconStartColor":431817727,
                              "WFWorkflowIconGlyphNumber":61440},
            "WFWorkflowTypes":[],
            "WFQuickActionSurfaces":[],
            "WFWorkflowInputContentItemClasses":["WFStringContentItem"] if typ in ("show_input","apple_map_search") else [],
            "WFWorkflowOutputContentItemClasses":[],
            "WFWorkflowImportQuestions":[],
            "WFWorkflowHasShortcutInputVariables":typ in ("show_input","apple_map_search"),
            "WFWorkflowHasOutputFallback":False,
            "WFWorkflowActions":actions}


def _sb_compile(plan,directory):
    """Compile to a unique unsigned binary shortcut; never claim installed."""
    wf=_sb_workflow(plan)
    raw=_sb_plistlib.dumps(wf,fmt=_sb_plistlib.FMT_BINARY)
    restored=_sb_plistlib.loads(raw)
    if len(restored["WFWorkflowActions"])!=len(wf["WFWorkflowActions"]):
        raise ValueError("写入动作数不一致")
    fingerprint=_sb_hashlib.sha256(raw).hexdigest()
    _sb_os.makedirs(directory,exist_ok=True)
    path=_sb_os.path.join(directory,plan["name"]+".unsigned.shortcut")
    if _sb_os.path.exists(path):
        with open(path,"rb") as f:
            if f.read()==raw:
                return {"path":path,"name":plan["name"],"template":plan["template"],
                        "sha256":fingerprint,"action_count":len(wf["WFWorkflowActions"]),
                        "unsigned":True,"reused":True}
        raise FileExistsError("此文件名已存在不同内容，不能覆盖；请人工检查："+path)
    # Create exclusively.  Do not overwrite previously generated recipes.
    with open(path,"xb") as f:
        f.write(raw)
    return {"path":path,"name":plan["name"],"template":plan["template"],
            "sha256":fingerprint,"action_count":len(wf["WFWorkflowActions"]),
            "unsigned":True,"reused":False}


def _sb_generate_from_speech(goal):
    """Run before reminder auto-capture or DeepSeek planning; no external writes."""
    plan=_sb_plan_from_voice(goal)
    if plan is None:
        return None
    if plan.get("error"):
        print("快捷指令生成器："+plan["error"])
        return {"status":"unsupported","reason":plan["error"]}
    root=_sb_os.path.join(DATA_DIR,"GeneratedShortcuts")
    try:
        result=_sb_compile(plan,root)
        # The ledger is NOT an installed-shortcut registry.
        manifest=_sb_os.path.join(root,plan["name"]+".metadata.json")
        if not _sb_os.path.isfile(manifest):
            with open(manifest,"x",encoding="utf-8") as f:
                _sb_json.dump({"name":result["name"],"template":result["template"],
                               "sha256":result["sha256"],"unsigned":True,
                               "installed":False,"validated_on_iphone":False},
                              f,ensure_ascii=False,indent=2)
        print("已生成未签名快捷指令（尚未安装，不能执行）：")
        print(result["path"])
        print("模板：{}；动作数：{}".format(result["template"],result["action_count"]))
        print("下一步：将文件分享至 Mac → 运行签名导入脚本 → Mac 快捷指令中点“添加” → iCloud 同步至手机。")
        if _sb_re.search(r"[A-Za-z]",result["name"]):
            print("名称："+result["name"])
        try:
            # Pythonista's iOS share sheet; user decides whether and where to send.
            if prompt_alert("分享快捷指令文件","已在本机生成文件。现在打开共享面板，以便发送到 Mac？"):
                import console
                if hasattr(console,"open_in"):
                    console.open_in(result["path"])
        except Exception as exc:
            print("分享面板不可用，可在 Pythonista Files 中手动选择该文件："+str(exc)[:90])
        return {"status":"generated","result":result}
    except Exception as exc:
        print("快捷指令文件生成失败："+str(exc)[:250])
        return {"status":"failed","reason":str(exc)[:250]}
