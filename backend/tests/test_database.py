import os

import pytest
import psycopg

from backend.database import (
    initialize_database,
    open_database,
    require_test_database_url,
)
from backend.seed import seed_database


def test_cleanup_guard_rejects_non_test_database_names() -> None:
    with pytest.raises(ValueError, match="_test"):
        require_test_database_url("postgresql://user:pass@localhost/cton")


def test_schema_and_fixed_seed_are_repeatable_without_overwriting_observations() -> None:
    database_url = os.environ["TEST_DATABASE_URL"]
    with open_database() as connection:
        connection.execute(
            """UPDATE weather_observations
               SET temperature_c = %s, source = %s
               WHERE city_id = %s AND observation_date = %s""",
            (12.5, "qweather", 1, "2026-08-01"),
        )

    initialize_database(database_url)
    initialize_database(database_url)
    with open_database() as connection:
        seed_database(connection)
        seed_database(connection)
        observation = connection.execute(
            """SELECT temperature_c, source FROM weather_observations
               WHERE city_id = %s AND observation_date = %s""",
            (1, "2026-08-01"),
        ).fetchone()
        station_count = connection.execute(
            "SELECT COUNT(*) AS station_count FROM route_stations WHERE route_id = 1"
        ).fetchone()["station_count"]

    assert observation == {"temperature_c": 12.5, "source": "qweather"}
    assert station_count == 8


def test_scheduled_update_run_composite_key_allows_three_slots_only_once() -> None:
    with open_database() as connection:
        for run_slot in ("morning", "afternoon", "evening"):
            connection.execute(
                """INSERT INTO scheduled_update_runs (
                       run_date, run_slot, trigger, status, started_at
                   ) VALUES ('2026-08-27', %s, 'cron', 'running', '2026-08-27T00:00:00Z')""",
                (run_slot,),
            )

    with pytest.raises(psycopg.errors.UniqueViolation):
        with open_database() as connection:
            connection.execute(
                """INSERT INTO scheduled_update_runs (
                       run_date, run_slot, trigger, status, started_at
                   ) VALUES ('2026-08-27', 'morning', 'cron', 'running',
                             '2026-08-27T01:00:00Z')"""
            )


def test_open_database_rolls_back_failed_transactions() -> None:
    with pytest.raises(RuntimeError, match="stop"):
        with open_database() as connection:
            connection.execute(
                """INSERT INTO travel_reports (
                       route_id, travel_date, content, model_name, prompt_hash,
                       generated_at, source_snapshot_json
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    1,
                    "2026-08-20",
                    "rollback",
                    "test",
                    "hash",
                    "2026-08-20T00:00:00Z",
                    "[]",
                ),
            )
            raise RuntimeError("stop")

    with open_database() as connection:
        saved = connection.execute(
            "SELECT 1 FROM travel_reports WHERE travel_date = %s", ("2026-08-20",)
        ).fetchone()
    assert saved is None
