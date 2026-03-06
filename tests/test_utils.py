import datetime
from unittest.mock import patch, MagicMock

import pytest
import pytz

from app.utils.time_utils import is_trading_time, get_current_time, SHANGHAI_TZ


def _make_shanghai_dt(hour: int, minute: int, weekday: int = 0) -> datetime.datetime:
    """
    Build a Shanghai-timezone datetime.
    weekday: 0=Monday … 6=Sunday
    We start from a known Monday (2024-01-08) and add weekday offset.
    """
    base_monday = datetime.date(2024, 1, 8)
    target_date = base_monday + datetime.timedelta(days=weekday)
    return SHANGHAI_TZ.localize(
        datetime.datetime(target_date.year, target_date.month, target_date.day, hour, minute, 0)
    )


class TestIsTradingTime:
    def _mock_trading(self, hour: int, minute: int, weekday: int = 0):
        """Patch get_current_time and is_workday for a controlled scenario."""
        dt = _make_shanghai_dt(hour, minute, weekday)

        with patch("app.utils.time_utils.get_current_time", return_value=dt), \
             patch("app.utils.time_utils.is_workday", return_value=(weekday < 5)), \
             patch("app.utils.time_utils._last_trading_state", None):
            return is_trading_time()

    def test_am_trading_window(self):
        # 10:00 on Monday → should be trading time
        result = self._mock_trading(10, 0, weekday=0)
        assert result is True

    def test_pm_trading_window(self):
        # 14:00 on Monday → should be trading time
        result = self._mock_trading(14, 0, weekday=0)
        assert result is True

    def test_before_am_open(self):
        # 09:00 on Monday → before market open
        result = self._mock_trading(9, 0, weekday=0)
        assert result is False

    def test_lunch_break(self):
        # 12:00 on Monday → lunch break
        result = self._mock_trading(12, 0, weekday=0)
        assert result is False

    def test_after_pm_close(self):
        # 15:30 on Monday → after market close
        result = self._mock_trading(15, 30, weekday=0)
        assert result is False

    def test_weekend_is_not_trading(self):
        # 10:00 on Saturday
        result = self._mock_trading(10, 0, weekday=5)
        assert result is False


class TestGetCurrentTime:
    def test_returns_shanghai_timezone(self):
        now = get_current_time()
        assert now.tzinfo is not None
        assert str(now.tzinfo) == "Asia/Shanghai"
