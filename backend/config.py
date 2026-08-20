"""Application configuration loaded from the local, untracked .env file."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class ApplicationSettings:
    environment: str
    cors_origins: tuple[str, ...]
    admin_api_token: str
    cron_secret: str
    database_url: str

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def get_application_settings() -> ApplicationSettings:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    configured_origins = os.getenv("CORS_ORIGINS")
    if configured_origins is None:
        configured_origins = "" if environment == "production" else "http://localhost:5173"
    cors_origins = tuple(
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip()
    )
    settings = ApplicationSettings(
        environment=environment,
        cors_origins=cors_origins,
        admin_api_token=os.getenv("ADMIN_API_TOKEN", "").strip(),
        cron_secret=os.getenv("CRON_SECRET", "").strip(),
        database_url=os.getenv("DATABASE_URL", "").strip(),
    )
    validate_application_settings(settings)
    return settings


def validate_application_settings(settings: ApplicationSettings) -> None:
    if not settings.is_production:
        return
    if len(settings.admin_api_token) < 32:
        raise ValueError("production 环境的 ADMIN_API_TOKEN 至少需要 32 个字符")
    if len(settings.cron_secret) < 32:
        raise ValueError("production 环境的 CRON_SECRET 至少需要 32 个字符")
    if settings.cron_secret == settings.admin_api_token:
        raise ValueError("production 环境的 CRON_SECRET 必须与 ADMIN_API_TOKEN 不同")
    _validate_production_database_url(settings.database_url)
    for origin in settings.cors_origins:
        if not _is_secure_public_origin(origin):
            raise ValueError(
                "production 环境的 CORS_ORIGINS 只能包含 HTTPS 正式域名"
            )
    qweather_settings = get_qweather_settings()
    if not qweather_settings.is_configured:
        raise ValueError("production 环境必须配置 QWEATHER_API_KEY 和 QWEATHER_BASE_URL")
    _require_https_url("QWEATHER_BASE_URL", qweather_settings.base_url)
    deepseek_settings = get_deepseek_settings()
    if not deepseek_settings.is_configured:
        raise ValueError("production 环境必须配置 DeepSeek")
    _require_https_url("DEEPSEEK_BASE_URL", deepseek_settings.base_url)
    if not get_amap_settings().is_security_proxy_configured:
        raise ValueError("production 环境必须配置 AMAP_SECURITY_JS_CODE")
    get_application_timezone()


def _validate_production_database_url(database_url: str) -> None:
    parsed_url = urlparse(database_url)
    if parsed_url.scheme not in {"postgresql", "postgres"} or not parsed_url.hostname:
        raise ValueError("production 环境必须配置 PostgreSQL DATABASE_URL")
    if "-pooler" not in parsed_url.hostname:
        raise ValueError("production 环境的 DATABASE_URL 必须使用 Neon 池化连接")
    if parse_qs(parsed_url.query).get("sslmode") != ["require"]:
        raise ValueError("production 环境的 DATABASE_URL 必须设置 sslmode=require")


def _require_https_url(name: str, value: str) -> None:
    parsed_url = urlparse(value)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise ValueError(f"production 环境的 {name} 必须是 HTTPS 地址")


def _is_secure_public_origin(origin: str) -> bool:
    if origin == "*":
        return False
    parsed_origin = urlparse(origin)
    hostname = parsed_origin.hostname
    if (
        parsed_origin.scheme != "https"
        or not hostname
        or parsed_origin.path
        or parsed_origin.params
        or parsed_origin.query
        or parsed_origin.fragment
        or parsed_origin.username
        or parsed_origin.password
    ):
        return False
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return "." in hostname
    return False


def get_application_timezone() -> ZoneInfo:
    timezone_name = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"APP_TIMEZONE 不是有效时区：{timezone_name}") from error


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
