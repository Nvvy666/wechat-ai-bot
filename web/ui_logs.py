"""
Logs Tab — 实时日志 + 日期筛选
"""
import gradio as gr
from database import get_logs


def _load_logs(date_from="", date_to="", level=None, source=None):
    logs = get_logs(limit=300, level=level, date_from=date_from, date_to=date_to)
    lines = []
    for log in logs:
        src = log.get("source", "system")
        if source and source != "ALL" and src != source:
            continue
        ts = log["created_at"][:19] if log.get("created_at") else ""
        lv = log.get("level", "INFO")
        msg = log.get("message", "")
        lines.append(f"[{ts}] [{lv}] [{src}] {msg}")
    return "\n".join(lines[-150:]) if lines else "(暂无日志)"


def create_logs_tab():
    gr.Markdown("## 运行日志")

    with gr.Row():
        date_from = gr.Textbox(label="日期从 (YYYY-MM-DD)", placeholder="2026-01-01", scale=2)
        date_to = gr.Textbox(label="日期到", placeholder="2026-12-31", scale=2)
        level_filter = gr.Dropdown(
            choices=["ALL", "DEBUG", "INFO", "WARN", "ERROR"],
            value="ALL", label="级别", scale=1,
        )
        source_filter = gr.Dropdown(
            choices=["ALL", "system", "bot", "wechat", "llm"],
            value="ALL", label="来源", scale=1,
        )

    with gr.Row():
        btn_refresh = gr.Button("刷新", variant="primary")
        btn_today = gr.Button("今天")
        btn_clear = gr.Button("全部")

    log_output = gr.Textbox(
        label="日志",
        value=_load_logs(),
        lines=22, max_lines=200,
        interactive=False, autoscroll=True,
    )

    def refresh(df, dt, lv, src):
        lv_n = None if lv == "ALL" else lv
        src_n = None if src == "ALL" else src
        return _load_logs(df, dt, lv_n, src_n)

    def today():
        from datetime import datetime
        d = datetime.now().strftime("%Y-%m-%d")
        return d, d, _load_logs(d, d)

    def clear():
        return "", "", _load_logs()

    btn_refresh.click(refresh, inputs=[date_from, date_to, level_filter, source_filter], outputs=log_output)
    btn_today.click(today, outputs=[date_from, date_to, log_output])
    btn_clear.click(clear, outputs=[date_from, date_to, log_output])

    return {}
