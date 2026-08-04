"""Database queries that assemble API-shaped data."""

from __future__ import annotations

from datetime import date
import json
import sqlite3
from typing import Any

from .travel_advice_validation import validate_travel_advice


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


def get_weather(connection: sqlite3.Connection, city_id: int) -> dict[str, Any] | None:
    city = get_city(connection, city_id)
    if not city:
        return None
    weather = row_data(connection.execute("SELECT * FROM weather_observations WHERE city_id = ? ORDER BY observed_at DESC LIMIT 1", (city_id,)).fetchone())
    if not weather:
        return {"city": city, "date": date.today().isoformat(), "observed_at": None, "weather": None, "air_quality": None, "atmosphere": None}
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


def get_weather_profile(connection: sqlite3.Connection, route_id: int) -> dict[str, Any] | None:
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
        (date.today().isoformat(), route_id),
    )
    points = [dict(row) for row in rows]
    return {"route_id": route_id, "date": date.today().isoformat(), "distance_unit": "km", "points": points, "missing_city_ids": [point["city_id"] for point in points if point["temperature_c"] is None]}


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
        report["is_stale"] = report["travel_date"] != date.today().isoformat()
        return report
    return None
