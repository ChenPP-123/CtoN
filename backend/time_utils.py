"""Application-wide date and time semantics."""

from __future__ import annotations

from datetime import date, datetime

from .config import get_application_timezone


def current_datetime() -> datetime:
    return datetime.now(get_application_timezone())


def current_date() -> date:
    return current_datetime().date()
