import sqlite3

from backend.database import initialize_database
from backend.external.deepseek_api import DeepSeekError
from backend.seed import seed_database
from backend.weather_service import refresh_active_route_weather


def test_refresh_finishes_all_weather_requests_before_generating_poems(monkeypatch, tmp_path) -> None:
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

    def fake_generate(_connection, city_id: int):
        events.append(f"poem:{city_id}")
        if city_id == 1:
            raise DeepSeekError("生成失败")
        return {"city_name": f"城市{city_id}"}

    monkeypatch.setattr("backend.weather_service.generate_city_poem", fake_generate)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        seed_database(connection)
        observation = connection.execute("SELECT id FROM weather_observations WHERE city_id = 1").fetchone()
        connection.execute(
            """INSERT INTO poems (city_id, weather_observation_id, content, model_name, prompt_hash, generated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (1, observation["id"], "巴山云作幕，江风入夏城。", "test-model", "test-hash", "2026-08-01T08:20:00Z"),
        )
        result = refresh_active_route_weather(connection)
        saved_poem = connection.execute("SELECT 1 FROM poems WHERE city_id = 1").fetchone()
    finally:
        connection.close()

    first_poem = next(index for index, event in enumerate(events) if event.startswith("poem:"))
    assert all(not event.startswith(("weather:", "air:", "save:")) for event in events[first_poem:])
    assert len(result["poems"]) == 8
    assert result["poems"][0] == {"city_id": 1, "status": "failed", "reason": "生成失败"}
    assert all(item["status"] == "generated" for item in result["poems"][1:])
    assert saved_poem is None
