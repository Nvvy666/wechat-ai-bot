"""
聊天记录分析器 — 从导出的微信聊天记录中提取说话风格
支持格式: WeChatMsg 导出的 txt/csv/json
"""
import re
import json
import csv
from pathlib import Path
from collections import Counter
from typing import Optional

import jieba


class StyleTraits:
    """风格特征"""
    def __init__(self):
        self.avg_reply_length: int = 0
        self.top_words: list[str] = []
        self.emoji_usage: float = 0.0
        self.use_punctuation: float = 0.0
        self.question_ratio: float = 0.0
        self.common_patterns: list[str] = []

    def to_dict(self) -> dict:
        return {
            "avg_reply_length": self.avg_reply_length,
            "top_words": self.top_words[:20],
            "emoji_usage": round(self.emoji_usage, 3),
            "use_punctuation": round(self.use_punctuation, 3),
            "question_ratio": round(self.question_ratio, 3),
            "common_patterns": self.common_patterns[:10],
        }

    def to_description(self) -> str:
        d = self.to_dict()
        lines = [
            f"平均回复长度: {d['avg_reply_length']} 字",
            f"常用词: {', '.join(d['top_words'][:10])}",
            f"Emoji使用率: {d['emoji_usage']:.0%}",
            f"标点使用率: {d['use_punctuation']:.0%}",
            f"反问频率: {d['question_ratio']:.0%}",
        ]
        return "\n".join(lines)


class ChatAnalyzer:
    """分析微信聊天记录，提取用户说话风格"""

    # 常见时间戳格式
    TIME_PATTERNS = [
        re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}:\d{2}'),
        re.compile(r'\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}'),
        re.compile(r'\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}'),
    ]

    EMOJI_PATTERN = re.compile(r'[\U0001F300-\U0001F9FF]|[☀-➿]|[︀-﻿]')

    def __init__(self, your_name: str):
        """
        Args:
            your_name: 你在微信中的显示名/昵称，用于筛选你的发言
        """
        self.your_name = your_name

    def analyze_file(self, filepath: str) -> tuple[list[str], StyleTraits]:
        """分析聊天记录文件，返回(你的发言列表, 风格特征)"""
        path = Path(filepath)
        if path.suffix == '.txt':
            lines = self._parse_txt(path)
        elif path.suffix == '.csv':
            lines = self._parse_csv(path)
        elif path.suffix == '.json':
            lines = self._parse_json(path)
        else:
            raise ValueError(f"不支持的文件格式: {path.suffix}")

        # 筛选你的发言
        your_msgs = self._extract_your_messages(lines)
        if not your_msgs:
            raise ValueError(f"未找到 {self.your_name} 的发言记录，请检查昵称是否正确")

        traits = self._analyze_traits(your_msgs)
        return your_msgs, traits

    def _parse_txt(self, path: Path) -> list[dict]:
        """解析 txt 格式聊天记录"""
        lines = []
        current = None
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                # 检查是否是新的消息行（以时间戳开头）
                is_new = any(p.match(line) for p in self.TIME_PATTERNS)
                if is_new:
                    if current:
                        lines.append(current)
                    current = {"raw": line}
                elif current:
                    current["raw"] += "\n" + line
        if current:
            lines.append(current)
        return lines

    def _parse_csv(self, path: Path) -> list[dict]:
        """解析 csv 格式 (WeChatMsg 导出格式)"""
        lines = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sender = row.get("sender", "") or row.get("talker", "") or row.get("发言人", "")
                content = row.get("content", "") or row.get("message", "") or row.get("消息", "")
                if sender and content:
                    lines.append({"sender": sender.strip(), "content": content.strip()})
        return lines

    def _parse_json(self, path: Path) -> list[dict]:
        """解析 json 格式"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [
                {"sender": item.get("sender", ""), "content": item.get("content", "")}
                for item in data
            ]
        return []

    def _extract_your_messages(self, lines: list[dict]) -> list[str]:
        """从解析的行中提取你的发言"""
        your_msgs = []
        for line in lines:
            # 如果已经解析过 sender
            if "sender" in line:
                if self.your_name in line["sender"]:
                    your_msgs.append(line["content"])
                continue

            # 从 raw 文本中提取
            raw = line.get("raw", "")
            # 常见格式: "时间 昵称: 消息内容"
            match = re.search(r'[\d:：]+\s+(\S+?)[:：]\s*(.+)', raw)
            if match:
                sender, content = match.group(1), match.group(2)
                if self.your_name in sender:
                    your_msgs.append(content)

        return your_msgs

    def _analyze_traits(self, messages: list[str]) -> StyleTraits:
        """分析消息列表，提取风格特征"""
        traits = StyleTraits()

        if not messages:
            return traits

        # 平均长度
        lengths = [len(m) for m in messages]
        traits.avg_reply_length = int(sum(lengths) / len(lengths))

        # 分词统计
        words = []
        for msg in messages:
            words.extend(jieba.lcut(msg))
        word_counter = Counter(w for w in words if len(w) > 1)
        traits.top_words = [w for w, _ in word_counter.most_common(20)]

        # Emoji 使用率
        emoji_count = sum(1 for m in messages if self.EMOJI_PATTERN.search(m))
        traits.emoji_usage = emoji_count / len(messages)

        # 标点使用率
        punct_count = sum(1 for m in messages if any(p in m for p in "，。！？…～"))
        traits.use_punctuation = punct_count / len(messages)

        # 反问/疑问比率
        question_count = sum(1 for m in messages if "？" in m or "?" in m or "吗" in m or "呢" in m)
        traits.question_ratio = question_count / len(messages)

        # 常见句式（2-5个汉字的连续片段）
        patterns = []
        for msg in messages:
            if 4 <= len(msg) <= 20:
                patterns.append(msg)
        traits.common_patterns = list(dict.fromkeys(patterns))[:10]

        return traits


def extract_fewshots(messages: list[str], your_name: str, max_pairs: int = 20) -> list[dict]:
    """
    从连续的对话中提取 few-shot 问答对
    启发式方法：你的每条回复的前一条消息作为 'user_msg'
    """
    # 仅支持完整对话格式，需要上下文信息
    # 简化版本：将用户消息作为示例
    pairs = []
    for msg in messages[:max_pairs]:
        pairs.append({
            "user_msg": "（根据上下文推断）",
            "bot_reply": msg,
            "scenario": "日常聊天",
        })
    return pairs
