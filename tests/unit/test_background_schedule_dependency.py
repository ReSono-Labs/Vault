"""Pin next-occurrence behavior at the scheduler package boundary."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

croniter = pytest.importorskip("croniter").croniter


@pytest.mark.parametrize("previous,expected", [
    ("2026-03-07T09:00:00-05:00", "2026-03-08T09:00:00-04:00"),
    ("2026-10-31T09:00:00-04:00", "2026-11-01T09:00:00-05:00"),
])
def test_cron_preserves_local_morning_across_dst(previous, expected):
    base = datetime.fromisoformat(previous).astimezone(ZoneInfo("America/New_York"))
    actual = croniter("0 9 * * *", base).get_next(datetime)
    assert actual.isoformat() == expected
