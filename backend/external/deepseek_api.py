"""Small adapter for generating route guidance with DeepSeek."""

from __future__ import annotations

from typing import Any

import httpx2 as httpx

from ..config import DeepSeekSettings


class DeepSeekError(RuntimeError):
    """DeepSeek did not return usable text."""


class DeepSeekClient:
    def __init__(self, settings: DeepSeekSettings) -> None:
        if not settings.is_configured:
            raise DeepSeekError("未配置 DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL 或 DEEPSEEK_MODEL")
        self.base_url = settings.base_url
        self.model = settings.model
        self.headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}

    def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一位严谨、简洁的中国高铁旅行气象顾问。"},
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": "disabled"},
            "stream": False,
            "temperature": 0.5,
            "max_tokens": 400,
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
            raise DeepSeekError(_missing_content_message(body))
        return content


def _message_content(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return None
    content = message["content"].strip()
    return content or None


def _missing_content_message(body: Any) -> str:
    finish_reason = _finish_reason(body)
    if finish_reason == "length":
        return "DeepSeek 输出额度耗尽，未返回路线建议（finish_reason=length）"
    if finish_reason == "content_filter":
        return "DeepSeek 路线建议被内容过滤（finish_reason=content_filter）"
    if finish_reason == "insufficient_system_resource":
        return "DeepSeek 服务资源不足，未返回路线建议（finish_reason=insufficient_system_resource）"
    return f"DeepSeek 响应缺少路线建议正文（finish_reason={finish_reason or 'unknown'}）"


def _finish_reason(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    finish_reason = choices[0].get("finish_reason")
    return finish_reason if isinstance(finish_reason, str) and finish_reason else None
