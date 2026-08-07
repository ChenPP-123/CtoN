import httpx2 as httpx

from backend.config import QWeatherSettings
from backend.external.qweather_api import QWeatherClient


def test_qweather_client_converts_weather_units_and_air_quality(monkeypatch) -> None:
    def fake_get(url: str, **kwargs) -> httpx.Response:
        request = httpx.Request("GET", url, headers=kwargs["headers"])
        if "/v7/weather/now" in url:
            return httpx.Response(200, request=request, json={
                "code": "200",
                "now": {
                    "obsTime": "2026-08-01T12:00+08:00", "temp": "30", "feelsLike": "33",
                    "icon": "104", "text": "阴", "humidity": "75", "windSpeed": "18",
                    "windDir": "东风", "vis": "9", "pressure": "1002", "cloud": "86",
                },
            })
        return httpx.Response(200, request=request, json={
            "indexes": [{"code": "cn-mep", "aqi": "42", "primaryPollutant": {"name": "PM2.5"}}],
            "pollutants": [
                {"code": "pm2p5", "concentration": {"value": "18.5"}},
                {"code": "pm10", "concentration": {"value": "34"}},
            ],
        })

    monkeypatch.setattr(httpx, "get", fake_get)
    client = QWeatherClient(QWeatherSettings(api_key="test-key", base_url="https://weather.example"))

    weather = client.get_current_weather("101040100")
    air_quality = client.get_current_air_quality(29.563, 106.552)

    assert weather.wind_speed_ms == 5.0
    assert weather.temperature_c == 30.0
    assert weather.cloud_cover_percent == 86
    assert air_quality.aqi == 42
    assert air_quality.pm25_ug_m3 == 18.5
    assert air_quality.pm10_ug_m3 == 34.0
