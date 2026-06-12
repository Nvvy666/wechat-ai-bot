"""
Gradio 主界面 — 组装所有 Tab
"""
import gradio as gr

from .ui_dashboard import create_dashboard_tab
from .ui_logs import create_logs_tab
from .ui_contacts import create_contacts_tab
from .ui_history import create_history_tab
from .ui_config import create_config_tab
from .ui_emojis import create_emoji_tab
from .ui_memories import create_memories_tab


def create_ui(on_start=None, on_stop=None):
    """创建完整的 Gradio Web UI"""
    theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="gray",
        neutral_hue="slate",
    )

    with gr.Blocks(title="微信 AI Bot") as app:
        gr.Markdown(
            """
            # WeChat AI Bot
            ### 微信 AI 自动回复机器人 — 控制面板
            """,
            elem_classes="main-header",
        )

        # 收集所有 tab 的组件引用
        components = {}

        with gr.Tab("仪表盘"):
            comps = create_dashboard_tab(on_start=on_start, on_stop=on_stop)
            components["dashboard"] = comps

        with gr.Tab("日志"):
            comps = create_logs_tab()
            components["logs"] = comps

        with gr.Tab("联系人"):
            comps = create_contacts_tab()
            components["contacts"] = comps

        with gr.Tab("聊天记录"):
            comps = create_history_tab()
            components["history"] = comps

        with gr.Tab("配置"):
            comps = create_config_tab()
            components["config"] = comps

        with gr.Tab("表情包"):
            comps = create_emoji_tab()
            components["emojis"] = comps

        with gr.Tab("记忆"):
            comps = create_memories_tab()
            components["memories"] = comps

    return app, components, theme
