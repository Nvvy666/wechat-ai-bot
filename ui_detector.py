"""
UI 目标检测 — OpenCV
识别微信聊天窗口中的：消息列表区域、图片消息气泡、未读红点
基于轮廓检测 + 颜色分割 + 纹理分析，无需训练模型
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image


@dataclass
class Rect:
    """Bounding box with optional confidence score."""
    x: int
    y: int
    w: int
    h: int
    confidence: float = 0.0

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def expand(self, padding: int = 10) -> "Rect":
        """Return a new Rect expanded by padding on all sides."""
        return Rect(
            x=max(0, self.x - padding),
            y=max(0, self.y - padding),
            w=self.w + 2 * padding,
            h=self.h + 2 * padding,
            confidence=self.confidence,
        )

    def clamp(self, img_w: int, img_h: int) -> "Rect":
        """Clamp this rect to image boundaries."""
        x = max(0, self.x)
        y = max(0, self.y)
        w = min(self.w, img_w - x)
        h = min(self.h, img_h - y)
        return Rect(x, y, w, h, self.confidence)

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class UIDetector:
    """
    Detects UI elements in WeChat chat window screenshots.

    Detection methods:
      - Message list region: background color segmentation + ratio heuristics
      - Image bubbles: Canny edge → contour finding → multi-factor filtering
      - Red dots: HSV red-hue threshold → circular contour filtering
    """

    # Tunable constants
    TITLE_RATIO_MAX = 0.08       # top 8% = title/nav bar
    INPUT_RATIO_MIN = 0.88       # bottom 12% = input area
    IMAGE_BUBBLE_MIN_H = 50      # minimum height for an image bubble
    IMAGE_BUBBLE_MIN_W = 80      # minimum width
    IMAGE_BUBBLE_MAX_ASPECT = 3.5  # max width/height ratio
    IMAGE_BUBBLE_MIN_SOLIDITY = 0.55  # minimum contour area / bounding rect area
    IMAGE_BUBBLE_MIN_VARIANCE = 1200  # minimum pixel variance (image > text)

    # Red dot detection (HSV)
    RED_HUE_LOW1 = (0, 120, 100)
    RED_HUE_HIGH1 = (10, 255, 255)
    RED_HUE_LOW2 = (160, 120, 100)
    RED_HUE_HIGH2 = (180, 255, 255)
    RED_DOT_MIN_AREA = 15
    RED_DOT_MAX_AREA = 500
    RED_DOT_MIN_CIRCULARITY = 0.6

    # ====== public API ======

    def find_message_list_region(self, img_bgr: np.ndarray) -> Rect:
        """
        Estimate the message-list region in the chat window.

        Uses ratio-based heuristics (WeChat layout is consistent):
          - Top ~8%: title bar with contact name
          - Bottom ~12%: input text area + toolbar
          - Middle: message list (our target)

        Refines with background color analysis where possible.
        """
        h, w = img_bgr.shape[:2]
        y_start = int(h * self.TITLE_RATIO_MAX)
        y_end = int(h * self.INPUT_RATIO_MIN)

        # Try to refine using background uniformity
        if y_end > y_start + 100:
            refined_start = self._find_first_text_row(img_bgr, y_start, y_end)
            if refined_start is not None:
                y_start = max(y_start, refined_start - 10)
            refined_end = self._find_last_text_row(img_bgr, y_start, y_end)
            if refined_end is not None:
                y_end = min(y_end, refined_end + 10)

        return Rect(x=0, y=y_start, w=w, h=max(10, y_end - y_start))

    def find_image_bubbles(self, img_bgr: np.ndarray,
                           roi: Optional[Rect] = None) -> List[Rect]:
        """
        Find rectangular regions likely to be image message bubbles.

        Method:
          1. Convert ROI to grayscale, apply Canny edge detection
          2. Find external contours
          3. Filter by area, aspect ratio, solidity, and image-like texture
          4. Score by pixel variance (images have higher variance than text)
          5. Return sorted by y-position (bottom-most = most recent first)
        """
        if roi is not None:
            work = img_bgr[roi.y:roi.bottom, roi.x:roi.right]
            offset_x, offset_y = roi.x, roi.y
        else:
            work = img_bgr
            offset_x, offset_y = 0, 0

        h, w = work.shape[:2]

        # Grayscale + bilateral filter (preserve edges, smooth noise)
        gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)

        # Canny edge detection
        edges = cv2.Canny(gray, 30, 90)

        # Dilate to connect nearby edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            cnt_area = cv2.contourArea(cnt)

            # Filter: minimum size
            if cw < self.IMAGE_BUBBLE_MIN_W or ch < self.IMAGE_BUBBLE_MIN_H:
                continue

            # Filter: aspect ratio (image bubbles are roughly square to 3:1)
            aspect = cw / max(ch, 1)
            if aspect > self.IMAGE_BUBBLE_MAX_ASPECT or aspect < 1.0 / self.IMAGE_BUBBLE_MAX_ASPECT:
                continue

            # Filter: solidity (filled rectangle vs sparse outline)
            if area > 0:
                solidity = cnt_area / area
                if solidity < self.IMAGE_BUBBLE_MIN_SOLIDITY:
                    continue

            # Filter: exclude edge-hugging regions (UI chrome)
            if x <= 3 or x + cw >= w - 3:
                continue

            # Score: how "image-like" is this region?
            roi_gray = gray[y:y+ch, x:x+cw]
            score = self._score_image_likeness(roi_gray)

            if score < 0.3:
                continue

            candidates.append(Rect(
                x=offset_x + x, y=offset_y + y,
                w=cw, h=ch, confidence=score,
            ))

        # Deduplicate overlapping boxes (keep higher confidence)
        candidates = self._nms(candidates, iou_threshold=0.5)

        # Sort by y (bottom-most first = most recent)
        candidates.sort(key=lambda r: r.bottom, reverse=True)
        return candidates

    def find_latest_image_bubble(self, img_bgr: np.ndarray,
                                  roi: Optional[Rect] = None) -> Optional[Rect]:
        """Convenience: return the bottom-most (most recent) image bubble."""
        bubbles = self.find_image_bubbles(img_bgr, roi)
        return bubbles[0] if bubbles else None

    def detect_red_dots(self, img_bgr: np.ndarray,
                        roi: Optional[Rect] = None) -> List[Rect]:
        """
        Detect unread-message red dots (small red circles on contact sidebar).

        Uses HSV thresholding for red color + circular contour filtering.
        """
        if roi is not None:
            work = img_bgr[roi.y:roi.bottom, roi.x:roi.right]
            offset_x, offset_y = roi.x, roi.y
        else:
            work = img_bgr
            offset_x, offset_y = 0, 0

        hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)

        # Red wraps around in HSV, so we need two masks
        mask1 = cv2.inRange(hsv, self.RED_HUE_LOW1, self.RED_HUE_HIGH1)
        mask2 = cv2.inRange(hsv, self.RED_HUE_LOW2, self.RED_HUE_HIGH2)
        mask = cv2.bitwise_or(mask1, mask2)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        dots = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.RED_DOT_MIN_AREA or area > self.RED_DOT_MAX_AREA:
                continue

            # Circularity check
            perimeter = cv2.arcLength(cnt, True)
            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                if circularity < self.RED_DOT_MIN_CIRCULARITY:
                    continue

            x, y, w, h = cv2.boundingRect(cnt)
            # Red dots are roughly square
            aspect = w / max(h, 1)
            if aspect < 0.5 or aspect > 2.0:
                continue

            dots.append(Rect(
                x=offset_x + x, y=offset_y + y,
                w=w, h=h, confidence=circularity,
            ))

        return dots

    # ====== helpers ======

    @staticmethod
    def _score_image_likeness(roi_gray: np.ndarray) -> float:
        """
        Score 0..1 how likely a region is an image vs text bubble.

        Images have:
          - Higher pixel variance (organic content vs uniform text bg)
          - Broader gradient distribution
          - Less horizontal-line structure (text has rows of sharp edges)

        Uses a weighted combination of:
          - Variance of pixel intensities
          - Edge density after Canny
        """
        if roi_gray.size < 100:
            return 0.0

        try:
            # 1. Pixel variance (normalized)
            variance = float(np.var(roi_gray))
            var_score = min(1.0, variance / 10000.0)

            # 2. Edge density: images have organic edges, text has uniform sharp lines
            edges = cv2.Canny(roi_gray, 50, 150)
            edge_density = np.count_nonzero(edges) / max(roi_gray.size, 1)

            # Text has high edge density (>0.15); moderate density is more image-like
            if edge_density < 0.02:
                edge_score = 0.0  # too flat = blank area
            elif edge_density > 0.25:
                edge_score = 0.2  # too dense = text or noise
            else:
                edge_score = 0.8  # moderate = likely image

            # 3. Horizontal line check: text rows create horizontal edge clusters
            h_edges = cv2.Sobel(roi_gray, cv2.CV_64F, 0, 1, ksize=3)
            v_edges = cv2.Sobel(roi_gray, cv2.CV_64F, 1, 0, ksize=3)
            h_sum = np.mean(np.abs(h_edges))
            v_sum = np.mean(np.abs(v_edges))
            if h_sum + v_sum > 0:
                h_ratio = h_sum / (h_sum + v_sum)
                # Text tends to have dominant horizontal edges (0.55-0.7)
                # Images are more balanced (0.45-0.55)
                if 0.48 <= h_ratio <= 0.56:
                    texture_score = 0.8
                elif 0.44 <= h_ratio <= 0.60:
                    texture_score = 0.5
                else:
                    texture_score = 0.2
            else:
                texture_score = 0.0

            # Weighted combination
            score = var_score * 0.4 + edge_score * 0.3 + texture_score * 0.3
            return float(np.clip(score, 0.0, 1.0))

        except Exception:
            return 0.0

    @staticmethod
    def _find_first_text_row(img_bgr: np.ndarray, y_start: int, y_end: int) -> Optional[int]:
        """Find the first row where the background transitions to message area."""
        try:
            h, w = img_bgr.shape[:2]
            y_end = min(y_end, h)
            # Sample vertical color profile from center column
            center = w // 2
            for y in range(y_start, y_end, 2):
                pixel = img_bgr[y, center]
                # WeChat message area is typically very light (RGB > 240)
                if np.mean(pixel) > 235:
                    return y
        except Exception:
            pass
        return None

    @staticmethod
    def _find_last_text_row(img_bgr: np.ndarray, y_start: int, y_end: int) -> Optional[int]:
        """Find the last row before the input area."""
        try:
            h = img_bgr.shape[:1][0]
            y_end = min(y_end, h)
            center = img_bgr.shape[1] // 2
            # Scan upward from bottom
            for y in range(y_end - 1, y_start, -2):
                pixel = img_bgr[y, center]
                # Input area has a distinct separator bar (gray line)
                if np.mean(pixel) < 200:
                    return min(y + 5, y_end)
        except Exception:
            pass
        return None

    @staticmethod
    def _nms(rects: List[Rect], iou_threshold: float = 0.5) -> List[Rect]:
        """Non-maximum suppression for overlapping bounding boxes."""
        if len(rects) <= 1:
            return rects

        # Sort by confidence descending
        rects = sorted(rects, key=lambda r: r.confidence, reverse=True)
        keep = []

        for i, r1 in enumerate(rects):
            suppressed = False
            for r2 in keep:
                iou = UIDetector._iou(r1, r2)
                if iou > iou_threshold:
                    suppressed = True
                    break
            if not suppressed:
                keep.append(r1)

        return keep

    @staticmethod
    def _iou(a: Rect, b: Rect) -> float:
        """Intersection over Union for two Rects."""
        x1 = max(a.x, b.x)
        y1 = max(a.y, b.y)
        x2 = min(a.right, b.right)
        y2 = min(a.bottom, b.bottom)

        inter_w = max(0, x2 - x1)
        inter_h = max(0, y2 - y1)
        inter_area = inter_w * inter_h

        union_area = a.area + b.area - inter_area
        if union_area <= 0:
            return 0.0
        return inter_area / union_area


# ====== PIL helpers ======

def pil_to_bgr(img: Image.Image) -> np.ndarray:
    """Convert PIL Image (RGB) to OpenCV BGR numpy array."""
    arr = np.array(img.convert('RGB'))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def bgr_to_pil(img_bgr: np.ndarray) -> Image.Image:
    """Convert OpenCV BGR numpy array to PIL Image."""
    arr = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr)


# Module-level singleton
ui_detector = UIDetector()
