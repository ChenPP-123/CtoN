"""Generate one practical recommendation from the active route's latest weather."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any

from .config import get_deepseek_settings
from .external.deepseek_api import DeepSeekClient, DeepSeekError
from .services import get_latest_travel_advice
from .travel_advice_validation import validate_travel_advice


class RouteWeatherUnavailableError(RuntimeError):
    """The route has no observations for today."""


def generate_travel_advice(connection: sqlite3.Connection, route_id: int) -> dict[str, Any]:
    route = connection.execute("SELECT id, name FROM routes WHERE id = ?", (route_id,)).fetchone()
    if not route:
        raise LookupError("路线不存在")

    travel_date = date.today().isoformat()
    snapshots = _get_route_snapshots(connection, route_id, travel_date)
    available_snapshots = [snapshot for snapshot in snapshots if snapshot["weather_observation_id"] is not None]
    if not available_snapshots:
        raise RouteWeatherUnavailableError("今天还没有可用于生成路线建议的天气观测")

    settings = get_deepseek_settings()
    prompt = _advice_prompt(route["name"], travel_date, snapshots)
    content = _generate_valid_advice(DeepSeekClient(settings), prompt)
    generated_at = datetime.now(timezone.utc).isoformat()
    source_snapshot_ids = [snapshot["weather_observation_id"] for snapshot in available_snapshots]
    connection.execute(
        """INSERT INTO travel_reports (
               route_id, travel_date, content, model_name, prompt_hash, generated_at, source_snapshot_json
           ) VALUES (?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(source_snapshot_ids),
        ),
    )
    saved_advice = get_latest_travel_advice(connection, route_id)
    if saved_advice is None:
        raise RuntimeError("路线建议保存后无法读取")
    return saved_advice


def _get_route_snapshots(connection: sqlite3.Connection, route_id: int, travel_date: str) -> list[sqlite3.Row]:
    return connection.execute(
        """SELECT rs.station_order, rs.station_name, c.name AS city_name,
                  w.id AS weather_observation_id, w.temperature_c, w.feels_like_c,
                  w.weather_text, w.humidity_percent, w.wind_speed_ms,
                  w.wind_direction, w.visibility_km, aq.aqi
           FROM route_stations rs
           JOIN cities c ON c.id = rs.city_id
           LEFT JOIN weather_observations w
                  ON w.city_id = c.id AND w.observation_date = ?
           LEFT JOIN air_quality_observations aq ON aq.weather_observation_id = w.id
           WHERE rs.route_id = ? ORDER BY rs.station_order""",
        (travel_date, route_id),
    ).fetchall()


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


def _advice_prompt(route_name: str, travel_date: str, snapshots: list[sqlite3.Row]) -> str:
    observations = []
    for snapshot in snapshots:
        if snapshot["weather_observation_id"] is None:
            observations.append(f"{snapshot['station_name']}：暂无今日观测")
            continue
        observations.append(
            f"{snapshot['station_name']}：{snapshot['weather_text']}，"
            f"{snapshot['temperature_c']}°C，体感{snapshot['feels_like_c'] or '暂无'}°C，"
            f"湿度{snapshot['humidity_percent']}%，{snapshot['wind_direction'] or '风向暂无'}"
            f"{snapshot['wind_speed_ms'] or '暂无'}m/s，能见度{snapshot['visibility_km'] or '暂无'}km，"
            f"AQI {snapshot['aqi'] if snapshot['aqi'] is not None else '暂无'}"
        )
    return "\n".join(
        [
            "请根据以下高铁沿线当天观测，写一段可执行的中文旅途建议。",
            "正文硬性限制为50至100个汉字，以65至85个汉字为目标，写成一个自然段中的2至3个完整句子。",
            "必须以。！或？收尾；最后一句必须给出完整、可执行的动作，不能以并、及时、定时、注意等尚需补充宾语的表达草率结束。",
            "只输出正文，不要标题、列表、Markdown或免责声明；不要通过截短句子满足字数。",
            "优先概括沿线温差、降雨和雨具需求、空气质量、防晒补水；不要虚构缺失数据。",
            f"路线：{route_name}",
            f"日期：{travel_date}",
            *observations,
        ]
    )
