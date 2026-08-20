"""Run mutually exclusive weather and travel-advice updates."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from .database import open_database
from .time_utils import current_date
from .travel_advice_service import generate_travel_advice
from .weather_service import refresh_active_route_weather


logger = logging.getLogger(__name__)
UPDATE_LEASE_NAME = "external-data-update"
UPDATE_LEASE_SECONDS = 360


class UpdateAlreadyRunningError(RuntimeError):
    """Another function invocation owns the database update lease."""


@contextmanager
def update_lease() -> Iterator[None]:
    owner_token = str(uuid.uuid4())
    if not _acquire_update_lease(owner_token):
        raise UpdateAlreadyRunningError("观测更新正在进行，请稍后重试")
    try:
        yield
    finally:
        _release_update_lease(owner_token)


def _acquire_update_lease(owner_token: str) -> bool:
    with open_database() as connection:
        claimed_lease = connection.execute(
            """INSERT INTO operation_leases (lease_name, owner_token, expires_at)
               VALUES (%s, %s, NOW() + %s * INTERVAL '1 second')
               ON CONFLICT(lease_name) DO UPDATE SET
                   owner_token = excluded.owner_token,
                   expires_at = excluded.expires_at
               WHERE operation_leases.expires_at <= NOW()
               RETURNING owner_token""",
            (UPDATE_LEASE_NAME, owner_token, UPDATE_LEASE_SECONDS),
        ).fetchone()
    return claimed_lease is not None


def _release_update_lease(owner_token: str) -> None:
    with open_database() as connection:
        connection.execute(
            "DELETE FROM operation_leases WHERE lease_name = %s AND owner_token = %s",
            (UPDATE_LEASE_NAME, owner_token),
        )


def refresh_weather_now() -> dict[str, Any]:
    with update_lease():
        with open_database() as connection:
            return refresh_active_route_weather(connection)


def generate_travel_advice_now(route_id: int) -> dict[str, Any]:
    with update_lease():
        with open_database() as connection:
            return generate_travel_advice(connection, route_id)


def run_daily_update() -> dict[str, Any]:
    """Claim and run today's cron update; a claimed date is not retried."""
    with update_lease():
        run_date = current_date().isoformat()
        if not _claim_run(run_date):
            logger.info("每日更新已跳过：%s 已有执行记录", run_date)
            return {"run_date": run_date, "status": "skipped"}
        return _execute_claimed_run(run_date)


def _execute_claimed_run(run_date: str) -> dict[str, Any]:
    weather_updated_count = 0
    weather_failed_count = 0
    advice_generated_count = 0
    advice_failed_count = 0
    errors: list[str] = []

    logger.info("开始每日天气与路线建议更新：%s", run_date)
    try:
        expected_city_count = _active_city_count()
        try:
            with open_database() as connection:
                weather_result = refresh_active_route_weather(connection)
            weather_updated_count = weather_result["updated_count"]
            failed_cities = [
                city for city in weather_result["cities"] if city["status"] == "failed"
            ]
            weather_failed_count = len(failed_cities)
            errors.extend(
                f"{city['city_name']}天气刷新失败：{city['reason']}"
                for city in failed_cities
            )
        except Exception as error:
            weather_failed_count = expected_city_count
            errors.append(f"天气刷新失败：{error}")
            logger.exception("每日天气刷新失败")

        for route_id in _active_route_ids():
            try:
                with open_database() as connection:
                    generate_travel_advice(connection, route_id)
                advice_generated_count += 1
            except Exception as error:
                advice_failed_count += 1
                errors.append(f"线路 {route_id} 建议生成失败：{error}")
                logger.exception("线路 %s 的每日建议生成失败", route_id)

        status = _run_status(
            weather_updated_count,
            weather_failed_count,
            advice_generated_count,
            advice_failed_count,
        )
    except Exception as error:
        status = "failed"
        errors.append(f"每日更新异常终止：{error}")
        logger.exception("每日更新异常终止")

    _finish_run(
        run_date,
        status=status,
        weather_updated_count=weather_updated_count,
        weather_failed_count=weather_failed_count,
        advice_generated_count=advice_generated_count,
        advice_failed_count=advice_failed_count,
        error_summary="\n".join(errors)[:4000] or None,
    )
    return {
        "run_date": run_date,
        "status": status,
        "weather_updated_count": weather_updated_count,
        "weather_failed_count": weather_failed_count,
        "advice_generated_count": advice_generated_count,
        "advice_failed_count": advice_failed_count,
        "errors": errors,
    }


def _run_status(
    weather_updated_count: int,
    weather_failed_count: int,
    advice_generated_count: int,
    advice_failed_count: int,
) -> str:
    if weather_failed_count == 0 and advice_failed_count == 0:
        return "succeeded"
    if weather_updated_count == 0 and advice_generated_count == 0:
        return "failed"
    return "partial"


def _active_city_count() -> int:
    with open_database() as connection:
        row = connection.execute(
            """SELECT COUNT(DISTINCT c.id) AS city_count
               FROM cities c
               JOIN route_stations rs ON rs.city_id = c.id
               JOIN routes r ON r.id = rs.route_id
               WHERE r.is_active = TRUE"""
        ).fetchone()
    return row["city_count"]


def _active_route_ids() -> list[int]:
    with open_database() as connection:
        rows = connection.execute("SELECT id FROM routes WHERE is_active = TRUE ORDER BY id")
        return [row["id"] for row in rows]


def _claim_run(run_date: str) -> bool:
    with open_database() as connection:
        claimed_run = connection.execute(
            """INSERT INTO daily_update_runs (run_date, trigger, status, started_at)
               VALUES (%s, 'cron', 'running', %s)
               ON CONFLICT(run_date) DO NOTHING
               RETURNING run_date""",
            (run_date, _utc_now()),
        ).fetchone()
    return claimed_run is not None


def _finish_run(
    run_date: str,
    *,
    status: str,
    weather_updated_count: int,
    weather_failed_count: int,
    advice_generated_count: int,
    advice_failed_count: int,
    error_summary: str | None,
) -> None:
    with open_database() as connection:
        connection.execute(
            """UPDATE daily_update_runs
               SET status = %s, finished_at = %s, weather_updated_count = %s,
                   weather_failed_count = %s, advice_generated_count = %s,
                   advice_failed_count = %s, error_summary = %s
               WHERE run_date = %s""",
            (
                status,
                _utc_now(),
                weather_updated_count,
                weather_failed_count,
                advice_generated_count,
                advice_failed_count,
                error_summary,
                run_date,
            ),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
