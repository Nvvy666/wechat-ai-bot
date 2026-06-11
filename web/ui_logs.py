"""
Logs Tab — 实时日志流
"""
import gradio as gr
from database import get_logs, add_log


def create_logs_tab():
    gr.Markdown("## 运行日志")

    with gr.Row():
        level_filter = gr.Dropdown(
            choices=["ALL", "INFO", "WARN", "ERROR"],
            value="ALL",
            label="日志级别",
            scale=1,
        )
        source_filter = gr.Dropdown(
            choices=["ALL", "system", "bot", "wechat", "llm"],
            value="ALL",
            label="来源",
            scale=1,
        )
        refresh_logs_btn = gr.Button("刷新", scale=1)

    log_output = gr.Textbox(
        label="日志输出",
        lines=25,
        max_lines=100,
        interactive=False,
        autoscroll=True,
    )

    def refresh_logs(level, source):
        level = None if level == "ALL" else level
        logs = get_logs(limit=200, level=level)
        lines = []
        for log in logs:
            src = log.get("source", "system")
            if source != "ALL" and src != source:
                continue
            ts = log["created_at"][:19] if log.get("created_at") else ""
            lv = log.get("level", "INFO")
            msg = log.get("message", "")
            lines.append(f"[{ts}] [{lv}] [{src}] {msg}")
        return "\n".join(lines[-100:])

    refresh_logs_btn.click(
        refresh_logs,
        inputs=[level_filter, source_filter],
        outputs=log_output,
    )

    # Auto-refresh trigger
    def auto_refresh():
        return refresh_logs("ALL", "ALL")

    return {
        "output": log_output,
        "refresh": refresh_logs_btn,
        "level_filter": level_filter,
        "source_filter": source_filter,
        "auto_refresh_fn": auto_refresh,
    }
