from fastapi import APIRouter
import logging

from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.services.backtester import run_backtest

router = APIRouter(prefix="/backtest", tags=["回测"])
logger = logging.getLogger(__name__)


@router.post("/single", summary="单标回测", response_model=BacktestResponse)
def backtest_single(req: BacktestRequest):
    """
    基于 MA250 乖离率策略的单标历史回测。

    - 支持个股和 ETF
    - 场外基金暂不支持
    - 买入/卖出均为全仓操作
    """
    logger.info(
        f"[backtest] 收到回测请求: code={req.code}, "
        f"buy={req.buy_bias_rate}, sell={req.sell_bias_rate}, "
        f"capital={req.initial_capital}"
    )
    result = run_backtest(
        code=req.code,
        buy_bias_rate=req.buy_bias_rate,
        sell_bias_rate=req.sell_bias_rate,
        initial_capital=req.initial_capital,
        start_date=req.start_date,
        end_date=req.end_date,
    )
    return result
