"""
wx4py 适配器 — 微信 4.x
基于 wx4py 库，是目前功能最完整的实现
"""
import time
import threading
from typing import Optional

from wx4py import WeChatClient
from wx4py.core import uiautomation as uia
from wx4py.features.messaging.listener import (
    _find_session_item, _find_window_by_title, _find_message_list,
    _read_visible_items, _double_click_control, MESSAGE_CLASSES,
)

from .adapter_base import WeChatAdapter, ChatMonitor as BaseMonitor
from database import add_log


class Wx4pyChatMonitor(BaseMonitor):
    """wx4py 实现的聊天监控器 — 双击侧边栏→独立窗口→监听消息列表"""

    def __init__(self, name: str, chat_type: str, wx_client: WeChatClient):
        super().__init__(name=name, chat_type=chat_type, adapter=None)
        self.wx = wx_client
        self.hwnd: int = 0
        self.msg_list = None
        self.seen = set()
        self.last_sent = set()
        self._thread: threading.Thread = None

    def start(self) -> bool:
        main_hwnd = self.wx.window.hwnd
        target_type = "group" if self.chat_type == "group" else "contact"

        # 检查是否已有独立窗口
        hwnd = _find_window_by_title(self.name, exclude_hwnd=main_hwnd)
        if hwnd:
            self.hwnd = hwnd
        else:
            if not self.wx.chat_window.open_chat(self.name, target_type=target_type):
                add_log("ERROR", f"wx4py: failed to open chat: {self.name}", "wechat")
                return False
            time.sleep(0.8)

            root = self.wx.window.uia.root
            item = _find_session_item(root, self.name)
            if not item or not _double_click_control(item):
                add_log("ERROR", f"wx4py: failed to detach window: {self.name}", "wechat")
                return False

            deadline = time.time() + 5
            while time.time() < deadline:
                hwnd = _find_window_by_title(self.name, exclude_hwnd=main_hwnd)
                if hwnd:
                    self.hwnd = hwnd
                    break
                time.sleep(0.2)

            if not self.hwnd:
                add_log("ERROR", f"wx4py: separate window not found: {self.name}", "wechat")
                return False

        root = uia.ControlFromHandle(self.hwnd)
        self.msg_list = _find_message_list(root)
        if not self.msg_list:
            add_log("ERROR", f"wx4py: message list not found: {self.name}", "wechat")
            return False

        for item in _read_visible_items(self.msg_list):
            if item.key:
                self.seen.add(item.key)

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        add_log("INFO", f"Monitor started: {self.name} (hwnd={self.hwnd})", "wechat")
        return True

    def stop(self):
        self.running = False
        if self.hwnd:
            try:
                import win32gui
                win32gui.CloseWindow(self.hwnd)
            except:
                pass

    def _run(self):
        while self.running:
            try:
                texts = self._poll()
                for t in texts:
                    if self.on_message:
                        self.on_message(self, self.name, t)
            except:
                pass
            time.sleep(1.5)

    def _poll(self) -> list[str]:
        if not self.msg_list:
            return []
        texts = []
        try:
            for item in _read_visible_items(self.msg_list):
                if item.key and item.key not in self.seen and item.kind == "message":
                    self.seen.add(item.key)
                    text = item.name.strip()
                    if text and text not in self.last_sent:
                        texts.append(text)
        except:
            pass
        return texts

    def mark_sent(self, text: str):
        self.last_sent.add(text[:50])


class Wx4pyAdapter(WeChatAdapter):
    """微信 4.x 适配器 — 基于 wx4py"""

    name = "wx4py"
    description = "wx4py — 微信 4.x (推荐)"
    supported_versions = ["4.0", "4.1"]

    def __init__(self):
        self._client: WeChatClient = None

    def connect(self) -> bool:
        try:
            self._client = WeChatClient()
            self._client.connect()
            add_log("INFO", "wx4py connected", "wechat")
            return True
        except Exception as e:
            add_log("ERROR", f"wx4py connect failed: {e}", "wechat")
            return False

    def disconnect(self):
        if self._client:
            try:
                self._client.disconnect()
            except:
                pass
            self._client = None

    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def send_message(self, target: str, text: str) -> bool:
        if not self._client:
            return False
        try:
            self._client.chat_window.send_to(target, text)
            return True
        except Exception as e:
            add_log("ERROR", f"Send failed to {target}: {e}", "wechat")
            return False

    def open_chat_monitor(self, name: str, chat_type: str = "contact") -> Optional[Wx4pyChatMonitor]:
        if not self._client:
            return None
        mon = Wx4pyChatMonitor(name, chat_type, self._client)
        mon.adapter = self
        return mon

    @property
    def client(self) -> WeChatClient:
        return self._client
