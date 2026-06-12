"""
Vision Client v5 — 统一图像识别管道

技术链路:
  PrintWindow 截图 → OpenCV UI 检测 → 裁剪图片区域
    ├── [lightweight] OCR 提取文字 → 普通文本 LLM
    └── [vision]      直接送入多模态 VL 模型

三条路线:
  - "lightweight": 截图→检测→裁剪→OCR→文本LLM (省VL额度)
  - "vision":      截图→检测→裁剪→VL API  (能看图/手写/照片)
  - "auto":        有VL模型→强力路线, 否则→轻量路线
"""
import os
import base64
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

from PIL import Image

from config import config
from screen_capture import ScreenCapture
from ui_detector import UIDetector, Rect, pil_to_bgr, bgr_to_pil
from ocr_reader import OCRReader
from database import add_log, get_active_llm_config, get_setting


class VisionClient:
    """统一图像识别管道 v5"""

    def __init__(self):
        self.temp_dir = Path(__file__).parent / "data" / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 子模块（OCR 懒加载）
        self._capture = ScreenCapture()
        self._detector = UIDetector()
        self._ocr: Optional[OCRReader] = None

    # ----- 属性: 懒加载 OCR -----
    @property
    def ocr(self) -> OCRReader:
        if self._ocr is None:
            self._ocr = OCRReader(prefer_paddle=config.ocr_prefer_paddle)
        return self._ocr

    # ====== 主入口 (替代旧 handle_image_message) ======

    def handle_image_message(self, hwnd: int = 0,
                             msg_control=None,
                             mode: str = None) -> str:
        """
        处理图片消息的完整管道。

        Args:
            hwnd: 聊天窗口句柄 (来自 monitor.hwnd)
            msg_control: UIA 消息控件 (可选，用于精确定位)
            mode: "lightweight" | "vision" | "auto", None=读配置

        Returns:
            嵌入 LLM 对话的上下文字符串，如:
              "[对方发了一张图片。通过OCR识别到的文字内容：\n今天的菜单...]"
              "[对方发了一张图片。图片内容描述：一只橘猫趴在窗台上]"
              "[对方发了一张图片]"
        """
        mode = self._resolve_mode(mode)
        add_log("INFO", f"Vision pipeline start: mode={mode} hwnd={hwnd}", "vision")

        # ---- Stage 1: 截图 ----
        screenshot = self._capture.capture_window(hwnd) if hwnd else None

        if screenshot is None and hwnd:
            add_log("WARN", "PrintWindow capture failed, trying chat area fallback", "vision")
            screenshot = self._capture.capture_chat_area(hwnd, msg_control)

        if screenshot is None:
            add_log("WARN", "All capture methods failed", "vision")
            return "[对方发了一张图片]"

        add_log("DEBUG", f"Screenshot captured: {screenshot.size}", "vision")

        # ---- Stage 2: 检测图片气泡 ----
        img_bgr = pil_to_bgr(screenshot)
        bubble = self._detector.find_latest_image_bubble(img_bgr)

        if bubble is None:
            # Try with message-list ROI
            msg_roi = self._detector.find_message_list_region(img_bgr)
            bubble = self._detector.find_latest_image_bubble(img_bgr, msg_roi)
            add_log("DEBUG", "Bubble detection with ROI fallback", "vision")

        if bubble is None and msg_control is not None:
            # Coarse location from UIA control
            try:
                uia_rect = msg_control.BoundingRectangle
                # Convert to client-relative coordinates
                import win32gui
                client_rect = win32gui.GetClientRect(hwnd)
                pt = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
                bx = max(0, uia_rect.left - pt[0])
                by = max(0, uia_rect.top - pt[1])
                bw = uia_rect.width()
                bh = uia_rect.height()
                w, h = screenshot.size
                bubble = Rect(
                    x=max(0, bx - 20), y=max(0, by - 20),
                    w=min(bw + 40, w - bx), h=min(bh + 40, h - by),
                    confidence=0.5,
                ).clamp(w, h)
                add_log("DEBUG", f"Bubble from UIA: {bubble}", "vision")
            except Exception:
                pass

        # ---- Stage 3: 裁剪 ----
        if bubble is not None:
            cropped = self._crop_bubble(screenshot, bubble)
            add_log("DEBUG", f"Bubble cropped: {cropped.size} from {bubble}", "vision")
        else:
            # 最后回退: 使用消息列表区域
            msg_roi = self._detector.find_message_list_region(img_bgr)
            cropped = screenshot.crop((msg_roi.x, msg_roi.y, msg_roi.right, msg_roi.bottom))
            add_log("DEBUG", f"Fallback to message list region: {cropped.size}", "vision")

        # ---- Stage 4: 识别 ----
        if mode == "vision":
            result = self._analyze_via_vl(cropped)
            if result:
                return self._build_context(result, route="vision")
            # VL 失败: 尝试 OCR 回退
            add_log("WARN", "VL failed, trying OCR fallback", "vision")
            ocr_text = self._analyze_via_ocr(cropped)
            if ocr_text:
                return self._build_context(ocr_text, route="ocr_fallback")

        elif mode == "lightweight":
            ocr_text = self._analyze_via_ocr(cropped)
            if ocr_text:
                return self._build_context(ocr_text, route="ocr")
            add_log("INFO", "OCR returned no text", "vision")

        # 全部失败
        return "[对方发了一张图片]"

    # ====== 管道阶段 (公开供测试/复用) ======

    def capture_window(self, hwnd: int) -> Optional[Image.Image]:
        """Stage 1: 截取聊天窗口客户区"""
        return self._capture.capture_window(hwnd)

    def detect_bubble(self, screenshot: Image.Image,
                      msg_control=None) -> Optional[Rect]:
        """Stage 2: 定位最新图片消息气泡"""
        img_bgr = pil_to_bgr(screenshot)
        bubble = self._detector.find_latest_image_bubble(img_bgr)
        if bubble is None:
            roi = self._detector.find_message_list_region(img_bgr)
            bubble = self._detector.find_latest_image_bubble(img_bgr, roi)
        return bubble

    def crop_bubble(self, screenshot: Image.Image,
                    bubble: Rect) -> Optional[Image.Image]:
        """Stage 3: 裁剪气泡区域（带小边距）"""
        return self._crop_bubble(screenshot, bubble)

    def analyze_via_ocr(self, cropped: Image.Image) -> str:
        """Stage 4a: OCR 提取文字"""
        return self._analyze_via_ocr(cropped)

    def analyze_via_vl(self, cropped: Image.Image,
                       question: str = None) -> Optional[str]:
        """Stage 4b: 多模态 VL 分析"""
        return self._analyze_via_vl(cropped, question)

    # ====== 内部实现 ======

    def _resolve_mode(self, mode: str = None) -> str:
        """
        解析有效的识别模式。
        优先级: 参数 > 数据库设置 > 环境变量 > 默认 "lightweight"
        """
        if mode is None:
            mode = get_setting("VISION_MODE", "") or os.getenv("VISION_MODE", "")
        if not mode:
            mode = "lightweight"

        mode = mode.strip().lower()

        if mode == "auto":
            active_cfg = get_active_llm_config()
            supports_vision = active_cfg and "vision" in (active_cfg.get("capabilities", "") or "")
            resolved = "vision" if supports_vision else "lightweight"
            add_log("INFO", f"Vision mode auto → {resolved} (VL available: {supports_vision})", "vision")
            return resolved

        if mode == "vision":
            active_cfg = get_active_llm_config()
            supports_vision = active_cfg and "vision" in (active_cfg.get("capabilities", "") or "")
            if not supports_vision:
                add_log("WARN", "Vision mode requested but no VL-capable model active, fallback to lightweight", "vision")
                return "lightweight"

        return mode

    def _crop_bubble(self, screenshot: Image.Image,
                     bubble: Rect, padding: int = 6) -> Image.Image:
        """裁剪气泡区域，加上小边距"""
        w, h = screenshot.size
        expanded = bubble.expand(padding).clamp(w, h)
        return screenshot.crop(expanded.to_tuple())

    def _analyze_via_ocr(self, cropped: Image.Image) -> str:
        """
        保存裁剪图为临时文件 → OCR 提取文字 → 清理临时文件
        返回提取的文字，失败返回空字符串
        """
        path = self._save_temp(cropped, prefix="ocr_")
        if path is None:
            return ""

        try:
            # 确保 OCR 引擎已加载
            if not self.ocr.available:
                add_log("WARN", f"OCR engine not available: {self.ocr.engine_name}", "vision")
                return ""

            text = self.ocr.extract_text(path)
            add_log("INFO", f"OCR result: {len(text)} chars, engine={self.ocr.engine_name}", "vision")
            return text
        except Exception as e:
            add_log("ERROR", f"OCR failed: {e}", "vision")
            return ""
        finally:
            self.cleanup(path)

    def _analyze_via_vl(self, cropped: Image.Image,
                        question: str = None) -> Optional[str]:
        """
        裁剪图 → base64 → 多模态 VL API → 返回描述文字
        """
        if question is None:
            question = "请详细描述这张图片的内容。如果是聊天截图，请提取其中的文字；如果是照片/图表，请描述画面内容。"

        path = self._save_temp(cropped, prefix="vl_")
        if path is None:
            return None

        try:
            return self._vl_api_call(path, question)
        except Exception as e:
            add_log("ERROR", f"VL API call failed: {e}", "vision")
            return None
        finally:
            self.cleanup(path)

    def _vl_api_call(self, image_path: str, question: str) -> Optional[str]:
        """
        调用 OpenAI 兼容的多模态 API。
        复用与 llm_client.py 相同的配置模式。
        """
        api_key = os.getenv("VISION_API_KEY", "") or config.llm_api_key
        if not api_key or "your-api-key" in api_key:
            add_log("WARN", "No VL API key configured", "vision")
            return None

        base = (os.getenv("VISION_BASE_URL", "") or config.llm_base_url).rstrip("/")
        if not base.endswith("/chat/completions"):
            base = base.rstrip("/v1") + "/v1/chat/completions"

        model = os.getenv("VISION_MODEL", "") or config.llm_model

        try:
            with open(image_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode()
        except Exception as e:
            add_log("ERROR", f"Cannot read image for VL: {e}", "vision")
            return None

        body = json.dumps({
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_data}"},
                    },
                    {"type": "text", "text": question},
                ],
            }],
            "max_tokens": 400,
        }).encode("utf-8")

        req = urllib.request.Request(
            url=base, data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
                result = data["choices"][0]["message"]["content"].strip()
                add_log("INFO", f"VL result: {len(result)} chars, model={model}", "vision")
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:300]
            add_log("ERROR", f"VL API HTTP {e.code}: {error_body}", "vision")
            return None
        except Exception as e:
            add_log("ERROR", f"VL API error: {e}", "vision")
            return None

    def _build_context(self, content: str, route: str = "ocr") -> str:
        """
        构建最终嵌入 LLM 对话的上下文字符串。
        """
        if not content or not content.strip():
            return "[对方发了一张图片]"

        if route in ("ocr", "ocr_fallback"):
            return (
                f"[对方发了一张图片。通过OCR识别到的文字内容：\n"
                f"{content.strip()}\n\n"
                f"请根据以上文字内容自然回复。如果识别结果不完整或看起来有误，"
                f"可以说'图片文字不太清楚'并尝试猜测。]"
            )
        elif route == "vision":
            return (
                f"[对方发了一张图片。图片内容描述：\n"
                f"{content.strip()}\n\n"
                f"请根据以上图片描述自然回复。]"
            )
        else:
            return f"[对方发了一张图片。{content}]"

    # ====== 工具方法 ======

    def _save_temp(self, img: Image.Image, prefix: str = "img") -> Optional[str]:
        """保存 PIL Image 到临时目录，返回路径"""
        try:
            fname = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
            path = str(self.temp_dir / fname)
            img.save(path, "PNG")
            return path
        except Exception as e:
            add_log("ERROR", f"Failed to save temp image: {e}", "vision")
            return None

    def cleanup(self, filepath: str = None):
        """删除临时文件"""
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass


# 全局单例
vision_client = VisionClient()
