"""Small adapter around the QWeather endpoints used by CtoN."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx2 as httpx

from ..config import QWeatherSettings


class QWeatherError(RuntimeError):
    """The provider did not return usable weather data."""


@dataclass(frozen=True)
class CurrentWeather:
    observed_at: str
    temperature_c: float
    feels_like_c: float | None
    weather_text: str
    weather_code: int | None
    humidity_percent: int
    wind_speed_ms: float | None
    wind_direction: str | None
    visibility_km: float | None
    pressure_hpa: float | None
    cloud_cover_percent: int | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class CurrentAirQuality:
    aqi: int
    pm25_ug_m3: float | None
    pm10_ug_m3: float | None
    primary_pollutant: str | None
    raw_payload: dict[str, Any]


class QWeatherClient:
    def __init__(self, settings: QWeatherSettings) -> None:
        if not settings.is_configured:
            raise QWeatherError("未配置 QWEATHER_API_KEY 或 QWEATHER_BASE_URL")
        self.base_url = settings.base_url
        self.headers = {"X-QW-Api-Key": settings.api_key, "Accept": "application/json"}

    def get_current_weather(self, city_code: str) -> CurrentWeather:
        payload = self._get("/v7/weather/now", params={"location": city_code, "lang": "zh"})
        now = payload.get("now")
        if not isinstance(now, dict):
            raise QWeatherError("和风天气响应缺少 now 数据")
        return CurrentWeather(
            observed_at=str(now["obsTime"]),
            temperature_c=_to_float(now.get("temp"), "temp"),
            feels_like_c=_to_optional_float(now.get("feelsLike")),
            weather_text=str(now.get("text") or "未知"),
            weather_code=_to_optional_int(now.get("icon")),
            humidity_percent=_to_int(now.get("humidity"), "humidity"),
            wind_speed_ms=_kilometers_per_hour_to_meters_per_second(now.get("windSpeed")),
            wind_direction=_to_optional_text(now.get("windDir")),
            visibility_km=_to_optional_float(now.get("vis")),
            pressure_hpa=_to_optional_float(now.get("pressure")),
            cloud_cover_percent=_percentage(now.get("cloud")),
            raw_payload=payload,
        )

    def get_current_air_quality(self, latitude: float, longitude: float) -> CurrentAirQuality:
        payload = self._get(f"/airquality/v1/current/{latitude:.2f}/{longitude:.2f}", params={"lang": "zh"})
        index = _find_preferred_index(payload.get("indexes"))
        if not index:
            raise QWeatherError("和风空气质量响应缺少 AQI 数据")
        pollutants = _pollutants_by_code(payload.get("pollutants"))
        primary = index.get("primaryPollutant") or {}
        return CurrentAirQuality(
            aqi=round(_to_float(index.get("aqi"), "aqi")),
            pm25_ug_m3=_pollutant_concentration(pollutants.get("pm2p5")),
            pm10_ug_m3=_pollutant_concentration(pollutants.get("pm10")),
            primary_pollutant=_to_optional_text(primary.get("name")) or _to_optional_text(primary.get("code")),
            raw_payload=payload,
        )

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = httpx.get(f"{self.base_url}{path}", headers=self.headers, params=params, timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise QWeatherError(f"和风天气请求失败：{error}") from error
        try:
            payload = response.json()
        except ValueError as error:
            raise QWeatherError("和风天气返回了非 JSON 响应") from error
        if payload.get("code") not in (None, "200", 200):
            raise QWeatherError(f"和风天气返回错误码：{payload.get('code')}")
        return payload


def _find_preferred_index(indexes: object) -> dict[str, Any] | None:
    if not isinstance(indexes, list):
        return None
    candidates = [index for index in indexes if isinstance(index, dict)]
    return next((index for index in candidates if index.get("code") == "cn-mep"), None) or next((index for index in candidates if index.get("code") == "qaqi"), None) or (candidates[0] if candidates else None)


def _pollutants_by_code(pollutants: object) -> dict[str, dict[str, Any]]:
    if not isinstance(pollutants, list):
        return {}
    return {str(item.get("code")): item for item in pollutants if isinstance(item, dict) and item.get("code")}


def _pollutant_concentration(pollutant: dict[str, Any] | None) -> float | None:
    if not pollutant or not isinstance(pollutant.get("concentration"), dict):
        return None
    return _to_optional_float(pollutant["concentration"].get("value"))


def _kilometers_per_hour_to_meters_per_second(value: object) -> float | None:
    kilometers_per_hour = _to_optional_float(value)
    return round(kilometers_per_hour / 3.6, 1) if kilometers_per_hour is not None else None


def _to_float(value: object, field_name: str) -> float:
    parsed = _to_optional_float(value)
    if parsed is None:
        raise QWeatherError(f"和风天气响应缺少 {field_name}")
    return parsed


def _to_int(value: object, field_name: str) -> int:
    parsed = _to_optional_int(value)
    if parsed is None:
        raise QWeatherError(f"和风天气响应缺少 {field_name}")
    return parsed


def _to_optional_float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_optional_int(value: object) -> int | None:
    parsed = _to_optional_float(value)
    return int(parsed) if parsed is not None else None


def _percentage(value: object) -> int | None:
    parsed = _to_optional_int(value)
    return parsed if parsed is not None and 0 <= parsed <= 100 else None


def _to_optional_text(value: object) -> str | None:
    return str(value) if value not in (None, "") else None
