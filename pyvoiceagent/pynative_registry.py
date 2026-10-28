# -*- coding: utf-8 -*-
"""Audited native tool registry. No dynamic code / import names from AI."""
TOOLS={
 "app.navigate.native":{"module":"pynative_router","handler":"open_target","permission":"navigation","description":"经原有 App 白名单核验的原生跳转"},
 "vision.ocr":{"module":"pynative_vision","handler":"run_ocr","permission":"photo_read","description":"用户选择照片后在本机识别文字"}
}
def capabilities(): return {name:dict(v) for name,v in TOOLS.items()}
def tool_info(name):
    if name not in TOOLS: raise ValueError("工具未获授权")
    return dict(TOOLS[name])
