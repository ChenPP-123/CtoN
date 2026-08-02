"""Validate the text contract shared by travel-advice writes and reads."""

from __future__ import annotations

import re


CHINESE_CHARACTER_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SENTENCE_ENDING_PATTERN = re.compile(r"[。！？]")


def validate_travel_advice(advice: str) -> str | None:
    """Return the first contract violation, or ``None`` for valid advice."""
    if "\n" in advice or "\r" in advice:
        return "正文必须是一个自然段，不能包含换行"

    chinese_character_count = len(CHINESE_CHARACTER_PATTERN.findall(advice))
    if chinese_character_count < 50:
        return f"汉字数不足：当前 {chinese_character_count} 个，至少需要 50 个"
    if chinese_character_count > 100:
        return f"汉字数过多：当前 {chinese_character_count} 个，最多允许 100 个"

    if not advice.endswith(("。", "！", "？")):
        return "缺少完整结尾：必须以。！或？收尾"

    sentence_count = len(SENTENCE_ENDING_PATTERN.findall(advice))
    if sentence_count not in (2, 3):
        return f"句子数量不符：当前 {sentence_count} 句，需要 2 至 3 句"
    return None
