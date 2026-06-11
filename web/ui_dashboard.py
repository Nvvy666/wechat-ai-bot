"""
Dashboard Tab — Bot 状态、统计、启动/停止
"""
import gradio as gr
from datetime import datetime
from typing import Callable

from database import get_message_stats, get_contacts, add_log
from config import config


def create_dashboard_tab(on_start: Callable = None, on_stop: Callable = None):
    with gr.Column():
        gr.Markdown("## 仪表盘")

        with gr.Row():
            with gr.Column(scale=1):
                status_indicator = gr.Textbox(
                    label="Bot 状态",
                    value="已停止",
                    interactive=False,
                )
                btn_start = gr.Button("启动 Bot", variant="primary", size="lg")
                btn_stop = gr.Button("停止 Bot", variant="stop", size="lg")

            with gr.Column(scale=2):
                stats_box = gr.JSON(label="今日统计", value={})

        refresh_btn = gr.Button("刷新统计")

        def refresh_stats():
            try:
                stats = get_message_stats()
                from database import get_active_profile
                profile = get_active_profile()
                return {
                    "总消息数": stats["total"],
                    "今日收到": stats["today_incoming"],
                    "今日回复": stats["today_outgoing"],
                    "今日活跃联系人": stats["today_active_contacts"],
                    "当前模型": config.llm_model,
                    "监控联系人数": len(get_contacts("contact")),
                    "监控群聊数": len(get_contacts("group")),
                    "激活的风格档案": profile["name"] if profile else "默认",
                }
            except Exception as e:
                return {"error": str(e)}

        refresh_btn.click(refresh_stats, outputs=stats_box)

        # Bind start/stop inside Blocks context
        if on_start:
            btn_start.click(
                fn=lambda: (on_start() or "运行中"),
                outputs=[status_indicator],
            )
        if on_stop:
            btn_stop.click(
                fn=lambda: (on_stop() or "已停止"),
                outputs=[status_indicator],
            )

        return {
            "status": status_indicator,
            "btn_start": btn_start,
            "btn_stop": btn_stop,
            "stats": stats_box,
            "refresh": refresh_btn,
        }
