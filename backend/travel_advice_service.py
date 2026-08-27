"""Generate one practical recommendation from the active route's latest weather."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .config import get_deepseek_settings
from .database import DatabaseConnection, DatabaseRow
from .external.deepseek_api import DeepSeekClient, DeepSeekError
from .services import get_latest_travel_advice
from .travel_advice_validation import validate_travel_advice
from .time_utils import current_date


class RouteWeatherUnavailableError(RuntimeError):
    """The route has no observations for today."""


def generate_travel_advice(
    connection: DatabaseConnection,
    route_id: int,
    *,
    run_slot: str = "manual",
    forecasts: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    route = connection.execute("SELECT id, name FROM routes WHERE id = %s", (route_id,)).fetchone()
    if not route:
        raise LookupError("路线不存在")

    travel_date = current_date().isoformat()
    observations = _get_route_observations(connection, route_id, travel_date)
    advice_inputs = _build_advice_inputs(observations, run_slot, forecasts or {})
    if not advice_inputs:
        raise RouteWeatherUnavailableError("今天还没有可用于生成路线建议的天气数据")

    settings = get_deepseek_settings()
    prompt = _advice_prompt(route["name"], travel_date, advice_inputs)
    content = _generate_valid_advice(DeepSeekClient(settings), prompt)
    generated_at = datetime.now(timezone.utc).isoformat()
    source_snapshot = {"run_slot": run_slot, "sources": advice_inputs}
    connection.execute(
        """INSERT INTO travel_reports (
               route_id, travel_date, content, model_name, prompt_hash, generated_at, source_snapshot_json
           ) VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT(route_id, travel_date) DO UPDATE SET
               content = excluded.content,
               model_name = excluded.model_name,
               prompt_hash = excluded.prompt_hash,
               generated_at = excluded.generated_at,
               source_snapshot_json = excluded.source_snapshot_json""",
        (
            route_id,
            travel_date,
            content,
            settings.model,
            hashlib.sha256(prompt.encode()).hexdigest(),
            generated_at,
            json.dumps(source_snapshot, ensure_ascii=False, sort_keys=True),
        ),
    )
    saved_advice = get_latest_travel_advice(connection, route_id)
    if saved_advice is None:
        raise RuntimeError("路线建议保存后无法读取")
    return saved_advice


def _get_route_observations(
    connection: DatabaseConnection, route_id: int, travel_date: str
) -> list[DatabaseRow]:
    return connection.execute(
        """SELECT rs.station_order, rs.station_name, c.id AS city_id, c.name AS city_name,
                  w.id AS weather_observation_id, w.observed_at, w.temperature_c, w.feels_like_c,
                  w.weather_text, w.humidity_percent, w.wind_speed_ms,
                  w.wind_direction, w.visibility_km, aq.aqi
           FROM route_stations rs
           JOIN cities c ON c.id = rs.city_id
           LEFT JOIN weather_observations w
                  ON w.city_id = c.id AND w.observation_date = %s
           LEFT JOIN air_quality_observations aq ON aq.weather_observation_id = w.id
           WHERE rs.route_id = %s ORDER BY rs.station_order""",
        (travel_date, route_id),
    ).fetchall()


def _build_advice_inputs(
    observations: list[DatabaseRow],
    run_slot: str,
    forecasts: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    for observation in observations:
        forecast = forecasts.get(observation["city_id"]) if run_slot == "morning" else None
        if forecast:
            inputs.append(
                {
                    "city_id": observation["city_id"],
                    "city_name": observation["city_name"],
                    "station_name": observation["station_name"],
                    "source_type": "forecast",
                    **forecast,
                    "aqi": observation["aqi"],
                }
            )
            continue
        if observation["weather_observation_id"] is None:
            continue
        inputs.append(
            {
                "city_id": observation["city_id"],
                "city_name": observation["city_name"],
                "station_name": observation["station_name"],
                "source_type": "observation",
                "weather_observation_id": observation["weather_observation_id"],
                "observed_at": observation["observed_at"],
                "temperature_c": observation["temperature_c"],
                "feels_like_c": observation["feels_like_c"],
                "weather_text": observation["weather_text"],
                "humidity_percent": observation["humidity_percent"],
                "wind_speed_ms": observation["wind_speed_ms"],
                "wind_direction": observation["wind_direction"],
                "visibility_km": observation["visibility_km"],
                "aqi": observation["aqi"],
            }
        )
    return inputs


def _generate_valid_advice(client: DeepSeekClient, prompt: str) -> str:
    draft = client.generate_text(prompt).strip()
    validation_error = validate_travel_advice(draft)
    if validation_error is None:
        return draft

    revised_advice = client.generate_text(_revision_prompt(prompt, draft, validation_error)).strip()
    revised_validation_error = validate_travel_advice(revised_advice)
    if revised_validation_error is None:
        return revised_advice
    raise DeepSeekError(f"DeepSeek 连续两次返回不合格的路线建议：{revised_validation_error}")
def _revision_prompt(original_prompt: str, draft: str, validation_error: str) -> str:
    return "\n".join(
        [
            original_prompt,
            "",
            "上一次草稿不合格，请完整重写全文，不要续写、补写或截短原稿。",
            f"不合格原因：{validation_error}",
            f"上一次草稿：{draft}",
            "请重新遵守全部要求，只输出重写后的正文。",
        ]
    )


def _advice_prompt(
    route_name: str, travel_date: str, advice_inputs: list[dict[str, Any]]
) -> str:
    weather_lines = [_weather_input_line(item) for item in advice_inputs]
    return "\n".join(
        [
            "请根据以下高铁沿线天气数据，写一段可执行的中文旅途建议。",
            "正文硬性限制为50至100个汉字，以65至85个汉字为目标，写成一个自然段中的2至3个完整句子。",
            "必须以。！或？收尾；最后一句必须给出完整、可执行的动作，不能以并、及时、定时、注意等尚需补充宾语的表达草率结束。",
            "只输出正文，不要标题、列表、Markdown或免责声明；不要通过截短句子满足字数。",
            "优先概括沿线温差、降雨和雨具需求、空气质量、防晒补水；不要虚构缺失数据。",
            "标注为预报的数据只代表可能发生的情况，必须使用预计、可能等措辞，禁止描述成已经发生的事实；实况可按其真实观测时间描述。",
            f"路线：{route_name}",
            f"日期：{travel_date}",
            *weather_lines,
        ]
    )


def _weather_input_line(weather_input: dict[str, Any]) -> str:
    if weather_input["source_type"] == "forecast":
        return (
            f"{weather_input['station_name']}【预报】：白天{weather_input['day_weather_text']}、"
            f"夜间{weather_input['night_weather_text']}，"
            f"{weather_input['temperature_min_c']}至{weather_input['temperature_max_c']}°C，"
            f"最高降水概率{_display(weather_input['precipitation_probability_percent'])}%，"
            f"湿度{_display(weather_input['humidity_percent'])}%，"
            f"{weather_input.get('wind_direction') or '风向暂无'}"
            f"{_display(weather_input.get('wind_speed_ms'))}m/s，"
            f"紫外线指数{_display(weather_input.get('uv_index'))}，"
            f"当前AQI {_display(weather_input.get('aqi'))}"
        )
    return (
        f"{weather_input['station_name']}【实况，观测时间{weather_input['observed_at']}】："
        f"{weather_input['weather_text']}，{weather_input['temperature_c']}°C，"
        f"体感{_display(weather_input['feels_like_c'])}°C，"
        f"湿度{weather_input['humidity_percent']}%，"
        f"{weather_input.get('wind_direction') or '风向暂无'}"
        f"{_display(weather_input.get('wind_speed_ms'))}m/s，"
        f"能见度{_display(weather_input.get('visibility_km'))}km，"
        f"AQI {_display(weather_input.get('aqi'))}"
    )


def _display(value: object) -> object:
    return value if value is not None else "暂无"
