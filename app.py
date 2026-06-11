"""
微信 AI Bot v4 — 主入口
启动 Gradio Web UI + 微信 AI Bot 引擎
"""
import sys
import time
import random
import threading
from pathlib import Path

import gradio as gr

# 确保项目目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from database import (
    init_db, get_contacts, add_contact, save_message,
    is_duplicate, add_log, get_setting,
)
from config import config
from llm_client import llm_client
from personality.prompt_builder import prompt_builder

# WeChat 适配器
from wechat.version_detector import VersionDetector
from wechat.wx4py_adapter import Wx4pyAdapter
from wechat.uia_adapter import UIAAdapter

# Web UI
from web.ui_main import create_ui


# ====== Bot Engine ======

class BotEngine:
    """Bot 核心引擎 — 管理微信连接、消息路由、AI 回复"""

    def __init__(self):
        self.adapter = None
        self.monitors = []
        self.running = False
        self._lock = threading.Lock()
        self.contexts = {}
        self.last_reply_time = {}      # 最近一次回复时间
        self.last_msg_time = {}        # 对方最近一次发消息时间
        self.consecutive_skips = {}    # 连续跳过次数
        self.max_context = 10

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
        add_log("INFO", f"Bot started with {len(self.monitors)} monitors", "bot")

        # 发送上线通知（可选）
        try:
            self.adapter.send_message("文件传输助手", "AI Bot online~")
        except:
            pass

        return True

    def stop(self):
        """停止 Bot"""
        add_log("INFO", "Stopping bot engine...", "bot")
        self.running = False

        for mon in self.monitors:
            try:
                mon.stop()
            except:
                pass
        self.monitors.clear()

        if self.adapter:
            try:
                self.adapter.disconnect()
            except:
                pass
            self.adapter = None

        self.contexts.clear()
        self.last_reply_time.clear()
        self.last_msg_time.clear()
        self.consecutive_skips.clear()
        add_log("INFO", "Bot stopped", "bot")

    def _on_message(self, monitor, sender: str, content: str):
        """收到新消息时的回调"""
        if not content or not content.strip():
            return

        # 去重
        if is_duplicate(monitor.name, content, within_seconds=60):
            return

        # 保存到数据库
        save_message(monitor.name, sender, content, "incoming")
        add_log("INFO", f"Msg from {monitor.name}: {content[:60]}", "bot")

        name = monitor.name
        now = time.time()

        # 判断是否在活跃对话中（对方3分钟内连续发过消息）
        last_msg = self.last_msg_time.get(name, 0)
        in_active_conversation = (now - last_msg) < 180
        self.last_msg_time[name] = now

        # 冷却检查：仅在自己刚回复完3秒内生效，防止重复回复同一条消息
        if name in self.last_reply_time:
            if now - self.last_reply_time[name] < 3:
                add_log("INFO", f"Anti-duplicate cooldown for {name}", "bot")
                return

        # 随机跳过：仅在不活跃时可能跳过，且不能连续跳过
        consecutive = self.consecutive_skips.get(name, 0)
        if not in_active_conversation and consecutive < 2:
            if random.random() < config.skip_probability:
                self.consecutive_skips[name] = consecutive + 1
                add_log("INFO", f"Randomly skipped {name} (consecutive: {consecutive+1})", "bot")
                return
        self.consecutive_skips[name] = 0  # 未跳过，重置

        # 生成 AI 回复
        try:
            ctx = self.contexts.setdefault(name, [])

            system_prompt = prompt_builder.build(
                sender_name=sender,
                chat_context=ctx,
            )

            messages = [
                {"role": "system", "content": system_prompt},
                *ctx[-self.max_context:],
                {"role": "user", "content": f"{sender}: {content}"},
            ]

            reply = llm_client.chat(messages)

            if not reply or reply.upper().startswith("[SKIP]"):
                add_log("INFO", f"LLM chose to skip {name}", "bot")
                return

            # 保存上下文
            ctx.append({"role": "user", "content": f"{sender}: {content}"})
            ctx.append({"role": "assistant", "content": reply})
            if len(ctx) > self.max_context * 2:
                self.contexts[name] = ctx[-self.max_context * 2:]

            # 延迟回复
            delay = random.uniform(config.reply_min_delay, config.reply_max_delay)
            time.sleep(delay)

            # 发送
            ok = self.adapter.send_message(name, reply)
            if ok:
                save_message(name, "bot", reply, "outgoing")
                monitor.mark_sent(reply) if hasattr(monitor, 'mark_sent') else None
                self.last_reply_time[name] = time.time()
                add_log("INFO", f"Reply to {name}: {reply[:60]}", "bot")

        except Exception as e:
            add_log("ERROR", f"Reply failed for {name}: {e}", "bot")

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
    init_db()
    add_log("INFO", "Bot v4 starting...", "system")

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
        """,
    )


if __name__ == "__main__":
    main()
