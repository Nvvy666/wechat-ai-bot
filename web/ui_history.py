"""
History Tab — 聊天记录 (纯文本文件视图)
"""
import gradio as gr
from datetime import datetime
from chat_store import get_context, list_contacts_with_chats, get_chat_path, get_stats
from database import get_contacts


def _all_names():
    names = set()
    for c in get_contacts(active_only=False):
        names.add(c["name"])
    for n in list_contacts_with_chats():
        names.add(n)
    return sorted(names)


def create_history_tab():
    gr.Markdown("## 聊天记录")

    names = _all_names()

    with gr.Row():
        contact_sel = gr.Dropdown(
            choices=names, value=names[0] if names else None,
            label="联系人", scale=2,
        )
        keyword_input = gr.Textbox(label="搜索关键词", placeholder="在聊天中搜索...", scale=2)
        with gr.Column(scale=1):
            btn_load = gr.Button("📄 加载", variant="primary")
            btn_today = gr.Button("📅 今天")

    info_md = gr.Markdown("👆 选择联系人加载聊天记录")

    chat_view = gr.Textbox(
        label="聊天记录",
        value="",
        lines=22, max_lines=500,
        interactive=False, autoscroll=True,
    )

    with gr.Row():
        line_slider = gr.Slider(label="显示行数", value=50, minimum=10, maximum=500, step=10, scale=2)
        btn_refresh = gr.Button("🔄 刷新", scale=1)

    # ---- Handlers ----
    def load_chat(contact, keyword, n_lines):
        if not contact:
            return "", "*请选择一个联系人*"
        ctx = get_context(contact, max_lines=int(n_lines))
        if not ctx:
            return f"*暂无聊天记录*\n\n文件路径: {get_chat_path(contact)}\nbot 运行后会自动生成。", f"📁 {contact}: 空"
        if keyword and keyword.strip():
            kw = keyword.strip().lower()
            lines = ctx.split("\n")
            filtered = [l for l in lines if kw in l.lower()]
            if filtered:
                ctx = "\n".join(filtered)
                info = f"🔍 **{keyword}** → 匹配 {len(filtered)}/{len(lines)} 行"
            else:
                ctx = f"(未找到包含「{keyword}」的内容)"
                info = f"🔍 **{keyword}** → 0 结果"
        else:
            stats = get_stats(contact)
            info = f"📁 **{contact}** | {stats.get('lines', 0)} 行 | {stats.get('size_kb', 0)} KB"
        return ctx, info

    def load_today(contact):
        if not contact:
            return "", "*请选择联系人*"
        d = datetime.now().strftime("%Y-%m-%d")
        ctx = get_context(contact, max_lines=200)
        if not ctx:
            return f"*{d} — 暂无记录*", f"📁 {contact}: 无"
        lines = ctx.split("\n")
        today = [l for l in lines if d in l]
        return "\n".join(today) if today else f"*{d} — 今天暂无消息*", f"📅 {contact} 今天: {len(today)} 条"

    btn_load.click(load_chat, [contact_sel, keyword_input, line_slider], [chat_view, info_md])
    btn_today.click(load_today, contact_sel, [chat_view, info_md])
    btn_refresh.click(load_chat, [contact_sel, keyword_input, line_slider], [chat_view, info_md])

    return {}
