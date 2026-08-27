from concurrent.futures import ThreadPoolExecutor
from datetime import date

from backend.daily_update import (
    _acquire_update_lease,
    _release_update_lease,
    run_scheduled_update,
)
from backend.database import open_database


RUN_DATE = date(2026, 8, 7)


def test_daily_update_runs_weather_before_advice_and_only_once(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr("backend.daily_update.current_date", lambda: RUN_DATE)

    def generate_advice(_connection, route_id, **_kwargs):
        events.append(f"advice:{route_id}")

    def refresh_weather(_connection):
        events.append("weather")
        return {
            "updated_count": 8,
            "cities": [
                {"city_name": f"城市{index}", "status": "updated"}
                for index in range(8)
            ],
        }

    monkeypatch.setattr(
        "backend.daily_update.refresh_active_route_weather", refresh_weather
    )
    monkeypatch.setattr(
        "backend.daily_update.generate_travel_advice", generate_advice
    )

    first_result = run_scheduled_update("afternoon")
    second_result = run_scheduled_update("afternoon")

    assert events == ["weather", "advice:1"]
    assert first_result["status"] == "succeeded"
    assert second_result["status"] == "skipped"
    with open_database() as connection:
        run = connection.execute(
            """SELECT * FROM scheduled_update_runs
               WHERE run_date = %s AND run_slot = 'afternoon'""",
            (RUN_DATE.isoformat(),),
        ).fetchone()
    assert run["trigger"] == "cron"
    assert run["status"] == "succeeded"
    assert run["weather_updated_count"] == 8
    assert run["advice_generated_count"] == 1


def test_partial_weather_failure_keeps_generating_advice(monkeypatch) -> None:
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
        lambda _connection, route_id, **_kwargs: generated_routes.append(route_id),
    )

    result = run_scheduled_update("afternoon")

    assert result["status"] == "partial"
    assert result["weather_failed_count"] == 1
    assert result["advice_generated_count"] == 1
    assert generated_routes == [1]


def test_failed_run_is_recorded_and_not_retried_same_day(monkeypatch) -> None:
    calls = {"weather": 0, "advice": 0}
    monkeypatch.setattr("backend.daily_update.current_date", lambda: RUN_DATE)

    def fail_weather(_connection):
        calls["weather"] += 1
        raise RuntimeError("天气服务不可用")

    def fail_advice(_connection, _route_id, **_kwargs):
        calls["advice"] += 1
        raise RuntimeError("模型服务不可用")

    monkeypatch.setattr(
        "backend.daily_update.refresh_active_route_weather", fail_weather
    )
    monkeypatch.setattr("backend.daily_update.generate_travel_advice", fail_advice)

    assert run_scheduled_update("evening")["status"] == "failed"
    assert run_scheduled_update("evening")["status"] == "skipped"
    assert calls == {"weather": 1, "advice": 1}


def test_each_slot_can_run_once_on_the_same_day(monkeypatch) -> None:
    monkeypatch.setattr("backend.daily_update.current_date", lambda: RUN_DATE)
    monkeypatch.setattr(
        "backend.daily_update.refresh_active_route_weather",
        lambda _connection: {
            "updated_count": 8,
            "cities": [
                {"city_name": f"城市{index}", "status": "updated"}
                for index in range(8)
            ],
        },
    )
    monkeypatch.setattr(
        "backend.daily_update.fetch_active_city_forecasts",
        lambda _connection: {
            "updated_count": 8,
            "cities": [
                {"city_name": f"城市{index}", "status": "updated"}
                for index in range(8)
            ],
            "forecasts": {1: {"forecast_date": RUN_DATE.isoformat()}},
        },
    )
    generated_slots: list[str] = []

    def generate_advice(_connection, _route_id, *, run_slot, forecasts):
        generated_slots.append(run_slot)
        assert bool(forecasts) is (run_slot == "morning")

    monkeypatch.setattr("backend.daily_update.generate_travel_advice", generate_advice)

    results = [
        run_scheduled_update(run_slot)
        for run_slot in ("morning", "afternoon", "evening")
    ]

    assert [result["status"] for result in results] == ["succeeded"] * 3
    assert generated_slots == ["morning", "afternoon", "evening"]
    with open_database() as connection:
        runs = connection.execute(
            """SELECT run_slot FROM scheduled_update_runs
               WHERE run_date = %s ORDER BY run_slot""",
            (RUN_DATE.isoformat(),),
        ).fetchall()
    assert [run["run_slot"] for run in runs] == ["afternoon", "evening", "morning"]


def test_invalid_slot_is_rejected_before_claiming_lease() -> None:
    import pytest

    with pytest.raises(ValueError, match="未知更新时段"):
        run_scheduled_update("midnight")


def test_same_slot_can_run_again_on_the_next_day(monkeypatch) -> None:
    run_dates = iter((RUN_DATE, date(2026, 8, 8)))
    monkeypatch.setattr("backend.daily_update.current_date", lambda: next(run_dates))
    monkeypatch.setattr(
        "backend.daily_update.refresh_active_route_weather",
        lambda _connection: {"updated_count": 0, "cities": []},
    )
    monkeypatch.setattr(
        "backend.daily_update.generate_travel_advice",
        lambda _connection, _route_id, **_kwargs: None,
    )

    first = run_scheduled_update("evening")
    second = run_scheduled_update("evening")

    assert first["status"] == "succeeded"
    assert second["status"] == "succeeded"
    assert first["run_date"] != second["run_date"]


def test_only_one_concurrent_instance_acquires_the_database_lease() -> None:
    owner_tokens = ("first-owner", "second-owner")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_acquire_update_lease, owner_tokens))

    assert sorted(results) == [False, True]
    winning_token = owner_tokens[results.index(True)]
    _release_update_lease(winning_token)


def test_expired_database_lease_can_be_reclaimed() -> None:
    assert _acquire_update_lease("expired-owner") is True
    with open_database() as connection:
        connection.execute(
            "UPDATE operation_leases SET expires_at = NOW() - INTERVAL '1 second'"
        )

    assert _acquire_update_lease("replacement-owner") is True
    _release_update_lease("replacement-owner")
