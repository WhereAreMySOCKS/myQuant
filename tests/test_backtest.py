"""
回测引擎单元测试

测试范围：
  - 核心计算辅助函数（MA250、最大回撤、年化收益率）
  - run_backtest() 主逻辑（使用 mock 历史数据）
  - 买入/卖出信号触发
  - 空仓时不卖出、满仓时不重复买入
  - 回测指标计算（总收益率、最大回撤、胜率等）
  - API 端点（mock data_fetcher 和 code_resolver）
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, AsyncMock

from app.services.backtester import (
    _compute_ma250,
    _calc_max_drawdown,
    _calc_annualized_return,
    run_backtest,
)
from app.core.exceptions import DataSourceException, ValidationException


# ========== 辅助函数测试 ==========

class TestComputeMa250:
    def test_returns_none_before_250_rows(self):
        series = pd.Series([1.0] * 249)
        assert _compute_ma250(series, 248) is None

    def test_returns_mean_at_exactly_250_rows(self):
        series = pd.Series([2.0] * 250)
        result = _compute_ma250(series, 249)
        assert result == pytest.approx(2.0)

    def test_returns_correct_rolling_mean(self):
        # 前 249 行为 1.0，第 250 行为 2.0  → MA250 = (249*1 + 2) / 250
        values = [1.0] * 249 + [2.0]
        series = pd.Series(values)
        expected = (249 * 1.0 + 2.0) / 250
        result = _compute_ma250(series, 249)
        assert result == pytest.approx(expected)

    def test_uses_window_of_250(self):
        # 500 行数据，idx=499 时只取最后 250 行
        values = [1.0] * 250 + [3.0] * 250
        series = pd.Series(values)
        result = _compute_ma250(series, 499)
        assert result == pytest.approx(3.0)


class TestCalcMaxDrawdown:
    def test_empty_returns_zero(self):
        assert _calc_max_drawdown([]) == 0.0

    def test_monotonic_increase_returns_zero(self):
        dd = _calc_max_drawdown([100, 110, 120, 130])
        assert dd == pytest.approx(0.0)

    def test_single_drawdown(self):
        # peak=120, trough=90 → drawdown = (90-120)/120 = -0.25
        dd = _calc_max_drawdown([100, 120, 90, 95])
        assert dd == pytest.approx(-0.25)

    def test_multiple_drawdowns_returns_worst(self):
        # peak1=110→low=100 => dd=-1/11≈-0.0909; peak2=120→low=85 => dd=-35/120≈-0.2917
        dd = _calc_max_drawdown([100, 110, 100, 120, 85])
        assert dd == pytest.approx(-35 / 120, rel=1e-4)


class TestCalcAnnualizedReturn:
    def test_zero_days_returns_zero(self):
        assert _calc_annualized_return(0.2, 0) == 0.0

    def test_one_year(self):
        # 1年总收益 20% → 年化 20%
        result = _calc_annualized_return(0.2, 365)
        assert result == pytest.approx(0.2, rel=1e-3)

    def test_two_years(self):
        # 2年总收益 44% → 年化 ~20%（(1.44)^0.5 - 1 = 0.2）
        result = _calc_annualized_return(0.44, 730)
        assert result == pytest.approx(0.2, rel=1e-2)

    def test_loss_greater_than_100pct(self):
        assert _calc_annualized_return(-1.0, 365) == -1.0


# ========== 构造测试用历史K线 ==========

def _make_df(n: int = 300, base_price: float = 100.0, trend: float = 0.0) -> pd.DataFrame:
    """
    生成 n 行合成历史K线 DataFrame。
    trend > 0 表示每日价格线性上涨，< 0 表示下跌。
    """
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    prices = [base_price + i * trend for i in range(n)]
    return pd.DataFrame({
        "日期": dates,
        "收盘": prices,
        "开盘": prices,
        "最高": [p * 1.01 for p in prices],
        "最低": [p * 0.99 for p in prices],
        "成交量": [1000.0] * n,
    })


# ========== run_backtest 核心逻辑测试 ==========

class TestRunBacktest:
    """使用 mock 数据源测试回测引擎主逻辑。"""

    def _mock_resolve(self, code: str):
        return {"code": code, "name": "测试股票", "type": "stock"}

    def _patch_all(self, df):
        """同时 patch code_resolver 和 data_fetcher。"""
        return [
            patch("app.services.backtester.resolve_code", side_effect=self._mock_resolve),
            patch("app.services.backtester.fetch_stock_history", return_value=df),
        ]

    def test_otc_raises_validation_error(self):
        """场外基金应返回 ValidationException。"""
        with patch("app.services.backtester.resolve_code",
                   return_value={"code": "012708", "name": "某基金", "type": "otc"}):
            with pytest.raises(ValidationException):
                run_backtest("012708", buy_bias_rate=-0.08, sell_bias_rate=0.15)

    def test_data_source_failure_raises_exception(self):
        """历史数据获取失败应抛出 DataSourceException。"""
        with patch("app.services.backtester.resolve_code",
                   return_value={"code": "600519", "name": "贵州茅台", "type": "stock"}):
            with patch("app.services.backtester.fetch_stock_history", return_value=None):
                with pytest.raises(DataSourceException):
                    run_backtest("600519", buy_bias_rate=-0.08, sell_bias_rate=0.15)

    def test_insufficient_data_raises_exception(self):
        """数据行数不足 250 应抛出 DataSourceException。"""
        small_df = _make_df(n=100)
        with patch("app.services.backtester.resolve_code",
                   return_value={"code": "600519", "name": "贵州茅台", "type": "stock"}):
            with patch("app.services.backtester.fetch_stock_history", return_value=small_df):
                with pytest.raises(DataSourceException):
                    run_backtest("600519", buy_bias_rate=-0.08, sell_bias_rate=0.15)

    def test_no_trades_when_price_within_range(self):
        """价格始终在阈值范围内，不产生任何交易。"""
        # MA250 ≈ 100，price 恒为 100 → bias_rate=0.0，不触发任何信号
        df = _make_df(n=300, base_price=100.0, trend=0.0)
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.15,
                initial_capital=100000,
            )
        assert result["summary"]["trade_count"] == 0
        # 没有交易，最终资金 = 初始资金
        assert result["summary"]["final_capital"] == pytest.approx(100000.0)

    def test_buy_signal_triggered(self):
        """当价格跌破买入阈值时应产生买入交易。"""
        n = 300
        # 前 260 行: price=100, 后 40 行: price=85 (bias≈-0.15 < -0.08 触发买入)
        prices = [100.0] * 260 + [85.0] * 40
        dates = pd.date_range("2022-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "日期": dates,
            "收盘": prices,
            "开盘": prices,
            "最高": prices,
            "最低": prices,
            "成交量": [1000.0] * n,
        })
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.15,
                initial_capital=100000,
            )
        buy_trades = [t for t in result["trades"] if t["action"] == "BUY"]
        assert len(buy_trades) >= 1
        assert buy_trades[0]["price"] == pytest.approx(85.0)

    def test_sell_signal_triggered(self):
        """当价格涨过卖出阈值时应产生卖出交易（前提：已持仓）。"""
        n = 320
        # 前 260 行 price=100; 261~280 price=85 (买入); 281~320 price=120 (bias≈0.20>0.15 卖出)
        prices = [100.0] * 260 + [85.0] * 20 + [120.0] * 40
        dates = pd.date_range("2022-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "日期": dates,
            "收盘": prices,
            "开盘": prices,
            "最高": prices,
            "最低": prices,
            "成交量": [1000.0] * n,
        })
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.15,
                initial_capital=100000,
            )
        sell_trades = [t for t in result["trades"] if t["action"] == "SELL"]
        assert len(sell_trades) >= 1

    def test_no_sell_when_no_position(self):
        """空仓时即使价格满足卖出条件，不产生卖出交易。"""
        # 价格从第 250 行开始就很高（触发卖出条件），但初始无持仓
        prices = [100.0] * 250 + [120.0] * 50
        n = len(prices)
        dates = pd.date_range("2022-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "日期": dates,
            "收盘": prices,
            "开盘": prices,
            "最高": prices,
            "最低": prices,
            "成交量": [1000.0] * n,
        })
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.15,
                initial_capital=100000,
            )
        sell_trades = [t for t in result["trades"] if t["action"] == "SELL"]
        assert len(sell_trades) == 0

    def test_no_buy_when_in_position(self):
        """持仓时即使再次触发买入信号，不重复买入。"""
        # 价格持续低迷，每次触发买入但已持仓
        prices = [100.0] * 250 + [85.0] * 50
        n = len(prices)
        dates = pd.date_range("2022-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "日期": dates,
            "收盘": prices,
            "开盘": prices,
            "最高": prices,
            "最低": prices,
            "成交量": [1000.0] * n,
        })
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.15,
                initial_capital=100000,
            )
        buy_trades = [t for t in result["trades"] if t["action"] == "BUY"]
        # 只应有一次买入
        assert len(buy_trades) == 1

    def test_unrealized_position_counted_in_final_capital(self):
        """回测结束时若仍持仓，按最后收盘价计入最终资金。"""
        # 前 260 行 price=100; 第 261~280 行 price=80（触发买入）; 最后 20 行 price=70（跌得更低）
        prices = [100.0] * 260 + [80.0] * 20 + [70.0] * 20
        n = len(prices)
        dates = pd.date_range("2022-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "日期": dates,
            "收盘": prices,
            "开盘": prices,
            "最高": prices,
            "最低": prices,
            "成交量": [1000.0] * n,
        })
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.50,  # 卖出阈值极高，不会卖出
                initial_capital=100000,
            )
        # 有买入交易
        buy_trades = [t for t in result["trades"] if t["action"] == "BUY"]
        assert len(buy_trades) >= 1
        # 最终资金应小于初始资金（因为买入后价格下跌）
        assert result["summary"]["final_capital"] < 100000.0

    def test_win_rate_calculation(self):
        """胜率 = 盈利卖出次数 / 总卖出次数。"""
        # 构造一次买入低价（85），卖出高价（120）→ 1次盈利，胜率=1.0
        prices = [100.0] * 260 + [85.0] * 20 + [120.0] * 40
        n = len(prices)
        dates = pd.date_range("2022-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "日期": dates,
            "收盘": prices,
            "开盘": prices,
            "最高": prices,
            "最低": prices,
            "成交量": [1000.0] * n,
        })
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.15,
                initial_capital=100000,
            )
        sell_trades = [t for t in result["trades"] if t["action"] == "SELL"]
        if sell_trades:
            assert result["summary"]["win_rate"] == pytest.approx(1.0)

    def test_result_structure(self):
        """回测结果包含所有必要字段。"""
        df = _make_df(n=300, base_price=100.0, trend=0.0)
        patchers = self._patch_all(df)
        with patchers[0], patchers[1]:
            result = run_backtest(
                "600519",
                buy_bias_rate=-0.08,
                sell_bias_rate=0.15,
                initial_capital=100000,
            )
        assert "code" in result
        assert "name" in result
        assert "type" in result
        assert "period" in result
        assert "params" in result
        assert "summary" in result
        assert "trades" in result

        summary = result["summary"]
        for key in [
            "total_return", "total_return_pct",
            "annualized_return", "annualized_return_pct",
            "max_drawdown", "max_drawdown_pct",
            "trade_count", "win_rate", "win_rate_pct",
            "final_capital", "benchmark_return", "benchmark_return_pct",
            "excess_return", "excess_return_pct",
        ]:
            assert key in summary, f"summary 缺少字段: {key}"

    def test_etf_uses_etf_history(self):
        """ETF 类型应调用 fetch_etf_history。"""
        df = _make_df(n=300)
        with patch("app.services.backtester.resolve_code",
                   return_value={"code": "510300", "name": "沪深300ETF", "type": "etf"}):
            with patch("app.services.backtester.fetch_etf_history", return_value=df) as mock_etf:
                run_backtest(
                    "510300",
                    buy_bias_rate=-0.08,
                    sell_bias_rate=0.15,
                    initial_capital=100000,
                )
                mock_etf.assert_called_once_with("510300")


# ========== API 端点测试 ==========


class TestBacktestAPI:
    """测试 POST /backtest/single 端点。"""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        # 跳过 init_security_info 和 monitor_loop，避免测试时发起网络请求
        with (
            patch("app.services.code_resolver.init_security_info"),
            patch("app.services.monitor.monitor_loop", new_callable=AsyncMock),
        ):
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c

    def _mock_run_backtest(self, **kwargs):
        """返回一个最小合法的回测结果。"""
        return {
            "code": "600519",
            "name": "贵州茅台",
            "type": "stock",
            "period": {"start": "2023-01-03", "end": "2025-03-06"},
            "params": {
                "buy_bias_rate": -0.08,
                "sell_bias_rate": 0.15,
                "initial_capital": 100000.0,
            },
            "summary": {
                "total_return": 0.2345,
                "total_return_pct": "23.45%",
                "annualized_return": 0.1123,
                "annualized_return_pct": "11.23%",
                "max_drawdown": -0.1567,
                "max_drawdown_pct": "-15.67%",
                "trade_count": 5,
                "win_rate": 0.6,
                "win_rate_pct": "60.00%",
                "final_capital": 123450.0,
                "benchmark_return": 0.15,
                "benchmark_return_pct": "15.00%",
                "excess_return": 0.0845,
                "excess_return_pct": "8.45%",
            },
            "trades": [],
        }

    def test_success(self, client):
        """正常请求应返回 200 和回测结果。"""
        with patch("app.routes.backtest.run_backtest",
                   side_effect=self._mock_run_backtest):
            resp = client.post("/backtest/single", json={
                "code": "600519",
                "buy_bias_rate": -0.08,
                "sell_bias_rate": 0.15,
                "initial_capital": 100000,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "600519"
        assert "summary" in data
        assert "trades" in data

    def test_otc_returns_error(self, client):
        """场外基金应返回 422 错误。"""
        with patch("app.routes.backtest.run_backtest",
                   side_effect=ValidationException("场外基金暂不支持")):
            resp = client.post("/backtest/single", json={
                "code": "012708",
                "buy_bias_rate": -0.08,
                "sell_bias_rate": 0.15,
            })
        assert resp.status_code == 422

    def test_data_source_error_returns_503(self, client):
        """数据源故障应返回 503。"""
        with patch("app.routes.backtest.run_backtest",
                   side_effect=DataSourceException("数据获取失败")):
            resp = client.post("/backtest/single", json={
                "code": "600519",
                "buy_bias_rate": -0.08,
                "sell_bias_rate": 0.15,
            })
        assert resp.status_code == 503

    def test_missing_required_fields_returns_422(self, client):
        """缺少必填字段应返回 422。"""
        resp = client.post("/backtest/single", json={"code": "600519"})
        assert resp.status_code == 422
