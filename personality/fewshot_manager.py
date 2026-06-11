"""
Few-shot 示例管理器
"""
from database import (
    get_active_profile, add_fewshot, get_fewshots,
    delete_fewshot, clear_fewshots, increment_fewshot_usage,
)


class FewShotManager:
    """管理 few-shot 示例的 CRUD 和智能选择"""

    def add(self, user_msg: str, bot_reply: str, scenario: str = "") -> int:
        profile = get_active_profile()
        if not profile:
            raise ValueError("没有激活的风格档案")
        return add_fewshot(profile["id"], user_msg, bot_reply, scenario, source="manual")

    def list(self, limit: int = 50) -> list[dict]:
        profile = get_active_profile()
        pid = profile["id"] if profile else None
        return get_fewshots(pid, limit)

    def delete(self, fid: int):
        delete_fewshot(fid)

    def clear(self):
        profile = get_active_profile()
        if profile:
            clear_fewshots(profile["id"])

    def record_usage(self, fid: int):
        increment_fewshot_usage(fid)

    def import_from_chat(self, chat_records: list[dict]):
        """从聊天记录批量导入 few-shot"""
        profile = get_active_profile()
        if not profile:
            raise ValueError("没有激活的风格档案")
        count = 0
        for record in chat_records:
            user_msg = record.get("user_msg", "")
            bot_reply = record.get("bot_reply", "")
            if user_msg and bot_reply:
                add_fewshot(profile["id"], user_msg, bot_reply, record.get("scenario", ""), source="auto_extracted")
                count += 1
        return count


fewshot_manager = FewShotManager()
