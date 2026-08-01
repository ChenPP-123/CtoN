"""Create a city weather poem without leaking provider concerns into routes."""

from __future__ import annotations

import sqlite3
from typing import Any

from .config import get_deepseek_settings
from .external.deepseek_api import DeepSeekClient
from .services import get_weather


def generate_city_poem(connection: sqlite3.Connection, city_id: int) -> dict[str, Any] | None:
    weather = get_weather(connection, city_id)
    if weather is None:
        return None
    poem = DeepSeekClient(get_deepseek_settings()).generate_poem(_poem_prompt(weather))
    return {"city_id": city_id, "city_name": weather["city"]["name"], "poem": poem}


def _poem_prompt(weather: dict[str, Any]) -> str:
    current = weather["weather"] or {}
    air_quality = weather["air_quality"] or {}
    atmosphere = weather["atmosphere"] or {}
    return "\n".join(
        [
            "请为高铁沿线的一座城市写一首现代中文短诗。",
            "只输出诗歌正文，不要标题、解释、引号或 Markdown。",
            "写 4 至 6 行，每行不超过 18 个汉字；语气克制，避免陈词滥调。",
            f"城市：{weather['city']['name']}",
            f"观测日期：{weather['date']}",
            f"天气：{current.get('text') or '暂无数据'}，气温：{current.get('temperature_c') or '暂无数据'}°C，湿度：{current.get('humidity_percent') or '暂无数据'}%",
            f"空气质量 AQI：{air_quality.get('aqi') or '暂无数据'}",
            f"大气状态：{atmosphere.get('stability_level') or '暂无数据'}；{atmosphere.get('explanation') or ''}",
        ]
    )
