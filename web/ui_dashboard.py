"""
Dashboard Tab — Bot 状态、统计、启动/停止
"""
import gradio as gr
from typing import Callable

from database import get_message_stats, get_contacts, add_log
from config import config
from chat_store import get_stats as chat_stats


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
                stats_box = gr.JSON(label="运行统计", value={})
                try:
                    _stats = get_message_stats()
                    _ac = None
                    try:
                        from database import get_active_llm_config
                        _ac = get_active_llm_config()
                    except:
                        pass
                    _cs = chat_stats()
                    stats_box.value = {
                        "消息统计": {
                            "总消息数": _stats["total"],
                            "今日收到": _stats["today_incoming"],
                            "今日回复": _stats["today_outgoing"],
                        },
                        "聊天文件": {
                            "文件数": _cs.get("files", 0),
                            "总行数": _cs.get("total_lines", 0),
                        },
                        "LLM": {
                            "激活配置": _ac["name"] if _ac else "无",
                            "模型": _ac["model"] if _ac else config.llm_model,
                        },
                        "监控": {
                            "联系人": len(get_contacts("contact")),
                            "群聊": len(get_contacts("group")),
                        },
                    }
                except:
                    stats_box.value = {"状态": "等待启动"}

        refresh_btn = gr.Button("🔄 刷新统计")

        def refresh_stats():
            try:
                stats = get_message_stats()
                _ac = None
                try:
                    from database import get_active_llm_config
                    _ac = get_active_llm_config()
                except:
                    pass
                _cs = chat_stats()
                return {
                    "消息统计": {
                        "总消息数": stats["total"],
                        "今日收到": stats["today_incoming"],
                        "今日回复": stats["today_outgoing"],
                        "今日活跃": stats["today_active_contacts"],
                    },
                    "聊天文件": {
                        "文件数": _cs.get("files", 0),
                        "总行数": _cs.get("total_lines", 0),
                    },
                    "LLM": {
                        "激活配置": _ac["name"] if _ac else "无",
                        "模型": _ac["model"] if _ac else config.llm_model,
                    },
                    "监控": {
                        "联系人": len(get_contacts("contact")),
                        "群聊": len(get_contacts("group")),
                    },
                }
            except Exception as e:
                return {"error": str(e)}

        refresh_btn.click(refresh_stats, outputs=stats_box)

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
