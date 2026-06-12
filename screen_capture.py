"""
窗口精准截图 — PrintWindow API
使用 Win32 PrintWindow 截取微信窗口像素，不截全屏，隔离其他软件干扰
替代失效的控件读取 + 剪贴板方案

技术栈: pywin32 + win32gui + PrintWindow + PIL
"""
import ctypes
import time
from typing import Optional, Tuple

import win32gui
import win32ui
import win32con
from PIL import Image, ImageGrab
import numpy as np


class ScreenCapture:
    """PrintWindow-based window capture with desktop fallback."""

    # Win32 constants
    PW_CLIENTONLY = 0x00000001
    SW_RESTORE = 9
    SW_SHOW = 5

    def __init__(self):
        self._user32 = ctypes.windll.user32

    # ====== public API ======

    def capture_window(self, hwnd: int) -> Optional[Image.Image]:
        """
        Capture the entire client area of the given window via PrintWindow.
        Returns a PIL Image (RGB) or None on failure.
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None

        # Ensure window is capturable
        if not self._ensure_window_ready(hwnd):
            return None

        # Try PrintWindow first
        img = self._print_window(hwnd)
        if img is not None and not self._is_blank_image(img):
            return img

        # Fallback to desktop grab
        return self._desktop_fallback(hwnd)

    def capture_chat_area(self, hwnd: int,
                          msg_list_control=None) -> Optional[Image.Image]:
        """
        Capture only the message-list portion of the chat window.

        Strategy:
          1. If msg_list_control is available, use its UIA BoundingRectangle
             to crop the full capture.
          2. Otherwise use ratio-based heuristics:
             - top ~6%    = title bar / nav bar
             - bottom ~10% = input area
             - middle     = message list
        Returns a PIL Image (RGB) or None.
        """
        img = self.capture_window(hwnd)
        if img is None:
            return None

        w, h = img.size

        if msg_list_control is not None:
            try:
                rect = msg_list_control.BoundingRectangle
                # Convert UIA screen coords to client-relative coords
                left, top_s, right, bottom_s = win32gui.GetWindowRect(hwnd)
                client_left, client_top = self._get_client_rect_screen(hwnd)
                if client_left is not None:
                    x1 = max(0, rect.left - client_left)
                    y1 = max(0, rect.top - client_top)
                    x2 = min(w, rect.right - client_left)
                    y2 = min(h, rect.bottom - client_top)
                    if x2 > x1 and y2 > y1:
                        return img.crop((x1, y1, x2, y2))
            except Exception:
                pass

        # Fallback: ratio-based crop
        crop_top = int(h * 0.06)
        crop_bottom = int(h * 0.90)
        if crop_bottom > crop_top:
            return img.crop((0, crop_top, w, crop_bottom))
        return img

    # ====== internals ======

    def _ensure_window_ready(self, hwnd: int) -> bool:
        """Check window state. If minimized, restore it. Returns True if capturable."""
        try:
            if not win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, self.SW_SHOW)
                time.sleep(0.3)

            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, self.SW_RESTORE)
                time.sleep(0.5)

            # Try to bring to foreground (best-effort)
            try:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.2)
            except Exception:
                pass

            return True
        except Exception:
            return False

    def _print_window(self, hwnd: int) -> Optional[Image.Image]:
        """Low-level PrintWindow capture. Returns PIL Image or None."""
        try:
            # Get client rect dimensions
            rect = win32gui.GetClientRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            if width <= 0 or height <= 0:
                return None

            # Get device context
            hwnd_dc = win32gui.GetDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()

            # Create compatible bitmap
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(bitmap)

            # PrintWindow: capture the window content
            # Flag 0x00000002 = PW_RENDERFULLCONTENT (Win8+)
            # Flag 0x00000001 = PW_CLIENTONLY
            result = ctypes.windll.user32.PrintWindow(
                ctypes.c_void_p(hwnd),
                ctypes.c_void_p(save_dc.GetSafeHdc()),
                ctypes.c_uint(0x00000002)  # PW_RENDERFULLCONTENT
            )

            if result == 0:
                # Try again with PW_CLIENTONLY
                result = ctypes.windll.user32.PrintWindow(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_void_p(save_dc.GetSafeHdc()),
                    ctypes.c_uint(0x00000001)  # PW_CLIENTONLY
                )

            # Convert to PIL Image
            bmp_info = bitmap.GetInfo()
            bmp_bits = bitmap.GetBitmapBits(True)

            im = Image.frombuffer(
                'RGB',
                (bmp_info['bmWidth'], bmp_info['bmHeight']),
                bmp_bits, 'raw', 'BGRX', 0, 1
            )

            # Clean up GDI resources
            win32gui.DeleteObject(bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)

            return im

        except Exception:
            self._cleanup_gdi()
            return None

    def _desktop_fallback(self, hwnd: int) -> Optional[Image.Image]:
        """
        Fallback when PrintWindow fails (e.g., window uses DirectX overlay).
        Uses ImageGrab to capture the window rectangle from the desktop.
        """
        try:
            rect = self._get_client_rect_screen(hwnd)
            if rect is None:
                return None

            left, top, right, bottom = rect
            if right <= left or bottom <= top:
                return None

            # Bring window to top first
            try:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.3)
            except Exception:
                pass

            img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
            return img
        except Exception:
            return None

    def _get_client_rect_screen(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """Convert client rect to screen coordinates."""
        try:
            rect = win32gui.GetClientRect(hwnd)
            pt = win32gui.ClientToScreen(hwnd, (rect[0], rect[1]))
            return (pt[0], pt[1], pt[0] + rect[2] - rect[0], pt[1] + rect[3] - rect[1])
        except Exception:
            # Fallback to GetWindowRect
            try:
                return win32gui.GetWindowRect(hwnd)
            except Exception:
                return None

    @staticmethod
    def _is_blank_image(img: Image.Image, threshold: float = 0.02) -> bool:
        """
        Detect if an image is mostly blank/black (PrintWindow failure indicator).
        threshold: max fraction of non-zero pixels to be considered "blank"
        """
        try:
            arr = np.array(img.convert('L'))
            non_zero = np.count_nonzero(arr)
            total = arr.size
            return (non_zero / total) < threshold
        except Exception:
            return False

    @staticmethod
    def _cleanup_gdi():
        """Best-effort GDI cleanup to prevent resource leaks."""
        try:
            ctypes.windll.gdi32.GdiFlush()
        except Exception:
            pass


# Module-level singleton
screen_capture = ScreenCapture()
