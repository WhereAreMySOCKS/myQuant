import time
import akshare as ak
import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
_RETRY_INTERVAL = 3


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
    logger.debug(f"[stock_realtime] 开始获取实时行情 {code}")
    t0 = time.time()

    # 主接口
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == code]
        if not row.empty:
            r = row.iloc[0]
            price = _safe_float(r.get('最新价'))
            result = {
                'price': price,
                'change_pct': _safe_float(r.get('涨跌幅')),
                'volume': _safe_float(r.get('成交量')),
                'amount': _safe_float(r.get('成交额')),
                'high': _safe_float(r.get('最高')),
                'low': _safe_float(r.get('最低')),
                'open': _safe_float(r.get('今开')),
                'pre_close': _safe_float(r.get('昨收')),
            }
            logger.debug(f"[stock_realtime] {code} 主接口成功: 价格={price}, 耗时={time.time()-t0:.2f}s")
            return result
        else:
            logger.warning(f"[stock_realtime] {code} 主接口返回数据中未找到该代码")
    except Exception as e:
        logger.warning(f"[stock_realtime] {code} 主接口失败: {e}")

    # 备用接口: stock_individual_info_em 返回 key-value 表
    try:
        df = ak.stock_individual_info_em(symbol=code)
        if df is not None and not df.empty:
            info = dict(zip(df['item'], df['value']))
            price = _safe_float(info.get('最新价', info.get('总市值')))
            if price > 0:
                logger.debug(f"[stock_realtime] {code} 备用接口(individual_info)成功: 价格={price}, 耗时={time.time()-t0:.2f}s")
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
        logger.warning(f"[stock_realtime] {code} 备用接口(individual_info)失败: {e}")

    # 最终兜底: 用历史K线最后一行收盘价
    try:
        logger.info(f"[stock_realtime] {code} 主/备用接口均失败，尝试历史K线兜底")
        hist = fetch_stock_history(code)
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            price = _safe_float(last['收盘'])
            logger.info(f"[stock_realtime] {code} 历史K线兜底成功: 收盘价={price}, 耗时={time.time()-t0:.2f}s")
            return {
                'price': price,
                'change_pct': _safe_float(last.get('涨跌幅')),
                'volume': _safe_float(last.get('成交量')),
                'amount': _safe_float(last.get('成交额')),
                'high': _safe_float(last.get('最高')),
                'low': _safe_float(last.get('最低')),
                'open': _safe_float(last.get('开盘')),
                'pre_close': None,
            }
    except Exception as e:
        logger.warning(f"[stock_realtime] {code} 历史K线兜底失败: {e}")

    logger.error(f"[stock_realtime] {code} 实时数据获取失败(全部接口不可用), 耗时={time.time()-t0:.2f}s")
    return None


def fetch_stock_history(code: str) -> pd.DataFrame | None:
    """获取个股历史日K线（带重试）"""
    logger.debug(f"[stock_history] 开始获取历史K线 {code}")
    t0 = time.time()
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date="20230101", adjust="qfq"
            )
            if df is None or df.empty:
                logger.warning(f"[stock_history] {code} 历史数据为空 (第 {attempt}/{MAX_RETRIES} 次)")
                return None
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.sort_values('日期').reset_index(drop=True)
            logger.debug(f"[stock_history] {code} 获取成功: {len(df)} 行, 耗时={time.time()-t0:.2f}s")
            return df
        except Exception as e:
            last_exc = e
            logger.warning(f"[stock_history] {code} 第 {attempt}/{MAX_RETRIES} 次失败: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(_RETRY_INTERVAL)
    logger.error(f"[stock_history] {code} 历史数据获取失败, 耗时={time.time()-t0:.2f}s", exc_info=last_exc)
    return None


# ==================== 场内基金 (ETF) ====================

def fetch_etf_realtime(code: str) -> dict | None:
    """
    获取ETF实时行情快照
    主接口: fund_etf_spot_em
    备用接口: fund_etf_hist_em 最后一行
    """
    logger.debug(f"[etf_realtime] 开始获取ETF实时行情 {code}")
    t0 = time.time()

    # 主接口
    try:
        df = ak.fund_etf_spot_em()
        row = df[df['代码'] == code]
        if not row.empty:
            r = row.iloc[0]
            price = _safe_float(r.get('最新价'))
            result = {
                'price': price,
                'change_pct': _safe_float(r.get('涨跌幅')),
            }
            logger.debug(f"[etf_realtime] {code} 主接口成功: 价格={price}, 耗时={time.time()-t0:.2f}s")
            return result
        else:
            logger.warning(f"[etf_realtime] {code} 主接口返回数据中未找到该代码")
    except Exception as e:
        logger.warning(f"[etf_realtime] {code} 主接口失败: {e}")

    # 备用: 历史K线最后一行
    try:
        logger.info(f"[etf_realtime] {code} 主接口失败，尝试历史K线兜底")
        hist = fetch_etf_history(code)
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            price = _safe_float(last['收盘'])
            logger.info(f"[etf_realtime] {code} 历史K线兜底成功: 收盘价={price}, 耗时={time.time()-t0:.2f}s")
            return {
                'price': price,
                'change_pct': _safe_float(last.get('涨跌幅')),
            }
    except Exception as e:
        logger.warning(f"[etf_realtime] {code} 历史K线兜底失败: {e}")

    logger.error(f"[etf_realtime] {code} 实时数据获取失败(全部接口不可用), 耗时={time.time()-t0:.2f}s")
    return None


def fetch_etf_history(code: str) -> pd.DataFrame | None:
    """获取ETF历史日K线（带重试）"""
    logger.debug(f"[etf_history] 开始获取ETF历史K线 {code}")
    t0 = time.time()
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = ak.fund_etf_hist_em(
                symbol=code, period="daily",
                start_date="20230101", adjust="qfq"
            )
            if df is None or df.empty:
                logger.warning(f"[etf_history] {code} 历史数据为空 (第 {attempt}/{MAX_RETRIES} 次)")
                return None
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.sort_values('日期').reset_index(drop=True)
            logger.debug(f"[etf_history] {code} 获取成功: {len(df)} 行, 耗时={time.time()-t0:.2f}s")
            return df
        except Exception as e:
            last_exc = e
            logger.warning(f"[etf_history] {code} 第 {attempt}/{MAX_RETRIES} 次失败: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(_RETRY_INTERVAL)
    logger.error(f"[etf_history] {code} 历史数据获取失败, 耗时={time.time()-t0:.2f}s", exc_info=last_exc)
    return None


# ==================== 场外基金 (OTC) ====================

def fetch_otc_estimation(code: str) -> dict | None:
    """获取场外基金实时估值"""
    logger.debug(f"[otc_estimation] 开始获取场外估值 {code}")
    t0 = time.time()
    try:
        df = ak.fund_value_estimation_em(symbol=code)
        if df is None or df.empty:
            logger.warning(f"[otc_estimation] {code} 场外估值数据为空")
            return None
        record = df.iloc[0]
        nav = float(record['估算净值'])
        growth_rate = float(record['估算增长率'])
        logger.debug(f"[otc_estimation] {code} 获取成功: 估算净值={nav}, 估算增长率={growth_rate}%, 耗时={time.time()-t0:.2f}s")
        return {
            "nav": nav,
            "growth_rate": growth_rate,
            "time": str(record['估算时间']),
        }
    except Exception as e:
        logger.error(f"[otc_estimation] {code} 场外估值获取失败, 耗时={time.time()-t0:.2f}s", exc_info=True)
        return None


def fetch_otc_history_nav(code: str) -> dict | None:
    """获取场外基金最近一天确认净值"""
    logger.debug(f"[otc_history_nav] 开始获取场外历史净值 {code}")
    t0 = time.time()
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is None or df.empty:
            logger.warning(f"[otc_history_nav] {code} 场外历史净值为空")
            return None
        last = df.iloc[-1]
        nav = float(last['单位净值'])
        date = str(last['净值日期'])
        logger.debug(f"[otc_history_nav] {code} 获取成功: 净值={nav}, 日期={date}, 耗时={time.time()-t0:.2f}s")
        return {
            "nav": nav,
            "date": date,
        }
    except Exception as e:
        logger.error(f"[otc_history_nav] {code} 场外历史净值获取失败, 耗时={time.time()-t0:.2f}s", exc_info=True)
        return None