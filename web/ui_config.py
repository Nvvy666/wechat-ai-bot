"""
Config Tab — LLM 配置管理 (cc-switch 风格)
预设卡片快速切换 + 编辑区折叠
"""
import gradio as gr
from database import (
    add_llm_config, get_llm_configs, set_active_llm_config,
    get_active_llm_config, delete_llm_config, update_llm_config,
    set_setting, add_log, get_setting,
)

PRESETS = {
    "DeepSeek V3":  ("https://api.deepseek.com/v1", "deepseek-chat", False),
    "DeepSeek R1":  ("https://api.deepseek.com/v1", "deepseek-reasoner", False),
    "千问 Plus":    ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", False),
    "千问 Max":     ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max", False),
    "千问 VL":      ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-vl-plus", True),
    "智谱 GLM-4":   ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", False),
    "智谱 GLM-4V":  ("https://open.bigmodel.cn/api/paas/v4", "glm-4v", True),
    "GPT-4o":       ("https://api.openai.com/v1", "gpt-4o", True),
    "GPT-4o-mini":  ("https://api.openai.com/v1", "gpt-4o-mini", False),
    "Kimi":         ("https://api.moonshot.cn/v1", "moonshot-v1-8k", False),
    "SiliconFlow":  ("https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V3", False),
    "Ollama":       ("http://localhost:11434/v1", "llama3", False),
    "腾讯云 DS":    ("https://api.lkeap.cloud.tencent.com/v1", "deepseek-chat", False),
}


def _detect_caps(model: str):
    m = model.lower()
    vl = any(k in m for k in ["vl", "vision", "gpt-4o", "gemini", "claude", "glm-4v", "qwen-vl", "visual"])
    return "vision" if vl else ""


def _ensure_default():
    if not get_llm_configs():
        from config import Config as C
        c = C()
        if c.llm_api_key and "your-api-key" not in c.llm_api_key:
            cid = add_llm_config("默认", c.llm_api_key, c.llm_base_url, c.llm_model, 400, 0.8)
            set_active_llm_config(cid)


def create_config_tab():
    _ensure_default()

    # ========== AI 模式 + Bot 名称 ==========
    with gr.Row():
        mode_dd = gr.Dropdown(
            choices=[("人格模式", "persona"), ("纯AI模式(自由发挥)", "pure")],
            value=get_setting("AI_MODE", "persona"),
            label="AI 回复模式", scale=2,
        )
        bot_name = gr.Textbox(
            label="机器人名称(群聊@用)",
            value=get_setting("BOT_NAME", ""),
            placeholder="@这个名称才会回复",
            scale=3,
        )
        top_save_btn = gr.Button("💾 保存", variant="primary", scale=1)

    # ========== 预设供应商 (cc-switch 卡片风格) ==========
    gr.Markdown("### 🚀 快速切换供应商")
    gr.Markdown("*点击预设自动填入下方编辑区，保存后生效*")

    # 分两行显示预设按钮
    preset_names = list(PRESETS.keys())
    row1_names = preset_names[:7]
    row2_names = preset_names[7:]

    preset_btns = {}
    with gr.Row():
        for name in row1_names:
            has_vl = "👁 " if PRESETS[name][2] else ""
            preset_btns[name] = gr.Button(f"{has_vl}{name}", size="sm", variant="secondary")
    with gr.Row():
        for name in row2_names:
            has_vl = "👁 " if PRESETS[name][2] else ""
            preset_btns[name] = gr.Button(f"{has_vl}{name}", size="sm", variant="secondary")

    # ========== 当前激活状态 ==========
    active = get_active_llm_config()
    active_md = gr.Markdown(
        f"**当前激活**: `{active['name']}` → 模型 `{active['model']}`"
        f"{' [支持识图]' if active.get('capabilities') and 'vision' in active['capabilities'] else ''}"
        if active else "**未配置**"
    )

    # ========== 配置编辑区 (折叠) ==========
    with gr.Accordion("⚙️ 编辑/新增配置", open=False):
        with gr.Row():
            cfg_name = gr.Textbox(
                label="配置名称", value=active["name"] if active else "",
                placeholder="给这个配置起个名", scale=2,
            )
            api_key = gr.Textbox(
                label="API Key", type="password",
                value=active["api_key"] if active and "your-api-key" not in str(active.get("api_key", "")) else "",
                placeholder="sk-...", scale=3,
            )
        with gr.Row():
            base_url = gr.Textbox(
                label="Base URL", value=active["base_url"] if active else "https://api.deepseek.com/v1",
                placeholder="https://api.xxx.com/v1", scale=2,
            )
            model = gr.Textbox(
                label="Model", value=active["model"] if active else "deepseek-chat",
                scale=2,
            )
        with gr.Row():
            mtok = gr.Number(label="Max Tokens", value=int(active.get("max_tokens", 400)) if active else 400, precision=0)
            temp = gr.Slider(label="Temperature", value=float(active.get("temperature", 0.8)) if active else 0.8, minimum=0, maximum=2)

        with gr.Row():
            save_btn = gr.Button("💾 保存为新配置", variant="primary", scale=2)
            test_btn = gr.Button("🔌 测试连接", scale=1)
            del_btn = gr.Button("🗑 删除配置", variant="stop", scale=1)

        # 已保存配置列表(紧凑)
        cfgs = get_llm_configs()
        cfg_names = [c["name"] for c in cfgs]
        cfg_sel = gr.Dropdown(
            label="已保存的配置 (选择即可切换)", choices=cfg_names,
            value=active["name"] if active else None,
        )

    # ========== 人格设置 (含角色克隆) ==========
    with gr.Accordion("🎭 人格设置", open=False):
        cur_persona = get_setting("PERSONALITY_DESC", "")

        gr.Markdown("### 快速设置")
        persona_box = gr.Textbox(
            label="人格描述",
            value=cur_persona,
            placeholder="用自然语言描述角色。例如：模仿前女友语气，傲娇又粘人，喜欢说「哼」「不理你了」但实际很关心对方...",
            lines=3,
        )
        persona_btn = gr.Button("💾 保存人格", variant="primary")

        gr.Markdown("---")
        gr.Markdown("### 🔮 角色克隆 (模仿特定人物)")
        gr.Markdown("*两种方式：上传聊天文件 或 粘贴样本 — AI 自动分析生成角色 Prompt*")

        clone_name = gr.Textbox(
            label="角色名称",
            placeholder="如: 傲娇前女友、毒舌闺蜜、温柔学姐...",
        )

        # 方式1: 上传文件
        gr.Markdown("**方式一：上传聊天记录文件**")
        gr.Markdown("*支持 WeChatMsg 导出的 txt/csv，或任何包含对话的文本文件*")
        clone_file = gr.File(label="上传聊天文件", file_types=[".txt", ".csv", ".json"])

        # 方式2: 粘贴文本
        gr.Markdown("**方式二：粘贴聊天样本**")
        clone_samples = gr.Textbox(
            label="聊天样本",
            placeholder="粘贴这个人的真实聊天记录，一行一条。\n如:\n你在干嘛呀 怎么不回我\n没有啊我刚在忙\n哼 每次都这样说 不理你了\n...",
            lines=5,
        )

        clone_desc = gr.Textbox(
            label="补充描述 (可选)",
            placeholder="补充性格特点、口头禅等...\n如: 口是心非，嘴上说随便但其实很在意，喜欢用「哼」「切」开头",
            lines=2,
        )

        with gr.Row():
            clone_btn = gr.Button("🪄 分析生成", variant="primary", scale=2)
            clone_use_btn = gr.Button("✅ 应用此角色", variant="secondary", scale=1)

        clone_result = gr.Textbox(
            label="生成的 System Prompt (可手动修改)",
            placeholder="点击「分析生成」后这里会显示 AI 生成的完整角色 Prompt...",
            lines=8, interactive=True,
        )

    # ========== 回复策略 ==========
    with gr.Accordion("⏱ 回复策略", open=False):
        from config import config as cfg
        with gr.Row():
            dmin = gr.Number(label="最小延迟(s)", value=cfg.reply_min_delay)
            dmax = gr.Number(label="最大延迟(s)", value=cfg.reply_max_delay)
            skip_p = gr.Slider(label="跳过率", value=cfg.skip_probability, minimum=0, maximum=0.5)
            cooldown = gr.Number(label="冷却(s)", value=cfg.reply_cooldown)
        reply_btn = gr.Button("💾 保存策略", variant="primary")

    # ========== 识图设置 ==========
    with gr.Accordion("🔍 识图设置", open=False):
        cur_vm = get_setting("VISION_MODE", "lightweight")
        with gr.Row():
            vm_dd = gr.Dropdown(
                label="识别模式",
                choices=[
                    ("轻量模式 (OCR→普通LLM, 免费)", "lightweight"),
                    ("强力模式 (视觉大模型看图, 消耗额度)", "vision"),
                    ("自动 (有视觉模型自动用)", "auto"),
                ],
                value=cur_vm,
                scale=2,
            )
            vm_btn = gr.Button("💾 保存", scale=1)

    # ========== Handlers ==========

    # 预设按钮 → 填入编辑区 (用闭包捕获 name)
    for pname in preset_names:
        url, mdl, has_vl = PRESETS[pname]

        def make_handler(n, u, m):
            def handler():
                caps_str = " [支持识图]" if PRESETS[n][2] else ""
                return u, m, f"**预设**: `{n}` → 模型 `{m}`{caps_str}"
            return handler

        preset_btns[pname].click(
            make_handler(pname, url, mdl),
            outputs=[base_url, model, active_md],
        ).then(fn=lambda n=pname: gr.Info(f"已选择预设: {n}", duration=2))

    # 保存模式+名称
    def save_top(mode, bname):
        v = "pure" if "pure" in str(mode) else "persona"
        set_setting("AI_MODE", v)
        set_setting("BOT_NAME", bname or "")
        add_log("INFO", f"Mode: {v}, Bot: {bname}", "system")
        raise gr.Info(f"已保存: 模式={v}, 名称={bname or '(空)'}", duration=3)

    top_save_btn.click(save_top, [mode_dd, bot_name])

    # 保存配置
    def do_save(name, key, url, mdl, mt, tp):
        if not name or not key:
            raise gr.Warning("名称和 API Key 不能为空", duration=3)
        caps = _detect_caps(mdl)
        cid = add_llm_config(name.strip(), key.strip(), url.strip(), mdl.strip(), int(mt), float(tp), caps)
        set_active_llm_config(cid)
        add_log("INFO", f"Config saved: {name}", "system")
        # 刷新列表
        new_cfgs = get_llm_configs()
        new_names = [c["name"] for c in new_cfgs]
        caps_str = " [识图]" if caps else ""
        return (
            gr.Dropdown(choices=new_names, value=name),
            f"**当前激活**: `{name}` → 模型 `{mdl}`{caps_str}",
        )

    save_btn.click(
        do_save, [cfg_name, api_key, base_url, model, mtok, temp],
        [cfg_sel, active_md],
    ).then(fn=lambda: gr.Info("配置已保存并激活", duration=3))

    # 切换配置
    def do_switch(name):
        if not name:
            raise gr.Warning("请选择一个配置", duration=2)
        for c in get_llm_configs():
            if c["name"] == name:
                set_active_llm_config(c["id"])
                caps = c.get("capabilities", "")
                caps_str = " [识图]" if "vision" in caps else ""
                add_log("INFO", f"Switched: {name}", "system")
                # 填入编辑区
                return (
                    c["name"], c["api_key"], c["base_url"], c["model"],
                    int(c.get("max_tokens", 400)), float(c.get("temperature", 0.8)),
                    f"**当前激活**: `{name}` → 模型 `{c['model']}`{caps_str}",
                )
        return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip()

    cfg_sel.change(
        do_switch, cfg_sel,
        [cfg_name, api_key, base_url, model, mtok, temp, active_md],
    ).then(fn=lambda: gr.Info("已切换配置", duration=2))

    # 测试连接
    def do_test(name, key, url, mdl):
        if not key:
            raise gr.Warning("需要 API Key", duration=2)
        from llm_client import LLMClient
        # 临时设置环境变量测试
        import os
        old_key = os.environ.get("LLM_API_KEY", "")
        old_url = os.environ.get("LLM_BASE_URL", "")
        os.environ["LLM_API_KEY"] = key
        os.environ["LLM_BASE_URL"] = url
        os.environ["LLM_MODEL"] = mdl
        try:
            c = LLMClient()
            c.url = url.rstrip("/") + "/v1/chat/completions" if not url.endswith("/chat/completions") else url
            c.model = mdl
            c.api_key = key
            ok, msg = c.test_connection()
            if ok:
                raise gr.Info(f"连接成功: {msg}", duration=3)
            else:
                raise gr.Warning(f"连接失败: {msg}", duration=5)
        except gr.Info:
            raise
        except gr.Warning:
            raise
        except Exception as e:
            raise gr.Warning(f"错误: {str(e)[:100]}", duration=5)

    test_btn.click(do_test, [cfg_name, api_key, base_url, model])

    # 删除配置
    def do_delete(name):
        cs = get_llm_configs()
        if len(cs) <= 1:
            raise gr.Warning("至少保留一个配置", duration=2)
        for c in cs:
            if c["name"] == name:
                delete_llm_config(c["id"])
                add_log("INFO", f"Deleted: {name}", "system")
                break
        new_cs = get_llm_configs()
        new_names = [c["name"] for c in new_cs]
        act = get_active_llm_config()
        return (
            gr.Dropdown(choices=new_names, value=act["name"] if act else None),
            f"**当前激活**: `{act['name']}` → 模型 `{act['model']}`" if act else "未配置",
        )

    del_btn.click(do_delete, cfg_sel, [cfg_sel, active_md]).then(
        fn=lambda: gr.Info("已删除配置", duration=2)
    )

    # 保存人格
    def save_persona(t):
        set_setting("PERSONALITY_DESC", t)
        add_log("INFO", "Personality saved", "system")
        raise gr.Info("人格已保存", duration=2)
    persona_btn.click(save_persona, persona_box)

    # 角色克隆
    def do_clone(name, file, samples, desc):
        # 合并所有文本来源
        all_text = ""
        # 1. 从上传文件读取
        if file is not None:
            try:
                filepath = file.name if hasattr(file, 'name') else str(file)
                with open(filepath, "r", encoding="utf-8") as f:
                    all_text += f.read()[:5000]
            except UnicodeDecodeError:
                try:
                    with open(filepath, "r", encoding="gbk") as f:
                        all_text += f.read()[:5000]
                except:
                    raise gr.Warning("无法读取文件编码，请用 UTF-8 或 GBK", duration=3)
            except Exception as e:
                raise gr.Warning(f"读取文件失败: {e}", duration=3)

        # 2. 粘贴的样本
        if samples and samples.strip():
            if all_text:
                all_text += "\n\n"
            all_text += samples.strip()

        if not all_text.strip() and not desc.strip():
            raise gr.Warning("请上传文件、粘贴样本、或填写描述", duration=3)

        from personality.persona_cloner import persona_cloner
        from llm_client import LLMClient
        try:
            full_desc = desc.strip() if desc.strip() else "从聊天样本中自动分析"
            if name.strip():
                full_desc = f"角色名: {name.strip()}\n" + full_desc

            c = LLMClient()
            result = persona_cloner.analyze(
                lambda msgs, max_tokens=1000, temperature=0.8: c.chat(msgs, max_tokens=max_tokens, temperature=temperature),
                full_desc,
                all_text.strip(),
            )
            final_prompt = persona_cloner.build_final_prompt(result)
            return final_prompt
        except Exception as e:
            raise gr.Warning(f"生成失败: {str(e)[:120]}", duration=5)

    def do_use_clone(prompt):
        if not prompt.strip():
            raise gr.Warning("先生成角色 Prompt", duration=2)
        set_setting("PERSONALITY_DESC", prompt.strip())
        add_log("INFO", "Cloned persona applied", "system")
        return prompt.strip()

    clone_btn.click(do_clone, [clone_name, clone_file, clone_samples, clone_desc], clone_result)
    clone_use_btn.click(do_use_clone, clone_result, persona_box).then(
        fn=lambda: gr.Info("角色已应用！", duration=2)
    )

    # 保存策略
    def save_reply(dmin_v, dmax_v, skip_v, cool_v):
        for k, v in [("REPLY_MIN_DELAY", str(dmin_v)), ("REPLY_MAX_DELAY", str(dmax_v)),
                     ("SKIP_REPLY_PROBABILITY", str(skip_v)), ("REPLY_COOLDOWN", str(int(cool_v)))]:
            set_setting(k, v)
        raise gr.Info("回复策略已保存", duration=2)
    reply_btn.click(save_reply, [dmin, dmax, skip_p, cooldown])

    # 保存识图
    def save_vm(m):
        v = m.strip()
        set_setting("VISION_MODE", v)
        add_log("INFO", f"Vision: {v}", "system")
        raise gr.Info(f"识图模式: {v}", duration=2)
    vm_btn.click(save_vm, vm_dd)

    return {}
