from fastapi.testclient import TestClient

from backend.database import initialize_database, open_database
from backend.main import app
from backend.seed import seed_database


def test_health_returns_database_status() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"]["database"] == "ok"


def test_route_includes_seeded_stations_in_order() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/routes/1")
    stations = response.json()["data"]["stations"]
    assert [station["station_name"] for station in stations] == ["重庆北站", "万州北站", "恩施站", "宜昌东站", "荆州站", "武汉站", "合肥南站", "南京南站"]
    assert [station["station_order"] for station in stations] == list(range(1, 9))
    assert all(-180 <= station["longitude"] <= 180 and -90 <= station["latitude"] <= 90 for station in stations)
    assert response.json()["data"]["geometry"]["coordinates"] == [[station["longitude"], station["latitude"]] for station in stations]


def test_weather_profile_is_ordered_by_station() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/routes/1/weather-profile")
    assert response.status_code == 200
    assert [point["station_order"] for point in response.json()["data"]["points"]] == list(range(1, 9))


def test_unknown_city_returns_documented_not_found_response() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/cities/999")
    assert response.status_code == 404
    assert response.json()["code"] == 40401


def test_city_poem_returns_generated_text(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.main.generate_city_poem",
        lambda connection, city_id: {"city_id": city_id, "city_name": "重庆", "poem": "雾从站台缓缓升起"},
    )
    with TestClient(app) as client:
        response = client.post("/api/v1/cities/1/poem")
    assert response.status_code == 200
    assert response.json()["data"]["poem"] == "雾从站台缓缓升起"


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
