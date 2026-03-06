import math
import pandas as pd
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 计算 MA250 所需的最少数据行数
MIN_HISTORY_ROWS = 250


def compute_indicators(df: pd.DataFrame, current_price: float, code: str = "") -> Optional[Dict[str, Any]]:
    """
    计算技术指标: MA5, MA20, MA120, MA250, 乖离率
    用实时价覆盖最后一行，盘中更准确。
    若任意关键均线计算结果为 NaN（数据不足），返回 None。
    """
    label = f" ({code})" if code else ""
    if df is None or len(df) < MIN_HISTORY_ROWS:
        logger.warning(
            f"历史数据不足{label}: 当前 {len(df) if df is not None else 0} 行, "
            f"需要至少 {MIN_HISTORY_ROWS} 行才能计算 MA250"
        )
        return None

    close = df['收盘'].copy()
    close.iloc[-1] = current_price

    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma120 = close.rolling(120).mean().iloc[-1]
    ma250 = close.rolling(250).mean().iloc[-1]

    # NaN 防御：任意关键均线为 NaN 时放弃计算
    if any(math.isnan(v) for v in (ma5, ma20, ma120, ma250)):
        logger.warning(
            f"[compute_indicators]{label} 均线含 NaN，数据可能存在缺失，跳过"
        )
        return None

    bias_rate = (current_price - ma250) / ma250

    result = {
        "price": round(current_price, 3),
        "ma5": round(ma5, 3),
        "ma20": round(ma20, 3),
        "ma120": round(ma120, 3),
        "ma250": round(ma250, 3),
        "bias_rate": round(bias_rate, 4),
        "bias_percent": f"{bias_rate:.2%}",
    }
    logger.debug(
        f"[compute_indicators]{label} 价格={result['price']}, MA120={result['ma120']}, "
        f"MA250={result['ma250']}, 乖离率={result['bias_percent']}"
    )
    return result


def check_signal(
    indicators: Dict[str, Any],
    buy_bias_rate: float | None = None,
    sell_bias_rate: float | None = None,
    buy_growth_rate: float | None = None,
    sell_growth_rate: float | None = None,
) -> Optional[str]:
    """
    判断买卖信号
    优先级: 卖出 > 买入（保守策略，优先止盈/止损）
    返回: 'BUY' / 'SELL' / None
    """
    if not indicators:
        logger.debug("[check_signal] indicators 为空，返回 None")
        return None

    # === 卖出信号（优先判断，保守策略） ===
    if sell_bias_rate is not None and indicators.get('bias_rate') is not None:
        if indicators['bias_rate'] >= sell_bias_rate:
            logger.debug(
                f"[check_signal] SELL 触发: bias_rate={indicators['bias_rate']:.4f} >= {sell_bias_rate}"
            )
            return 'SELL'

    if sell_growth_rate is not None and indicators.get('growth_rate') is not None:
        if indicators['growth_rate'] >= sell_growth_rate:
            logger.debug(
                f"[check_signal] SELL 触发: growth_rate={indicators['growth_rate']} >= {sell_growth_rate}"
            )
            return 'SELL'

    # === 买入信号 ===
    if buy_bias_rate is not None and indicators.get('bias_rate') is not None:
        if indicators['bias_rate'] <= buy_bias_rate:
            logger.debug(
                f"[check_signal] BUY 触发: bias_rate={indicators['bias_rate']:.4f} <= {buy_bias_rate}"
            )
            return 'BUY'

    if buy_growth_rate is not None and indicators.get('growth_rate') is not None:
        if indicators['growth_rate'] <= buy_growth_rate:
            logger.debug(
                f"[check_signal] BUY 触发: growth_rate={indicators['growth_rate']} <= {buy_growth_rate}"
            )
            return 'BUY'

    logger.debug("[check_signal] 无信号触发，返回 None")
    return None