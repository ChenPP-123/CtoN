"""Repeatable fixed route and offline observations used by the demonstration."""

from __future__ import annotations

import json
import sqlite3


DEMO_DATE = "2026-08-01"
OBSERVED_AT = "2026-08-01T08:00:00Z"

# Coordinates are AMap (GCJ-02) station positions, deliberately separate from
# city weather coordinates. They are maintained as static route data.
STATIONS = [
    (1, "重庆", "101040100", "重庆市", 106.5516, 29.5630, "重庆北站", 1, 0, 106.5500, 29.6145),
    (4, "万州", "101041300", "重庆市", 108.4087, 30.8078, "万州北站", 2, 245, 108.3968, 30.7988),
    (5, "恩施", "101201001", "湖北省", 109.4882, 30.2722, "恩施站", 3, 410, 109.4859, 30.2911),
    (6, "宜昌", "101200901", "湖北省", 111.2865, 30.6919, "宜昌东站", 4, 560, 111.3856, 30.6466),
    (7, "荆州", "101200801", "湖北省", 112.2397, 30.3352, "荆州站", 5, 650, 112.2451, 30.3478),
    (2, "武汉", "101200101", "湖北省", 114.3054, 30.5931, "武汉站", 6, 850, 114.4252, 30.6095),
    (8, "合肥", "101220101", "安徽省", 117.2272, 31.8206, "合肥南站", 7, 1070, 117.3097, 31.7936),
    (3, "南京", "101190101", "江苏省", 118.7969, 32.0603, "南京南站", 8, 1245, 118.7982, 31.9517),
]
ROUTE_GEOMETRY = [[station[9], station[10]] for station in STATIONS]


def seed_database(connection: sqlite3.Connection) -> None:
    connection.execute(
        """INSERT INTO routes (id, code, name, origin_city_name, destination_city_name, total_distance_km, geometry_json, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             code = excluded.code, name = excluded.name,
             origin_city_name = excluded.origin_city_name, destination_city_name = excluded.destination_city_name,
             total_distance_km = excluded.total_distance_km, geometry_json = excluded.geometry_json,
             is_active = excluded.is_active""",
        (1, "CTN", "重庆至南京高铁沿线", "重庆", "南京", 1245, json.dumps(ROUTE_GEOMETRY), 1),
    )
    # Route stations are static configuration with no dependents, so replacing
    # this route's rows avoids transient unique-order conflicts during upgrades.
    connection.execute("DELETE FROM route_stations WHERE route_id = ?", (1,))
    city_ids: dict[str, int] = {}
    for _, name, city_code, province, longitude, latitude, station_name, station_order, distance, station_longitude, station_latitude in STATIONS:
        connection.execute(
            """INSERT INTO cities (name, city_code, province, longitude, latitude, description, climate_description)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(city_code) DO UPDATE SET
                 name = excluded.name, province = excluded.province,
                 longitude = excluded.longitude, latitude = excluded.latitude""",
            (name, city_code, province, longitude, latitude, *_city_copy(name)),
        )
        city_id = connection.execute("SELECT id FROM cities WHERE city_code = ?", (city_code,)).fetchone()["id"]
        city_ids[city_code] = city_id
        connection.execute(
            """INSERT INTO route_stations (
                   route_id, city_id, station_order, distance_from_origin_km, station_name, longitude, latitude
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (1, city_id, station_order, distance, station_name, station_longitude, station_latitude),
        )
    _seed_observations(connection, city_ids)


def _city_copy(name: str) -> tuple[str, str]:
    return (
        f"{name}是这条固定高铁示范主线上的观测城市。",
        "沿线夏季湿热多雨，局地天气会随地形和水汽条件变化。",
    )


def _seed_observations(connection: sqlite3.Connection, city_ids: dict[str, int]) -> None:
    weather_rows = [
        ("101040100", 29.4, 33.1, "多云", 104, 78, 2.1, "东南风", 35, 8.0, 62, 38, 61, "PM2.5"),
        ("101041300", 28.6, 32.4, "阴", 103, 82, 1.7, "东风", 40, 7.0, 55, 29, 48, "PM2.5"),
        ("101201001", 27.8, 31.0, "小雨", 305, 86, 1.4, "东北风", 75, 5.5, 51, 25, 42, None),
        ("101200901", 30.1, 34.0, "多云", 104, 73, 2.3, "东南风", 30, 9.0, 49, 23, 39, None),
        ("101200801", 30.5, 34.6, "晴", 100, 68, 2.6, "南风", 15, 12.0, 46, 21, 36, None),
        ("101200101", 31.0, 35.0, "晴", 100, 65, 2.8, "南风", 15, 12.0, 48, 24, 45, None),
        ("101220101", 30.8, 34.8, "多云", 101, 70, 2.2, "东南风", 25, 10.0, 53, 28, 46, "PM2.5"),
        ("101190101", 30.2, 34.2, "小雨", 305, 82, 1.9, "东风", 70, 6.0, 55, 31, 52, "PM2.5"),
    ]
    for city_code, temperature, feels_like, text, code, humidity, wind_speed, wind_direction, precipitation, visibility, aqi, pm25, pm10, pollutant in weather_rows:
        city_id = city_ids[city_code]
        connection.execute(
            """INSERT INTO weather_observations (
                   city_id, observation_date, observed_at, temperature_c, feels_like_c, weather_text,
                   weather_code, humidity_percent, wind_speed_ms, wind_direction,
                   precipitation_probability_percent, visibility_km, source
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(city_id, observation_date) DO UPDATE SET
                 observed_at = excluded.observed_at, temperature_c = excluded.temperature_c,
                 feels_like_c = excluded.feels_like_c, weather_text = excluded.weather_text,
                 weather_code = excluded.weather_code, humidity_percent = excluded.humidity_percent,
                 wind_speed_ms = excluded.wind_speed_ms, wind_direction = excluded.wind_direction,
                 precipitation_probability_percent = excluded.precipitation_probability_percent,
                 visibility_km = excluded.visibility_km
               WHERE weather_observations.source = 'local-demo'""",
            (city_id, DEMO_DATE, OBSERVED_AT, temperature, feels_like, text, code, humidity, wind_speed, wind_direction, precipitation, visibility, "local-demo"),
        )
        observation = connection.execute(
            "SELECT id FROM weather_observations WHERE city_id = ? AND observation_date = ?", (city_id, DEMO_DATE)
        ).fetchone()
        connection.execute(
            """INSERT INTO air_quality_observations (
                   weather_observation_id, city_id, aqi, pm25_ug_m3, pm10_ug_m3, primary_pollutant
               ) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(weather_observation_id) DO UPDATE SET
                 city_id = excluded.city_id, aqi = excluded.aqi, pm25_ug_m3 = excluded.pm25_ug_m3,
                 pm10_ug_m3 = excluded.pm10_ug_m3, primary_pollutant = excluded.primary_pollutant
               WHERE (SELECT source FROM weather_observations WHERE id = air_quality_observations.weather_observation_id) = 'local-demo'""",
            (observation["id"], city_id, aqi, pm25, pm10, pollutant),
        )
