"""
wx4py 适配器 v2
修复：图片检测、翻阅不触发、空文本处理
"""
import os, time, threading, traceback
from typing import Optional
from wx4py import WeChatClient
from wx4py.core import uiautomation as uia
from wx4py.features.messaging.listener import (
    _find_session_item, _find_window_by_title, _find_message_list,
    _read_visible_items, _double_click_control, MESSAGE_CLASSES,
    _safe_children, _safe_text, _safe_runtime_id,
)

# 扩展消息类名: wx4py 内置的 MESSAGE_CLASSES 只有 ChatBubbleItemView 和 ChatTextItemView，
# 但微信 4.x 图片/文件/引用消息使用的是 ChatBubbleReferItemView
EXTENDED_MESSAGE_CLASSES = MESSAGE_CLASSES | {
    "mmui::ChatBubbleReferItemView",  # 图片/文件/引用消息
}
from .adapter_base import WeChatAdapter, ChatMonitor as BaseMonitor
from database import add_log


class Wx4pyChatMonitor(BaseMonitor):
    def __init__(self, name, chat_type, wx_client):
        super().__init__(name=name, chat_type=chat_type, adapter=None)
        self.wx = wx_client
        self.hwnd = 0
        self.msg_list = None
        self.seen = set()
        self.seen_texts = set()  # 文本去重
        self.seen_non_text = set()  # 非文本去重 (runtime_id)
        self.last_sent = set()
        self._thread = None
        self._debug_n = 0

    def start(self) -> bool:
        main_hwnd = self.wx.window.hwnd
        target_type = "group" if self.chat_type == "group" else "contact"
        hwnd = _find_window_by_title(self.name, exclude_hwnd=main_hwnd)
        if hwnd:
            self.hwnd = hwnd
        else:
            if not self.wx.chat_window.open_chat(self.name, target_type=target_type):
                add_log("ERROR", f"open_chat failed: {self.name}", "wechat")
                return False
            time.sleep(0.8)
            root = self.wx.window.uia.root
            item = _find_session_item(root, self.name)
            if not item or not _double_click_control(item):
                add_log("ERROR", f"detach failed: {self.name}", "wechat")
                return False
            deadline = time.time() + 5
            while time.time() < deadline:
                hwnd = _find_window_by_title(self.name, exclude_hwnd=main_hwnd)
                if hwnd: self.hwnd = hwnd; break
                time.sleep(0.2)
            if not self.hwnd:
                add_log("ERROR", f"window not found: {self.name}", "wechat")
                return False

        root = uia.ControlFromHandle(self.hwnd)
        self.msg_list = _find_message_list(root)
        if not self.msg_list:
            add_log("ERROR", f"msg_list not found: {self.name}", "wechat")
            return False

        for item in _read_visible_items(self.msg_list):
            if item.key: self.seen.add(item.key)
            if item.name: self.seen_texts.add(item.name.strip()[:80])

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        add_log("INFO", f"Monitor: {self.name}", "wechat")
        return True

    def stop(self):
        self.running = False
        try:
            import win32gui
            if self.hwnd: win32gui.CloseWindow(self.hwnd)
        except: pass

    def _run(self):
        failures = 0
        while self.running:
            try:
                items = self._poll()
                if items:
                    failures = 0
                    for item in items:
                        if self.on_message:
                            self.on_message(self, self.name, item["text"],
                                            is_image=item["is_image"],
                                            msg_control=item.get("control"),
                                            is_group=(self.chat_type == "group"),
                                            is_at=self._check_at(item["text"]),
                                            hwnd=self.hwnd)
                else:
                    failures += 1
                    if failures > 20:
                        import win32gui
                        try:
                            if not win32gui.IsWindow(self.hwnd):
                                add_log("WARN", f"Window gone: {self.name}", "wechat")
                                self.running = False; break
                        except: pass
                        failures = 0
            except:
                failures += 1
                if failures > 3:
                    add_log("ERROR", f"Monitor dead: {self.name}", "wechat")
                    self.running = False; break
            time.sleep(1.5)

    def _check_at(self, text: str) -> bool:
        bot_name = os.getenv("BOT_NAME", "")
        return bool(bot_name and f"@{bot_name}" in text)

    def _poll(self) -> list[dict]:
        if not self.msg_list: return []
        items = []

        # 非文本标记
        NON_TEXT = ["[图片]","[Image]","[表情]","[Sticker]","[文件]","[File]",
                    "[视频]","[Video]","[语音]","[Voice]","[链接]","[Link]",
                    "[小程序]","[Mini Program]","[动画表情]","[Animated Sticker]"]

        # 每20轮 dump UIA 结构
        self._debug_n += 1

        try:
            # ---- 路径1: 文本消息 (Name 非空) ----
            all_items = _read_visible_items(self.msg_list)
            if self._debug_n % 20 == 0 and all_items:
                last = all_items[-1]
                add_log("DEBUG", f"UIA last: kind={last.kind} name={last.name!r} cls={last.class_name}", "wechat")

            # ---- 诊断: 每30轮dump所有msg_list子元素 (含Name为空的) ----
            if self._debug_n % 30 == 0:
                all_children = _safe_children(self.msg_list)
                classes_seen = {}
                for child in all_children:
                    cls = _safe_text(child, "ClassName")
                    name = _safe_text(child, "Name").strip()
                    ctrl_type = ""
                    try: ctrl_type = str(child.ControlTypeName or "")
                    except: pass
                    key = f"{cls}|{ctrl_type}"
                    if key not in classes_seen:
                        classes_seen[key] = {"count": 0, "has_name": 0, "empty_name": 0, "sample_name": ""}
                    classes_seen[key]["count"] += 1
                    if name:
                        classes_seen[key]["has_name"] += 1
                        if not classes_seen[key]["sample_name"]:
                            classes_seen[key]["sample_name"] = name[:40]
                    else:
                        classes_seen[key]["empty_name"] += 1
                dump = "; ".join(
                    f"{k}(total={v['count']} named={v['has_name']} empty={v['empty_name']} e.g.{v['sample_name']!r})"
                    for k, v in sorted(classes_seen.items(), key=lambda x: -x[1]['count'])
                )
                add_log("DEBUG", f"UIA children dump [{len(all_children)}]: {dump[:500]}", "wechat")

            for item in all_items:
                # 只处理消息类型
                if item.kind != "message":
                    continue

                # UIA key 去重（runtime_id 级别）
                if item.key and item.key in self.seen:
                    continue
                if item.key:
                    self.seen.add(item.key)

                text = (item.name or "").strip()

                # 文本去重
                dedup = text[:80] if text else ""
                if dedup and dedup in self.seen_texts:
                    continue
                if dedup:
                    self.seen_texts.add(dedup)
                if len(self.seen_texts) > 3000:
                    self.seen_texts = set(list(self.seen_texts)[-1500:])

                # 跳过自己发的
                if text and text in self.last_sent:
                    continue

                # 判断是否图片/非文本
                is_image = any(m in text for m in NON_TEXT)
                if not text:
                    # 空文本 = 99% 是图片/表情/文件
                    is_image = True
                    text = "[非文本消息]"

                items.append({"text": text, "is_image": is_image,
                              "control": item.control if hasattr(item, 'control') else None})
        except Exception as e:
            add_log("ERROR", f"Poll path1 error: {e}", "wechat")

        # ---- 路径2: 非文本消息 (ChatBubbleReferItemView 等) ----
        # _read_visible_items 的 MESSAGE_CLASSES 缺少 ChatBubbleReferItemView，
        # 微信图片/表情/文件等消息使用此类，Name 通常为 "图片"/"[图片]" 等
        try:
            non_text_children = []
            for child in _safe_children(self.msg_list):
                cls = _safe_text(child, "ClassName")
                if cls not in EXTENDED_MESSAGE_CLASSES:
                    continue
                name = _safe_text(child, "Name").strip()
                if name and cls != "mmui::ChatBubbleReferItemView":
                    continue  # 有文本且不是ReferItem → 路径1已处理
                # ChatBubbleReferItemView 或有 Name 的非文本标记 → 非文本消息
                rid = _safe_runtime_id(child)
                if not rid:
                    continue
                non_text_children.append((rid, child, name))

            for rid, child, name in non_text_children:
                if rid in self.seen_non_text:
                    continue
                self.seen_non_text.add(rid)
                if len(self.seen_non_text) > 3000:
                    self.seen_non_text = set(list(self.seen_non_text)[-1500:])

                # 尝试从 Name 识别消息类型
                label = "[非文本消息]"
                name_lower = name.lower() if name else ""
                if "图片" in name_lower or "image" in name_lower:
                    label = "[图片]"
                elif "表情" in name or "sticker" in name_lower:
                    label = "[表情]"
                elif "文件" in name or "file" in name_lower:
                    label = "[文件]"
                elif "视频" in name or "video" in name_lower:
                    label = "[视频]"
                elif "语音" in name or "voice" in name_lower:
                    label = "[语音]"
                elif "链接" in name or "link" in name_lower:
                    label = "[链接]"
                elif "小程序" in name or "mini" in name_lower:
                    label = "[小程序]"

                items.append({
                    "text": label,
                    "is_image": True,
                    "control": child,
                })

            if non_text_children and self._debug_n % 5 == 0:
                add_log("DEBUG", f"Non-text items: {[(n[:20], _safe_text(c,'ClassName')[:40]) for _,c,n in non_text_children]}", "wechat")
        except Exception as e:
            add_log("ERROR", f"Poll path2 error: {e}\n{traceback.format_exc()[-300:]}", "wechat")

        return items

    def mark_sent(self, text: str):
        self.last_sent.add(text[:50])


class Wx4pyAdapter(WeChatAdapter):
    name = "wx4py"
    description = "wx4py - WeChat 4.x"
    supported_versions = ["4.0","4.1"]

    def __init__(self):
        self._client = None

    def connect(self) -> bool:
        try:
            self._client = WeChatClient()
            self._client.connect()
            add_log("INFO", "wx4py connected", "wechat")
            return True
        except Exception as e:
            add_log("ERROR", f"wx4py: {e}", "wechat")
            return False

    def disconnect(self):
        if self._client:
            try: self._client.disconnect()
            except: pass
            self._client = None

    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def send_message(self, target: str, text: str) -> bool:
        if not self._client: return False
        try:
            self._client.chat_window.send_to(target, text)
            return True
        except Exception as e:
            add_log("ERROR", f"Send: {e}", "wechat")
            return False

    def send_file(self, target: str, filepath: str) -> bool:
        if not self._client: return False
        try:
            self._client.chat_window.send_file_to(target, filepath)
            add_log("INFO", f"File: {filepath}", "wechat")
            return True
        except Exception as e:
            add_log("ERROR", f"File: {e}", "wechat")
            return False

    def open_chat_monitor(self, name, chat_type="contact") -> Optional[Wx4pyChatMonitor]:
        if not self._client: return None
        mon = Wx4pyChatMonitor(name, chat_type, self._client)
        mon.adapter = self
        return mon

    @property
    def client(self): return self._client
