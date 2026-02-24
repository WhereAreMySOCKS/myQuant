import pandas as pd
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 计算 MA250 所需的最少数据行数
MIN_HISTORY_ROWS = 250


def compute_indicators(df: pd.DataFrame, current_price: float) -> Optional[Dict[str, Any]]:
    """
    计算技术指标: MA5, MA20, MA250, 乖离率
    用实时价覆盖最后一行，盘中更准确
    """
    if df is None or len(df) < MIN_HISTORY_ROWS:
        logger.warning(
            f"历史数据不足: 当前 {len(df) if df is not None else 0} 行, "
            f"需要至少 {MIN_HISTORY_ROWS} 行才能计算 MA250"
        )
        return None

    close = df['收盘'].copy()
    close.iloc[-1] = current_price

    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma250 = close.rolling(250).mean().iloc[-1]
    bias_rate = (current_price - ma250) / ma250

    return {
        "price": round(current_price, 3),
        "ma5": round(ma5, 3),
        "ma20": round(ma20, 3),
        "ma250": round(ma250, 3),
        "bias_rate": round(bias_rate, 4),
        "bias_percent": f"{bias_rate:.2%}",
    }


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
        return None

    # === 卖出信号（优先判断，保守策略） ===
    if sell_bias_rate is not None and indicators.get('bias_rate') is not None:
        if indicators['bias_rate'] >= sell_bias_rate:
            return 'SELL'

    if sell_growth_rate is not None and indicators.get('growth_rate') is not None:
        if indicators['growth_rate'] >= sell_growth_rate:
            return 'SELL'

    # === 买入信号 ===
    if buy_bias_rate is not None and indicators.get('bias_rate') is not None:
        if indicators['bias_rate'] <= buy_bias_rate:
            return 'BUY'

    if buy_growth_rate is not None and indicators.get('growth_rate') is not None:
        if indicators['growth_rate'] <= buy_growth_rate:
            return 'BUY'

    return None