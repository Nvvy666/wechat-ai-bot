"""
简化 Prompt 构建器 — 基于文本描述 + 聊天上下文
参考 chatgpt-on-wechat 的简洁风格
"""
from database import get_setting
from chat_store import get_context


class PromptBuilder:
    """构建发给 LLM 的 System Prompt"""

    BASE_RULES = """## 核心规则
1. 你是一个聪明、幽默的AI助手，正在帮主人回复微信
2. 回复要自然：1-3句话为主，该详细时就详细
3. 展现智能：回答问题、提供建议、分析情况
4. 保持轻松语气，适当用语气词和热梗
5. 不知道就说不知道，不要编造
6. 用中文回复
7. 如果完全不需要回复，回复 [SKIP]

## 表情包使用
可以在回复末尾加 [STICKER:关键词或情绪] 来配表情包。
根据当前对话的情绪和场景来选择合适的表情包，不要每条都用。

## 自动记忆
如果你在和对方的对话中了解到值得记住的信息（如对方的爱好、工作、宠物等），请在回复末尾加 [MEMORY:简短事实]。系统会自动保存并在下次对话时提醒你。"""

    def build(
        self,
        sender_name: str = "",
        chat_name: str = "",
        personality_text: str = None,
        pure_ai: bool = False,
        is_group: bool = False,
        bot_name: str = "",
    ) -> str:
        """
        构建完整的 System Prompt。

        Args:
            sender_name: 发送者名字
            chat_name: 聊天对象名（群名或联系人名）
            personality_text: 自定义人格描述文本（覆盖默认）
            pure_ai: True=纯AI模式，忽略人格
            is_group: 是否群聊
            bot_name: 机器人名字（群聊@检测用）
        """
        parts = []

        # 1. 角色设定
        if pure_ai:
            persona = "你是一个聪明、有用的AI助手，正在微信上帮主人回复消息。"
        elif personality_text and personality_text.strip():
            persona = (
                f"你是微信聊天助手，正在替主人回复消息。\n\n"
                f"## 你的风格\n{personality_text.strip()}"
            )
        else:
            default_persona = get_setting("PERSONALITY_DESC", "")
            if default_persona:
                persona = (
                    f"你是微信聊天助手，正在替主人回复消息。\n\n"
                    f"## 你的风格\n{default_persona}"
                )
            else:
                persona = "你是微信聊天助手，正在替主人回复消息。风格：随和、幽默、自然。"

        parts.append(persona)

        # 2. 聊天上下文（从文本文件读取最近对话）
        if chat_name:
            ctx_text = get_context(chat_name, max_lines=30)
            if ctx_text:
                parts.append(f"## 最近对话\n{ctx_text}")
            # 群聊时也加载发送者的上下文
            if is_group and sender_name and sender_name != chat_name:
                sender_ctx = get_context(sender_name, max_lines=10)
                if sender_ctx:
                    parts.append(f"## 与 {sender_name} 的历史\n{sender_ctx}")

        # 3. 群聊信息
        if is_group and bot_name:
            parts.append(
                f"## 群聊信息\n这是群聊「{chat_name}」。你的名字是「{bot_name}」。"
                f"只有明确 @{bot_name} 时才回复。其他人之间的对话只是上下文，不要回复。"
            )

        # 4. 核心规则
        parts.append(self.BASE_RULES)

        return "\n\n".join(parts)


# 全局单例
prompt_builder = PromptBuilder()
