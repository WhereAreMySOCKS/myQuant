import pandas as pd
import pytest

from app.services.analyzer import compute_indicators, check_signal


def _make_df(n: int, price: float = 10.0) -> pd.DataFrame:
    """Create a minimal DataFrame with n rows of closing prices."""
    return pd.DataFrame({"收盘": [price] * n})


# ===== compute_indicators =====

class TestComputeIndicators:
    def test_sufficient_data_returns_dict(self):
        df = _make_df(250, price=10.0)
        result = compute_indicators(df, current_price=10.0)
        assert result is not None
        assert "price" in result
        assert "ma5" in result
        assert "ma20" in result
        assert "ma250" in result
        assert "bias_rate" in result
        assert "bias_percent" in result

    def test_insufficient_data_returns_none(self):
        df = _make_df(249)
        result = compute_indicators(df, current_price=10.0)
        assert result is None

    def test_none_df_returns_none(self):
        result = compute_indicators(None, current_price=10.0)
        assert result is None

    def test_bias_rate_calculation(self):
        # All prices = 10, current price = 12
        # MA250 ≈ (249*10 + 12)/250 = 10.008; bias ≈ (12-10.008)/10.008 ≈ 0.199
        df = _make_df(250, price=10.0)
        result = compute_indicators(df, current_price=12.0)
        assert result is not None
        assert abs(result["bias_rate"] - 0.199) < 0.001

    def test_price_is_overridden(self):
        df = _make_df(250, price=10.0)
        result = compute_indicators(df, current_price=15.0)
        assert result is not None
        assert result["price"] == 15.0


# ===== check_signal =====

class TestCheckSignal:
    def test_buy_signal_below_threshold(self):
        indicators = {"bias_rate": -0.10}
        signal = check_signal(indicators, buy_bias_rate=-0.08)
        assert signal == "BUY"

    def test_sell_signal_above_threshold(self):
        indicators = {"bias_rate": 0.20}
        signal = check_signal(indicators, sell_bias_rate=0.15)
        assert signal == "SELL"

    def test_no_signal_within_range(self):
        indicators = {"bias_rate": 0.05}
        signal = check_signal(indicators, buy_bias_rate=-0.08, sell_bias_rate=0.15)
        assert signal is None

    def test_sell_takes_priority_over_buy(self):
        # Edge case: bias_rate triggers both (shouldn't happen in practice,
        # but sell should win because it's checked first)
        indicators = {"bias_rate": 0.20}
        signal = check_signal(indicators, buy_bias_rate=0.25, sell_bias_rate=0.15)
        assert signal == "SELL"

    def test_otc_buy_signal(self):
        indicators = {"growth_rate": -3.0}
        signal = check_signal(indicators, buy_growth_rate=-2.0)
        assert signal == "BUY"

    def test_otc_sell_signal(self):
        indicators = {"growth_rate": 4.0}
        signal = check_signal(indicators, sell_growth_rate=3.0)
        assert signal == "SELL"

    def test_empty_indicators_returns_none(self):
        signal = check_signal({})
        assert signal is None

    def test_none_thresholds_returns_none(self):
        indicators = {"bias_rate": -0.20}
        signal = check_signal(indicators)
        assert signal is None
