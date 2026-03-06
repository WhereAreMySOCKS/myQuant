from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import datetime


class BacktestRequest(BaseModel):
    """回测请求参数"""
    code: str = Field(..., description="证券代码，如 600519、510300")
    buy_bias_rate: float = Field(..., description="买入乖离率阈值，如 -0.08")
    sell_bias_rate: float = Field(..., description="卖出乖离率阈值，如 0.15")
    initial_capital: float = Field(100000.0, description="初始资金（元），默认 100000")
    start_date: Optional[str] = Field(None, description="回测起始日期（YYYY-MM-DD），默认动态计算")
    end_date: Optional[str] = Field(None, description="回测结束日期（YYYY-MM-DD），默认今天")


class TradeRecord(BaseModel):
    """单笔交易记录"""
    date: str = Field(..., description="交易日期")
    action: str = Field(..., description="交易方向：BUY / SELL")
    price: float = Field(..., description="成交价格")
    shares: int = Field(..., description="成交股数")
    amount: float = Field(..., description="成交金额")
    bias_rate: float = Field(..., description="当日乖离率")
    capital_after: float = Field(..., description="交易后现金余额")


class BacktestPeriod(BaseModel):
    """回测区间"""
    start: str
    end: str


class BacktestParams(BaseModel):
    """回测参数快照"""
    buy_bias_rate: float
    sell_bias_rate: float
    initial_capital: float


class BacktestSummary(BaseModel):
    """回测汇总指标"""
    total_return: float = Field(..., description="总收益率")
    total_return_pct: str
    annualized_return: float = Field(..., description="年化收益率")
    annualized_return_pct: str
    max_drawdown: float = Field(..., description="最大回撤（负数）")
    max_drawdown_pct: str
    trade_count: int = Field(..., description="交易次数（买+卖）")
    win_rate: float = Field(..., description="胜率")
    win_rate_pct: str
    final_capital: float = Field(..., description="最终资金（含持仓市值）")
    benchmark_return: float = Field(..., description="基准收益率（买入持有）")
    benchmark_return_pct: str
    excess_return: float = Field(..., description="超额收益率")
    excess_return_pct: str


class BacktestResponse(BaseModel):
    """回测结果响应"""
    code: str
    name: str
    type: str
    period: BacktestPeriod
    params: BacktestParams
    summary: BacktestSummary
    trades: List[TradeRecord]
