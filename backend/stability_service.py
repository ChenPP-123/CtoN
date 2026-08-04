"""Estimate Pasquill stability from one surface weather observation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import sqlite3

from astral import Observer
from astral.sun import elevation, sun


CALCULATION_VERSION = "pasquill-v1"
METHOD = "pasquill-turner-estimate"

DAY_CLASSES = {
    "strong": ("A", "A-B", "B", "C", "C"),
    "moderate": ("A-B", "B", "B-C", "C-D", "D"),
    "slight": ("B", "C", "C", "D", "D"),
    "weak": ("C", "C", "D", "D", "D"),
}
# The common table leaves calm nighttime conditions open; F is the conservative
# teaching estimate because mechanical mixing is weakest below 2 m/s.
NIGHT_CLASSES = {
    "cloudy": ("F", "E", "D", "D", "D"),
    "clear": ("F", "F", "E", "D", "D"),
}
STABILITY_LEVELS = {
    "A": "极不稳定",
    "A-B": "极不稳定至不稳定",
    "B": "不稳定",
    "B-C": "不稳定至弱不稳定",
    "C": "弱不稳定",
    "C-D": "弱不稳定至中性",
    "D": "中性",
    "E": "弱稳定",
    "F": "稳定",
}
INSOLATION_LEVELS = ("weak", "slight", "moderate", "strong")
INSOLATION_LABELS = {"strong": "强", "moderate": "中等", "slight": "弱", "weak": "微弱"}


@dataclass(frozen=True)
class StabilityAnalysis:
    stability_class: str
    stability_level: str
    period: str
    wind_speed_ms: float
    cloud_cover_percent: int
    solar_elevation_deg: float
    insolation_category: str | None
    confidence: str
    method: str
    explanation: str
    calculation_version: str


def estimate_pasquill_stability(
    *,
    observed_at: str,
    latitude: float,
    longitude: float,
    wind_speed_ms: float | None,
    cloud_cover_percent: int | None,
) -> StabilityAnalysis | None:
    if wind_speed_ms is None or wind_speed_ms < 0:
        return None
    if cloud_cover_percent is None or not 0 <= cloud_cover_percent <= 100:
        return None

    observation_time = _parse_observation_time(observed_at)
    if observation_time is None:
        return None

    observer = Observer(latitude=latitude, longitude=longitude)
    try:
        solar_times = sun(observer, date=observation_time.date(), tzinfo=observation_time.tzinfo)
        solar_elevation = round(elevation(observer, observation_time), 1)
    except ValueError:
        return None

    night_starts = solar_times["sunset"] - timedelta(hours=1)
    night_ends = solar_times["sunrise"] + timedelta(hours=1)
    is_night = observation_time < night_ends or observation_time >= night_starts
    wind_index = _wind_class_index(wind_speed_ms)

    if is_night:
        sky_condition = "cloudy" if cloud_cover_percent >= 50 else "clear"
        stability_class = NIGHT_CLASSES[sky_condition][wind_index]
        explanation = (
            f"当前处于夜间，云量{cloud_cover_percent}%，风速{wind_speed_ms:g} m/s，"
            f"近地层估算为{STABILITY_LEVELS[stability_class]}。"
        )
        return StabilityAnalysis(
            stability_class=stability_class,
            stability_level=STABILITY_LEVELS[stability_class],
            period="night",
            wind_speed_ms=wind_speed_ms,
            cloud_cover_percent=cloud_cover_percent,
            solar_elevation_deg=solar_elevation,
            insolation_category=None,
            confidence="estimated",
            method=METHOD,
            explanation=explanation,
            calculation_version=CALCULATION_VERSION,
        )

    if cloud_cover_percent == 100:
        insolation_category = "weak"
        stability_class = "D"
        confidence = "low"
    else:
        insolation_category = _insolation_category(solar_elevation)
        confidence = "estimated"
        if cloud_cover_percent > 50:
            # Turner also uses cloud-base height. QWeather does not provide it,
            # so assume a middle cloud layer and expose the lower confidence.
            insolation_category = _weaken_insolation(insolation_category)
            confidence = "low"
        stability_class = DAY_CLASSES[insolation_category][wind_index]

    explanation = (
        f"当前处于白天，{INSOLATION_LABELS[insolation_category]}日照、云量{cloud_cover_percent}%，"
        f"风速{wind_speed_ms:g} m/s，近地层估算为{STABILITY_LEVELS[stability_class]}。"
    )
    return StabilityAnalysis(
        stability_class=stability_class,
        stability_level=STABILITY_LEVELS[stability_class],
        period="day",
        wind_speed_ms=wind_speed_ms,
        cloud_cover_percent=cloud_cover_percent,
        solar_elevation_deg=solar_elevation,
        insolation_category=insolation_category,
        confidence=confidence,
        method=METHOD,
        explanation=explanation,
        calculation_version=CALCULATION_VERSION,
    )


def replace_stability_analysis(
    connection: sqlite3.Connection,
    *,
    weather_observation_id: int,
    city_id: int,
    observed_at: str,
    latitude: float,
    longitude: float,
    wind_speed_ms: float | None,
    cloud_cover_percent: int | None,
) -> StabilityAnalysis | None:
    connection.execute(
        "DELETE FROM atmosphere_analyses WHERE weather_observation_id = ?",
        (weather_observation_id,),
    )
    analysis = estimate_pasquill_stability(
        observed_at=observed_at,
        latitude=latitude,
        longitude=longitude,
        wind_speed_ms=wind_speed_ms,
        cloud_cover_percent=cloud_cover_percent,
    )
    if analysis is None:
        return None

    connection.execute(
        """INSERT INTO atmosphere_analyses (
               weather_observation_id, city_id, stability_class, stability_level, period,
               wind_speed_ms, cloud_cover_percent, solar_elevation_deg, insolation_category,
               confidence, method, explanation, calculation_version
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            weather_observation_id,
            city_id,
            analysis.stability_class,
            analysis.stability_level,
            analysis.period,
            analysis.wind_speed_ms,
            analysis.cloud_cover_percent,
            analysis.solar_elevation_deg,
            analysis.insolation_category,
            analysis.confidence,
            analysis.method,
            analysis.explanation,
            analysis.calculation_version,
        ),
    )
    return analysis


def _parse_observation_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _wind_class_index(wind_speed_ms: float) -> int:
    if wind_speed_ms < 2:
        return 0
    if wind_speed_ms < 3:
        return 1
    if wind_speed_ms < 5:
        return 2
    if wind_speed_ms < 6:
        return 3
    return 4


def _insolation_category(solar_elevation_deg: float) -> str:
    if solar_elevation_deg > 60:
        return "strong"
    if solar_elevation_deg > 35:
        return "moderate"
    if solar_elevation_deg > 15:
        return "slight"
    return "weak"


def _weaken_insolation(category: str) -> str:
    index = INSOLATION_LEVELS.index(category)
    return INSOLATION_LEVELS[max(0, index - 1)]
