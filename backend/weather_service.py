"""Refresh CtoN observations from QWeather without exposing provider details."""

from __future__ import annotations

from datetime import date
import json
import sqlite3
from typing import Any

from .config import get_qweather_settings
from .external.deepseek_api import DeepSeekError
from .external.qweather_api import QWeatherClient, QWeatherError
from .poem_service import generate_city_poem


def refresh_active_route_weather(connection: sqlite3.Connection) -> dict[str, Any]:
    client = QWeatherClient(get_qweather_settings())
    cities = connection.execute(
        """SELECT DISTINCT c.id, c.name, c.city_code, c.latitude, c.longitude
           FROM cities c
           JOIN route_stations rs ON rs.city_id = c.id
           JOIN routes r ON r.id = rs.route_id
           WHERE r.is_active = 1 ORDER BY c.id"""
    ).fetchall()
    results: list[dict[str, Any]] = []
    updated_city_ids: list[int] = []
    for city in cities:
        try:
            weather = client.get_current_weather(city["city_code"])
            air_quality = client.get_current_air_quality(city["latitude"], city["longitude"])
            _save_snapshot(connection, city["id"], weather, air_quality)
            results.append({"city_name": city["name"], "status": "updated"})
            updated_city_ids.append(city["id"])
        except QWeatherError as error:
            results.append({"city_name": city["name"], "status": "failed", "reason": str(error)})
    poem_results = _generate_poems(connection, updated_city_ids)
    updated_count = sum(result["status"] == "updated" for result in results)
    return {"date": date.today().isoformat(), "updated_count": updated_count, "cities": results, "poems": poem_results}


def _generate_poems(connection: sqlite3.Connection, city_ids: list[int]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for city_id in city_ids:
        connection.execute(
            """DELETE FROM poems
               WHERE weather_observation_id = (
                   SELECT id FROM weather_observations WHERE city_id = ? ORDER BY observed_at DESC LIMIT 1
               )""",
            (city_id,),
        )
        try:
            poem = generate_city_poem(connection, city_id)
            if poem:
                results.append({"city_id": city_id, "city_name": poem["city_name"], "status": "generated"})
            else:
                results.append({"city_id": city_id, "status": "failed", "reason": "城市没有可用于生成诗歌的天气数据"})
        except DeepSeekError as error:
            results.append({"city_id": city_id, "status": "failed", "reason": str(error)})
    return results


def _save_snapshot(connection: sqlite3.Connection, city_id: int, weather, air_quality) -> None:
    observation_date = weather.observed_at[:10]
    connection.execute(
        """INSERT INTO weather_observations (
                city_id, observation_date, observed_at, temperature_c, feels_like_c,
                weather_text, weather_code, humidity_percent, wind_speed_ms,
                wind_direction, precipitation_probability_percent, visibility_km, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(city_id, observation_date) DO UPDATE SET
                observed_at = excluded.observed_at,
                temperature_c = excluded.temperature_c,
                feels_like_c = excluded.feels_like_c,
                weather_text = excluded.weather_text,
                weather_code = excluded.weather_code,
                humidity_percent = excluded.humidity_percent,
                wind_speed_ms = excluded.wind_speed_ms,
                wind_direction = excluded.wind_direction,
                precipitation_probability_percent = excluded.precipitation_probability_percent,
                visibility_km = excluded.visibility_km,
                source = excluded.source""",
        (city_id, observation_date, weather.observed_at, weather.temperature_c, weather.feels_like_c,
         weather.weather_text, weather.weather_code, weather.humidity_percent, weather.wind_speed_ms,
         weather.wind_direction, None, weather.visibility_km, "qweather"),
    )
    observation = connection.execute(
        "SELECT id FROM weather_observations WHERE city_id = ? AND observation_date = ?",
        (city_id, observation_date),
    ).fetchone()
    connection.execute(
        """INSERT INTO air_quality_observations (
                weather_observation_id, city_id, aqi, pm25_ug_m3, pm10_ug_m3, primary_pollutant
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(weather_observation_id) DO UPDATE SET
                aqi = excluded.aqi,
                pm25_ug_m3 = excluded.pm25_ug_m3,
                pm10_ug_m3 = excluded.pm10_ug_m3,
                primary_pollutant = excluded.primary_pollutant""",
        (observation["id"], city_id, air_quality.aqi, air_quality.pm25_ug_m3, air_quality.pm10_ug_m3, air_quality.primary_pollutant),
    )
