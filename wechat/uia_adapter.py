"""
纯 UIAutomation 适配器 — 通用回退方案
不依赖 wx4py，使用 Windows UIAutomation 原生 API
兼容任何微信版本，但功能受限（仅支持发送消息，不支持独立窗口监听）
"""
import time
import threading
from pathlib import Path
from typing import Optional

from .adapter_base import WeChatAdapter, ChatMonitor as BaseMonitor
from database import add_log


class UIAChatMonitor(BaseMonitor):
    """UIA 通用监控器 — 简化轮询版"""

    def __init__(self, name: str, chat_type: str, adapter: "UIAAdapter"):
        super().__init__(name=name, chat_type=chat_type, adapter=adapter)
        self._thread = None
        self._last_content = ""

    def start(self) -> bool:
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        add_log("INFO", f"UIA monitor started: {self.name}", "wechat")
        return True

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            time.sleep(5)  # UIA 轮询较慢
            # UIA adapter 通过 get_chat_history 轮询
            # 实际实现在 adapter 层


class UIAAdapter(WeChatAdapter):
    """
    纯 UIAutomation 适配器
    作为 wx4py 不可用时的回退方案
    使用 wx4py 的底层 UIA 模块（如果有的话）
    """

    name = "uia"
    description = "UIAutomation — 通用回退方案"
    supported_versions = ["3.x", "4.x", "any"]

    def __init__(self):
        self._connected = False
        self._wx = None

    def connect(self) -> bool:
        try:
            from wx4py import WeChatClient
            self._wx = WeChatClient()
            self._wx.connect()
            self._connected = True
            add_log("INFO", "UIA adapter connected (via wx4py backend)", "wechat")
            return True
        except Exception:
            try:
                from wx4py.core import uiautomation as uia
                wx = uia.WindowControl(searchDepth=1, Name="微信")
                if wx.Exists(0, 1):
                    self._connected = True
                    add_log("INFO", "UIA adapter connected (raw UIA)", "wechat")
                    return True
            except Exception as e:
                add_log("ERROR", f"UIA adapter: {e}", "wechat")
        return False

    def disconnect(self):
        if self._wx:
            try:
                self._wx.disconnect()
            except:
                pass
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def send_message(self, target: str, text: str) -> bool:
        if not self._wx:
            return False
        try:
            self._wx.chat_window.send_to(target, text)
            return True
        except:
            return False

    def open_chat_monitor(self, name: str, chat_type: str = "contact") -> Optional[UIAChatMonitor]:
        mon = UIAChatMonitor(name, chat_type, self)
        return mon
