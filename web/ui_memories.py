"""
Memories Tab — AI 记忆管理
格式: 联系人: 事实，可编辑
"""
import gradio as gr
from database import get_memories, add_memory, delete_memory, add_log
from chat_store import list_contacts_with_chats
from database import get_contacts


def _all_contacts():
    """所有有记录的联系人"""
    names = set()
    for c in get_contacts(active_only=False):
        names.add(c["name"])
    for n in list_contacts_with_chats():
        names.add(n)
    return sorted(names)


def _mem_text(contact_filter: str = None):
    mems = get_memories(contact_filter if contact_filter else None)
    lines = []
    for m in mems:
        lines.append(f"[{m['id']}] {m['contact_name']}: {m['fact']}")
    return "\n".join(lines) if lines else "(暂无记忆)"


def create_memories_tab():
    gr.Markdown("## 记忆管理")
    gr.Markdown("AI 自动通过 `[MEMORY:事实]` 标记保存记忆，也可以手动编辑。")

    # 筛选
    contact_choices = ["全部"] + _all_contacts()
    with gr.Row():
        mem_filter = gr.Dropdown(
            choices=contact_choices, value="全部",
            label="筛选联系人", scale=3,
        )
        refresh_btn = gr.Button("🔄 刷新", scale=1)

    # 编辑区
    mem_editor = gr.Textbox(
        label="记忆内容（格式: 联系人: 事实，一行一条。可直接编辑后保存）",
        value=_mem_text(),
        lines=15,
        placeholder="张三: 喜欢喝咖啡\n李四: 在腾讯工作\n...",
    )
    with gr.Row():
        save_all_btn = gr.Button("💾 保存修改", variant="primary", scale=2)
        del_selected_btn = gr.Button("🗑 清空筛选的联系人", variant="stop", scale=1)

    # 快速添加
    gr.Markdown("### 快速添加")
    with gr.Row():
        add_contact = gr.Dropdown(
            label="联系人",
            choices=_all_contacts(),
            allow_custom_value=True,
            scale=2,
        )
        add_fact = gr.Textbox(label="事实", placeholder="例如：喜欢喝咖啡", scale=3)
        add_btn = gr.Button("➕ 添加", scale=1)

    result = gr.Textbox(label="操作结果", interactive=False)

    # ---- Handlers ----
    def do_filter(sel):
        cf = None if sel == "全部" else sel
        return _mem_text(cf)

    def do_save_all(text):
        if not text or text.strip() == "(暂无记忆)":
            return _mem_text(), "已清空"
        # 先删全部，再逐行添加
        mems = get_memories()
        for m in mems:
            delete_memory(m["id"])
        count = 0
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # 去掉 [ID] 前缀
            if line.startswith("[") and "] " in line:
                line = line.split("] ", 1)[1]
            if ": " in line or "：" in line:
                sep = ": " if ": " in line else "："
                contact, fact = line.split(sep, 1)
                contact, fact = contact.strip(), fact.strip()
                if contact and fact:
                    add_memory(contact, fact)
                    count += 1
        add_log("INFO", f"Memories saved: {count} records", "system")
        return _mem_text(), f"已保存 {count} 条记忆"

    def do_clear_filtered(sel):
        cf = None if sel == "全部" else sel
        if cf is None:
            return _mem_text(), "请先筛选联系人再清空"
        mems = get_memories(cf)
        for m in mems:
            delete_memory(m["id"])
        add_log("INFO", f"Memories cleared for: {cf}", "system")
        return _mem_text(), f"已清空 {cf} 的 {len(mems)} 条记忆"

    def do_add(contact, fact):
        if not contact or not fact:
            return _mem_text(), "填写联系人和事实"
        cname = contact.strip()
        add_memory(cname, fact.strip())
        add_log("INFO", f"Memory: {cname}", "system")
        return _mem_text(), f"已添加: {cname} — {fact[:30]}"

    mem_filter.change(do_filter, mem_filter, mem_editor)
    refresh_btn.click(lambda sel: _mem_text(None if sel == "全部" else sel), mem_filter, mem_editor)
    save_all_btn.click(do_save_all, mem_editor, [mem_editor, result]).then(
        fn=lambda: gr.Info("记忆已保存", duration=2)
    )
    del_selected_btn.click(do_clear_filtered, mem_filter, [mem_editor, result])
    add_btn.click(do_add, [add_contact, add_fact], [mem_editor, result]).then(
        fn=lambda: gr.Info("记忆已添加", duration=2)
    )

    return {}
