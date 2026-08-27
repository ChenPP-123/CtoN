import json

import pytest

from backend.database import open_database
from backend.external.deepseek_api import DeepSeekError
from backend.services import get_latest_travel_advice
from backend.travel_advice_service import (
    RouteWeatherUnavailableError,
    _generate_valid_advice,
    generate_travel_advice,
)
from backend.travel_advice_validation import validate_travel_advice
from backend.time_utils import current_date


VALID_ADVICE = "沿线天气湿热多变，建议穿轻薄透气衣物并及时补水。重庆至恩施段可能有雨，请随身携带雨具。武汉以后注意防晒，空气质量整体适合出行。"
REPLACEMENT_ADVICE = "沿线今日湿热且温差明显，建议穿轻薄透气衣物并分次补水。重庆至恩施段可能有雨，请将雨具放在随手可取处。武汉以后紫外线较强，出站前请补涂防晒霜。"


def test_generate_advice_retries_once_then_saves_report(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with open_database() as connection:
        connection.execute("UPDATE weather_observations SET observation_date = %s", (current_date().isoformat(),))

    generated = iter(["太短", VALID_ADVICE])
    prompts = []

    def generate_text(_client, prompt):
        prompts.append(prompt)
        return next(generated)

    monkeypatch.setattr("backend.travel_advice_service.DeepSeekClient.generate_text", generate_text)

    with open_database() as connection:
        result = generate_travel_advice(connection, 1)

    assert result["content"] == VALID_ADVICE
    assert result["travel_date"] == current_date().isoformat()
    assert result["is_stale"] is False
    assert "上一次草稿：太短" in prompts[1]
    assert "不合格原因：汉字数不足" in prompts[1]
    assert "完整重写全文，不要续写、补写或截短原稿" in prompts[1]
    assert "以65至85个汉字为目标" in prompts[0]
    assert "2至3个完整句子" in prompts[0]
    assert "不能以并、及时、定时、注意等" in prompts[0]


def test_failed_generation_preserves_last_successful_advice(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with open_database() as connection:
        connection.execute("UPDATE weather_observations SET observation_date = %s", (current_date().isoformat(),))
        connection.execute(
            """INSERT INTO travel_reports (
                   route_id, travel_date, content, model_name, prompt_hash, generated_at, source_snapshot_json
               ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (1, current_date().isoformat(), VALID_ADVICE, "old-model", "old-hash", "2026-08-01T08:00:00Z", "[]"),
        )

    monkeypatch.setattr("backend.travel_advice_service.DeepSeekClient.generate_text", lambda _client, _prompt: "太短")
    with pytest.raises(DeepSeekError):
        with open_database() as connection:
            generate_travel_advice(connection, 1)

    with open_database() as connection:
        saved = get_latest_travel_advice(connection, 1)
    assert saved["content"] == VALID_ADVICE
    assert saved["model_name"] == "old-model"


def test_morning_advice_mixes_forecasts_with_observation_fallback(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    today = current_date().isoformat()
    with open_database() as connection:
        connection.execute("UPDATE weather_observations SET observation_date = %s", (today,))

    prompts: list[str] = []
    monkeypatch.setattr(
        "backend.travel_advice_service.DeepSeekClient.generate_text",
        lambda _client, prompt: prompts.append(prompt) or VALID_ADVICE,
    )
    forecast = {
        "forecast_date": today,
        "temperature_max_c": 34.0,
        "temperature_min_c": 25.0,
        "day_weather_text": "阵雨",
        "night_weather_text": "多云",
        "precipitation_probability_percent": 70,
        "humidity_percent": 75,
        "wind_speed_ms": 3.0,
        "wind_direction": "东南风",
        "uv_index": 8,
    }

    with open_database() as connection:
        generate_travel_advice(connection, 1, run_slot="morning", forecasts={1: forecast})
        snapshot_json = connection.execute(
            "SELECT source_snapshot_json FROM travel_reports WHERE route_id = 1 AND travel_date = %s",
            (today,),
        ).fetchone()["source_snapshot_json"]

    snapshot = json.loads(snapshot_json)
    assert snapshot["run_slot"] == "morning"
    assert snapshot["sources"][0]["source_type"] == "forecast"
    assert snapshot["sources"][1]["source_type"] == "observation"
    assert "重庆北站【预报】" in prompts[0]
    assert "万州北站【实况，观测时间" in prompts[0]
    assert "禁止描述成已经发生的事实" in prompts[0]


def test_morning_advice_can_use_forecasts_without_current_observations(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    today = current_date().isoformat()
    monkeypatch.setattr(
        "backend.travel_advice_service.DeepSeekClient.generate_text",
        lambda _client, _prompt: VALID_ADVICE,
    )
    forecast = {
        "forecast_date": today,
        "temperature_max_c": 30.0,
        "temperature_min_c": 20.0,
        "day_weather_text": "晴",
        "night_weather_text": "多云",
        "precipitation_probability_percent": None,
        "humidity_percent": None,
        "wind_speed_ms": None,
        "wind_direction": None,
        "uv_index": None,
    }

    with open_database() as connection:
        result = generate_travel_advice(
            connection,
            1,
            run_slot="morning",
            forecasts={city_id: forecast for city_id in range(1, 9)},
        )

    assert result["travel_date"] == today


def test_morning_advice_falls_back_when_all_forecasts_fail(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    prompts: list[str] = []
    monkeypatch.setattr(
        "backend.travel_advice_service.DeepSeekClient.generate_text",
        lambda _client, prompt: prompts.append(prompt) or VALID_ADVICE,
    )
    with open_database() as connection:
        connection.execute(
            "UPDATE weather_observations SET observation_date = %s",
            (current_date().isoformat(),),
        )
        generate_travel_advice(connection, 1, run_slot="morning", forecasts={})

    assert "【预报】" not in prompts[0]
    assert prompts[0].count("【实况，观测时间") == 8


def test_non_morning_advice_uses_observations_and_requires_today_data(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    prompts: list[str] = []
    monkeypatch.setattr(
        "backend.travel_advice_service.DeepSeekClient.generate_text",
        lambda _client, prompt: prompts.append(prompt) or VALID_ADVICE,
    )
    with open_database() as connection:
        connection.execute(
            "UPDATE weather_observations SET observation_date = %s",
            (current_date().isoformat(),),
        )
        generate_travel_advice(
            connection,
            1,
            run_slot="evening",
            forecasts={1: {"day_weather_text": "不应使用"}},
        )

    assert "【预报】" not in prompts[0]
    assert "【实况，观测时间" in prompts[0]

    with open_database() as connection:
        connection.execute("UPDATE weather_observations SET observation_date = '2026-01-01'")
        with pytest.raises(RouteWeatherUnavailableError):
            generate_travel_advice(connection, 1, run_slot="afternoon")


def test_valid_advice_failure_after_two_attempts() -> None:
    class InvalidClient:
        def __init__(self) -> None:
            self.calls = 0

        def generate_text(self, _prompt: str) -> str:
            self.calls += 1
            return "太短"

    client = InvalidClient()
    with pytest.raises(DeepSeekError):
        _generate_valid_advice(client, "prompt")
    assert client.calls == 2


def test_incomplete_83_character_advice_is_rejected() -> None:
    incomplete_advice = "重庆至南京沿线天气湿热且温差明显，重庆至恩施段可能有雨，宜昌以后云量减少。建议穿轻薄透气衣物并随身携带雨具，途中分次补水。武汉至南京空气质量总体都良好，紫外线较强，请加强防晒并定时"

    assert validate_travel_advice(incomplete_advice) == "缺少完整结尾：必须以。！或？收尾"


@pytest.mark.parametrize(
    ("advice", "expected_error"),
    [
        ("沿" * 25 + "。" + "途" * 25 + "。", None),
        ("沿" * 50 + "。" + "途" * 50 + "。", None),
        ("沿" * 24 + "。" + "途" * 25 + "。", "汉字数不足"),
        ("沿" * 50 + "。" + "途" * 51 + "。", "汉字数过多"),
        ("沿" * 25 + "。\n" + "途" * 25 + "。", "正文必须是一个自然段"),
        (VALID_ADVICE[:-1], "缺少完整结尾"),
        ("沿" * 50 + "。", "句子数量不符"),
        ("沿" * 13 + "。" + "途" * 13 + "。" + "晴" * 12 + "。" + "雨" * 12 + "。", "句子数量不符"),
    ],
)
def test_advice_validation_contract(advice: str, expected_error: str | None) -> None:
    validation_error = validate_travel_advice(advice)
    if expected_error is None:
        assert validation_error is None
    else:
        assert validation_error.startswith(expected_error)


def test_latest_advice_skips_incomplete_history(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with open_database() as connection:
        connection.execute("UPDATE weather_observations SET observation_date = %s", (current_date().isoformat(),))
        connection.execute(
            """INSERT INTO travel_reports (
                   route_id, travel_date, content, model_name, prompt_hash, generated_at, source_snapshot_json
               ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (1, "2026-08-01", VALID_ADVICE, "valid-model", "valid-hash", "2026-08-01T08:00:00Z", "[]"),
        )
        connection.execute(
            """INSERT INTO travel_reports (
                   route_id, travel_date, content, model_name, prompt_hash, generated_at, source_snapshot_json
               ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (1, current_date().isoformat(), "请加强防晒并定时", "invalid-model", "invalid-hash", "2026-08-02T08:00:00Z", "[]"),
        )
        advice = get_latest_travel_advice(connection, 1)

    assert advice["content"] == VALID_ADVICE
    assert advice["model_name"] == "valid-model"
    assert advice["is_stale"] is True

    monkeypatch.setattr(
        "backend.travel_advice_service.DeepSeekClient.generate_text",
        lambda _client, _prompt: REPLACEMENT_ADVICE,
    )
    with open_database() as connection:
        replacement = generate_travel_advice(connection, 1)

    assert replacement["content"] == REPLACEMENT_ADVICE
    assert replacement["is_stale"] is False


def test_latest_advice_returns_none_when_all_history_is_incomplete(monkeypatch) -> None:
    with open_database() as connection:
        connection.execute(
            """INSERT INTO travel_reports (
                   route_id, travel_date, content, model_name, prompt_hash, generated_at, source_snapshot_json
               ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (1, current_date().isoformat(), "请加强防晒并定时", "invalid-model", "invalid-hash", "2026-08-02T08:00:00Z", "[]"),
        )
        advice = get_latest_travel_advice(connection, 1)

    assert advice is None
