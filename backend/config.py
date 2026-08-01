"""Application configuration loaded from the local, untracked .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class QWeatherSettings:
    api_key: str
    base_url: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)


def get_qweather_settings() -> QWeatherSettings:
    return QWeatherSettings(
        api_key=os.getenv("QWEATHER_API_KEY", ""),
        base_url=os.getenv("QWEATHER_BASE_URL", "").rstrip("/"),
    )


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    base_url: str
    model: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


def get_deepseek_settings() -> DeepSeekSettings:
    return DeepSeekSettings(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    )
