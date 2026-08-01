from fastapi.testclient import TestClient

from backend.main import app


def test_health_returns_database_status() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"]["database"] == "ok"


def test_route_includes_seeded_stations_in_order() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/routes/1")
    stations = response.json()["data"]["stations"]
    assert [station["city_name"] for station in stations] == ["重庆", "武汉", "南京"]
    assert [station["distance_from_origin_km"] for station in stations] == [0.0, 720.0, 1200.0]


def test_weather_profile_is_ordered_by_station() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/routes/1/weather-profile")
    assert response.status_code == 200
    assert [point["station_order"] for point in response.json()["data"]["points"]] == [1, 2, 3]


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
