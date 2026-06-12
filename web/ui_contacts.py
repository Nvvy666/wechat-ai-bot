"""
Contacts Tab — 联系人管理
简化: 表格折叠，主界面只留操作区
"""
import gradio as gr
from database import get_contacts, add_contact, remove_contact, set_contact_active, add_log


def _contact_choices():
    contacts = get_contacts(active_only=False)
    return [f"{c['name']} ({c['type']})" for c in contacts]


def _contact_rows():
    contacts = get_contacts(active_only=False)
    rows = []
    for i, c in enumerate(contacts, 1):
        status = "✅ 启用" if c["is_active"] else "⏸ 停用"
        rows.append([i, c["id"], c["name"], c["type"], status])
    if not rows:
        rows = [["", "", "(空)", "", ""]]
    return rows


def create_contacts_tab():
    gr.Markdown("## 联系人管理")

    # ---- 添加 ----
    with gr.Row():
        name_input = gr.Textbox(label="名称（微信显示名）", placeholder="输入联系人或群聊名称", scale=3)
        type_selector = gr.Dropdown(choices=["contact (联系人)", "group (群聊)"], value="contact (联系人)", label="类型", scale=1)
        btn_add = gr.Button("➕ 添加", variant="primary", scale=1)

    # ---- 快捷操作 ----
    gr.Markdown("### 管理")
    with gr.Row():
        contact_sel = gr.Dropdown(label="选择联系人", choices=_contact_choices(), scale=3)
        btn_enable = gr.Button("✅ 启用", scale=1)
        btn_disable = gr.Button("⏸ 停用", scale=1)
        btn_remove = gr.Button("🗑 删除", variant="stop", scale=1)

    # ---- 列表折叠 ----
    with gr.Accordion("📋 完整列表", open=False):
        contacts_table = gr.Dataframe(
            headers=["#", "DB_ID", "名称", "类型", "状态"],
            value=_contact_rows(), label="监控列表", interactive=False,
        )

    # ---- Handlers ----
    def refresh_all():
        return _contact_rows(), gr.Dropdown(choices=_contact_choices())

    def do_add(name, ctype):
        ct = "group" if "group" in ctype else "contact"
        if not name.strip():
            raise gr.Warning("名称不能为空", duration=2)
        if add_contact(name.strip(), ct):
            add_log("INFO", f"Added {ct}: {name}", "system")
            raise gr.Info(f"已添加: {name}", duration=2)
        raise gr.Warning(f"已存在: {name}", duration=2)

    def do_enable(sel):
        name = sel.rsplit(" (", 1)[0].strip() if sel else ""
        if not name: raise gr.Warning("请选择一个联系人", duration=2)
        set_contact_active(name, True)
        t, s = refresh_all(); return t, s

    def do_disable(sel):
        name = sel.rsplit(" (", 1)[0].strip() if sel else ""
        if not name: raise gr.Warning("请选择一个联系人", duration=2)
        set_contact_active(name, False)
        t, s = refresh_all(); return t, s

    def do_remove(sel):
        name = sel.rsplit(" (", 1)[0].strip() if sel else ""
        if not name: raise gr.Warning("请选择一个联系人", duration=2)
        remove_contact(name)
        add_log("INFO", f"Removed: {name}", "system")
        t, s = refresh_all(); return t, s

    btn_add.click(do_add, [name_input, type_selector], [contacts_table, contact_sel])
    btn_enable.click(do_enable, contact_sel, [contacts_table, contact_sel]).then(
        fn=lambda: gr.Info("已启用", duration=2)
    )
    btn_disable.click(do_disable, contact_sel, [contacts_table, contact_sel]).then(
        fn=lambda: gr.Info("已停用", duration=2)
    )
    btn_remove.click(do_remove, contact_sel, [contacts_table, contact_sel]).then(
        fn=lambda: gr.Info("已删除", duration=2)
    )

    return {"table": contacts_table, "refresh_fn": refresh_all}
