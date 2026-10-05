"""bdm-007 -- the edit-window rule at the IST day boundary (spec §5.4; Review Focus 1). Pure: fixed instants, no database."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services import bdm_appointments as svc


def report(submitted_at: datetime, legacy: bool = False):
    return SimpleNamespace(submitted_at=submitted_at, legacy=legacy)


def test_window_closes_at_midnight_ist_not_utc():
    """Filed 23:50 IST, now 00:05 IST the next day -- the same UTC date (18:20Z / 18:35Z), yet closed."""
    assert svc.report_editable(report(datetime(2030, 1, 7, 18, 20, tzinfo=UTC)), datetime(2030, 1, 7, 18, 35, tzinfo=UTC)) is False


def test_window_stays_open_across_midnight_utc_within_one_ist_day():
    """Filed 05:00 IST, now 06:00 IST -- a different UTC date (23:30Z / 00:30Z), yet open."""
    assert svc.report_editable(report(datetime(2030, 1, 7, 23, 30, tzinfo=UTC)), datetime(2030, 1, 8, 0, 30, tzinfo=UTC)) is True


def test_legacy_reports_are_never_editable():
    now = datetime(2030, 1, 7, 6, 0, tzinfo=UTC)
    assert svc.report_editable(report(now, legacy=True), now) is False
