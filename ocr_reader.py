"""
OCR 文字提取 — 轻量化识图路线
从裁剪后的图片消息中提取文字内容

引擎优先级: PaddleOCR (中文精度高) → RapidOCR (轻量ONNX回退)
懒加载: 首次收到图片消息时才加载，避免启动时导入耗时
"""
from typing import List, Optional, Dict


class OCREngine:
    """抽象 OCR 引擎接口"""

    def recognize(self, image_path: str) -> str:
        """返回所有识别到的文字，换行分隔"""
        raise NotImplementedError

    def recognize_structured(self, image_path: str) -> List[dict]:
        """返回结构化结果 [{"text": str, "confidence": float, "box": [...]}]"""
        raise NotImplementedError


class PaddleOCREngine(OCREngine):
    """PaddleOCR 封装 — 中文识别精度最高"""

    def __init__(self, use_gpu: bool = False, show_log: bool = False):
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(
            use_angle_cls=True,    # 检测旋转文字
            lang='ch',             # 中文 + 英文
            use_gpu=use_gpu,
            show_log=show_log,
            det_db_thresh=0.3,     # 检测阈值(调低=更敏感)
            rec_batch_num=1,       # 单张识别
        )
        self._name = "PaddleOCR"

    def recognize(self, image_path: str) -> str:
        try:
            result = self._ocr.ocr(image_path, cls=True)
            if not result or not result[0]:
                return ""
            lines = []
            for line in result[0]:
                text = line[1][0]
                if text and text.strip():
                    lines.append(text.strip())
            return "\n".join(lines)
        except Exception:
            return ""

    def recognize_structured(self, image_path: str) -> List[dict]:
        try:
            result = self._ocr.ocr(image_path, cls=True)
            if not result or not result[0]:
                return []
            return [
                {
                    "text": line[1][0],
                    "confidence": float(line[1][1]),
                    "box": line[0],
                }
                for line in result[0]
            ]
        except Exception:
            return []


class RapidOCREngine(OCREngine):
    """RapidOCR (onnxruntime) 封装 — 轻量级回退方案"""

    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self._ocr = RapidOCR()
        self._name = "RapidOCR"

    def recognize(self, image_path: str) -> str:
        try:
            result, _ = self._ocr(image_path)
            if not result:
                return ""
            lines = []
            for line in result:
                text = line[1]
                if text and text.strip():
                    lines.append(text.strip())
            return "\n".join(lines)
        except Exception:
            return ""

    def recognize_structured(self, image_path: str) -> List[dict]:
        try:
            result, _ = self._ocr(image_path)
            if not result:
                return []
            return [
                {
                    "text": line[1],
                    "confidence": float(line[2]),
                    "box": line[0],
                }
                for line in result
            ]
        except Exception:
            return []


class OCRReader:
    """
    OCR 读取器 — 工厂模式，两阶段初始化

    使用方式:
        reader = OCRReader()
        # 首次调用时自动加载引擎（可能耗时 2-10 秒）
        text = reader.extract_text("path/to/image.png")

    引擎选择:
        - prefer_paddle=True: 先尝试 PaddleOCR，失败则回退 RapidOCR
        - prefer_paddle=False: 直接使用 RapidOCR
    """

    def __init__(self, prefer_paddle: bool = True):
        self._engine: Optional[OCREngine] = None
        self._prefer_paddle = prefer_paddle
        self._init_attempted = False
        self._engine_name: str = "none"

    # ----- properties -----

    @property
    def available(self) -> bool:
        """是否已加载可用的 OCR 引擎"""
        if not self._init_attempted:
            self._ensure_engine()
        return self._engine is not None

    @property
    def engine_name(self) -> str:
        """当前使用的引擎名称"""
        if not self._init_attempted:
            self._ensure_engine()
        return self._engine_name

    # ----- public API -----

    def extract_text(self, image_path: str) -> str:
        """
        提取图片中的所有文字，多行用换行符连接。
        返回空字符串表示无文字或引擎不可用。
        """
        if not self.available:
            return ""
        try:
            return self._engine.recognize(image_path)
        except Exception:
            return ""

    def extract_structured(self, image_path: str) -> List[dict]:
        """
        提取带位置和置信度的结构化识别结果。
        返回空列表表示无结果或引擎不可用。
        """
        if not self.available:
            return []
        try:
            return self._engine.recognize_structured(image_path)
        except Exception:
            return []

    def get_text_summary(self, image_path: str) -> Dict:
        """
        获取识别结果的摘要信息。
        返回 {"text": str, "line_count": int, "engine": str, "success": bool}
        """
        text = self.extract_text(image_path)
        lines = [l for l in text.split("\n") if l.strip()] if text else []
        return {
            "text": text,
            "line_count": len(lines),
            "engine": self._engine_name,
            "success": bool(text.strip()),
        }

    # ----- internals -----

    def _ensure_engine(self):
        """懒加载：按优先级尝试加载 OCR 引擎"""
        if self._init_attempted:
            return
        self._init_attempted = True

        if self._prefer_paddle:
            if self._try_load_paddle():
                return
            # 回退到 RapidOCR
            if self._try_load_rapid():
                return
        else:
            if self._try_load_rapid():
                return

        self._engine = None
        self._engine_name = "none"

    def _try_load_paddle(self) -> bool:
        try:
            self._engine = PaddleOCREngine(use_gpu=False, show_log=False)
            self._engine_name = "PaddleOCR"
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _try_load_rapid(self) -> bool:
        try:
            self._engine = RapidOCREngine()
            self._engine_name = "RapidOCR"
            return True
        except ImportError:
            return False
        except Exception:
            return False


# Module-level singleton (lazy — won't load engine until first use)
ocr_reader = OCRReader(prefer_paddle=True)
