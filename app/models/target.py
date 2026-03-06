import enum
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy import Enum as SAEnum

from app.core.database import Base


class TargetType(str, enum.Enum):
    STOCK = "stock"
    ETF = "etf"
    OTC = "otc"


class Target(Base):
    """用户关注的标的"""
    __tablename__ = "targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    type = Column(SAEnum(TargetType), nullable=False)
    buy_bias_rate = Column(Float, nullable=True)
    sell_bias_rate = Column(Float, nullable=True)
    buy_growth_rate = Column(Float, nullable=True)
    sell_growth_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=True)


class SecurityInfo(Base):
    """标的信息缓存表（个股 + ETF + 场外基金）"""
    __tablename__ = "security_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(10), nullable=False)  # stock / etf / otc
