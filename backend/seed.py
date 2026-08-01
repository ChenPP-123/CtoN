"""Repeatable fixed observations used by the offline demonstration."""

from __future__ import annotations

import json
import sqlite3


DEMO_DATE = "2026-08-01"
OBSERVED_AT = "2026-08-01T08:00:00Z"
ROUTE_GEOMETRY = [[106.5516, 29.5630], [114.3054, 30.5931], [118.7969, 32.0603]]


def seed_database(connection: sqlite3.Connection) -> None:
    has_route = connection.execute("SELECT 1 FROM routes WHERE id = 1").fetchone()
    if has_route:
        return

    connection.execute(
        "INSERT INTO routes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (1, "CTN", "重庆至南京高铁沿线", "重庆", "南京", 1200, json.dumps(ROUTE_GEOMETRY), 1),
    )
    connection.executemany(
        "INSERT INTO cities VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "重庆", "101040100", "重庆市", 106.5516, 29.5630, "山城与两江相拥，云雾与坡地共同塑造城市天际线。", "夏季湿热多雨，江谷地形使水汽与热量更易滞留。"),
            (2, "武汉", "101200101", "湖北省", 114.3054, 30.5931, "长江与汉江在此相汇，江城开阔而明亮。", "夏季炎热、降水集中，强对流天气较活跃。"),
            (3, "南京", "101190101", "江苏省", 118.7969, 32.0603, "钟山与秦淮相映，古城临江而立。", "夏季高温湿润，梅雨期云雨变化显著。"),
        ],
    )
    connection.executemany(
        "INSERT INTO route_stations (route_id, city_id, station_order, distance_from_origin_km, station_name) VALUES (?, ?, ?, ?, ?)",
        [(1, 1, 1, 0, "重庆北站"), (1, 2, 2, 720, "武汉站"), (1, 3, 3, 1200, "南京南站")],
    )
    observations = [
        (1001, 1, DEMO_DATE, OBSERVED_AT, 29.4, 33.1, "多云", 104, 78, 2.1, "东南风", 35, 8.0, "local-demo"),
        (1002, 2, DEMO_DATE, OBSERVED_AT, 31.0, 35.0, "晴", 100, 65, 2.8, "南风", 15, 12.0, "local-demo"),
        (1003, 3, DEMO_DATE, OBSERVED_AT, 30.2, 34.2, "小雨", 305, 82, 1.9, "东风", 70, 6.0, "local-demo"),
    ]
    connection.executemany("INSERT INTO weather_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", observations)
    connection.executemany(
        "INSERT INTO air_quality_observations (weather_observation_id, city_id, aqi, pm25_ug_m3, pm10_ug_m3, primary_pollutant) VALUES (?, ?, ?, ?, ?, ?)",
        [(1001, 1, 62, 38, 61, "PM2.5"), (1002, 2, 48, 24, 45, None), (1003, 3, 55, 31, 52, "PM2.5")],
    )
    connection.executemany(
        "INSERT INTO atmosphere_analyses (weather_observation_id, city_id, stability_level, lapse_rate_c_per_km, pressure_hpa, explanation, calculation_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1001, 1, "弱不稳定", 8.2, 985, "午后地面加热增强，垂直混合作用增强，有利于近地层污染扩散。", "v1"),
            (1002, 2, "不稳定", 9.5, 1002, "晴空辐射使地面升温明显，近地层空气交换更活跃。", "v1"),
            (1003, 3, "中性", 6.1, 1008, "云雨削弱地面加热，垂直混合处于中等水平。", "v1"),
        ],
    )
