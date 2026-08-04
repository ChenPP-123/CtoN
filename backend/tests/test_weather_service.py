import sqlite3
from types import SimpleNamespace

from backend.database import initialize_database, open_database
from backend.seed import seed_database
from backend.weather_service import _save_snapshot, refresh_active_route_weather


def test_refresh_updates_weather_without_waiting_for_ai(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "cton.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    initialize_database()
    events: list[str] = []

    class FakeWeatherClient:
        def __init__(self, _settings) -> None:
            pass

        def get_current_weather(self, city_code: str):
            events.append(f"weather:{city_code}")
            return object()

        def get_current_air_quality(self, latitude: float, longitude: float):
            events.append(f"air:{latitude}:{longitude}")
            return object()

    monkeypatch.setattr("backend.weather_service.QWeatherClient", FakeWeatherClient)
    monkeypatch.setattr("backend.weather_service._save_snapshot", lambda _connection, city, _weather, _air: events.append(f"save:{city['id']}"))

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        seed_database(connection)
        result = refresh_active_route_weather(connection)
    finally:
        connection.close()

    assert result["updated_count"] == 8
    assert len(result["cities"]) == 8
    assert "poems" not in result
    assert len([event for event in events if event.startswith("save:")]) == 8


def test_snapshot_replaces_stability_and_removes_it_when_cloud_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "cton.db"))
    initialize_database()
    weather = SimpleNamespace(
        observed_at="2026-08-04T12:00:00+08:00",
        temperature_c=31.0,
        feels_like_c=35.0,
        weather_text="晴",
        weather_code=100,
        humidity_percent=65,
        wind_speed_ms=3.4,
        wind_direction="南风",
        visibility_km=12.0,
        cloud_cover_percent=20,
    )
    air_quality = SimpleNamespace(aqi=48, pm25_ug_m3=24.0, pm10_ug_m3=45.0, primary_pollutant=None)

    with open_database() as connection:
        seed_database(connection)
        city = connection.execute("SELECT * FROM cities WHERE id = 1").fetchone()
        _save_snapshot(connection, city, weather, air_quality)
        analysis_count = connection.execute("SELECT COUNT(*) FROM atmosphere_analyses WHERE city_id = 1").fetchone()[0]
        assert analysis_count == 2

        weather.cloud_cover_percent = None
        _save_snapshot(connection, city, weather, air_quality)
        current_analysis = connection.execute(
            """SELECT aa.id FROM atmosphere_analyses aa
               JOIN weather_observations w ON w.id = aa.weather_observation_id
               WHERE aa.city_id = 1 AND w.observation_date = '2026-08-04'"""
        ).fetchone()

    assert current_analysis is None
