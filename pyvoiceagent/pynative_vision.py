# -*- coding: utf-8 -*-
"""Local Apple Vision OCR; selectable OCR language and visible accuracy warnings.

V1.9.2: Simplified Chinese priority or English-only recognition; images stay on
device. A successful Vision request does NOT mean that recognized text is right.
"""
import io
import os
import tempfile

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_TEXT_CHARS = 6000
PNG_MAGIC = bytes((137, 80, 78, 71, 13, 10, 26, 10))
JPEG_MAGIC = bytes((255, 216, 255))
MODES = {"zh": ["zh-Hans", "en-US"], "en": ["en-US"]}


def _result(lines, confidences=None, mode="zh"):
    cleaned = [str(x).strip()[:500] for x in list(lines)[:200] if str(x).strip()]
    joined = "\n".join(cleaned)
    scores = [float(x) for x in (confidences or []) if x is not None and 0 <= float(x) <= 1]
    avg = round(sum(scores) / len(scores), 3) if scores else None
    low = sum(1 for x in scores if x < 0.55)
    return {
        "status": "ok" if cleaned else "empty",
        "verified": False,
        "mode": mode,
        "text": joined[:MAX_TEXT_CHARS],
        "lines": len(cleaned),
        "confidence_average": avg,
        "low_confidence_lines": low,
        "truncated": len(joined) > MAX_TEXT_CHARS,
        "needs_review": bool(cleaned) and (avg is None or avg < 0.65 or low > 0),
    }


def recognize_bytes(data, engine=None, mode="zh"):
    if mode not in MODES:
        raise ValueError("未支持的识别语言模式")
    if not isinstance(data, bytes) or not (10 < len(data) <= MAX_IMAGE_BYTES):
        raise ValueError("图片为空或超过15MB")
    if engine is not None:
        return _result(engine(data), mode=mode)
    if not (data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC)):
        raise ValueError("图片格式必须为 JPEG 或 PNG")
    try:
        from objc_util import ObjCClass, ns, nsurl, load_framework
    except ImportError:
        raise RuntimeError("Apple Vision 仅能在 Pythonista iPhone 上运行")
    path = None
    try:
        load_framework("Vision")
        Request = ObjCClass("VNRecognizeTextRequest")
        Handler = ObjCClass("VNImageRequestHandler")
        req = Request.alloc().init()
        if req is None:
            raise RuntimeError("VNRecognizeTextRequest 初始化失败")
        req.setRecognitionLevel_(1)  # Accurate
        # Vision otherwise biases OCR toward English.
        req.setRecognitionLanguages_(ns(MODES[mode]))
        req.setAutomaticallyDetectsLanguage_(False)
        # Apple's language correction is not supported for Chinese.
        req.setUsesLanguageCorrection_(mode == "en")
        suffix = ".png" if data.startswith(PNG_MAGIC) else ".jpg"
        with tempfile.NamedTemporaryFile(prefix="pyvoice_ocr_", suffix=suffix,
                                         delete=False) as temp:
            path = temp.name
            temp.write(data)
        handler = Handler.alloc().initWithURL_options_(nsurl(path), ns({}))
        if handler is None:
            raise RuntimeError("VNImageRequestHandler 初始化失败")
        if not handler.performRequests_error_(ns([req]), None):
            raise RuntimeError("Vision 图像识别请求失败")
        lines, scores = [], []
        for obs in (req.results() or []):
            candidates = obs.topCandidates_(1)
            if candidates and len(candidates):
                candidate = candidates[0]
                lines.append(str(candidate.string()))
                try:
                    scores.append(float(candidate.confidence()))
                except (AttributeError, TypeError, ValueError):
                    scores.append(None)
        return _result(lines, scores, mode)
    except Exception as e:
        raise RuntimeError("Vision OCR 不可用：" + str(e)[:160])
    finally:
        if path is not None:
            try:
                os.remove(path)
            except OSError:
                pass


def _select_mode():
    try:
        import dialogs
        choice = dialogs.list_dialog("选择图片主要文字", [
            "中文优先（简体中文＋英文）",
            "英文优先（英文／数字）",
        ])
    except ImportError:
        choice = "中文优先"
    if not choice:
        return None
    return "en" if choice.startswith("英文") else "zh"


def _encode_image(image):
    # Keep screenshots lossless, rather than compressing text with JPEG quality 88.
    try:
        from PIL import ImageOps
        image = ImageOps.exif_transpose(image)
    except (ImportError, AttributeError):
        pass
    rgb = image.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    data = buf.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=96, subsampling=0)
        data = buf.getvalue()
    return data


def run_ocr(image_bytes=None, photo_picker=None, mode="choose"):
    try:
        if mode == "choose":
            mode = _select_mode()
            if mode is None:
                return {"status": "declined", "verified": False,
                        "result": "用户取消选择识别模式"}
        if mode not in MODES:
            raise ValueError("未知 OCR 语言模式")
        if image_bytes is None:
            if photo_picker is None:
                import photos
                photo_picker = photos.pick_image
            image = photo_picker()
            if image is None:
                return {"status": "declined", "verified": False,
                        "result": "用户取消选择图片"}
            image_bytes = _encode_image(image)
        out = recognize_bytes(image_bytes, mode=mode)
        if out["status"] == "empty":
            return {"status": "needs_review", "verified": False,
                    "result": "没有找到可识别文字，请换清晰原图或更换语言模式"}
        mode_label = "中文优先" if mode == "zh" else "英文优先"
        quality = ("%.0f%%" % (out["confidence_average"] * 100)
                   if out["confidence_average"] is not None else "未知")
        warning = ("\n注意：部分文字置信度偏低，请人工核对原图。"
                   if out["needs_review"] else "\n文字仍需与原图核对，置信度不保证准确。")
        return {
            "status": "needs_review" if out["needs_review"] else "ok",
            "verified": False,
            "mode": mode,
            "result": "OCR 模式：{}；{}行；平均置信度：{}\n{}{}".format(
                mode_label, out["lines"], quality, out["text"], warning),
            "text": out["text"],
            "confidence_average": out["confidence_average"],
            "truncated": out["truncated"],
        }
    except Exception as e:
        return {"status": "unavailable", "verified": False,
                "result": str(e)[:220]}
