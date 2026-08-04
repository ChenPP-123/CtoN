from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.stability_service import estimate_pasquill_stability


DAY_CLASSES = {
    "strong": ("A", "A-B", "B", "C", "C"),
    "moderate": ("A-B", "B", "B-C", "C-D", "D"),
    "slight": ("B", "C", "C", "D", "D"),
    "weak": ("C", "C", "D", "D", "D"),
}
NIGHT_CLASSES = {
    20: ("F", "F", "E", "D", "D"),
    80: ("F", "E", "D", "D", "D"),
}
WIND_SPEEDS = (1.9, 2.0, 3.0, 5.0, 6.0)


@pytest.fixture
def fixed_solar_times(monkeypatch) -> SimpleNamespace:
    state = SimpleNamespace(elevation=45.0)

    def solar_times(_observer, *, date, tzinfo):
        return {
            "sunrise": datetime(date.year, date.month, date.day, 6, tzinfo=tzinfo),
            "sunset": datetime(date.year, date.month, date.day, 18, tzinfo=tzinfo),
        }

    monkeypatch.setattr("backend.stability_service.sun", solar_times)
    monkeypatch.setattr("backend.stability_service.elevation", lambda _observer, _time: state.elevation)
    return state


@pytest.mark.parametrize(
    ("insolation", "elevation"),
    [("strong", 61), ("moderate", 60), ("moderate", 36), ("slight", 35), ("slight", 16), ("weak", 15)],
)
@pytest.mark.parametrize(("wind_index", "wind_speed"), list(enumerate(WIND_SPEEDS)))
def test_daytime_pasquill_table(fixed_solar_times, insolation, elevation, wind_index, wind_speed) -> None:
    fixed_solar_times.elevation = elevation

    result = estimate_pasquill_stability(
        observed_at="2026-08-04T12:00:00+08:00",
        latitude=30.59,
        longitude=114.31,
        wind_speed_ms=wind_speed,
        cloud_cover_percent=20,
    )

    assert result.stability_class == DAY_CLASSES[insolation][wind_index]
    assert result.insolation_category == insolation
    assert result.period == "day"


@pytest.mark.parametrize(("cloud_cover", "expected_classes"), NIGHT_CLASSES.items())
@pytest.mark.parametrize(("wind_index", "wind_speed"), list(enumerate(WIND_SPEEDS)))
def test_nighttime_pasquill_table(fixed_solar_times, cloud_cover, expected_classes, wind_index, wind_speed) -> None:
    result = estimate_pasquill_stability(
        observed_at="2026-08-04T22:00:00+08:00",
        latitude=30.59,
        longitude=114.31,
        wind_speed_ms=wind_speed,
        cloud_cover_percent=cloud_cover,
    )

    assert result.stability_class == expected_classes[wind_index]
    assert result.insolation_category is None
    assert result.period == "night"


def test_cloudy_day_weakens_insolation_and_confidence(fixed_solar_times) -> None:
    fixed_solar_times.elevation = 61

    result = estimate_pasquill_stability(
        observed_at="2026-08-04T12:00:00+08:00",
        latitude=30.59,
        longitude=114.31,
        wind_speed_ms=3,
        cloud_cover_percent=51,
    )

    assert result.insolation_category == "moderate"
    assert result.stability_class == "B-C"
    assert result.confidence == "low"


def test_half_cloud_cover_does_not_weaken_insolation(fixed_solar_times) -> None:
    fixed_solar_times.elevation = 61

    result = estimate_pasquill_stability(
        observed_at="2026-08-04T12:00:00+08:00",
        latitude=30.59,
        longitude=114.31,
        wind_speed_ms=3,
        cloud_cover_percent=50,
    )

    assert result.insolation_category == "strong"
    assert result.confidence == "estimated"


def test_overcast_day_is_neutral(fixed_solar_times) -> None:
    result = estimate_pasquill_stability(
        observed_at="2026-08-04T12:00:00+08:00",
        latitude=30.59,
        longitude=114.31,
        wind_speed_ms=1,
        cloud_cover_percent=100,
    )

    assert result.stability_class == "D"
    assert result.confidence == "low"


@pytest.mark.parametrize(
    ("observed_at", "expected_period"),
    [
        ("2026-08-04T06:59:00+08:00", "night"),
        ("2026-08-04T07:00:00+08:00", "day"),
        ("2026-08-04T16:59:00+08:00", "day"),
        ("2026-08-04T17:00:00+08:00", "night"),
    ],
)
def test_twilight_boundaries(fixed_solar_times, observed_at, expected_period) -> None:
    result = estimate_pasquill_stability(
        observed_at=observed_at,
        latitude=30.59,
        longitude=114.31,
        wind_speed_ms=3,
        cloud_cover_percent=20,
    )

    assert result.period == expected_period


@pytest.mark.parametrize(
    ("wind_speed", "cloud_cover", "observed_at"),
    [
        (None, 20, "2026-08-04T12:00:00+08:00"),
        (-1, 20, "2026-08-04T12:00:00+08:00"),
        (2, None, "2026-08-04T12:00:00+08:00"),
        (2, 101, "2026-08-04T12:00:00+08:00"),
        (2, 20, "invalid"),
        (2, 20, "2026-08-04T12:00:00"),
    ],
)
def test_missing_or_invalid_inputs_are_not_classified(fixed_solar_times, wind_speed, cloud_cover, observed_at) -> None:
    assert estimate_pasquill_stability(
        observed_at=observed_at,
        latitude=30.59,
        longitude=114.31,
        wind_speed_ms=wind_speed,
        cloud_cover_percent=cloud_cover,
    ) is None
