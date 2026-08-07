"""Run the route's weather and travel-advice update once per business day."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import sqlite3
from threading import Lock
from typing import Any, Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .config import DailyUpdateSettings, get_daily_update_settings
from .database import open_database
from .services import get_latest_travel_advice
from .time_utils import current_date, current_datetime
from .travel_advice_service import generate_travel_advice
from .weather_service import refresh_active_route_weather


logger = logging.getLogger(__name__)
RunTrigger = Literal["scheduled", "startup"]
_update_lock = Lock()


class UpdateAlreadyRunningError(RuntimeError):
    """Another automatic or manual external-data update owns the process lock."""


def refresh_weather_now() -> dict[str, Any]:
    if not _update_lock.acquire(blocking=False):
        raise UpdateAlreadyRunningError("观测更新正在进行，请稍后重试")
    try:
        with open_database() as connection:
            return refresh_active_route_weather(connection)
    finally:
        _update_lock.release()


def generate_travel_advice_now(route_id: int) -> dict[str, Any]:
    if not _update_lock.acquire(blocking=False):
        raise UpdateAlreadyRunningError("观测更新正在进行，请稍后重试")
    try:
        with open_database() as connection:
            return generate_travel_advice(connection, route_id)
    finally:
        _update_lock.release()


def run_daily_update(trigger: RunTrigger = "scheduled") -> dict[str, Any]:
    """Claim and run today's update; a claimed date is never retried automatically."""
    _update_lock.acquire()
    try:
        run_date = current_date().isoformat()
        if not _claim_run(run_date, trigger):
            logger.info("每日更新已跳过：%s 已有执行记录", run_date)
            return {"run_date": run_date, "status": "skipped"}
        return _execute_claimed_run(run_date)
    finally:
        _update_lock.release()


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
            failed_cities = [city for city in weather_result["cities"] if city["status"] == "failed"]
            weather_failed_count = len(failed_cities)
            errors.extend(
                f"{city['city_name']}天气刷新失败：{city['reason']}" for city in failed_cities
            )
        except Exception as error:
            weather_failed_count = expected_city_count
            errors.append(f"天气刷新失败：{error}")
            logger.exception("每日天气刷新失败")

        route_ids = _active_route_ids()
        for route_id in route_ids:
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
    logger.info(
        "每日更新结束：date=%s status=%s weather=%s/%s advice=%s/%s",
        run_date,
        status,
        weather_updated_count,
        weather_updated_count + weather_failed_count,
        advice_generated_count,
        advice_generated_count + advice_failed_count,
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
            """SELECT COUNT(DISTINCT c.id)
               FROM cities c
               JOIN route_stations rs ON rs.city_id = c.id
               JOIN routes r ON r.id = rs.route_id
               WHERE r.is_active = 1"""
        ).fetchone()
    return row[0]


def _active_route_ids() -> list[int]:
    with open_database() as connection:
        rows = connection.execute("SELECT id FROM routes WHERE is_active = 1 ORDER BY id")
        return [row["id"] for row in rows]


def _claim_run(run_date: str, trigger: RunTrigger) -> bool:
    with open_database() as connection:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO daily_update_runs (
                   run_date, trigger, status, started_at
               ) VALUES (?, ?, 'running', ?)""",
            (run_date, trigger, _utc_now()),
        )
    return cursor.rowcount == 1


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
               SET status = ?, finished_at = ?, weather_updated_count = ?,
                   weather_failed_count = ?, advice_generated_count = ?,
                   advice_failed_count = ?, error_summary = ?
               WHERE run_date = ?""",
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


def start_daily_update_scheduler() -> AsyncIOScheduler | None:
    settings = get_daily_update_settings()
    if not settings.is_enabled:
        logger.info("每日自动更新已禁用")
        return None

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        run_daily_update,
        CronTrigger(
            hour=settings.run_time.hour,
            minute=settings.run_time.minute,
            timezone=settings.timezone,
        ),
        id="daily-weather-and-advice-update",
        name="每日天气与路线建议更新",
        kwargs={"trigger": "scheduled"},
        coalesce=True,
        max_instances=1,
        misfire_grace_time=7200,
        replace_existing=True,
    )
    if _needs_startup_catchup(settings):
        scheduler.add_job(
            run_daily_update,
            DateTrigger(run_date=current_datetime()),
            id="startup-daily-update-catchup",
            name="启动时补跑每日更新",
            kwargs={"trigger": "startup"},
            misfire_grace_time=60,
            replace_existing=True,
        )
    scheduler.start()
    logger.info(
        "每日自动更新已启动：每天 %s，时区 %s",
        settings.run_time.strftime("%H:%M"),
        settings.timezone.key,
    )
    return scheduler


def shutdown_daily_update_scheduler(scheduler: AsyncIOScheduler | None) -> None:
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)


def _needs_startup_catchup(settings: DailyUpdateSettings) -> bool:
    now = current_datetime()
    if now.timetz().replace(tzinfo=None) < settings.run_time:
        return False

    run_date = now.date().isoformat()
    with open_database() as connection:
        if connection.execute(
            "SELECT 1 FROM daily_update_runs WHERE run_date = ?", (run_date,)
        ).fetchone():
            return False
        if not _has_complete_data(connection, run_date):
            return True
        connection.execute(
            """INSERT INTO daily_update_runs (
                   run_date, trigger, status, started_at, finished_at, error_summary
               ) VALUES (?, 'startup', 'skipped', ?, ?, ?)""",
            (run_date, _utc_now(), _utc_now(), "当天观测和路线建议已完整"),
        )
    return False


def _has_complete_data(connection: sqlite3.Connection, run_date: str) -> bool:
    expected_city_count = connection.execute(
        """SELECT COUNT(DISTINCT c.id)
           FROM cities c
           JOIN route_stations rs ON rs.city_id = c.id
           JOIN routes r ON r.id = rs.route_id
           WHERE r.is_active = 1"""
    ).fetchone()[0]
    observed_city_count = connection.execute(
        """SELECT COUNT(DISTINCT w.city_id)
           FROM weather_observations w
           JOIN route_stations rs ON rs.city_id = w.city_id
           JOIN routes r ON r.id = rs.route_id
           WHERE r.is_active = 1 AND w.observation_date = ?""",
        (run_date,),
    ).fetchone()[0]
    if observed_city_count != expected_city_count:
        return False

    for route_id in _active_route_ids_for_connection(connection):
        advice = get_latest_travel_advice(connection, route_id)
        if advice is None or advice["travel_date"] != run_date:
            return False
    return True


def _active_route_ids_for_connection(connection: sqlite3.Connection) -> list[int]:
    rows = connection.execute("SELECT id FROM routes WHERE is_active = 1 ORDER BY id")
    return [row["id"] for row in rows]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
