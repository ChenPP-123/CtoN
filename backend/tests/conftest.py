"""Shared safeguards for backend tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.database import open_database
from backend.main import app
from backend.time_utils import current_date


@pytest.fixture(autouse=True)
def isolate_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every test away from the application's local database."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "cton.db"))
    monkeypatch.setenv("DAILY_UPDATE_ENABLED", "false")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_weather_today(client: TestClient) -> str:
    today = current_date().isoformat()
    with open_database() as connection:
        connection.execute("UPDATE weather_observations SET observation_date = ?", (today,))
    return today
