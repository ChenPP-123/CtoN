"""Database queries that assemble API-shaped data."""

from __future__ import annotations

import json
from random import choice
import sqlite3
from typing import Any

from .travel_advice_validation import validate_travel_advice
from .time_utils import current_date


PROFILE_METRICS = {
    "temperature": "temperature_c",
    "humidity": "humidity_percent",
    "aqi": "aqi",
    "wind_speed": "wind_speed_ms",
}


def row_data(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def list_routes(connection: sqlite3.Connection, active_only: bool) -> list[dict[str, Any]]:
    query = "SELECT id, code, name, origin_city_name, destination_city_name, total_distance_km, is_active FROM routes"
    if active_only:
        query += " WHERE is_active = 1"
    return [dict(row) for row in connection.execute(query + " ORDER BY id")]


def get_route(connection: sqlite3.Connection, route_id: int) -> dict[str, Any] | None:
    route = row_data(connection.execute("SELECT * FROM routes WHERE id = ?", (route_id,)).fetchone())
    if not route:
        return None
    route["geometry"] = {"type": "LineString", "coordinates": json.loads(route.pop("geometry_json"))}
    stations = connection.execute(
        """SELECT rs.city_id, c.name AS city_name, rs.station_name, rs.station_order,
                  rs.distance_from_origin_km, rs.longitude, rs.latitude
           FROM route_stations rs JOIN cities c ON c.id = rs.city_id
           WHERE rs.route_id = ? ORDER BY rs.station_order""",
        (route_id,),
    )
    route["stations"] = [dict(station) for station in stations]
    return route


def get_city(connection: sqlite3.Connection, city_id: int) -> dict[str, Any] | None:
    return row_data(connection.execute("SELECT id, name, city_code, province, longitude, latitude, description, climate_description FROM cities WHERE id = ?", (city_id,)).fetchone())


def get_weather(
    connection: sqlite3.Connection, city_id: int, observation_date: str | None
) -> dict[str, Any] | None:
    city = get_city(connection, city_id)
    if not city:
        return None
    if observation_date is None:
        weather_query = "SELECT * FROM weather_observations WHERE city_id = ? ORDER BY observed_at DESC LIMIT 1"
        weather_parameters = (city_id,)
    else:
        weather_query = "SELECT * FROM weather_observations WHERE city_id = ? AND observation_date = ?"
        weather_parameters = (city_id, observation_date)
    weather = row_data(connection.execute(weather_query, weather_parameters).fetchone())
    if not weather:
        return {
            "city": city,
            "date": observation_date or current_date().isoformat(),
            "observed_at": None,
            "weather": None,
            "air_quality": None,
            "atmosphere": None,
        }
    air_quality = row_data(connection.execute("SELECT aqi, pm25_ug_m3, pm10_ug_m3, primary_pollutant FROM air_quality_observations WHERE weather_observation_id = ?", (weather["id"],)).fetchone())
    atmosphere_row = row_data(connection.execute(
        """SELECT stability_class, stability_level, period, wind_speed_ms,
                  cloud_cover_percent, solar_elevation_deg, insolation_category,
                  confidence, method, explanation, calculation_version
           FROM atmosphere_analyses WHERE weather_observation_id = ?""",
        (weather["id"],),
    ).fetchone())
    atmosphere = _atmosphere_data(atmosphere_row)
    return {
        "city": {key: city[key] for key in ("id", "name", "longitude", "latitude")},
        "date": weather["observation_date"],
        "observed_at": weather["observed_at"],
        "weather": {"temperature_c": weather["temperature_c"], "feels_like_c": weather["feels_like_c"], "text": weather["weather_text"], "code": weather["weather_code"], "humidity_percent": weather["humidity_percent"], "wind_speed_ms": weather["wind_speed_ms"], "wind_direction": weather["wind_direction"], "precipitation_probability_percent": weather["precipitation_probability_percent"], "visibility_km": weather["visibility_km"]},
        "air_quality": air_quality,
        "atmosphere": atmosphere,
    }


def _atmosphere_data(analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    if analysis is None:
        return None
    return {
        "stability_class": analysis["stability_class"],
        "stability_level": analysis["stability_level"],
        "period": analysis["period"],
        "insolation_category": analysis["insolation_category"],
        "confidence": analysis["confidence"],
        "method": analysis["method"],
        "inputs": {
            "wind_speed_ms": analysis["wind_speed_ms"],
            "cloud_cover_percent": analysis["cloud_cover_percent"],
            "solar_elevation_deg": analysis["solar_elevation_deg"],
        },
        "explanation": analysis["explanation"],
        "calculation_version": analysis["calculation_version"],
    }


def get_weather_profile(
    connection: sqlite3.Connection,
    route_id: int,
    observation_date: str,
    metrics: tuple[str, ...],
) -> dict[str, Any] | None:
    if not connection.execute("SELECT 1 FROM routes WHERE id = ?", (route_id,)).fetchone():
        return None
    rows = connection.execute(
        """SELECT rs.city_id, c.name AS city_name, rs.station_order, rs.distance_from_origin_km,
                  w.temperature_c, w.humidity_percent, aq.aqi, w.wind_speed_ms
           FROM route_stations rs
           JOIN cities c ON c.id = rs.city_id
           LEFT JOIN weather_observations w ON w.city_id = c.id AND w.observation_date = ?
           LEFT JOIN air_quality_observations aq ON aq.weather_observation_id = w.id
           WHERE rs.route_id = ? ORDER BY rs.station_order""",
        (observation_date, route_id),
    )
    metric_fields = [PROFILE_METRICS[metric] for metric in metrics]
    points = [
        {
            "city_id": row["city_id"],
            "city_name": row["city_name"],
            "station_order": row["station_order"],
            "distance_from_origin_km": row["distance_from_origin_km"],
            **{field: row[field] for field in metric_fields},
        }
        for row in rows
    ]
    return {
        "route_id": route_id,
        "date": observation_date,
        "distance_unit": "km",
        "points": points,
        "missing_city_ids": [
            point["city_id"]
            for point in points
            if all(point[field] is None for field in metric_fields)
        ],
    }


def get_random_trip(
    connection: sqlite3.Connection, route_id: int, observation_date: str
) -> dict[str, Any] | None:
    if not connection.execute("SELECT 1 FROM routes WHERE id = ?", (route_id,)).fetchone():
        return None
    stations = connection.execute(
        """SELECT rs.city_id, c.name AS city_name, rs.station_name, rs.station_order,
                  rs.distance_from_origin_km, w.temperature_c, w.feels_like_c,
                  w.weather_text, w.humidity_percent, aq.aqi, aa.stability_level
           FROM route_stations rs
           JOIN cities c ON c.id = rs.city_id
           LEFT JOIN weather_observations w
                  ON w.city_id = c.id AND w.observation_date = ?
           LEFT JOIN air_quality_observations aq ON aq.weather_observation_id = w.id
           LEFT JOIN atmosphere_analyses aa ON aa.weather_observation_id = w.id
           WHERE rs.route_id = ? ORDER BY rs.station_order""",
        (observation_date, route_id),
    ).fetchall()
    if not stations:
        return None

    station = choice(stations)
    weather = None
    if station["temperature_c"] is not None:
        weather = {
            "temperature_c": station["temperature_c"],
            "feels_like_c": station["feels_like_c"],
            "text": station["weather_text"],
            "humidity_percent": station["humidity_percent"],
            "aqi": station["aqi"],
            "stability_level": station["stability_level"],
        }
    return {
        "route_id": route_id,
        "date": observation_date,
        "station": {
            key: station[key]
            for key in (
                "city_id",
                "city_name",
                "station_name",
                "station_order",
                "distance_from_origin_km",
            )
        },
        "weather": weather,
    }


def get_latest_travel_advice(connection: sqlite3.Connection, route_id: int) -> dict[str, Any] | None:
    reports = connection.execute(
        """SELECT route_id, travel_date, content, model_name, generated_at
           FROM travel_reports WHERE route_id = ?
           ORDER BY travel_date DESC, generated_at DESC""",
        (route_id,),
    )
    for row in reports:
        report = dict(row)
        if validate_travel_advice(report["content"]) is not None:
            continue
        report["is_stale"] = report["travel_date"] != current_date().isoformat()
        return report
    return None
