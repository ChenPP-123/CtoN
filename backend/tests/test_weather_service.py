import sqlite3

from backend.database import initialize_database
from backend.seed import seed_database
from backend.weather_service import refresh_active_route_weather


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
    monkeypatch.setattr("backend.weather_service._save_snapshot", lambda _connection, city_id, _weather, _air: events.append(f"save:{city_id}"))

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
