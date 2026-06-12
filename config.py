"""
微信 AI Bot — 统一配置管理
.env 文件 + 数据库 settings 表
"""
import os
from pathlib import Path
from typing import Optional

from database import get_setting, set_setting, get_all_settings

ENV_FILE = Path(__file__).parent / ".env"


def load_env_file():
    """加载 .env 到 os.environ"""
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k not in os.environ or not os.environ[k]:
                    os.environ[k] = v


load_env_file()


class Config:
    """统一配置入口 — 优先级: os.environ > DB settings > 默认值"""

    @staticmethod
    def _resolve(key: str, env_key: str, default: str = "") -> str:
        # 1. 环境变量
        val = os.getenv(env_key, "")
        if val:
            return val
        # 2. 数据库
        val = get_setting(key, "")
        if val:
            return val
        return default

    @classmethod
    def get(cls, key: str, env_key: str = None, default: str = "") -> str:
        if env_key is None:
            env_key = key
        return cls._resolve(key, env_key, default)

    @classmethod
    def set(cls, key: str, value: str):
        set_setting(key, value)
        os.environ[key] = value

    # ---- LLM (优先 DB 多配置) ----
    @property
    def llm_api_key(self) -> str:
        from database import get_active_llm_config
        cfg = get_active_llm_config()
        if cfg and cfg.get("api_key"):
            return cfg["api_key"]
        return self._resolve("LLM_API_KEY", "LLM_API_KEY", "")

    @property
    def llm_base_url(self) -> str:
        from database import get_active_llm_config
        cfg = get_active_llm_config()
        if cfg and cfg.get("base_url"):
            return cfg["base_url"]
        return self._resolve("LLM_BASE_URL", "LLM_BASE_URL", "https://api.deepseek.com/v1")

    @property
    def llm_model(self) -> str:
        from database import get_active_llm_config
        cfg = get_active_llm_config()
        if cfg and cfg.get("model"):
            return cfg["model"]
        return self._resolve("LLM_MODEL", "LLM_MODEL", "deepseek-chat")

    @property
    def llm_max_tokens(self) -> int:
        from database import get_active_llm_config
        cfg = get_active_llm_config()
        if cfg and cfg.get("max_tokens"):
            return int(cfg["max_tokens"])
        return int(self._resolve("LLM_MAX_TOKENS", "LLM_MAX_TOKENS", "400"))

    # ---- Reply Strategy ----
    @property
    def reply_min_delay(self) -> float:
        return float(self._resolve("REPLY_MIN_DELAY", "REPLY_MIN_DELAY", "1.0"))

    @property
    def reply_max_delay(self) -> float:
        return float(self._resolve("REPLY_MAX_DELAY", "REPLY_MAX_DELAY", "5.0"))

    @property
    def skip_probability(self) -> float:
        return float(self._resolve("SKIP_REPLY_PROBABILITY", "SKIP_REPLY_PROBABILITY", "0.05"))

    @property
    def reply_cooldown(self) -> int:
        """同一联系人两次回复的最小间隔(秒)"""
        return int(self._resolve("REPLY_COOLDOWN", "REPLY_COOLDOWN", "30"))

    # ---- Vision ----
    @property
    def vision_mode(self) -> str:
        """
        图片识别模式:
          "lightweight" - OCR 提取文字 → 文本 LLM
          "vision"      - 截图直接送多模态 VL 模型
          "auto"        - 有 VL 模型就用，否则用 OCR
        """
        return self._resolve("VISION_MODE", "VISION_MODE", "lightweight")

    @property
    def ocr_prefer_paddle(self) -> bool:
        """是否优先使用 PaddleOCR (False = 直接使用 RapidOCR)"""
        val = self._resolve("OCR_ENGINE", "OCR_ENGINE", "paddle")
        return val.lower() != "rapid"

    # ---- Personality ----
    @property
    def personality_profile(self) -> str:
        return self._resolve(
            "PERSONALITY_PROFILE", "PERSONALITY_PROFILE",
            "一个随和的年轻人，说话简洁幽默，喜欢用口语化表达"
        )

    @property
    def active_style_profile_id(self) -> Optional[int]:
        from database import get_active_profile
        p = get_active_profile()
        return p["id"] if p else None

    # ---- Web UI ----
    @property
    def web_password(self) -> str:
        return self._resolve("WEB_PASSWORD", "WEB_PASSWORD", "")

    @property
    def web_port(self) -> int:
        return int(self._resolve("WEB_PORT", "WEB_PORT", "7860"))

    # ---- Contacts ----
    @property
    def contacts(self) -> list[str]:
        val = self._resolve("CONTACT_LIST", "CONTACT_LIST", "")
        return [c.strip() for c in val.split(",") if c.strip()]

    @property
    def groups(self) -> list[str]:
        val = self._resolve("GROUP_LIST", "GROUP_LIST", "")
        return [g.strip() for g in val.split(",") if g.strip()]


# 全局单例
config = Config()
