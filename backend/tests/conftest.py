"""Shared PostgreSQL setup and safeguards for backend tests."""

from collections.abc import Iterator
import os

import pytest
from fastapi.testclient import TestClient


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
if not TEST_DATABASE_URL:
    pytest.skip(
        "Set TEST_DATABASE_URL to a PostgreSQL database whose name ends in _test",
        allow_module_level=True,
    )

# backend.main constructs the application during import, so point all runtime
# connections at the guarded test database before importing it.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from backend.database import (  # noqa: E402
    initialize_database,
    open_database,
    require_test_database_url,
    reset_test_database,
)
from backend.main import app  # noqa: E402
from backend.seed import seed_database, seed_demo_observations  # noqa: E402
from backend.time_utils import current_date  # noqa: E402


ADMIN_API_TOKEN = "test-admin-token-with-at-least-32-characters"
CRON_SECRET = "test-cron-secret-with-at-least-32-characters"


@pytest.fixture(scope="session", autouse=True)
def initialize_test_schema() -> Iterator[None]:
    require_test_database_url(TEST_DATABASE_URL)
    initialize_database(TEST_DATABASE_URL)
    yield
    reset_test_database(TEST_DATABASE_URL)


@pytest.fixture(autouse=True)
def isolate_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    reset_test_database(TEST_DATABASE_URL)
    with open_database(TEST_DATABASE_URL) as connection:
        seed_database(connection)
        seed_demo_observations(connection)
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("ADMIN_API_TOKEN", ADMIN_API_TOKEN)
    monkeypatch.setenv("CRON_SECRET", CRON_SECRET)
    yield


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_API_TOKEN}"}


@pytest.fixture
def cron_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CRON_SECRET}"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_weather_today(client: TestClient) -> str:
    today = current_date().isoformat()
    with open_database() as connection:
        connection.execute(
            "UPDATE weather_observations SET observation_date = %s", (today,)
        )
    return today
