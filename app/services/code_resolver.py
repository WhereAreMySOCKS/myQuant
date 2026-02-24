import time
import akshare as ak
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.database import SessionLocal, SecurityInfo

logger = logging.getLogger(__name__)

# akshare 接口请求间隔（秒）
REQUEST_INTERVAL = 3


def _safe_fetch(func, label: str):
    """安全调用 akshare，带重试"""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            result = func()
            return result
        except Exception as e:
            logger.warning(f"{label} 第 {attempt}/{max_retries} 次失败: {e}")
            if attempt < max_retries:
                time.sleep(REQUEST_INTERVAL * 2)
    return None


# ==================== 初始化：全量拉取入库 ====================

def init_security_info():
    """
    服务启动时调用：
    检查 security_info 表是否有数据，没有则从 akshare 拉取全量数据入库
    """
    db = SessionLocal()
    try:
        count = db.query(SecurityInfo).count()
        if count > 0:
            logger.info(f"标的信息表已存在，共 {count} 条记录，跳过初始化")
            return

        logger.info("标的信息表为空，开始拉取全量数据...")

        total = 0

        # 1. 拉取个股
        logger.info("[1/3] 拉取个股数据...")
        stock_count = _fetch_and_save_stocks(db)
        total += stock_count
        logger.info(f"[1/3] 个股数据入库完成: {stock_count} 条")

        time.sleep(REQUEST_INTERVAL)

        # 2. 拉取 ETF
        logger.info("[2/3] 拉取ETF数据...")
        etf_count = _fetch_and_save_etfs(db)
        total += etf_count
        logger.info(f"[2/3] ETF数据入库完成: {etf_count} 条")

        time.sleep(REQUEST_INTERVAL)

        # 3. 拉取场外基金
        logger.info("[3/3] 拉取场外基金数据...")
        otc_count = _fetch_and_save_otcs(db)
        total += otc_count
        logger.info(f"[3/3] 场外基金数据入库完成: {otc_count} 条")

        logger.info(f"标的信息初始化完成，共入库 {total} 条")

    except Exception as e:
        logger.error(f"标的信息初始化失败: {e}")
        db.rollback()
    finally:
        db.close()


def _fetch_and_save_stocks(db: Session) -> int:
    """拉取个股全量表并入库"""
    df = _safe_fetch(lambda: ak.stock_zh_a_spot_em(), "个股全量拉取")
    if df is None or df.empty:
        logger.error("个股全量表拉取失败")
        return 0

    records = []
    for _, row in df.iterrows():
        code = str(row['代码'])
        name = str(row['名称'])
        records.append(SecurityInfo(code=code, name=name, type="stock"))

    db.bulk_save_objects(records)
    db.commit()
    return len(records)


def _fetch_and_save_etfs(db: Session) -> int:
    """拉取ETF全量表并入库"""
    df = _safe_fetch(lambda: ak.fund_etf_spot_em(), "ETF全量拉取")
    if df is None or df.empty:
        logger.error("ETF全量表拉取失败")
        return 0

    records = []
    existing_codes = {r.code for r in db.query(SecurityInfo.code).all()}

    for _, row in df.iterrows():
        code = str(row['代码'])
        if code in existing_codes:
            continue
        name = str(row['名称'])
        records.append(SecurityInfo(code=code, name=name, type="etf"))

    db.bulk_save_objects(records)
    db.commit()
    return len(records)


def _fetch_and_save_otcs(db: Session) -> int:
    """拉取场外基金全量表并入库"""
    df = _safe_fetch(lambda: ak.fund_name_em(), "场外基金全量拉取")
    if df is None or df.empty:
        logger.error("场外基金全量表拉取失败")
        return 0

    records = []
    existing_codes = {r.code for r in db.query(SecurityInfo.code).all()}

    for _, row in df.iterrows():
        code = str(row['基金代码'])
        if code in existing_codes:
            continue
        name = str(row['基金简称'])
        records.append(SecurityInfo(code=code, name=name, type="otc"))

    db.bulk_save_objects(records)
    db.commit()
    return len(records)


# ==================== 查询：本地优先，接口兜底 ====================

def resolve_code(code: str) -> Optional[dict]:
    """
    根据代码查询名称和类型
    优先查本地 security_info 表，查不到再调接口补查并入库
    """
    db = SessionLocal()
    try:
        # 1. 先查本地
        info = db.query(SecurityInfo).filter(SecurityInfo.code == code).first()
        if info:
            logger.info(f"本地命中: {code} -> {info.name} ({info.type})")
            return {"code": info.code, "name": info.name, "type": info.type}

        # 2. 本地没有，去接口查
        logger.info(f"本地未找到 {code}，尝试从接口查询...")
        result = _fetch_single_from_remote(code, db)
        return result

    finally:
        db.close()


def _fetch_single_from_remote(code: str, db: Session) -> Optional[dict]:
    """从接口逐个查询单个代码，找到后同步入库"""

    # 1. 尝试个股
    df = _safe_fetch(lambda: ak.stock_zh_a_spot_em(), f"个股查询 {code}")
    if df is not None and not df.empty:
        row = df[df['代码'] == code]
        if not row.empty:
            name = str(row.iloc[0]['名称'])
            _save_to_cache(db, code, name, "stock")
            return {"code": code, "name": name, "type": "stock"}

    time.sleep(REQUEST_INTERVAL)

    # 2. 尝试 ETF
    df = _safe_fetch(lambda: ak.fund_etf_spot_em(), f"ETF查询 {code}")
    if df is not None and not df.empty:
        row = df[df['代码'] == code]
        if not row.empty:
            name = str(row.iloc[0]['名称'])
            _save_to_cache(db, code, name, "etf")
            return {"code": code, "name": name, "type": "etf"}

    time.sleep(REQUEST_INTERVAL)

    # 3. 尝试场外基金
    df = _safe_fetch(lambda: ak.fund_name_em(), f"场外基金查询 {code}")
    if df is not None and not df.empty:
        row = df[df['基金代码'] == code]
        if not row.empty:
            name = str(row.iloc[0]['基金简称'])
            _save_to_cache(db, code, name, "otc")
            return {"code": code, "name": name, "type": "otc"}

    logger.error(f"所有数据源均无法识别代码: {code}")
    return None


def _save_to_cache(db: Session, code: str, name: str, type_str: str):
    """将单条记录存入缓存表"""
    try:
        existing = db.query(SecurityInfo).filter(SecurityInfo.code == code).first()
        if not existing:
            db.add(SecurityInfo(code=code, name=name, type=type_str))
            db.commit()
            logger.info(f"已补充入库: {code} -> {name} ({type_str})")
    except Exception as e:
        logger.warning(f"缓存入库失败 {code}: {e}")
        db.rollback()