from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, Target
from app.utils import is_trading_time
from app.services.data_fetcher import (
    fetch_stock_realtime, fetch_stock_history,
    fetch_etf_realtime, fetch_etf_history,
    fetch_otc_estimation, fetch_otc_history_nav,
)
from app.services.analyzer import compute_indicators

router = APIRouter(tags=["行情查询"])


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

    # ====== 个股 ======
    if t_type == "stock":
        if trading:
            rt = fetch_stock_realtime(code)
            if rt:
                hist_df = fetch_stock_history(code)
                indicators = compute_indicators(hist_df, rt['price']) if hist_df is not None else None
                return {
                    "code": code, "name": target.name,
                    "type": "stock", "status": "realtime",
                    "realtime": rt, "indicators": indicators,
                }
        # 盘后
        hist_df = fetch_stock_history(code)
        if hist_df is not None and not hist_df.empty:
            last = hist_df.iloc[-1]
            return {
                "code": code, "name": target.name,
                "type": "stock", "status": "closed",
                "close_price": float(last['收盘']),
                "close_date": str(last['日期'].date()),
            }

    # ====== ETF ======
    elif t_type == "etf":
        if trading:
            rt = fetch_etf_realtime(code)
            if rt:
                hist_df = fetch_etf_history(code)
                indicators = compute_indicators(hist_df, rt['price']) if hist_df is not None else None
                return {
                    "code": code, "name": target.name,
                    "type": "etf", "status": "realtime",
                    "realtime": rt, "indicators": indicators,
                }
        hist_df = fetch_etf_history(code)
        if hist_df is not None and not hist_df.empty:
            last = hist_df.iloc[-1]
            return {
                "code": code, "name": target.name,
                "type": "etf", "status": "closed",
                "close_price": float(last['收盘']),
                "close_date": str(last['日期'].date()),
            }

    # ====== 场外基金 ======
    elif t_type == "otc":
        if trading:
            est = fetch_otc_estimation(code)
            if est:
                return {
                    "code": code, "name": target.name,
                    "type": "otc", "status": "estimation",
                    "data": est,
                }
        nav = fetch_otc_history_nav(code)
        if nav:
            return {
                "code": code, "name": target.name,
                "type": "otc", "status": "closed",
                "data": nav,
            }

    raise HTTPException(404, "数据获取失败")