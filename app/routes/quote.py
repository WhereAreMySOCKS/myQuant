from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from app.database import get_db, Target
from app.utils import is_trading_time
from app.services.data_fetcher import (
    fetch_stock_realtime, fetch_stock_history,
    fetch_etf_realtime, fetch_etf_history,
    fetch_otc_estimation, fetch_otc_history_nav,
)
from app.services.analyzer import compute_indicators

router = APIRouter(tags=["行情查询"])
logger = logging.getLogger(__name__)


@router.get("/quote/{code}", summary="查询实时行情/估值")
def get_quote(code: str, db: Session = Depends(get_db)):
    """
    统一查询接口:
    - 交易时间 → 个股/ETF返回实时价+技术指标，场外基金返回实时估值
    - 非交易时间 → 个股/ETF返回收盘价，场外基金返回确认净值
    """
    target = db.query(Target).filter(Target.code == code).first()
    if not target:
        raise HTTPException(404, f"标的 {code} 未关注，请先添加")

    t_type = target.type.value
    trading = is_trading_time()
    logger.info(f"[quote] 收到行情请求: code={code}, name={target.name}, type={t_type}, 交易时间={trading}")

    # ====== 个股 ======
    if t_type == "stock":
        if trading:
            logger.debug(f"[quote] {code} 走实时行情分支")
            rt = fetch_stock_realtime(code)
            if rt:
                hist_df = fetch_stock_history(code)
                indicators = compute_indicators(hist_df, rt['price'], code=code) if hist_df is not None else None
                logger.info(f"[quote] {code} 实时返回: 价格={rt['price']}, 指标={'有' if indicators else '无'}")
                return {
                    "code": code, "name": target.name,
                    "type": "stock", "status": "realtime",
                    "realtime": rt, "indicators": indicators,
                }
            logger.warning(f"[quote] {code} 实时数据获取失败，降级到历史收盘价")
        # 盘后
        logger.debug(f"[quote] {code} 走历史收盘价分支")
        hist_df = fetch_stock_history(code)
        if hist_df is not None and not hist_df.empty:
            last = hist_df.iloc[-1]
            close_price = float(last['收盘'])
            close_date = str(last['日期'].date())
            logger.info(f"[quote] {code} 历史收盘价返回: 价格={close_price}, 日期={close_date}")
            return {
                "code": code, "name": target.name,
                "type": "stock", "status": "closed",
                "close_price": close_price,
                "close_date": close_date,
            }

    # ====== ETF ======
    elif t_type == "etf":
        if trading:
            logger.debug(f"[quote] {code} 走ETF实时行情分支")
            rt = fetch_etf_realtime(code)
            if rt:
                hist_df = fetch_etf_history(code)
                indicators = compute_indicators(hist_df, rt['price'], code=code) if hist_df is not None else None
                logger.info(f"[quote] {code} ETF实时返回: 价格={rt['price']}, 指标={'有' if indicators else '无'}")
                return {
                    "code": code, "name": target.name,
                    "type": "etf", "status": "realtime",
                    "realtime": rt, "indicators": indicators,
                }
            logger.warning(f"[quote] {code} ETF实时数据获取失败，降级到历史收盘价")
        logger.debug(f"[quote] {code} 走ETF历史收盘价分支")
        hist_df = fetch_etf_history(code)
        if hist_df is not None and not hist_df.empty:
            last = hist_df.iloc[-1]
            close_price = float(last['收盘'])
            close_date = str(last['日期'].date())
            logger.info(f"[quote] {code} ETF历史收盘价返回: 价格={close_price}, 日期={close_date}")
            return {
                "code": code, "name": target.name,
                "type": "etf", "status": "closed",
                "close_price": close_price,
                "close_date": close_date,
            }

    # ====== 场外基金 ======
    elif t_type == "otc":
        if trading:
            logger.debug(f"[quote] {code} 走场外实时估值分支")
            est = fetch_otc_estimation(code)
            if est:
                logger.info(f"[quote] {code} 场外估值返回: 估算净值={est['nav']}, 增长率={est['growth_rate']}%")
                return {
                    "code": code, "name": target.name,
                    "type": "otc", "status": "estimation",
                    "data": est,
                }
            logger.warning(f"[quote] {code} 场外实时估值获取失败，降级到确认净值")
        logger.debug(f"[quote] {code} 走场外确认净值分支")
        nav = fetch_otc_history_nav(code)
        if nav:
            logger.info(f"[quote] {code} 场外确认净值返回: 净值={nav['nav']}, 日期={nav['date']}")
            return {
                "code": code, "name": target.name,
                "type": "otc", "status": "closed",
                "data": nav,
            }

    logger.error(f"[quote] {code} 所有数据源均不可用，返回 503")
    raise HTTPException(503, "数据获取失败，上游接口暂不可用")