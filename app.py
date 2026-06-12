"""
微信 AI Bot v5 — 主入口
消息队列 + 上下文增强 + 识图 + 生图
"""
import sys
import os
import re
import time
import random
import queue
import threading
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).parent))

from database import (
    get_contacts, add_contact,
    is_duplicate, add_log, get_setting,
)
from config import config
from llm_client import llm_client
from personality.prompt_builder import prompt_builder
from vision import vision_client
from image_gen import image_gen
from chat_store import append_message as chat_append

from wechat.version_detector import VersionDetector
from wechat.wx4py_adapter import Wx4pyAdapter
from wechat.uia_adapter import UIAAdapter

from web.ui_main import create_ui


# ====== Bot Engine ======

class BotEngine:
    """Bot 核心引擎 v5 — 消息队列 + 上下文增强 + 识图 + 生图"""

    def __init__(self):
        self.adapter = None
        self.monitors = []
        self.running = False
        self._lock = threading.Lock()
        self.contexts = {}             # 对话上下文 {chat: [msgs]}
        self.pending = {}              # 待处理的缓冲消息 {chat: [texts]}
        self.last_reply_time = {}      # 最近回复时间
        self.last_msg_time = {}        # 对方最近消息时间
        self.consecutive_skips = {}    # 连续跳过次数
        self.max_context = 15
        self.msg_queue = queue.Queue() # 消息队列
        self._worker = None

    def start(self) -> bool:
        """启动 Bot"""
        if self.running:
            add_log("WARN", "Bot is already running", "bot")
            return False

        add_log("INFO", "Starting bot engine...", "bot")

        # 检测微信版本，选择适配器
        version = VersionDetector.detect()
        if version:
            adapter_name = VersionDetector.recommend_adapter(version)
            add_log("INFO", f"WeChat version: {version.version_str}, adapter: {adapter_name}", "bot")
        else:
            adapter_name = "wx4py"
            add_log("WARN", "Could not detect WeChat version, trying wx4py", "bot")

        # 初始化适配器
        if adapter_name == "wx4py":
            self.adapter = Wx4pyAdapter()
        else:
            self.adapter = UIAAdapter()

        if not self.adapter.connect():
            add_log("ERROR", "Failed to connect to WeChat", "bot")
            return False

        # 从数据库加载联系人列表
        contacts = get_contacts("contact", active_only=True)
        groups = get_contacts("group", active_only=True)

        if not contacts and not groups:
            # 回退到 .env 配置
            for name in config.contacts:
                add_contact(name, "contact")
                contacts.append({"name": name, "type": "contact"})
            for name in config.groups:
                add_contact(name, "group")
                contacts.append({"name": name, "type": "group"})
            contacts = get_contacts("contact", active_only=True)
            groups = get_contacts("group", active_only=True)

        # 打开监控窗口
        for c in contacts:
            mon = self.adapter.open_chat_monitor(c["name"], "contact")
            if mon:
                mon.on_message = self._on_message
                if mon.start():
                    self.monitors.append(mon)
                    add_log("INFO", f"Monitoring: {c['name']}", "bot")
                time.sleep(1)

        for g in groups:
            mon = self.adapter.open_chat_monitor(g["name"], "group")
            if mon:
                mon.on_message = self._on_message
                if mon.start():
                    self.monitors.append(mon)
                    add_log("INFO", f"Monitoring group: {g['name']}", "bot")
                time.sleep(1)

        self.running = True
        # 清空启动期间各 monitor 初始轮询产生的旧消息，避免回复错人
        time.sleep(2)  # 等所有 monitor 完成初始扫描
        drained = 0
        while not self.msg_queue.empty():
            try:
                self.msg_queue.get_nowait()
                drained += 1
            except:
                break
        if drained:
            add_log("INFO", f"Startup: drained {drained} old messages from queue", "bot")
        # 启动消息队列 worker
        self._worker = threading.Thread(target=self._process_queue, daemon=True)
        self._worker.start()
        add_log("INFO", f"Bot started with {len(self.monitors)} monitors", "bot")

        try:
            self.adapter.send_message("文件传输助手", "AI Bot online~")
        except:
            pass
        return True

    def stop(self):
        """停止 Bot"""
        add_log("INFO", "Stopping bot engine...", "bot")
        self.running = False

        # 清空队列
        while not self.msg_queue.empty():
            try: self.msg_queue.get_nowait()
            except: break

        for mon in self.monitors:
            try: mon.stop()
            except: pass
        self.monitors.clear()

        if self.adapter:
            try: self.adapter.disconnect()
            except: pass
            self.adapter = None

        self.contexts.clear()
        self.pending.clear()
        self.last_reply_time.clear()
        self.last_msg_time.clear()
        self.consecutive_skips.clear()
        add_log("INFO", "Bot stopped", "bot")

    def _on_message(self, monitor, sender: str, content: str, is_image: bool = False,
                    msg_control=None, is_group: bool = False, is_at: bool = False,
                    hwnd: int = 0):
        """收到新消息时的回调 — 进入队列"""
        if not content and not is_image:
            return

        name = monitor.name

        # 群聊未被@则只读不回复（但保存上下文）
        if is_group and not is_at:
            ctx = self.contexts.setdefault(name, [])
            ctx.append({"role": "user", "content": f"{sender}: {content}"})
            if len(ctx) > self.max_context * 2:
                self.contexts[name] = ctx[-self.max_context * 2:]
            return

        # 去重
        key = content[:80] if content else "image"
        if is_duplicate(name, key, within_seconds=30):
            return

        chat_append(name, sender, content or "[图片]", "incoming")

        if is_image:
            add_log("INFO", f"Image detected: {name} text={content!r}", "bot")

        # 加入队列
        self.msg_queue.put({
            "monitor": monitor,
            "sender": sender,
            "content": content,
            "is_image": is_image,
            "msg_control": msg_control,
            "chat": name,
            "is_group": is_group,
            "is_at": is_at,
            "hwnd": hwnd,
        })

    def _process_queue(self):
        """消息队列 worker — 串行处理，保证上下文不乱"""
        while self.running:
            try:
                item = self.msg_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self._handle_message(item)
            except Exception as e:
                add_log("ERROR", f"Queue handler error: {e}", "bot")

    def _handle_message(self, item: dict):
        """处理单条消息"""
        name = item["chat"]
        sender = item["sender"]
        content = item["content"]
        monitor = item["monitor"]
        is_group = item.get("is_group", False)
        is_at = item.get("is_at", False)

        now = time.time()
        last_msg = self.last_msg_time.get(name, 0)
        in_active = (now - last_msg) < 180
        self.last_msg_time[name] = now

        # 冷却：3秒内刚回复过则跳过
        if name in self.last_reply_time and now - self.last_reply_time[name] < 3:
            add_log("INFO", f"Cooldown for {name}", "bot")
            return

        # 随机跳过
        consecutive = self.consecutive_skips.get(name, 0)
        if not in_active and consecutive < 2:
            if random.random() < config.skip_probability:
                self.consecutive_skips[name] = consecutive + 1
                add_log("INFO", f"Random skip {name}", "bot")
                return
        self.consecutive_skips[name] = 0

        # 缓冲同一联系人短时间内的多条消息
        pending = self.pending.setdefault(name, [])
        now_ts = time.time()

        if item.get("is_image"):
            raw_text = content or ""
            for marker in ["[图片]", "[Image]", "[非文本消息]", "[消息]", "[表情]", "[文件]", "[视频]"]:
                raw_text = raw_text.replace(marker, "")
            text_without_marker = raw_text.strip()

            # 提取 HWND 和 UIA 控件引用
            hwnd = item.get("hwnd", 0)
            msg_ctrl = item.get("msg_control")

            # 统一视觉管道: PrintWindow截图 → OpenCV检测 → OCR或VL
            img_context = vision_client.handle_image_message(
                hwnd=hwnd,
                msg_control=msg_ctrl,
                mode=config.vision_mode,
            )

            if text_without_marker:
                content = f"{img_context}\n对方说：{text_without_marker}"
            else:
                content = img_context
            add_log("INFO", f"Image msg from {name}: mode={config.vision_mode}", "bot")

        pending.append({"role": "user", "content": f"{sender}: {content}", "ts": now_ts})

        # 等待缓冲窗口：如果1.5秒内还有新消息到达，合并处理
        time.sleep(1.5)

        # 收集缓冲窗口内所有消息
        window_msgs = [m for m in pending if now_ts - m["ts"] <= 3.0]
        self.pending[name] = []  # 清空缓冲

        if not window_msgs:
            return

        # 构建 LLM 对话
        ctx = self.contexts.setdefault(name, [])

        pure_ai = get_setting("AI_MODE", "persona") == "pure"
        personality_text = get_setting("PERSONALITY_DESC", "")

        # 加载记忆
        from database import get_memories
        memories = get_memories(name)
        if is_group and sender and sender != name:
            memories += get_memories(sender)
        seen_facts = set()
        memory_text = ""
        for m in memories:
            if m["fact"] not in seen_facts:
                seen_facts.add(m["fact"])
        if seen_facts:
            memory_text = "## 关于此人/此群的记忆\n" + "\n".join(f"- {f}" for f in list(seen_facts)[:15])

        bot_name = get_setting("BOT_NAME", "")
        system_prompt = prompt_builder.build(
            sender_name=sender,
            chat_name=name,
            personality_text=personality_text if personality_text else None,
            pure_ai=pure_ai,
            is_group=is_group,
            bot_name=bot_name,
        )
        if memory_text:
            system_prompt = memory_text + "\n\n" + system_prompt

        # 多消息合并提示
        if len(window_msgs) > 1:
            merged = "\n".join(m["content"] for m in window_msgs)
            user_msg = f"[短时间内连续发了{len(window_msgs)}条消息]\n{merged}"
        else:
            user_msg = window_msgs[0]["content"]

        messages = [
            {"role": "system", "content": system_prompt},
            *ctx[-self.max_context:],
            {"role": "user", "content": user_msg},
        ]

        try:
            reply = llm_client.chat(messages)
        except Exception as e:
            add_log("ERROR", f"LLM error for {name}: {e}", "bot")
            return

        if not reply or reply.upper().startswith("[SKIP]"):
            return

        # 自动记忆：[MEMORY:xxx]
        # 群聊中记忆存到发送者名下，私聊存到联系人名下
        import re as _re2
        for m in _re2.finditer(r'\[MEMORY[:：]\s*(.+?)\]', reply, _re2.IGNORECASE):
            fact = m.group(1).strip()
            if fact:
                from database import add_memory
                mem_target = sender if (is_group and sender and sender != name) else name
                add_memory(mem_target, fact)
                add_log("INFO", f"Auto-memory [{mem_target}]: {fact[:40]}", "bot")
        reply = _re2.sub(r'\[MEMORY[:：]\s*.+?\]', '', reply, flags=_re2.IGNORECASE).strip()

        # 解析 [STICKER:xx] 和 [IMAGE:xx]
        sticker_path = None
        image_path = None

        for marker, pattern in [
            ("STICKER", re.compile(r'\[STICKER[:：]\s*([^\]]+)\]', re.IGNORECASE)),
            ("IMAGE", re.compile(r'\[IMAGE[:：]\s*([^\]]+)\]', re.IGNORECASE)),
        ]:
            m = pattern.search(reply)
            if m:
                kw = m.group(1).strip()
                reply = pattern.sub("", reply).strip()
                if marker == "STICKER":
                    from database import get_emojis_by_keyword, increment_emoji_usage
                    matches = get_emojis_by_keyword(kw)
                    if matches:
                        import random as _random
                        pick = _random.choice(matches) if len(matches) > 1 else matches[0]
                        sticker_path = pick["filepath"]
                        increment_emoji_usage(pick["id"])
                elif marker == "IMAGE":
                    img = image_gen.generate(kw)
                    if img:
                        image_path = img

        # 保存上下文
        for m in window_msgs:
            ctx.append(m)
        ctx.append({"role": "assistant", "content": reply})
        if len(ctx) > self.max_context * 2:
            self.contexts[name] = ctx[-self.max_context * 2:]

        # 延迟回复
        delay = random.uniform(config.reply_min_delay, config.reply_max_delay)
        time.sleep(delay)

        # 发送文字
        if reply:
            try:
                self.adapter.send_message(name, reply)
                chat_append(name, "bot", reply, "outgoing")
                monitor.mark_sent(reply) if hasattr(monitor, 'mark_sent') else None
                add_log("INFO", f"Reply to {name}: {reply[:60]}", "bot")
            except Exception as e:
                add_log("ERROR", f"Send failed: {e}", "bot")

        # 发送表情包
        if sticker_path:
            time.sleep(0.5)
            self.adapter.send_file(name, sticker_path)

        # 发送生成图片
        if image_path:
            time.sleep(0.5)
            self.adapter.send_file(name, image_path)
            image_gen.cleanup(image_path)

        self.last_reply_time[name] = time.time()

    @property
    def is_running(self) -> bool:
        return self.running

    @property
    def monitor_count(self) -> int:
        return len(self.monitors)


# ====== 全局 Bot 实例 ======
bot_engine = BotEngine()


# ====== Main ======

def main():
    print("=" * 55)
    print("  WeChat AI Bot v4")
    print("  Web UI + Bot Engine")
    print("=" * 55)

    # 初始化数据库
    add_log("INFO", "Bot v5 starting...", "system")

    # 定义回调
    def on_start():
        ok = bot_engine.start()
        add_log("INFO", f"Bot start: {'OK' if ok else 'FAILED'}", "system")
        return "运行中" if ok else "连接失败"

    def on_stop():
        bot_engine.stop()
        return "已停止"

    # 创建 Gradio UI（所有事件绑定在 Blocks 上下文内完成）
    app, components, theme = create_ui(on_start=on_start, on_stop=on_stop)

    # 启动 Gradio
    web_password = config.web_password
    auth = (("admin", web_password),) if web_password else None

    print(f"\n[OK] Starting Web UI on http://localhost:{config.web_port}")
    if auth:
        print(f"  Password protected: admin / {web_password}")

    app.queue(default_concurrency_limit=10).launch(
        server_name="127.0.0.1",
        server_port=config.web_port,
        auth=auth,
        share=False,
        inbrowser=True,
        theme=theme,
        css="""
        .main-header { text-align: center; padding: 10px; }
        .status-running { color: green; font-weight: bold; }
        .status-stopped { color: red; font-weight: bold; }
        /* Toast 通知定位到页面底部中央 */
        .toast-wrap { bottom: 24px !important; top: auto !important; }
        .toast-body { font-size: 15px !important; border-radius: 10px !important;
                      box-shadow: 0 4px 20px rgba(0,0,0,0.15) !important; }
        """,
    )


if __name__ == "__main__":
    main()
