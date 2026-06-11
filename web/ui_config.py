"""
Config Tab — API配置、回复策略、人格档案切换
"""
import gradio as gr
from database import set_setting, get_all_settings
from config import config
from llm_client import LLMClient


def create_config_tab():
    gr.Markdown("## 系统配置")

    with gr.Tab("LLM API"):
        with gr.Column():
            api_key_input = gr.Textbox(
                label="API Key",
                value=config.llm_api_key,
                type="password",
                placeholder="sk-xxx",
            )
            base_url_input = gr.Textbox(
                label="Base URL",
                value=config.llm_base_url,
                placeholder="https://api.deepseek.com/v1",
            )
            model_input = gr.Textbox(
                label="Model",
                value=config.llm_model,
                placeholder="deepseek-chat",
            )
            max_tokens_input = gr.Number(
                label="Max Tokens",
                value=config.llm_max_tokens,
                minimum=50,
                maximum=4000,
                step=50,
            )
            btn_save_llm = gr.Button("保存 LLM 配置", variant="primary")
            btn_test_llm = gr.Button("测试连接")
            llm_test_result = gr.Textbox(label="测试结果", interactive=False)

    with gr.Tab("回复策略"):
        with gr.Column():
            delay_min = gr.Number(label="最小回复延迟(秒)", value=config.reply_min_delay, minimum=0.1, step=0.5)
            delay_max = gr.Number(label="最大回复延迟(秒)", value=config.reply_max_delay, minimum=0.5, step=0.5)
            skip_prob = gr.Slider(label="随机跳过概率", value=config.skip_probability, minimum=0, maximum=0.5, step=0.01)
            cooldown = gr.Number(label="回复冷却时间(秒)", value=config.reply_cooldown, minimum=5, step=5)
            personality_text = gr.Textbox(
                label="默认人格描述",
                value=config.personality_profile,
                lines=3,
                placeholder="描述你的说话风格...",
            )
            btn_save_reply = gr.Button("保存回复策略", variant="primary")

    with gr.Tab("人格档案"):
        from database import get_profiles, set_active_profile, get_active_profile
        profiles = get_profiles()
        choices = [f"{p['id']}: {p['name']}" for p in profiles]
        active = get_active_profile()

        profile_selector = gr.Dropdown(
            label="激活的人格档案",
            choices=choices,
            value=f"{active['id']}: {active['name']}" if active else None,
        )
        btn_activate_profile = gr.Button("切换档案", variant="primary")
        profile_info = gr.Textbox(label="档案详情", interactive=False, lines=5)

    # ---- Handlers ----

    def save_llm(api_key, base_url, model, max_tokens):
        set_setting("LLM_API_KEY", api_key)
        set_setting("LLM_BASE_URL", base_url)
        set_setting("LLM_MODEL", model)
        set_setting("LLM_MAX_TOKENS", str(int(max_tokens)))
        return "已保存"

    def test_llm():
        client = LLMClient()
        ok, msg = client.test_connection()
        return f"{'OK' if ok else 'FAIL'}: {msg}"

    def save_reply(dmin, dmax, skip, cool, personality):
        set_setting("REPLY_MIN_DELAY", str(dmin))
        set_setting("REPLY_MAX_DELAY", str(dmax))
        set_setting("SKIP_REPLY_PROBABILITY", str(skip))
        set_setting("REPLY_COOLDOWN", str(int(cool)))
        set_setting("PERSONALITY_PROFILE", personality)
        return "已保存"

    def switch_profile(selection):
        if not selection:
            return "请先选择一个档案"
        pid = int(selection.split(":")[0])
        set_active_profile(pid)
        p = get_active_profile()
        return str(p) if p else "切换失败"

    btn_save_llm.click(save_llm, [api_key_input, base_url_input, model_input, max_tokens_input], outputs=gr.Textbox(visible=False))
    btn_test_llm.click(test_llm, outputs=llm_test_result)
    btn_save_reply.click(save_reply, [delay_min, delay_max, skip_prob, cooldown, personality_text], outputs=gr.Textbox(visible=False))
    btn_activate_profile.click(switch_profile, inputs=profile_selector, outputs=profile_info)

    return {}
