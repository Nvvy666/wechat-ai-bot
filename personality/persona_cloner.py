"""
角色克隆引擎 — 模仿特定人物的说话风格
参考抖音"前女友语气"等 AI 角色扮演玩法

完整逻辑:
  1. 用户提供: 人物描述 + 聊天样本
  2. LLM 分析: 提取语气特征、常用词、句式、表情习惯
  3. 生成: 详细的 System Prompt + Few-shot 示例
  4. 运行时: Prompt 驱动 LLM 模仿该人物语气回复
"""
import json
import re
from database import get_setting, set_setting, add_log


class PersonaCloner:
    """分析样本 → 生成角色 Prompt"""

    ANALYSIS_PROMPT = """你是一个角色分析专家。请分析以下人物的说话风格，输出 JSON。

## 人物描述
{description}

## 聊天样本
{samples}

## 分析要求
从样本中提取这个人的说话特征，输出 JSON (不要markdown代码块):

{{
  "persona_name": "角色名(10字以内)",
  "tone": "语气描述(如: 傲娇、温柔、毒舌、撒娇)",
  "speech_traits": {{
    "sentence_length": "短/中/长",
    "punctuation_style": "喜欢用的标点(如: ~ ... ！！！)",
    "common_openings": ["常用开头1", "常用开头2"],
    "common_endings": ["常用结尾1", "常用结尾2"],
    "catchphrases": ["口头禅1", "口头禅2", "口头禅3"],
    "emoji_style": "表情使用习惯(如: 爱用猫猫表情包、不用表情、用颜文字)",
    "topic_preferences": ["喜欢聊的话题", "讨厌的话题"]
  }},
  "fewshot_examples": [
    {{"user_says": "对方说什么", "persona_replies": "角色怎么回复"}},
    {{"user_says": "对方说什么", "persona_replies": "角色怎么回复"}}
  ],
  "system_prompt": "完整的 System Prompt，包含角色设定、语气要求、回复规则。要让 AI 读了这个 prompt 就能准确模仿这个人物。200-400字。"
}}

只输出 JSON，不要其他内容。"""

    SIMPLE_PROMPT = """根据以下描述生成一个完整的角色 Prompt。输出 JSON (不要 markdown):

## 角色描述
{description}

{{
  "persona_name": "角色名",
  "tone": "语气",
  "system_prompt": "完整 System Prompt，让 AI 能准确模仿。150-300字。"
}}

只输出 JSON。"""

    @classmethod
    def analyze(cls, llm_chat_fn, description: str, samples: str = "") -> dict:
        """
        分析人物风格，返回生成的角色数据。

        Args:
            llm_chat_fn: LLM 调用函数 (messages) -> str
            description: 人物描述
            samples: 聊天样本 (可选但强烈推荐)

        Returns:
            {"persona_name": str, "tone": str, "system_prompt": str,
             "speech_traits": dict, "fewshot_examples": list}
        """
        if not description.strip():
            raise ValueError("请填写人物描述")

        if samples.strip():
            prompt = cls.ANALYSIS_PROMPT.format(
                description=description.strip(),
                samples=samples.strip()[:3000],  # 限制长度
            )
        else:
            prompt = cls.SIMPLE_PROMPT.format(description=description.strip())

        try:
            reply = llm_chat_fn([{"role": "user", "content": prompt}], max_tokens=1000, temperature=0.8)
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', reply)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # 如果 LLM 没返回 JSON，用文本作为 system_prompt
                data = {
                    "persona_name": description[:10],
                    "tone": "自定义",
                    "system_prompt": reply,
                    "speech_traits": {},
                    "fewshot_examples": [],
                }
            return data
        except json.JSONDecodeError:
            return cls._fallback_analysis(description, samples)
        except Exception as e:
            raise RuntimeError(f"分析失败: {e}")

    @classmethod
    def build_final_prompt(cls, analysis: dict) -> str:
        """
        将分析结果组装成最终可用的 System Prompt。
        融合角色设定 + 语气特征 + few-shot 示例。
        """
        parts = []

        # 角色名称
        name = analysis.get("persona_name", "")
        tone = analysis.get("tone", "")

        # 主要 System Prompt
        sys_prompt = analysis.get("system_prompt", "")
        if sys_prompt:
            parts.append(sys_prompt)
        else:
            # 从特征中构建
            traits = analysis.get("speech_traits", {})
            desc_parts = [f"你是「{name}」，一个{tone}的角色。"] if name else []
            if traits.get("catchphrases"):
                desc_parts.append(f"口头禅: {', '.join(traits['catchphrases'][:5])}")
            if traits.get("common_openings"):
                desc_parts.append(f"常用开头: {', '.join(traits['common_openings'][:3])}")
            parts.append("\n".join(desc_parts))

        # Few-shot 示例
        fewshots = analysis.get("fewshot_examples", [])
        if fewshots:
            fs_lines = ["\n## 参考对话示例 (模仿此风格回复)"]
            for i, fs in enumerate(fewshots[:6], 1):
                user_says = fs.get("user_says", "")
                reply = fs.get("persona_replies", "")
                if user_says and reply:
                    fs_lines.append(f"{i}. 对方: {user_says}")
                    fs_lines.append(f"   你: {reply}")
            parts.append("\n".join(fs_lines))

        # 通用规则
        parts.append("""
## 回复规则
- 严格模仿上述角色的语气、句式、用词风格
- 自然融入角色的口头禅和习惯表达
- 中文回复, 1-3句话为主
- 需要时用 [STICKER:关键词] 配表情包
- 如果完全不需要回复, 回复 [SKIP]
- 记住对方说的话, 适时用 [MEMORY:事实] 保存重要信息""")

        return "\n\n".join(parts)

    @classmethod
    def _fallback_analysis(cls, description: str, samples: str = "") -> dict:
        """LLM 分析失败时的简单回退"""
        prompt = f"""你是一个角色扮演AI。请严格模仿以下人物的语气、说话方式、用词习惯。

## 角色描述
{description}"""

        if samples:
            prompt += f"""

## 参考样本 (务必模仿此风格)
{samples[:1500]}"""

        prompt += """

## 回复要求
- 完全代入角色，用角色的口吻说话
- 自然使用角色的常用词和句式
- 中文回复，1-3句话为主
- 适当使用 [STICKER:情绪词] 配表情包
- 不需要回复时说 [SKIP]"""

        return {
            "persona_name": description[:10] if description else "自定义角色",
            "tone": "自定义",
            "system_prompt": prompt,
            "speech_traits": {},
            "fewshot_examples": [],
        }


persona_cloner = PersonaCloner()
