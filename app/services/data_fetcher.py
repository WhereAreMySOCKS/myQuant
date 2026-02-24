import akshare as ak
import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ==================== 个股 ====================

def fetch_stock_realtime(code: str) -> dict | None:
    """
    获取个股实时行情快照
    主接口: stock_zh_a_spot_em (全量表筛选)
    备用接口: stock_individual_info_em (单只查询)
    """
    # 主接口
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == code]
        if not row.empty:
            r = row.iloc[0]
            return {
                'price': _safe_float(r.get('最新价')),
                'change_pct': _safe_float(r.get('涨跌幅')),
                'volume': _safe_float(r.get('成交量')),
                'amount': _safe_float(r.get('成交额')),
                'high': _safe_float(r.get('最高')),
                'low': _safe_float(r.get('最低')),
                'open': _safe_float(r.get('今开')),
                'pre_close': _safe_float(r.get('昨收')),
            }
    except Exception as e:
        logger.warning(f"个股实时主接口失败 {code}: {e}")

    # 备用接口: stock_individual_info_em 返回 key-value 表
    try:
        df = ak.stock_individual_info_em(symbol=code)
        if df is not None and not df.empty:
            info = dict(zip(df['item'], df['value']))
            price = _safe_float(info.get('最新价', info.get('总市值')))
            if price > 0:
                return {
                    'price': price,
                    'change_pct': None,
                    'volume': None,
                    'amount': None,
                    'high': None,
                    'low': None,
                    'open': None,
                    'pre_close': None,
                }
    except Exception as e:
        logger.warning(f"个股实时备用接口(individual_info)失败 {code}: {e}")

    # 最终兜底: 用历史K线最后一行收盘价
    try:
        hist = fetch_stock_history(code)
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            logger.info(f"个股 {code} 使用历史K线最后收盘价兜底")
            return {
                'price': _safe_float(last['收盘']),
                'change_pct': _safe_float(last.get('涨跌幅')),
                'volume': _safe_float(last.get('成交量')),
                'amount': _safe_float(last.get('成交额')),
                'high': _safe_float(last.get('最高')),
                'low': _safe_float(last.get('最低')),
                'open': _safe_float(last.get('开盘')),
                'pre_close': None,
            }
    except Exception as e:
        logger.warning(f"个股历史K线兜底失败 {code}: {e}")

    logger.error(f"个股实时数据获取失败(全部接口不可用) {code}")
    return None


def fetch_stock_history(code: str) -> pd.DataFrame | None:
    """获取个股历史日K线"""
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date="20230101", adjust="qfq"
        )
        if df is None or df.empty:
            logger.warning(f"个股历史数据为空 {code}")
            return None
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期').reset_index(drop=True)
        return df
    except Exception as e:
        logger.error(f"个股历史数据获取失败 {code}: {e}")
        return None


# ==================== 场内基金 (ETF) ====================

def fetch_etf_realtime(code: str) -> dict | None:
    """
    获取ETF实时行情快照
    主接口: fund_etf_spot_em
    备用接口: fund_etf_hist_em 最后一行
    """
    # 主接口
    try:
        df = ak.fund_etf_spot_em()
        row = df[df['代码'] == code]
        if not row.empty:
            r = row.iloc[0]
            return {
                'price': _safe_float(r.get('最新价')),
                'change_pct': _safe_float(r.get('涨跌幅')),
            }
    except Exception as e:
        logger.warning(f"ETF实时主接口失败 {code}: {e}")

    # 备用: 历史K线最后一行
    try:
        hist = fetch_etf_history(code)
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            logger.info(f"ETF {code} 使用历史K线最后收盘价兜底")
            return {
                'price': _safe_float(last['收盘']),
                'change_pct': _safe_float(last.get('涨跌幅')),
            }
    except Exception as e:
        logger.warning(f"ETF历史K线兜底失败 {code}: {e}")

    logger.error(f"ETF实时数据获��失败(全部接口不可用) {code}")
    return None


def fetch_etf_history(code: str) -> pd.DataFrame | None:
    """获取ETF历史日K线"""
    try:
        df = ak.fund_etf_hist_em(
            symbol=code, period="daily",
            start_date="20230101", adjust="qfq"
        )
        if df is None or df.empty:
            logger.warning(f"ETF历史数据为空 {code}")
            return None
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期').reset_index(drop=True)
        return df
    except Exception as e:
        logger.error(f"ETF历史数据获取失败 {code}: {e}")
        return None


# ==================== 场外基金 (OTC) ====================

def fetch_otc_estimation(code: str) -> dict | None:
    """获取场外基金实时估值"""
    try:
        df = ak.fund_value_estimation_em(symbol=code)
        if df is None or df.empty:
            logger.warning(f"场外估值数据为空 {code}")
            return None
        record = df.iloc[0]
        return {
            "nav": float(record['估算净值']),
            "growth_rate": float(record['估算增长率']),
            "time": str(record['估算时间']),
        }
    except Exception as e:
        logger.error(f"场外估值获取失败 {code}: {e}")
        return None


def fetch_otc_history_nav(code: str) -> dict | None:
    """获取场外基金最近一天确认净值"""
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is None or df.empty:
            logger.warning(f"场外历史净值为空 {code}")
            return None
        last = df.iloc[-1]
        return {
            "nav": float(last['单位净值']),
            "date": str(last['净值日期']),
        }
    except Exception as e:
        logger.error(f"场外历史净值获取失败 {code}: {e}")
        return None