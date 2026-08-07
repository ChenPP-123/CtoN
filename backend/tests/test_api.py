from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.database import initialize_database, open_database
from backend.external.deepseek_api import DeepSeekError
from backend.seed import seed_database
from backend.time_utils import current_date
from backend.travel_advice_service import RouteWeatherUnavailableError


VALID_ADVICE = "沿线天气湿热多变，建议穿轻薄透气衣物并及时补水。重庆至恩施段可能有雨，请随身携带雨具。武汉以后注意防晒，空气质量整体适合出行。"


def test_health_returns_database_status(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "health-test"})
    assert response.status_code == 200
    assert response.json()["data"]["database"] == "ok"
    assert response.json()["request_id"] == "health-test"
    assert response.headers["X-Request-ID"] == "health-test"


def test_route_includes_seeded_stations_in_order(client: TestClient) -> None:
    response = client.get("/api/v1/routes/1")
    stations = response.json()["data"]["stations"]
    assert [station["station_name"] for station in stations] == ["重庆北站", "万州北站", "恩施站", "宜昌东站", "荆州站", "武汉站", "合肥南站", "南京南站"]
    assert [station["station_order"] for station in stations] == list(range(1, 9))
    assert all(-180 <= station["longitude"] <= 180 and -90 <= station["latitude"] <= 90 for station in stations)
    assert response.json()["data"]["geometry"]["coordinates"] == [[station["longitude"], station["latitude"]] for station in stations]


def test_weather_profile_is_ordered_by_station(
    client: TestClient, seeded_weather_today: str
) -> None:
    response = client.get("/api/v1/routes/1/weather-profile")
    assert response.status_code == 200
    assert [point["station_order"] for point in response.json()["data"]["points"]] == list(range(1, 9))


def test_weather_profile_filters_requested_metrics(
    client: TestClient, seeded_weather_today: str
) -> None:
    response = client.get(
        "/api/v1/routes/1/weather-profile",
        params={"date": seeded_weather_today, "metrics": "temperature,aqi,temperature"},
    )

    assert response.status_code == 200
    profile = response.json()["data"]
    assert profile["date"] == seeded_weather_today
    assert set(profile["points"][0]) == {
        "city_id",
        "city_name",
        "station_order",
        "distance_from_origin_km",
        "temperature_c",
        "aqi",
    }


def test_weather_profile_rejects_unknown_or_empty_metrics(client: TestClient) -> None:
    unknown_response = client.get(
        "/api/v1/routes/1/weather-profile", params={"metrics": "temperature,pressure"}
    )
    empty_response = client.get(
        "/api/v1/routes/1/weather-profile", params={"metrics": ""}
    )

    assert unknown_response.status_code == 422
    assert empty_response.status_code == 422


def test_unknown_city_returns_documented_not_found_response(client: TestClient) -> None:
    response = client.get("/api/v1/cities/999")
    assert response.status_code == 404
    assert response.json()["code"] == 40401


def test_city_weather_no_longer_depends_on_generated_poem(
    client: TestClient, seeded_weather_today: str
) -> None:
    response = client.get("/api/v1/cities/1/weather")
    assert response.status_code == 200
    assert "poem" not in response.json()["data"]


def test_city_weather_defaults_to_latest_available_observation(client: TestClient) -> None:
    response = client.get("/api/v1/cities/1/weather")

    assert response.status_code == 200
    assert response.json()["data"]["weather"] is not None
    assert response.json()["data"]["date"] == "2026-08-01"


def test_city_weather_uses_requested_date(client: TestClient) -> None:
    requested_date = current_date() - timedelta(days=1)
    with open_database() as connection:
        connection.execute(
            "UPDATE weather_observations SET observation_date = ?",
            (requested_date.isoformat(),),
        )
    response = client.get(
        "/api/v1/cities/1/weather", params={"date": requested_date.isoformat()}
    )

    assert response.status_code == 200
    assert response.json()["data"]["date"] == requested_date.isoformat()
    assert response.json()["data"]["weather"]["temperature_c"] == 29.4


def test_weather_date_only_supports_recent_fifteen_days(client: TestClient) -> None:
    unsupported_date = current_date() - timedelta(days=15)
    response = client.get(
        "/api/v1/cities/1/weather", params={"date": unsupported_date.isoformat()}
    )

    assert response.status_code == 422
    assert response.json()["code"] == 42200
    assert "最近 15 个自然日" in response.json()["message"]


def test_city_weather_exposes_pasquill_inputs_without_lapse_rate(
    client: TestClient, seeded_weather_today: str
) -> None:
    response = client.get("/api/v1/cities/1/weather")

    atmosphere = response.json()["data"]["atmosphere"]
    assert atmosphere["stability_class"] in {"A", "A-B", "B", "B-C", "C", "C-D", "D", "E", "F"}
    assert atmosphere["method"] == "pasquill-turner-estimate"
    assert atmosphere["inputs"]["cloud_cover_percent"] == 70
    assert "lapse_rate_c_per_km" not in atmosphere


def test_random_trip_returns_one_route_station_with_weather(
    client: TestClient, seeded_weather_today: str
) -> None:
    response = client.get(
        "/api/v1/routes/1/random-trip", params={"date": seeded_weather_today}
    )

    assert response.status_code == 200
    trip = response.json()["data"]
    assert trip["route_id"] == 1
    assert trip["date"] == seeded_weather_today
    assert trip["station"]["station_order"] in range(1, 9)
    assert trip["weather"] is not None
    assert set(trip["weather"]) == {
        "temperature_c",
        "feels_like_c",
        "text",
        "humidity_percent",
        "aqi",
        "stability_level",
    }


def test_random_trip_returns_not_found_for_unknown_route(client: TestClient) -> None:
    response = client.get("/api/v1/routes/999/random-trip")

    assert response.status_code == 404


def test_city_poem_is_not_generated_on_demand(client: TestClient) -> None:
    response = client.post("/api/v1/cities/1/poem")
    assert response.status_code == 404


def test_route_advice_returns_latest_saved_report(client: TestClient) -> None:
    with open_database() as connection:
        connection.execute(
            """INSERT INTO travel_reports (
                   route_id, travel_date, content, model_name, prompt_hash, generated_at, source_snapshot_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(route_id, travel_date) DO UPDATE SET content = excluded.content""",
            (1, current_date().isoformat(), VALID_ADVICE, "test-model", "test-hash", "2026-08-02T08:20:00Z", "[]"),
        )
    response = client.get("/api/v1/routes/1/travel-advice")
    assert response.status_code == 200
    assert response.json()["data"]["content"] == VALID_ADVICE
    assert response.json()["data"]["is_stale"] is False


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (RouteWeatherUnavailableError("今天没有观测"), 409),
        (DeepSeekError("模型服务不可用"), 503),
    ],
)
def test_create_travel_advice_exposes_actionable_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    def fail_generation(_route_id):
        raise error

    monkeypatch.setattr("backend.main.generate_travel_advice_now", fail_generation)
    response = client.post("/api/v1/routes/1/travel-advice")

    assert response.status_code == expected_status
    assert response.json()["message"] == str(error)


def test_manual_update_returns_business_conflict_when_daily_update_is_running(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_update():
        from backend.daily_update import UpdateAlreadyRunningError

        raise UpdateAlreadyRunningError("观测更新正在进行，请稍后重试")

    monkeypatch.setattr("backend.main.refresh_weather_now", reject_update)

    response = client.post("/api/v1/weather/refresh")

    assert response.status_code == 409
    assert response.json()["code"] == 40901
    assert response.json()["message"] == "观测更新正在进行，请稍后重试"


def test_database_migration_adds_station_coordinates(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    import sqlite3

    connection = sqlite3.connect(database_path)
    connection.execute(
        """CREATE TABLE route_stations (
            id INTEGER PRIMARY KEY, route_id INTEGER NOT NULL, city_id INTEGER NOT NULL,
            station_order INTEGER NOT NULL, distance_from_origin_km REAL NOT NULL,
            station_name TEXT NOT NULL, UNIQUE(route_id, city_id), UNIQUE(route_id, station_order)
        )"""
    )
    connection.commit()
    connection.close()

    initialize_database()
    with open_database() as connection:
        seed_database(connection)
        station = connection.execute("SELECT longitude, latitude FROM route_stations WHERE route_id = 1 AND city_id = 1").fetchone()
    assert station["longitude"] is not None
    assert station["latitude"] is not None


def test_database_migration_replaces_obsolete_atmosphere_schema(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "legacy-atmosphere.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    import sqlite3

    connection = sqlite3.connect(database_path)
    connection.execute(
        """CREATE TABLE atmosphere_analyses (
               id INTEGER PRIMARY KEY, weather_observation_id INTEGER NOT NULL,
               city_id INTEGER NOT NULL, stability_level TEXT NOT NULL,
               lapse_rate_c_per_km REAL NOT NULL, pressure_hpa REAL,
               explanation TEXT NOT NULL, calculation_version TEXT NOT NULL
           )"""
    )
    connection.commit()
    connection.close()

    initialize_database()

    with open_database() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(atmosphere_analyses)")}
    assert "stability_class" in columns
    assert "solar_elevation_deg" in columns
    assert "lapse_rate_c_per_km" not in columns
