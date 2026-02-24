import akshare as ak
import logging

logger = logging.getLogger(__name__)


def resolve_code(code: str) -> dict | None:
    """
    根据代码自动识别标的类型和名称
    查询顺序: 个股 → ETF → 场外基金
    返回: {"code": "600519", "name": "贵州茅台", "type": "stock"} 或 None
    """

    # 1. 尝试个股
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == code]
        if not row.empty:
            name = row.iloc[0]['名称']
            logger.info(f"识别为个股: {code} -> {name}")
            return {"code": code, "name": str(name), "type": "stock"}
    except Exception as e:
        logger.warning(f"个股查询异常 {code}: {e}")

    # 2. 尝试 ETF
    try:
        df = ak.fund_etf_spot_em()
        row = df[df['代码'] == code]
        if not row.empty:
            name = row.iloc[0]['名称']
            logger.info(f"识别为ETF: {code} -> {name}")
            return {"code": code, "name": str(name), "type": "etf"}
    except Exception as e:
        logger.warning(f"ETF查询异常 {code}: {e}")

    # 3. 尝试场外基金
    try:
        df = ak.fund_name_em()
        row = df[df['基金代码'] == code]
        if not row.empty:
            name = row.iloc[0]['基金简称']
            logger.info(f"识别为场外基金: {code} -> {name}")
            return {"code": code, "name": str(name), "type": "otc"}
    except Exception as e:
        logger.warning(f"场外基金查询异常 {code}: {e}")

    logger.error(f"无法识别代码 {code}")
    return None