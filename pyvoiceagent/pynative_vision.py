# -*- coding: utf-8 -*-
"""Apple Vision on-device OCR. Explicit photo selection, no automatic upload."""
import io
import os
import tempfile
MAX_IMAGE_BYTES=15*1024*1024
MAX_TEXT_CHARS=6000
def _result(lines):
    lines=[str(x).strip()[:500] for x in list(lines)[:200] if str(x).strip()]
    joined="\n".join(lines)
    return {"status":"ok","verified":True,"text":joined[:MAX_TEXT_CHARS],"lines":len(lines),"truncated":len(joined)>MAX_TEXT_CHARS}
def recognize_bytes(data,engine=None):
    if not isinstance(data,bytes) or not (10<len(data)<=MAX_IMAGE_BYTES):
        raise ValueError("图片为空或超过15MB")
    if engine is not None: return _result(engine(data))
    if not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\\r\\n\x1a\\n")):
        raise ValueError("图片格式必须为 JPEG 或 PNG")
    try:
        from objc_util import ObjCClass,ns,nsurl,load_framework
    except ImportError:
        raise RuntimeError("Apple Vision 仅能在 Pythonista 设备上运行")
    path=None
    try:
        load_framework("Vision")
        Request=ObjCClass("VNRecognizeTextRequest")
        Handler=ObjCClass("VNImageRequestHandler")
        req=Request.alloc().init()
        if req is None: raise RuntimeError("VNRecognizeTextRequest 初始化失败")
        req.setRecognitionLevel_(1)
        req.setUsesLanguageCorrection_(True)
        # A local image file URL avoids Pythonista's NSData bytearray conversion.
        suffix=".png" if data.startswith(b"\x89PNG") else ".jpg"
        with tempfile.NamedTemporaryFile(prefix="pyvoice_ocr_",suffix=suffix,delete=False) as temp:
            path=temp.name
            temp.write(data)
        handler=Handler.alloc().initWithURL_options_(nsurl(path),ns({}))
        if handler is None:
            raise RuntimeError("VNImageRequestHandler 初始化失败，请检查图片或系统框架兼容性")
        if not handler.performRequests_error_(ns([req]),None):
            raise RuntimeError("Vision 图像识别请求失败")
        lines=[]
        for obs in (req.results() or []):
            candidates=obs.topCandidates_(1)
            if candidates and len(candidates): lines.append(str(candidates[0].string()))
        return _result(lines)
    except Exception as e:
        raise RuntimeError("Vision OCR 不可用："+str(e)[:160])
    finally:
        if path is not None:
            try: os.remove(path)
            except OSError: pass

def run_ocr(image_bytes=None,photo_picker=None):
    try:
        if image_bytes is None:
            if photo_picker is None:
                import photos
                photo_picker=photos.pick_image
            image=photo_picker()
            if image is None: return {"status":"declined","verified":False,"result":"用户取消选图"}
            buf=io.BytesIO()
            image.convert("RGB").save(buf,format="JPEG",quality=88)
            image_bytes=buf.getvalue()
        out=recognize_bytes(image_bytes)
        return {"status":"ok","verified":True,"result":"本地识别到{}行文字：\n{}".format(out["lines"],out["text"]),"truncated":out["truncated"]}
    except Exception as e:
        return {"status":"unavailable","verified":False,"result":str(e)[:200]}
