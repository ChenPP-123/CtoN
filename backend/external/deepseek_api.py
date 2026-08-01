"""Small adapter for generating a short poem with DeepSeek."""

from __future__ import annotations

from typing import Any

import httpx

from ..config import DeepSeekSettings


class DeepSeekError(RuntimeError):
    """DeepSeek did not return a usable poem."""


class DeepSeekClient:
    def __init__(self, settings: DeepSeekSettings) -> None:
        if not settings.is_configured:
            raise DeepSeekError("未配置 DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL 或 DEEPSEEK_MODEL")
        self.base_url = settings.base_url
        self.model = settings.model
        self.headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}

    def generate_poem(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一位克制的中文旅行诗人。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
            "max_tokens": 180,
        }
        try:
            response = httpx.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise DeepSeekError(f"DeepSeek 请求失败：{error}") from error
        try:
            body = response.json()
        except ValueError as error:
            raise DeepSeekError("DeepSeek 返回了非 JSON 响应") from error
        content = _message_content(body)
        if not content:
            raise DeepSeekError("DeepSeek 响应未包含诗歌内容")
        return content


def _message_content(body: dict[str, Any]) -> str | None:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return None
    content = message["content"].strip()
    return content or None
