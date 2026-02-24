import enum
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

os.makedirs("data", exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()