"""
History Tab — 浏览和搜索聊天记录
"""
import gradio as gr
from database import get_messages, search_messages, get_contacts


def create_history_tab():
    gr.Markdown("## 聊天记录")

    with gr.Row():
        all_contacts = [""] + [c["name"] for c in get_contacts(active_only=False)]
        contact_filter = gr.Dropdown(
            choices=all_contacts,
            value="",
            label="按联系人筛选",
            scale=2,
            allow_custom_value=True,
        )
        search_input = gr.Textbox(label="搜索关键词", placeholder="输入关键词搜索", scale=2)
        btn_search = gr.Button("搜索", variant="primary", scale=1)
        btn_refresh = gr.Button("刷新", scale=1)

    history_table = gr.Dataframe(
        headers=["时间", "联系人", "发送者", "内容", "方向"],
        datatype=["str", "str", "str", "str", "str"],
        label="聊天记录",
        interactive=False,
        wrap=True,
        column_widths=["15%", "10%", "10%", "55%", "10%"],
    )

    def load_contacts():
        contacts = get_contacts(active_only=False)
        names = [c["name"] for c in contacts]
        return gr.Dropdown(choices=[""] + names, value="")

    def refresh(contact, keyword):
        if keyword:
            msgs = search_messages(keyword, limit=200)
        else:
            msgs = get_messages(contact if contact else None, limit=200)
        rows = []
        for m in msgs:
            direction = "收到" if m["role"] == "incoming" else "发出"
            rows.append([
                m["created_at"][:19] if m["created_at"] else "",
                m["contact_name"],
                m["sender"],
                m["content"][:200],
                direction,
            ])
        return rows

    btn_search.click(refresh, inputs=[contact_filter, search_input], outputs=history_table)
    btn_refresh.click(lambda: refresh("", ""), outputs=history_table)

    return {
        "table": history_table,
        "contact_filter": contact_filter,
    }
