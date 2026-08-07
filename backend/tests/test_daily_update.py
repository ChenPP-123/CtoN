from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from backend.config import DailyUpdateSettings, get_daily_update_settings
from backend.daily_update import (
    UpdateAlreadyRunningError,
    _needs_startup_catchup,
    _update_lock,
    run_daily_update,
    start_daily_update_scheduler,
)
from backend.database import initialize_database, open_database
from backend.seed import seed_database


RUN_DATE = date(2026, 8, 7)
SHANGHAI = ZoneInfo("Asia/Shanghai")
SETTINGS = DailyUpdateSettings(is_enabled=True, run_time=time(6, 30), timezone=SHANGHAI)
VALID_ADVICE = (
    "沿线天气湿热多变，建议穿轻薄透气衣物并及时补水。"
    "重庆至恩施段可能有雨，请随身携带雨具。"
    "武汉以后注意防晒，空气质量整体适合出行。"
)


def initialize_seeded_database() -> None:
    initialize_database()
    with open_database() as connection:
        seed_database(connection)


def test_daily_update_runs_weather_before_advice_and_only_once(monkeypatch) -> None:
    initialize_seeded_database()
    events: list[str] = []
    monkeypatch.setattr("backend.daily_update.current_date", lambda: RUN_DATE)

    def generate_advice(_connection, route_id):
        events.append(f"advice:{route_id}")

    def refresh_weather(connection):
        events.append("weather")
        return {
            "updated_count": 8,
            "cities": [
                {"city_name": f"城市{index}", "status": "updated"} for index in range(8)
            ],
        }

    monkeypatch.setattr("backend.daily_update.refresh_active_route_weather", refresh_weather)
    monkeypatch.setattr("backend.daily_update.generate_travel_advice", generate_advice)

    first_result = run_daily_update("scheduled")
    second_result = run_daily_update("startup")

    assert events == ["weather", "advice:1"]
    assert first_result["status"] == "succeeded"
    assert second_result["status"] == "skipped"
    with open_database() as connection:
        run = connection.execute(
            "SELECT * FROM daily_update_runs WHERE run_date = ?", (RUN_DATE.isoformat(),)
        ).fetchone()
    assert run["trigger"] == "scheduled"
    assert run["status"] == "succeeded"
    assert run["weather_updated_count"] == 8
    assert run["advice_generated_count"] == 1


def test_partial_weather_failure_keeps_generating_advice(monkeypatch) -> None:
    initialize_seeded_database()
    monkeypatch.setattr("backend.daily_update.current_date", lambda: RUN_DATE)
    monkeypatch.setattr(
        "backend.daily_update.refresh_active_route_weather",
        lambda _connection: {
            "updated_count": 7,
            "cities": [
                *[
                    {"city_name": f"城市{index}", "status": "updated"}
                    for index in range(7)
                ],
                {"city_name": "南京", "status": "failed", "reason": "超时"},
            ],
        },
    )
    generated_routes: list[int] = []
    monkeypatch.setattr(
        "backend.daily_update.generate_travel_advice",
        lambda _connection, route_id: generated_routes.append(route_id),
    )

    result = run_daily_update("scheduled")

    assert result["status"] == "partial"
    assert result["weather_failed_count"] == 1
    assert result["advice_generated_count"] == 1
    assert generated_routes == [1]


def test_failed_run_is_recorded_and_not_retried_same_day(monkeypatch) -> None:
    initialize_seeded_database()
    calls = {"weather": 0, "advice": 0}
    monkeypatch.setattr("backend.daily_update.current_date", lambda: RUN_DATE)

    def fail_weather(_connection):
        calls["weather"] += 1
        raise RuntimeError("天气服务不可用")

    def fail_advice(_connection, _route_id):
        calls["advice"] += 1
        raise RuntimeError("模型服务不可用")

    monkeypatch.setattr("backend.daily_update.refresh_active_route_weather", fail_weather)
    monkeypatch.setattr("backend.daily_update.generate_travel_advice", fail_advice)

    first_result = run_daily_update("scheduled")
    second_result = run_daily_update("startup")

    assert first_result["status"] == "failed"
    assert second_result["status"] == "skipped"
    assert calls == {"weather": 1, "advice": 1}


def test_startup_catchup_only_runs_after_daily_time_when_data_is_missing(monkeypatch) -> None:
    initialize_seeded_database()
    monkeypatch.setattr(
        "backend.daily_update.current_datetime",
        lambda: datetime(2026, 8, 7, 6, 29, tzinfo=SHANGHAI),
    )
    assert _needs_startup_catchup(SETTINGS) is False

    monkeypatch.setattr(
        "backend.daily_update.current_datetime",
        lambda: datetime(2026, 8, 7, 6, 31, tzinfo=SHANGHAI),
    )
    assert _needs_startup_catchup(SETTINGS) is True


def test_startup_records_skip_when_daily_data_is_already_complete(monkeypatch) -> None:
    initialize_seeded_database()
    with open_database() as connection:
        connection.execute(
            "UPDATE weather_observations SET observation_date = ?",
            (RUN_DATE.isoformat(),),
        )
        connection.execute(
            """INSERT INTO travel_reports (
                   route_id, travel_date, content, model_name, prompt_hash,
                   generated_at, source_snapshot_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                1,
                RUN_DATE.isoformat(),
                VALID_ADVICE,
                "test-model",
                "test-hash",
                "2026-08-07T00:00:00+00:00",
                "[]",
            ),
        )
    monkeypatch.setattr(
        "backend.daily_update.current_datetime",
        lambda: datetime(2026, 8, 7, 6, 31, tzinfo=SHANGHAI),
    )

    assert _needs_startup_catchup(SETTINGS) is False
    with open_database() as connection:
        run = connection.execute(
            "SELECT status FROM daily_update_runs WHERE run_date = ?",
            (RUN_DATE.isoformat(),),
        ).fetchone()
    assert run["status"] == "skipped"


def test_manual_update_rejects_a_busy_process_lock() -> None:
    assert _update_lock.acquire(blocking=False)
    try:
        from backend.daily_update import refresh_weather_now

        with pytest.raises(UpdateAlreadyRunningError, match="正在进行"):
            refresh_weather_now()
    finally:
        _update_lock.release()


@pytest.mark.parametrize("value", ["6:30", "24:00", "not-a-time"])
def test_daily_update_time_rejects_invalid_values(monkeypatch, value) -> None:
    monkeypatch.setenv("DAILY_UPDATE_TIME", value)

    with pytest.raises(ValueError, match="HH:MM"):
        get_daily_update_settings()


def test_daily_update_settings_use_shanghai_defaults(monkeypatch) -> None:
    monkeypatch.delenv("DAILY_UPDATE_ENABLED", raising=False)
    monkeypatch.delenv("DAILY_UPDATE_TIME", raising=False)
    monkeypatch.delenv("APP_TIMEZONE", raising=False)

    settings = get_daily_update_settings()

    assert settings.is_enabled is True
    assert settings.run_time == time(6, 30)
    assert settings.timezone.key == "Asia/Shanghai"


def test_scheduler_registers_one_daily_cron_job(monkeypatch) -> None:
    captured_jobs: list[dict] = []

    class FakeScheduler:
        def __init__(self, *, timezone):
            self.timezone = timezone
            self.running = False

        def add_job(self, function, trigger, **options):
            captured_jobs.append(
                {"function": function, "trigger": trigger, "options": options}
            )

        def start(self):
            self.running = True

    monkeypatch.setattr("backend.daily_update.AsyncIOScheduler", FakeScheduler)
    monkeypatch.setattr("backend.daily_update.get_daily_update_settings", lambda: SETTINGS)
    monkeypatch.setattr("backend.daily_update._needs_startup_catchup", lambda _settings: False)

    scheduler = start_daily_update_scheduler()

    assert scheduler.running is True
    assert scheduler.timezone.key == "Asia/Shanghai"
    assert len(captured_jobs) == 1
    job = captured_jobs[0]
    assert job["options"]["id"] == "daily-weather-and-advice-update"
    assert job["options"]["coalesce"] is True
    assert job["options"]["max_instances"] == 1
    assert "hour='6'" in str(job["trigger"])
    assert "minute='30'" in str(job["trigger"])


def test_invalid_timezone_fails_clearly(monkeypatch) -> None:
    monkeypatch.setenv("APP_TIMEZONE", "Mars/Olympus")

    with pytest.raises(ValueError, match="APP_TIMEZONE"):
        get_daily_update_settings()
