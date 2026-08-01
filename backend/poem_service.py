"""Create a city weather poem without leaking provider concerns into routes."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
import sqlite3
from typing import Any

from .config import get_deepseek_settings
from .external.deepseek_api import DeepSeekClient, DeepSeekError
from .services import get_weather


def generate_city_poem(connection: sqlite3.Connection, city_id: int) -> dict[str, Any] | None:
    weather = get_weather(connection, city_id)
    if weather is None or weather["weather"] is None:
        return None
    settings = get_deepseek_settings()
    prompt = _poem_prompt(weather)
    poem = _generate_valid_poem(DeepSeekClient(settings), prompt)
    observation = connection.execute(
        "SELECT id FROM weather_observations WHERE city_id = ? ORDER BY observed_at DESC LIMIT 1",
        (city_id,),
    ).fetchone()
    if not observation:
        return None
    generated_at = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """INSERT INTO poems (city_id, weather_observation_id, content, model_name, prompt_hash, generated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(weather_observation_id) DO UPDATE SET
               content = excluded.content,
               model_name = excluded.model_name,
               prompt_hash = excluded.prompt_hash,
               generated_at = excluded.generated_at""",
        (city_id, observation["id"], poem, settings.model, hashlib.sha256(prompt.encode()).hexdigest(), generated_at),
    )
    return {"city_id": city_id, "city_name": weather["city"]["name"], "poem": poem}


def _generate_valid_poem(client: DeepSeekClient, prompt: str) -> str:
    for _ in range(2):
        poem = client.generate_poem(prompt)
        if _is_regulated_poem(poem):
            return poem
    raise DeepSeekError("DeepSeek 返回的诗歌不符合两句或四句五言、七言绝句格式")


def _is_regulated_poem(poem: str) -> bool:
    if not re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff，。！？；、…—\s]+", poem):
        return False
    lines = [line.strip() for line in poem.splitlines() if line.strip()]
    if len(lines) not in (2, 4):
        return False
    line_lengths = {len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", line)) for line in lines}
    return len(line_lengths) == 1 and line_lengths <= {5, 7}


def _poem_prompt(weather: dict[str, Any]) -> str:
    current = weather["weather"] or {}
    air_quality = weather["air_quality"] or {}
    atmosphere = weather["atmosphere"] or {}
    return "\n".join(
        [
            "请为高铁沿线的一座城市写一首中文绝句。",
            "只输出诗歌正文，不要标题、解释、引号或 Markdown。",
            "仅写两句或四句；同一首诗每句必须都是五个或都是七个汉字。可使用中文标点；语气克制，避免陈词滥调。",
            f"城市：{weather['city']['name']}",
            f"观测日期：{weather['date']}",
            f"天气：{current.get('text') or '暂无数据'}，气温：{current.get('temperature_c') or '暂无数据'}°C，湿度：{current.get('humidity_percent') or '暂无数据'}%",
            f"空气质量 AQI：{air_quality.get('aqi') or '暂无数据'}",
            f"大气状态：{atmosphere.get('stability_level') or '暂无数据'}；{atmosphere.get('explanation') or ''}",
        ]
    )
