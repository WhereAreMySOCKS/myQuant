from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum


# ========== 枚举 ==========
class TargetTypeEnum(str, Enum):
    stock = "stock"
    etf = "etf"
    otc = "otc"


# ========== 关注标的 ==========
class TargetCreate(BaseModel):
    code: str = Field(..., description="代码，如 600519、510300、012708")
    name: str = Field(..., description="名称，如 贵州茅台")
    type: TargetTypeEnum = Field(..., description="类型: stock / etf / otc")
    buy_bias_rate: Optional[float] = Field(None, description="个股/ETF 乖离率买入阈值，如 -0.08")
    sell_bias_rate: Optional[float] = Field(None, description="个股/ETF 乖离率卖出阈值，如 0.15")
    buy_growth_rate: Optional[float] = Field(None, description="场外基金 估算跌幅买入阈值，如 -2.0")
    sell_growth_rate: Optional[float] = Field(None, description="场外基金 估算涨幅卖出阈值，如 3.0")


class TargetUpdate(BaseModel):
    name: Optional[str] = None
    buy_bias_rate: Optional[float] = None
    sell_bias_rate: Optional[float] = None
    buy_growth_rate: Optional[float] = None
    sell_growth_rate: Optional[float] = None


class TargetResponse(BaseModel):
    id: int
    code: str
    name: str
    type: str
    buy_bias_rate: Optional[float] = None
    sell_bias_rate: Optional[float] = None
    buy_growth_rate: Optional[float] = None
    sell_growth_rate: Optional[float] = None

    class Config:
        from_attributes = True


# ========== 查询响应 ==========
class HealthResponse(BaseModel):
    status: str
    trading_time: bool
    monitored_count: int


class RealtimeData(BaseModel):
    price: float
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    pre_close: Optional[float] = None


class IndicatorData(BaseModel):
    price: float
    ma5: float
    ma20: float
    ma250: float
    bias_rate: float
    bias_percent: str


class QuoteResponse(BaseModel):
    code: str
    name: str
    type: str
    status: str  # realtime / estimation / closed
    realtime: Optional[Dict[str, Any]] = None
    indicators: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    close_price: Optional[float] = None
    close_date: Optional[str] = None