import time
import akshare as ak
import logging
from typing import Optional, Callable, List
from sqlalchemy.orm import Session

from app.database import SessionLocal, SecurityInfo

logger = logging.getLogger(__name__)

# akshare 接口请求间隔（秒）
REQUEST_INTERVAL = 3
MAX_RETRIES = 3


# ==================== 通用工具 ====================

def _safe_fetch(func: Callable, label: str) -> Optional[object]:
    """安全调用 akshare，带重试"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = func()
            return result
        except Exception as e:
            logger.warning(f"{label} 第 {attempt}/{MAX_RETRIES} 次失败: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_INTERVAL * 2)
    return None


def _try_with_fallbacks(calls: List[tuple]) -> Optional[object]:
    """
    按顺序尝试多个接口，返回第一个成功的结果
    calls: [(callable, label), ...]
    """
    for func, label in calls:
        result = _safe_fetch(func, label)
        if result is not None:
            return result
        time.sleep(REQUEST_INTERVAL)
    return None


def _detect_columns(df, candidates: List[List[str]]) -> Optional[List[str]]:
    """
    自动检测 DataFrame 的列名
    candidates: [[可能的code列名...], [可能的name列名...]]
    返回: [实际code列名, 实际name列名] 或 None
    """
    result = []
    for group in candidates:
        found = None
        for col in group:
            if col in df.columns:
                found = col
                break
        if found is None:
            return None
        result.append(found)
    return result


# ==================== 个股数据源 ====================

def _fetch_stocks_spot_em():
    return ak.stock_zh_a_spot_em()


def _fetch_stocks_code_name():
    return ak.stock_info_a_code_name()


STOCK_SOURCES = [
    (_fetch_stocks_spot_em, "个股(stock_zh_a_spot_em)"),
    (_fetch_stocks_code_name, "个股(stock_info_a_code_name)"),
]

STOCK_COL_CANDIDATES = [
    ["代码", "code"],   # code 列
    ["名称", "name"],   # name 列
]


# ==================== ETF数据源 ====================

def _fetch_etf_spot_em():
    return ak.fund_etf_spot_em()


def _fetch_etf_category_sina():
    return ak.fund_etf_category_sina(symbol="ETF基金")


ETF_SOURCES = [
    (_fetch_etf_spot_em, "ETF(fund_etf_spot_em)"),
    (_fetch_etf_category_sina, "ETF(fund_etf_category_sina)"),
]

ETF_COL_CANDIDATES = [
    ["代码", "基金代码", "code"],
    ["名称", "基金简称", "name"],
]


# ==================== 场外基金数据源 ====================

def _fetch_otc_fund_name():
    return ak.fund_name_em()


OTC_SOURCES = [
    (_fetch_otc_fund_name, "场外基金(fund_name_em)"),
]

OTC_COL_CANDIDATES = [
    ["基金代码", "代码", "code"],
    ["基金简称", "名称", "name"],
]


# ==================== 初始化：按类型分别检查和拉取 ====================

def init_security_info():
    """
    服务启动时调用：
    按类型分别检查，缺失哪个类型就补拉哪个，避免部分失败后无法恢复
    """
    db = SessionLocal()
    try:
        stock_count = db.query(SecurityInfo).filter(SecurityInfo.type == "stock").count()
        etf_count = db.query(SecurityInfo).filter(SecurityInfo.type == "etf").count()
        otc_count = db.query(SecurityInfo).filter(SecurityInfo.type == "otc").count()

        logger.info(f"当前标的信息: 个股={stock_count}, ETF={etf_count}, 场外={otc_count}")

        # 1. 个股
        if stock_count == 0:
            logger.info("[1/3] 个股数据缺失，开始拉取...")
            n = _fetch_and_save(db, STOCK_SOURCES, STOCK_COL_CANDIDATES, "stock")
            logger.info(f"[1/3] 个股入库完成: {n} 条")
            time.sleep(REQUEST_INTERVAL)
        else:
            logger.info(f"[1/3] 个股数据已存在: {stock_count} 条，跳过")

        # 2. ETF
        if etf_count == 0:
            logger.info("[2/3] ETF数据缺失，开始拉取...")
            n = _fetch_and_save(db, ETF_SOURCES, ETF_COL_CANDIDATES, "etf")
            logger.info(f"[2/3] ETF入库完成: {n} 条")
            time.sleep(REQUEST_INTERVAL)
        else:
            logger.info(f"[2/3] ETF数据已存在: {etf_count} 条，跳过")

        # 3. 场外基金
        if otc_count == 0:
            logger.info("[3/3] 场外基金数据缺失，开始拉取...")
            n = _fetch_and_save(db, OTC_SOURCES, OTC_COL_CANDIDATES, "otc")
            logger.info(f"[3/3] 场外基金入库完成: {n} 条")
        else:
            logger.info(f"[3/3] 场外基金数据已存在: {otc_count} 条，跳过")

        total = db.query(SecurityInfo).count()
        logger.info(f"标的信息初始化完成，共 {total} 条")

    except Exception as e:
        logger.error(f"标的信息初始化失败: {e}")
        db.rollback()
    finally:
        db.close()


def _fetch_and_save(
    db: Session,
    sources: List[tuple],
    col_candidates: List[List[str]],
    type_str: str,
) -> int:
    """
    通用的拉取+入库逻辑
    自动尝试多个数据源，自动检测列名，去重后入库
    """
    df = _try_with_fallbacks(sources)
    if df is None or df.empty:
        logger.error(f"{type_str} 全量表拉取失败（所有数据源均不可用）")
        return 0

    cols = _detect_columns(df, col_candidates)
    if cols is None:
        logger.error(f"{type_str} 列名无法识别，实际列: {list(df.columns)}")
        return 0

    code_col, name_col = cols
    existing_codes = {r.code for r in db.query(SecurityInfo.code).all()}

    records = []
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        if code in existing_codes:
            continue
        name = str(row[name_col]).strip()
        records.append(SecurityInfo(code=code, name=name, type=type_str))
        existing_codes.add(code)  # 防止同一批次内重复

    if records:
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

    # 按 个股 → ETF → 场外 顺序查找
    search_plan = [
        (STOCK_SOURCES, STOCK_COL_CANDIDATES, "stock"),
        (ETF_SOURCES, ETF_COL_CANDIDATES, "etf"),
        (OTC_SOURCES, OTC_COL_CANDIDATES, "otc"),
    ]

    for sources, col_candidates, type_str in search_plan:
        df = _try_with_fallbacks(sources)
        if df is None or df.empty:
            continue

        cols = _detect_columns(df, col_candidates)
        if cols is None:
            continue

        code_col, name_col = cols
        row = df[df[code_col].astype(str) == code]
        if not row.empty:
            name = str(row.iloc[0][name_col]).strip()
            _save_to_cache(db, code, name, type_str)
            return {"code": code, "name": name, "type": type_str}

        time.sleep(REQUEST_INTERVAL)

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