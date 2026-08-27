import json
from pathlib import Path


def test_vercel_config_has_three_daily_slot_crons() -> None:
    config = json.loads((Path(__file__).parents[2] / "vercel.json").read_text())

    assert config["crons"] == [
        {
            "path": "/api/v1/internal/scheduled-update/morning",
            "schedule": "0 23 * * *",
        },
        {
            "path": "/api/v1/internal/scheduled-update/afternoon",
            "schedule": "0 6 * * *",
        },
        {
            "path": "/api/v1/internal/scheduled-update/evening",
            "schedule": "0 13 * * *",
        },
    ]
