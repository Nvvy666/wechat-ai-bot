"""
LLM 客户端 — 支持 DeepSeek/千问/OpenAI 等 OpenAI 兼容 API
"""
import json
import urllib.request
import urllib.error
from typing import Optional

from config import config


class LLMClient:
    def __init__(self):
        self._reload()

    def _reload(self):
        """每次调用前重新加载配置，支持运行时切换模型"""
        base_url = config.llm_base_url.rstrip("/")
        if not base_url.endswith("/chat/completions"):
            if base_url.endswith("/v1"):
                base_url += "/chat/completions"
            else:
                base_url += "/v1/chat/completions"
        self.url = base_url
        self.model = config.llm_model
        self.api_key = config.llm_api_key
        self.max_tokens = config.llm_max_tokens

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.8,
        max_tokens: int = None,
    ) -> str:
        """发送 Chat Completion 请求，返回文本回复"""
        self._reload()

        if not self.api_key:
            return "[ERROR] API Key not configured"

        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

        req = urllib.request.Request(
            url=self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {e.code}: {body[:300]}")
        except Exception as e:
            raise RuntimeError(f"LLM Error: {e}")

    def test_connection(self) -> tuple[bool, str]:
        """测试 API 连接"""
        try:
            reply = self.chat([
                {"role": "user", "content": "回复OK即可"}
            ], max_tokens=10)
            return True, reply[:50]
        except Exception as e:
            return False, str(e)[:200]


# 全局单例
llm_client = LLMClient()
