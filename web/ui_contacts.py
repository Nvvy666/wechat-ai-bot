"""
Contacts Tab — 管理监控的联系人和群聊
"""
import gradio as gr
from database import get_contacts, add_contact, remove_contact, set_contact_active, add_log


def create_contacts_tab():
    gr.Markdown("## 联系人管理")

    with gr.Row():
        with gr.Column(scale=2):
            name_input = gr.Textbox(label="名称（微信显示名）", placeholder="输入联系人或群聊名称")
        with gr.Column(scale=1):
            type_selector = gr.Dropdown(
                choices=["contact", "group"],
                value="contact",
                label="类型",
            )
        with gr.Column(scale=1):
            btn_add = gr.Button("添加", variant="primary")

    contacts_table = gr.Dataframe(
        headers=["ID", "名称", "类型", "状态", "添加时间"],
        datatype=["number", "str", "str", "str", "str"],
        label="监控列表",
        interactive=False,
    )

    with gr.Row():
        remove_name_input = gr.Textbox(label="要删除的名称", scale=2)
        btn_remove = gr.Button("删除", variant="stop", scale=1)

    with gr.Row():
        toggle_name = gr.Textbox(label="名称", scale=2)
        toggle_action = gr.Dropdown(
            choices=["enable", "disable"],
            value="enable",
            label="操作",
            scale=1,
        )
        btn_toggle = gr.Button("切换状态", scale=1)

    def refresh_table():
        contacts = get_contacts(active_only=False)
        rows = []
        for c in contacts:
            status = "启用" if c["is_active"] else "停用"
            rows.append([c["id"], c["name"], c["type"], status, c["created_at"][:19] if c["created_at"] else ""])
        return rows

    def do_add(name, ctype):
        if not name.strip():
            return refresh_table(), "名称不能为空"
        if add_contact(name.strip(), ctype):
            add_log("INFO", f"Added {ctype}: {name}", "system")
            return refresh_table(), f"已添加: {name}"
        return refresh_table(), f"添加失败（可能已存在）: {name}"

    def do_remove(name):
        if not name.strip():
            return refresh_table(), "名称不能为空"
        remove_contact(name.strip())
        add_log("INFO", f"Removed: {name}", "system")
        return refresh_table(), f"已删除: {name}"

    def do_toggle(name, action):
        if not name.strip():
            return refresh_table(), "名称不能为空"
        set_contact_active(name.strip(), action == "enable")
        return refresh_table(), f"已{'启用' if action == 'enable' else '停用'}: {name}"

    btn_add.click(do_add, inputs=[name_input, type_selector], outputs=[contacts_table, gr.Textbox(visible=False)])
    btn_remove.click(do_remove, inputs=[remove_name_input], outputs=[contacts_table, gr.Textbox(visible=False)])
    btn_toggle.click(do_toggle, inputs=[toggle_name, toggle_action], outputs=[contacts_table, gr.Textbox(visible=False)])

    return {
        "table": contacts_table,
        "refresh_fn": refresh_table,
    }
