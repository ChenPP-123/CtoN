import httpx2 as httpx
import pytest

from backend.config import QWeatherSettings
from backend.external.qweather_api import QWeatherClient, QWeatherError


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


def test_qweather_client_parses_daily_day_and_night_forecast(monkeypatch) -> None:
    def fake_get(url: str, **kwargs) -> httpx.Response:
        request = httpx.Request("GET", url, headers=kwargs["headers"])
        assert kwargs["params"] == {"days": "1", "localTime": "true", "lang": "zh"}
        return httpx.Response(200, request=request, json={
            "days": [{
                "forecastStartTime": "2026-08-27T00:00+08:00",
                "temperatureMax": {"value": 34, "unit": "°C"},
                "temperatureMin": {"value": 25, "unit": "°C"},
                "uvIndexMax": 8,
                "daytime": {
                    "condition": {"text": "阵雨"},
                    "humidity": 0.68,
                    "wind": {"direction": {"compass": "se"}, "speed": {"value": 10.8, "unit": "km/h"}},
                    "precipitation": {"probability": 0.7},
                },
                "nighttime": {
                    "condition": {"text": "多云"},
                    "humidity": 0.82,
                    "wind": {"direction": {"compass": "e"}, "speed": {"value": 2.0, "unit": "m/s"}},
                    "precipitation": {"probability": 0.3},
                },
            }],
        })

    monkeypatch.setattr(httpx, "get", fake_get)
    client = QWeatherClient(QWeatherSettings(api_key="test-key", base_url="https://weather.example"))

    forecast = client.get_daily_forecast(29.563, 106.552)

    assert forecast.forecast_date == "2026-08-27"
    assert forecast.day_weather_text == "阵雨"
    assert forecast.night_weather_text == "多云"
    assert forecast.precipitation_probability_percent == 70
    assert forecast.humidity_percent == 75
    assert forecast.wind_speed_ms == 3.0
    assert forecast.wind_direction == "se"
    assert forecast.uv_index == 8


def test_daily_forecast_allows_optional_fields_to_be_missing(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: httpx.Response(
        200,
        request=httpx.Request("GET", url),
        json={"days": [{
            "forecastStartTime": "2026-08-27T00:00+08:00",
            "temperatureMax": {"value": 30},
            "temperatureMin": {"value": 20},
            "daytime": {"condition": {"text": "晴"}},
            "nighttime": {"condition": {"text": "多云"}},
        }]},
    ))
    client = QWeatherClient(QWeatherSettings(api_key="test-key", base_url="https://weather.example"))

    forecast = client.get_daily_forecast(29.563, 106.552)

    assert forecast.precipitation_probability_percent is None
    assert forecast.wind_speed_ms is None
    assert forecast.humidity_percent is None


@pytest.mark.parametrize(
    ("response", "expected_message"),
    [
        (httpx.Response(200, json={"code": "403"}), "错误码：403"),
        (httpx.Response(200, text="not-json"), "非 JSON"),
        (httpx.Response(200, json={"days": []}), "缺少逐日预报数据"),
    ],
)
def test_daily_forecast_rejects_unusable_responses(monkeypatch, response, expected_message) -> None:
    def fake_get(url: str, **_kwargs) -> httpx.Response:
        response.request = httpx.Request("GET", url)
        return response

    monkeypatch.setattr(httpx, "get", fake_get)
    client = QWeatherClient(QWeatherSettings(api_key="test-key", base_url="https://weather.example"))

    with pytest.raises(QWeatherError, match=expected_message):
        client.get_daily_forecast(29.563, 106.552)


def test_daily_forecast_wraps_timeout(monkeypatch) -> None:
    def time_out(url: str, **_kwargs):
        raise httpx.TimeoutException("timeout", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", time_out)
    client = QWeatherClient(QWeatherSettings(api_key="test-key", base_url="https://weather.example"))

    with pytest.raises(QWeatherError, match="请求失败"):
        client.get_daily_forecast(29.563, 106.552)
