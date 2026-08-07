"""SQLite connection and schema setup for the offline demo."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def get_database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH", "./data/cton.db")
    return Path(configured_path)


def connect() -> sqlite3.Connection:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def open_database() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with open_database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                origin_city_name TEXT NOT NULL,
                destination_city_name TEXT NOT NULL,
                total_distance_km INTEGER NOT NULL,
                geometry_json TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                city_code TEXT NOT NULL UNIQUE,
                province TEXT NOT NULL,
                longitude REAL NOT NULL,
                latitude REAL NOT NULL,
                description TEXT,
                climate_description TEXT
            );

            CREATE TABLE IF NOT EXISTS route_stations (
                id INTEGER PRIMARY KEY,
                route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
                city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE RESTRICT,
                station_order INTEGER NOT NULL,
                distance_from_origin_km REAL NOT NULL,
                station_name TEXT NOT NULL,
                longitude REAL NOT NULL,
                latitude REAL NOT NULL,
                UNIQUE(route_id, city_id),
                UNIQUE(route_id, station_order)
            );

            CREATE TABLE IF NOT EXISTS weather_observations (
                id INTEGER PRIMARY KEY,
                city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE RESTRICT,
                observation_date TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                temperature_c REAL NOT NULL,
                feels_like_c REAL,
                weather_text TEXT NOT NULL,
                weather_code INTEGER,
                humidity_percent INTEGER NOT NULL,
                wind_speed_ms REAL,
                wind_direction TEXT,
                precipitation_probability_percent INTEGER,
                visibility_km REAL,
                cloud_cover_percent INTEGER,
                source TEXT NOT NULL,
                UNIQUE(city_id, observation_date)
            );

            CREATE TABLE IF NOT EXISTS air_quality_observations (
                id INTEGER PRIMARY KEY,
                weather_observation_id INTEGER NOT NULL UNIQUE REFERENCES weather_observations(id) ON DELETE CASCADE,
                city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE RESTRICT,
                aqi INTEGER NOT NULL,
                pm25_ug_m3 REAL,
                pm10_ug_m3 REAL,
                primary_pollutant TEXT
            );

            CREATE TABLE IF NOT EXISTS travel_reports (
                id INTEGER PRIMARY KEY,
                route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE RESTRICT,
                travel_date TEXT NOT NULL,
                content TEXT NOT NULL,
                model_name TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                source_snapshot_json TEXT NOT NULL,
                UNIQUE(route_id, travel_date)
            );

            CREATE TABLE IF NOT EXISTS daily_update_runs (
                run_date TEXT PRIMARY KEY,
                trigger TEXT NOT NULL CHECK(trigger IN ('scheduled', 'startup')),
                status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'partial', 'failed', 'skipped')),
                started_at TEXT NOT NULL,
                finished_at TEXT,
                weather_updated_count INTEGER NOT NULL DEFAULT 0,
                weather_failed_count INTEGER NOT NULL DEFAULT 0,
                advice_generated_count INTEGER NOT NULL DEFAULT 0,
                advice_failed_count INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_route_stations_route_order
                ON route_stations(route_id, station_order);
            CREATE INDEX IF NOT EXISTS idx_weather_city_date
                ON weather_observations(city_id, observation_date DESC);
            CREATE INDEX IF NOT EXISTS idx_travel_reports_route_date
                ON travel_reports(route_id, travel_date DESC);
            """
        )
        _add_route_station_coordinate_columns(connection)
        _add_weather_cloud_cover_column(connection)
        _initialize_atmosphere_analyses(connection)


def _add_route_station_coordinate_columns(connection: sqlite3.Connection) -> None:
    """Upgrade databases created before station coordinates were introduced."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(route_stations)")}
    if "longitude" not in columns:
        connection.execute("ALTER TABLE route_stations ADD COLUMN longitude REAL")
    if "latitude" not in columns:
        connection.execute("ALTER TABLE route_stations ADD COLUMN latitude REAL")


def _add_weather_cloud_cover_column(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(weather_observations)")}
    if "cloud_cover_percent" not in columns:
        connection.execute("ALTER TABLE weather_observations ADD COLUMN cloud_cover_percent INTEGER")


def _initialize_atmosphere_analyses(connection: sqlite3.Connection) -> None:
    """Replace the obsolete lapse-rate table; its rows are derived and can be recalculated."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(atmosphere_analyses)")}
    if columns and "stability_class" not in columns:
        connection.execute("DROP TABLE atmosphere_analyses")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS atmosphere_analyses (
               id INTEGER PRIMARY KEY,
               weather_observation_id INTEGER NOT NULL UNIQUE REFERENCES weather_observations(id) ON DELETE CASCADE,
               city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE RESTRICT,
               stability_class TEXT NOT NULL,
               stability_level TEXT NOT NULL,
               period TEXT NOT NULL,
               wind_speed_ms REAL NOT NULL,
               cloud_cover_percent INTEGER NOT NULL,
               solar_elevation_deg REAL NOT NULL,
               insolation_category TEXT,
               confidence TEXT NOT NULL,
               method TEXT NOT NULL,
               explanation TEXT NOT NULL,
               calculation_version TEXT NOT NULL
           )"""
    )
