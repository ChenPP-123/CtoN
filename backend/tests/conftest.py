"""Shared safeguards for backend tests."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every test away from the application's local database."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "cton.db"))
