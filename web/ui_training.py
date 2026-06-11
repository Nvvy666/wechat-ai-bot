"""
Training Tab — 上传聊天记录、生成风格档案、管理 few-shot
"""
import os
import json
import gradio as gr

from database import (
    create_profile, get_profiles, update_profile, delete_profile,
    set_active_profile, get_active_profile, get_fewshots,
    add_fewshot, delete_fewshot, clear_fewshots, add_log,
)
from personality.trainer import ChatAnalyzer


def create_training_tab():
    gr.Markdown("## 人格训练")

    with gr.Tab("风格档案"):
        with gr.Row():
            with gr.Column(scale=2):
                profile_name = gr.Textbox(label="档案名称", placeholder="我的风格")
                profile_desc = gr.Textbox(label="描述", lines=2, placeholder="从聊天记录中提取的风格")
            with gr.Column(scale=1):
                btn_create_profile = gr.Button("创建档案", variant="primary")
                profiles_list = gr.Dropdown(
                    label="现有档案",
                    choices=[f"{p['id']}: {p['name']}" for p in get_profiles()]
                )

        with gr.Row():
            btn_activate = gr.Button("激活此档案")
            btn_delete_profile = gr.Button("删除档案", variant="stop")

        profile_detail = gr.JSON(label="档案详情")

    with gr.Tab("上传聊天记录"):
        gr.Markdown("上传 WeChatMsg 导出的聊天记录，自动分析你的说话风格")
        your_name_input = gr.Textbox(label="你的微信昵称", placeholder="输入你在微信中的显示名")
        file_upload = gr.File(label="聊天记录文件 (.txt / .csv / .json)")
        btn_analyze = gr.Button("分析风格", variant="primary")
        analysis_result = gr.Textbox(label="分析结果", lines=10, interactive=False)
        analysis_traits = gr.JSON(label="风格特征")
        btn_save_profile = gr.Button("保存为风格档案", variant="primary")

    with gr.Tab("Few-Shot 管理"):
        with gr.Row():
            user_msg_input = gr.Textbox(label="对方消息", placeholder="对方说了什么")
            bot_reply_input = gr.Textbox(label="你的回复", placeholder="你应该怎么回复")
            scenario_input = gr.Textbox(label="场景（可选）")
        btn_add_fewshot = gr.Button("添加示例", variant="primary")
        btn_clear_fewshots = gr.Button("清空当前档案的示例", variant="stop")

        fewshot_table = gr.Dataframe(
            headers=["ID", "场景", "对方消息", "你的回复", "使用次数"],
            label="Few-Shot 示例库",
            interactive=False,
        )
        with gr.Row():
            fewshot_id_input = gr.Number(label="要删除的 ID", precision=0)
            btn_delete_fewshot = gr.Button("删除", variant="stop")

    # ---- State ----
    _last_analysis = {}

    # ---- Handlers ----

    def refresh_profiles():
        profiles = get_profiles()
        choices = [f"{p['id']}: {p['name']}" for p in profiles]
        return gr.Dropdown(choices=choices)

    def do_create_profile(name, desc):
        if not name:
            return refresh_profiles(), "名称不能为空"
        pid = create_profile(name, desc)
        add_log("INFO", f"Created profile: {name} (id={pid})", "system")
        return refresh_profiles(), f"已创建: {name}"

    def do_activate(selection):
        if not selection:
            return "请先选择档案"
        pid = int(selection.split(":")[0])
        set_active_profile(pid)
        profile = get_active_profile()
        return profile if profile else "激活失败"

    def do_delete_profile(selection):
        if not selection:
            return refresh_profiles(), "请先选择"
        pid = int(selection.split(":")[0])
        delete_profile(pid)
        return refresh_profiles(), "已删除"

    def do_analyze(your_name, file):
        nonlocal _last_analysis
        if not your_name or not file:
            return "", {}, "请填写昵称并上传文件"
        try:
            analyzer = ChatAnalyzer(your_name)
            msgs, traits = analyzer.analyze_file(file.name)
            _last_analysis = {"msgs": msgs, "traits": traits}
            return traits.to_description(), traits.to_dict(), f"分析完成！提取了 {len(msgs)} 条你的发言"
        except Exception as e:
            return str(e), {}, "分析失败"

    def do_save_profile():
        nonlocal _last_analysis
        if not _last_analysis:
            return refresh_profiles(), "请先分析聊天记录"
        traits = _last_analysis["traits"]
        msgs = _last_analysis["msgs"]
        desc = traits.to_description()
        pid = create_profile(
            name=f"提取的风格 {len(get_profiles())+1}",
            description=desc,
            traits=traits.to_dict(),
        )
        # 自动添加 few-shot
        for msg in msgs[:20]:
            if len(msg) > 3:
                add_fewshot(pid, "（日常聊天）", msg, source="auto_extracted")
        add_log("INFO", f"Auto-created profile from chat analysis (id={pid})", "system")
        return refresh_profiles(), f"已保存！ID={pid}"

    def refresh_fewshots():
        profile = get_active_profile()
        rows = []
        if profile:
            fshots = get_fewshots(profile["id"], limit=50)
            for fs in fshots:
                rows.append([fs["id"], fs.get("scenario", ""), fs["user_msg"], fs["bot_reply"], fs.get("usage_count", 0)])
        return rows

    def do_add_fewshot(user_msg, bot_reply, scenario):
        profile = get_active_profile()
        if not profile:
            return refresh_fewshots(), "没有激活的风格档案"
        if not user_msg or not bot_reply:
            return refresh_fewshots(), "消息不能为空"
        add_fewshot(profile["id"], user_msg, bot_reply, scenario)
        return refresh_fewshots(), "已添加"

    def do_delete_fewshot(fid):
        if fid:
            delete_fewshot(int(fid))
        return refresh_fewshots()

    def do_clear_fewshots():
        profile = get_active_profile()
        if profile:
            clear_fewshots(profile["id"])
        return refresh_fewshots()

    # ---- Bindings ----
    btn_create_profile.click(do_create_profile, [profile_name, profile_desc], outputs=[profiles_list, gr.Textbox(visible=False)])
    btn_activate.click(do_activate, inputs=profiles_list, outputs=profile_detail)
    btn_delete_profile.click(do_delete_profile, inputs=profiles_list, outputs=[profiles_list, gr.Textbox(visible=False)])
    btn_analyze.click(do_analyze, inputs=[your_name_input, file_upload], outputs=[analysis_result, analysis_traits, gr.Textbox(visible=False)])
    btn_save_profile.click(do_save_profile, outputs=[profiles_list, gr.Textbox(visible=False)])
    btn_add_fewshot.click(do_add_fewshot, inputs=[user_msg_input, bot_reply_input, scenario_input], outputs=[fewshot_table, gr.Textbox(visible=False)])
    btn_delete_fewshot.click(do_delete_fewshot, inputs=fewshot_id_input, outputs=fewshot_table)
    btn_clear_fewshots.click(do_clear_fewshots, outputs=fewshot_table)

    return {
        "profiles_list": profiles_list,
    }
