"""A pytest plugin that moves the run's clock to another day (the test review, owner 2026-11-15: what breaks after March 1,
2027, seen today). tools/test_all.py loads it with --as-of; by hand:

    set KICKOFF_TEST_CLOCK=2027-03-02 and run pytest with -p clock_shift (tools/ on PYTHONPATH)

datetime.datetime and datetime.date are replaced before the app is imported, so `datetime.now()` and `date.today()` read the
shifted day at the same time of day; arithmetic on them keeps the shifted class (Python 3.8 and later). Nothing else moves:
the tests' own fixed clocks stay fixed.
"""

from __future__ import annotations

import datetime as _dt
import os

_RealDT, _RealDate = _dt.datetime, _dt.date
_target = os.environ.get("KICKOFF_TEST_CLOCK", "").strip()
SHIFT = (_RealDT.fromisoformat(_target).replace(tzinfo=_dt.timezone.utc) - _RealDT.now(_dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)) if _target else _dt.timedelta(0)


class ShiftedDateTime(_RealDT):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        real = _RealDT.now(tz) + SHIFT
        return cls(real.year, real.month, real.day, real.hour, real.minute, real.second, real.microsecond, real.tzinfo)

    @classmethod
    def utcnow(cls):  # type: ignore[override]
        real = _RealDT.now(_dt.timezone.utc).replace(tzinfo=None) + SHIFT
        return cls(real.year, real.month, real.day, real.hour, real.minute, real.second, real.microsecond)

    @classmethod
    def today(cls):  # type: ignore[override]
        return cls.now()


class ShiftedDate(_RealDate):
    @classmethod
    def today(cls):  # type: ignore[override]
        real = (_RealDT.now() + SHIFT).date()
        return cls(real.year, real.month, real.day)


if _target:
    _dt.datetime = ShiftedDateTime  # type: ignore[misc]
    _dt.date = ShiftedDate  # type: ignore[misc]
