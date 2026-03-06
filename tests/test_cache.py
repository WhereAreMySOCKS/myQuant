"""tests/test_cache.py — 测试 HistoryCache 与 AlertStateManager。"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from app.services.cache import HistoryCache, AlertStateManager


# ==================== HistoryCache ====================

class TestHistoryCache:
    def _make_df(self) -> pd.DataFrame:
        return pd.DataFrame({"收盘": [10.0] * 5})

    def test_cache_miss_calls_fetcher(self):
        """未命中时应调用对应的 fetcher 函数。"""
        cache = HistoryCache()
        df = self._make_df()
        with patch("app.services.cache.fetch_stock_history", return_value=df) as mock_fetch:
            result = cache.get("600000", "stock")
            mock_fetch.assert_called_once_with("600000")
            assert result is not None
            assert len(result) == 5

    def test_cache_hit_does_not_call_fetcher(self):
        """命中时不应再次调用 fetcher。"""
        cache = HistoryCache()
        df = self._make_df()
        with patch("app.services.cache.fetch_stock_history", return_value=df) as mock_fetch:
            cache.get("600000", "stock")  # 第一次：写入缓存
            cache.get("600000", "stock")  # 第二次：命中缓存
            assert mock_fetch.call_count == 1

    def test_failed_fetch_not_cached(self):
        """fetcher 返回 None 时不应写入缓存，下次仍会重新拉取。"""
        cache = HistoryCache()
        with patch("app.services.cache.fetch_stock_history", return_value=None) as mock_fetch:
            result1 = cache.get("000001", "stock")
            result2 = cache.get("000001", "stock")
            assert result1 is None
            assert result2 is None
            assert mock_fetch.call_count == 2

    def test_cross_day_refresh(self):
        """跨日后应自动清空缓存并重新拉取。"""
        cache = HistoryCache()
        df = self._make_df()
        with patch("app.services.cache.fetch_stock_history", return_value=df) as mock_fetch, \
             patch("app.services.cache.get_current_time") as mock_time:
            # 第一天
            dt1 = MagicMock()
            dt1.strftime.return_value = "2024-01-08"
            mock_time.return_value = dt1
            cache.get("600000", "stock")
            assert mock_fetch.call_count == 1

            # 次日
            dt2 = MagicMock()
            dt2.strftime.return_value = "2024-01-09"
            mock_time.return_value = dt2
            cache.get("600000", "stock")
            assert mock_fetch.call_count == 2

    def test_clear_resets_cache(self):
        """clear() 后再次访问应重新拉取。"""
        cache = HistoryCache()
        df = self._make_df()
        with patch("app.services.cache.fetch_stock_history", return_value=df) as mock_fetch:
            cache.get("600000", "stock")
            cache.clear()
            cache.get("600000", "stock")
            assert mock_fetch.call_count == 2

    def test_stats_returns_size(self):
        """stats() 应返回正确的缓存大小。"""
        cache = HistoryCache()
        df = self._make_df()
        with patch("app.services.cache.fetch_stock_history", return_value=df):
            assert cache.stats()["size"] == 0
            cache.get("600000", "stock")
            assert cache.stats()["size"] == 1

    def test_unsupported_type_returns_none(self):
        """不支持的资产类型应返回 None。"""
        cache = HistoryCache()
        result = cache.get("000001", "unknown_type")
        assert result is None

    def test_etf_calls_etf_fetcher(self):
        """etf 类型应调用 fetch_etf_history 而非 fetch_stock_history。"""
        cache = HistoryCache()
        df = self._make_df()
        with patch("app.services.cache.fetch_etf_history", return_value=df) as mock_etf, \
             patch("app.services.cache.fetch_stock_history") as mock_stock:
            cache.get("510300", "etf")
            mock_etf.assert_called_once_with("510300")
            mock_stock.assert_not_called()


# ==================== AlertStateManager ====================

class TestAlertStateManager:
    def test_not_alerted_initially(self):
        """初始状态下 is_alerted 应返回 False。"""
        mgr = AlertStateManager()
        assert mgr.is_alerted("600000", "BUY") is False

    def test_mark_and_check(self):
        """mark_alerted 后 is_alerted 应返回 True。"""
        mgr = AlertStateManager()
        mgr.mark_alerted("600000", "BUY")
        assert mgr.is_alerted("600000", "BUY") is True

    def test_different_signal_not_alerted(self):
        """标记 BUY 后，SELL 仍未报警。"""
        mgr = AlertStateManager()
        mgr.mark_alerted("600000", "BUY")
        assert mgr.is_alerted("600000", "SELL") is False

    def test_cross_day_reset(self):
        """跨日后 is_alerted 应返回 False（报警记录已过期）。"""
        mgr = AlertStateManager()
        with patch("app.services.cache.get_current_time") as mock_time:
            dt1 = MagicMock()
            dt1.strftime.return_value = "2024-01-08"
            mock_time.return_value = dt1
            mgr.mark_alerted("600000", "BUY")
            assert mgr.is_alerted("600000", "BUY") is True

            dt2 = MagicMock()
            dt2.strftime.return_value = "2024-01-09"
            mock_time.return_value = dt2
            assert mgr.is_alerted("600000", "BUY") is False

    def test_clear_resets_all(self):
        """clear() 后所有报警记录应被清除。"""
        mgr = AlertStateManager()
        mgr.mark_alerted("600000", "BUY")
        mgr.clear()
        assert mgr.is_alerted("600000", "BUY") is False

    def test_stats_today_alerted(self):
        """stats() 中 today_alerted 应反映今日已报警的标的数量。"""
        mgr = AlertStateManager()
        with patch("app.services.cache.get_current_time") as mock_time:
            dt = MagicMock()
            dt.strftime.return_value = "2024-01-08"
            mock_time.return_value = dt

            mgr.mark_alerted("600000", "BUY")
            mgr.mark_alerted("600000", "SELL")  # 同一标的不同信号
            mgr.mark_alerted("000001", "BUY")

            stats = mgr.stats()
            assert stats["today_alerted"] == 2  # 两个不同标的
            assert stats["total_codes"] == 2
