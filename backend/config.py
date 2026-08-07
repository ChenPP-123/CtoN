"""Application configuration loaded from the local, untracked .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class DailyUpdateSettings:
    is_enabled: bool
    run_time: time
    timezone: ZoneInfo


def get_application_timezone() -> ZoneInfo:
    timezone_name = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"APP_TIMEZONE 不是有效时区：{timezone_name}") from error


def get_daily_update_settings() -> DailyUpdateSettings:
    return DailyUpdateSettings(
        is_enabled=_parse_boolean("DAILY_UPDATE_ENABLED", default=True),
        run_time=_parse_time(os.getenv("DAILY_UPDATE_TIME", "06:30")),
        timezone=get_application_timezone(),
    )


def _parse_boolean(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized_value = value.strip().lower()
    if normalized_value in {"true", "1", "yes"}:
        return True
    if normalized_value in {"false", "0", "no"}:
        return False
    raise ValueError(f"{name} 只支持 true 或 false")


def _parse_time(value: str) -> time:
    try:
        hour_text, minute_text = value.strip().split(":")
        if len(hour_text) != 2 or len(minute_text) != 2:
            raise ValueError
        return time(hour=int(hour_text), minute=int(minute_text))
    except (TypeError, ValueError) as error:
        raise ValueError("DAILY_UPDATE_TIME 必须使用 HH:MM 格式") from error


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


@dataclass(frozen=True)
class AMapSettings:
    web_service_key: str
    security_js_code: str
    base_url: str = "https://restapi.amap.com"

    @property
    def is_web_service_configured(self) -> bool:
        return bool(self.web_service_key)

    @property
    def is_security_proxy_configured(self) -> bool:
        return bool(self.security_js_code)


def get_amap_settings() -> AMapSettings:
    return AMapSettings(
        web_service_key=os.getenv("AMAP_WEB_SERVICE_KEY", ""),
        security_js_code=os.getenv("AMAP_SECURITY_JS_CODE", ""),
        base_url=os.getenv("AMAP_BASE_URL", "https://restapi.amap.com").rstrip("/"),
    )
