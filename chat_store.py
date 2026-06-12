"""
聊天记录存储 — 每个联系人/群聊独立文本文件
格式: data/chats/{contact_name}.txt
每行: [2024-01-01 12:00] 发送者: 消息内容
AI 提取上下文时只需读取文件末尾 N 行即可
"""
import os
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"
CHATS_DIR = DATA_DIR / "chats"
CHATS_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

# 保留 JSON 全局存储的引用（向后兼容）
from database import save_message as _db_save_message


def _safe_filename(name: str) -> str:
    """将联系人名转为安全文件名，保留中文"""
    unsafe = '<>:"/\\|?*'
    for c in unsafe:
        name = name.replace(c, "_")
    return name.strip()[:100]


def get_chat_path(name: str) -> Path:
    """获取某联系人的聊天记录文件路径"""
    return CHATS_DIR / f"{_safe_filename(name)}.txt"


def append_message(contact_name: str, sender: str, content: str, role: str = "incoming"):
    """
    追加一条消息到联系人聊天文件。
    同时保存到 JSON 数据库（向后兼容）。
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if role == "outgoing":
        line = f"[{ts}] 🤖 bot: {content}\n"
    else:
        line = f"[{ts}] {sender}: {content}\n"

    try:
        with _lock:
            path = get_chat_path(contact_name)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass

    # 向后兼容: JSON 存储
    try:
        _db_save_message(contact_name, sender, content, role)
    except Exception:
        pass


def get_context(contact_name: str, max_lines: int = 40) -> str:
    """
    读取联系人聊天文件的最后 N 行作为上下文。
    用于构建 LLM System Prompt 的对话历史部分。
    """
    path = get_chat_path(contact_name)
    if not path.exists():
        return ""

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 取最后 max_lines 行
        recent = lines[-max_lines:] if len(lines) > max_lines else lines
        return "".join(recent).strip()
    except Exception:
        return ""


def get_context_messages(contact_name: str, max_msgs: int = 20) -> list[dict]:
    """
    读取最后 N 条消息，返回 LLM 可用的 messages 列表。
    解析格式: [timestamp] sender: content
    """
    path = get_chat_path(contact_name)
    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    messages = []
    for line in lines[-max_msgs:]:
        line = line.strip()
        if not line:
            continue
        # 格式: [2024-01-01 12:00] sender: content
        try:
            bracket_end = line.index("] ")
            rest = line[bracket_end + 2:]
            if ": " in rest:
                sender, content = rest.split(": ", 1)
                role = "assistant" if "bot" in sender else "user"
                messages.append({"role": role, "content": f"{sender}: {content}"})
        except (ValueError, IndexError):
            continue

    return messages


def get_stats(contact_name: str = None) -> dict:
    """获取聊天记录统计"""
    if contact_name:
        path = get_chat_path(contact_name)
        if not path.exists():
            return {"file": str(path), "lines": 0, "size_kb": 0}
        size = path.stat().st_size
        with open(path, "r", encoding="utf-8") as f:
            lines = sum(1 for _ in f)
        return {"file": str(path), "lines": lines, "size_kb": round(size / 1024, 1)}
    else:
        files = list(CHATS_DIR.glob("*.txt"))
        total_lines = 0
        total_size = 0
        for f in files:
            total_size += f.stat().st_size
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    total_lines += sum(1 for _ in fh)
            except:
                pass
        return {
            "files": len(files),
            "total_lines": total_lines,
            "total_size_kb": round(total_size / 1024, 1),
        }


def list_contacts_with_chats() -> list[str]:
    """列出所有有聊天记录的联系人"""
    files = CHATS_DIR.glob("*.txt")
    return [f.stem for f in files]
