"""
动态 Prompt 构建器 — 根据激活的风格档案和 few-shot 示例构建 System Prompt
"""
import json
from typing import Optional

from database import get_active_profile, get_fewshots
from config import config


class PromptBuilder:
    """构建发给 LLM 的 System Prompt"""

    BASE_RULES = """## 核心规则
1. 回复简短自然，通常1-3句话
2. 适当使用语气词（～、哈哈哈、嗯嗯）
3. 不知道就说不知道
4. 绝对不要表现出你是AI或机器人
5. 你就是主人本人，用第一人称
6. 用中文回复
7. 如果不需要回复，回复 [SKIP]"""

    def build(
        self,
        sender_name: str = "",
        chat_context: list[dict] = None,
        personality: str = None,
    ) -> str:
        """
        构建完整的 System Prompt
        优先级：DB 风格档案 > config 中的 PERSONALITY_PROFILE
        """
        parts = []

        # 1. 角色设定
        profile = get_active_profile()
        if profile and profile.get("prompt_template"):
            parts.append(profile["prompt_template"])
        elif profile and profile.get("traits"):
            traits = json.loads(profile["traits"]) if isinstance(profile["traits"], str) else profile["traits"]
            desc = profile.get("description", "")
            parts.append(self._build_from_traits(desc, traits))
        else:
            parts.append(f"你是微信聊天助手，正在替主人回复消息。\n\n## 主人风格\n{personality or config.personality_profile}")

        # 2. Few-shot 示例
        fewshots = get_fewshots(profile["id"] if profile else None, limit=10)
        if fewshots:
            parts.append(self._format_fewshots(fewshots))

        # 3. 对话上下文
        if chat_context:
            parts.append(self._format_context(chat_context))

        # 4. 规则
        parts.append(self.BASE_RULES)

        return "\n\n".join(parts)

    def _build_from_traits(self, description: str, traits: dict) -> str:
        lines = [description, "", "## 风格特征"]
        if traits.get("avg_reply_length"):
            lines.append(f"- 平均回复长度: {traits['avg_reply_length']} 字")
        if traits.get("top_words"):
            lines.append(f"- 常用词: {', '.join(traits['top_words'][:10])}")
        if traits.get("emoji_usage"):
            lines.append(f"- Emoji使用频率: {'高' if traits['emoji_usage'] > 0.3 else '中' if traits['emoji_usage'] > 0.1 else '低'}")
        if traits.get("question_ratio"):
            lines.append(f"- 反问频率: {'高' if traits['question_ratio'] > 0.2 else '中' if traits['question_ratio'] > 0.1 else '低'}")
        if traits.get("common_patterns"):
            lines.append(f"- 常用句式: {' / '.join(traits['common_patterns'][:5])}")
        return "\n".join(lines)

    def _format_fewshots(self, fewshots: list[dict]) -> str:
        lines = ["## 参考对话示例"]
        for i, fs in enumerate(fewshots, 1):
            lines.append(f"{i}. 对方: {fs['user_msg']}")
            lines.append(f"   你: {fs['bot_reply']}")
        return "\n".join(lines)

    def _format_context(self, context: list[dict]) -> str:
        if not context:
            return ""
        lines = ["## 最近对话"]
        for msg in context[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            sender = msg.get("sender", "")
            if role == "user":
                lines.append(f"{sender}: {content}")
            else:
                lines.append(f"你: {content}")
        return "\n".join(lines)


# 全局单例
prompt_builder = PromptBuilder()
