"""
回测引擎 — 基于 MA250 乖离率策略的单标回测模块

策略说明：
  - 个股 / ETF：乖离率 = (收盘价 - MA250) / MA250
    * 乖离率 <= buy_bias_rate  → BUY（全仓买入）
    * 乖离率 >= sell_bias_rate → SELL（全仓卖出）
  - 场外基金：暂不支持，返回提示

回测规则：
  1. 使用历史K线数据（通过 data_fetcher 获取）
  2. 从第 250 根K线开始，保证 MA250 有效
  3. 全仓操作：买入时用全部现金买入尽可能多的整股；卖出时清空全部持仓
  4. 资金不足时（买不起 1 手）不执行买入
  5. 回测结束时若仍持仓，按最后一日收盘价计算市值纳入最终资金
"""

import datetime
import logging
from typing import Optional, List, Dict, Any

import pandas as pd

from app.services.data_fetcher import fetch_stock_history, fetch_etf_history
from app.services.code_resolver import resolve_code
from app.core.exceptions import DataSourceException, ValidationException

logger = logging.getLogger(__name__)

# A 股最小买入单位（1 手 = 100 股）
_LOT_SIZE = 100


def _compute_ma250(close_series: pd.Series, idx: int) -> Optional[float]:
    """计算第 idx 行的 MA250（使用前 250 根K线收盘价均值）。"""
    if idx < 249:
        return None
    window = close_series.iloc[idx - 249: idx + 1]
    if len(window) < 250:
        return None
    return float(window.mean())


def _calc_max_drawdown(equity_curve: List[float]) -> float:
    """计算最大回撤（负数）。"""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
    return max_dd


def _calc_annualized_return(total_return: float, days: int) -> float:
    """根据总收益率和持有天数计算年化收益率。"""
    if days <= 0:
        return 0.0
    years = days / 365.0
    if total_return <= -1.0:
        return -1.0
    return (1 + total_return) ** (1 / years) - 1


def run_backtest(
    code: str,
    buy_bias_rate: float,
    sell_bias_rate: float,
    initial_capital: float = 100000.0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    执行单标回测，返回回测结果字典。

    Args:
        code: 证券代码
        buy_bias_rate: 买入乖离率阈值（如 -0.08）
        sell_bias_rate: 卖出乖离率阈值（如 0.15）
        initial_capital: 初始资金（元）
        start_date: 回测起始日期（YYYY-MM-DD），默认取历史数据第一条
        end_date: 回测结束日期（YYYY-MM-DD），默认今天

    Returns:
        包含 code/name/type/period/params/summary/trades 的字典

    Raises:
        DataSourceException: 历史数据获取失败
        ValidationException: 参数不合法或不支持的证券类型
    """
    logger.info(f"[backtester] 开始回测: code={code}, buy={buy_bias_rate}, sell={sell_bias_rate}, "
                f"capital={initial_capital}")

    # ===== 1. 解析证券信息 =====
    info = resolve_code(code)
    if not info:
        raise DataSourceException(f"无法识别证券代码 {code}，请确认代码正确")
    name = info["name"]
    asset_type = info["type"]

    # 场外基金暂不支持
    if asset_type == "otc":
        raise ValidationException(
            f"{code}（{name}）为场外基金，回测引擎暂不支持场外基金，"
            "请使用个股或ETF代码"
        )

    # ===== 2. 获取历史K线 =====
    if asset_type == "stock":
        df = fetch_stock_history(code)
    else:  # etf
        df = fetch_etf_history(code)

    if df is None or df.empty:
        raise DataSourceException(f"获取 {code} 历史数据失败，数据源暂不可用")
    if len(df) < 250:
        raise DataSourceException(
            f"{code} 历史数据不足 250 条（当前 {len(df)} 条），无法计算 MA250"
        )

    # ===== 3. 过滤日期范围 =====
    df = df.copy().reset_index(drop=True)
    df["日期"] = pd.to_datetime(df["日期"])

    end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.today().normalize()
    df = df[df["日期"] <= end_dt].reset_index(drop=True)

    if start_date:
        # start_date 仅限制信号触发，但 MA250 计算仍需前 250 条数据
        start_dt = pd.to_datetime(start_date)
        # 找到 start_date 对应的索引（或之后第一条）
        start_idx_list = df.index[df["日期"] >= start_dt].tolist()
        signal_start_idx = start_idx_list[0] if start_idx_list else len(df)
        # MA250 至少需要 249 条前置数据
        signal_start_idx = max(signal_start_idx, 249)
    else:
        signal_start_idx = 249  # 从第 250 条（index=249）开始

    if len(df) <= signal_start_idx:
        raise DataSourceException(f"{code} 在所选日期范围内数据不足，无法回测")

    close_series = df["收盘"].astype(float)

    # ===== 4. 回测主循环 =====
    cash = initial_capital
    shares = 0          # 当前持股数
    trades: List[dict] = []
    equity_curve: List[float] = []
    last_buy_price: Optional[float] = None
    win_count = 0
    sell_count = 0

    actual_start_date: Optional[str] = None
    actual_end_date: Optional[str] = None

    for idx in range(signal_start_idx, len(df)):
        row = df.iloc[idx]
        date_str = str(row["日期"].date())
        price = float(row["收盘"])

        if actual_start_date is None:
            actual_start_date = date_str
        actual_end_date = date_str

        ma250 = _compute_ma250(close_series, idx)
        if ma250 is None or ma250 == 0:
            equity = cash + shares * price
            equity_curve.append(equity)
            continue

        bias_rate = (price - ma250) / ma250

        # 卖出优先（保守策略）
        if shares > 0 and bias_rate >= sell_bias_rate:
            amount = shares * price
            if last_buy_price is not None and price > last_buy_price:
                win_count += 1
            sell_count += 1
            cash += amount
            logger.debug(f"[backtester] {date_str} SELL: 价格={price:.3f}, 股数={shares}, 金额={amount:.2f}")
            trades.append({
                "date": date_str,
                "action": "SELL",
                "price": round(price, 3),
                "shares": shares,
                "amount": round(amount, 2),
                "bias_rate": round(bias_rate, 4),
                "capital_after": round(cash, 2),
            })
            shares = 0
            last_buy_price = None

        # 买入
        elif shares == 0 and bias_rate <= buy_bias_rate:
            # 全仓买入，按 100 股最小手数取整
            max_shares = int(cash / price / _LOT_SIZE) * _LOT_SIZE
            if max_shares > 0:
                amount = max_shares * price
                cash -= amount
                shares = max_shares
                last_buy_price = price
                logger.debug(f"[backtester] {date_str} BUY: 价格={price:.3f}, 股数={shares}, 金额={amount:.2f}")
                trades.append({
                    "date": date_str,
                    "action": "BUY",
                    "price": round(price, 3),
                    "shares": shares,
                    "amount": round(amount, 2),
                    "bias_rate": round(bias_rate, 4),
                    "capital_after": round(cash, 2),
                })

        equity = cash + shares * price
        equity_curve.append(equity)

    # 回测结束时仍持仓，按最后一日收盘价计算市值
    last_price = float(close_series.iloc[-1])
    final_capital = cash + shares * last_price

    # ===== 5. 计算回测指标 =====
    actual_start_date = actual_start_date or str(df.iloc[signal_start_idx]["日期"].date())
    actual_end_date = actual_end_date or str(df.iloc[-1]["日期"].date())

    total_return = (final_capital - initial_capital) / initial_capital

    start_ts = pd.to_datetime(actual_start_date)
    end_ts = pd.to_datetime(actual_end_date)
    days = max((end_ts - start_ts).days, 1)
    annualized = _calc_annualized_return(total_return, days)

    max_dd = _calc_max_drawdown(equity_curve)

    trade_count = len(trades)
    win_rate = (win_count / sell_count) if sell_count > 0 else 0.0

    # 基准收益：在信号起始日以全仓买入，回测结束日卖出
    benchmark_start_price = float(close_series.iloc[signal_start_idx])
    benchmark_end_price = last_price
    benchmark_return = (
        (benchmark_end_price - benchmark_start_price) / benchmark_start_price
        if benchmark_start_price > 0
        else 0.0
    )
    excess_return = total_return - benchmark_return

    logger.info(
        f"[backtester] {code} 回测完成: 总收益={total_return:.4f}, "
        f"年化={annualized:.4f}, 最大回撤={max_dd:.4f}, 交易次数={trade_count}"
    )

    return {
        "code": code,
        "name": name,
        "type": asset_type,
        "period": {
            "start": actual_start_date,
            "end": actual_end_date,
        },
        "params": {
            "buy_bias_rate": buy_bias_rate,
            "sell_bias_rate": sell_bias_rate,
            "initial_capital": initial_capital,
        },
        "summary": {
            "total_return": round(total_return, 6),
            "total_return_pct": f"{total_return:.2%}",
            "annualized_return": round(annualized, 6),
            "annualized_return_pct": f"{annualized:.2%}",
            "max_drawdown": round(max_dd, 6),
            "max_drawdown_pct": f"{max_dd:.2%}",
            "trade_count": trade_count,
            "win_rate": round(win_rate, 4),
            "win_rate_pct": f"{win_rate:.2%}",
            "final_capital": round(final_capital, 2),
            "benchmark_return": round(benchmark_return, 6),
            "benchmark_return_pct": f"{benchmark_return:.2%}",
            "excess_return": round(excess_return, 6),
            "excess_return_pct": f"{excess_return:.2%}",
        },
        "trades": trades,
    }
