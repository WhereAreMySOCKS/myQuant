import json
import re
import time
import requests
import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
_RETRY_INTERVAL = 2

_TENCENT_REALTIME_URL = "https://qt.gtimg.cn/q={prefix}{code}"
_TENCENT_HISTORY_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_SINA_HISTORY_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
    "/CN_MarketData.getKLineData"
)
_TIANTIAN_ESTIMATION_URL = "https://fundgz.1234567.com.cn/js/{code}.js"
_TIANTIAN_HISTORY_URL = "https://api.fund.eastmoney.com/f10/lsjz"


def safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _exchange_prefix(code: str) -> str:
    """根据代码首字符判断交易所前缀 sh/sz"""
    return "sh" if code[0] in ("6", "5") else "sz"


def _get(url: str, **kwargs) -> requests.Response:
    """带重试的 GET 请求"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=10, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(_RETRY_INTERVAL)
            else:
                raise


# ==================== 个股 ====================

def fetch_stock_realtime(code: str) -> dict | None:
    """
    获取个股实时行情快照
    主接口: 腾讯财经 qt.gtimg.cn
    备用接口: 历史K线最后一行收盘价
    """
    logger.debug(f"[stock_realtime] 开始获取实时行情 {code}")
    t0 = time.time()

    prefix = _exchange_prefix(code)
    url = _TENCENT_REALTIME_URL.format(prefix=prefix, code=code)
    try:
        resp = _get(url)
        text = resp.text
        # 格式: v_sz000001="1~平安银行~000001~...~涨跌幅~..."
        m = re.search(r'"([^"]+)"', text)
        if m:
            fields = m.group(1).split("~")
            # 腾讯财经字段索引: 3=现价, 4=昨收, 5=今开, 8=涨跌, 31=涨跌幅(%), 36=成交量(手), 37=成交额(元), 33=最高, 34=最低
            if len(fields) > 37:
                price = safe_float(fields[3])
                result = {
                    "price": price,
                    "change_pct": safe_float(fields[31]),
                    "volume": safe_float(fields[36]),
                    "amount": safe_float(fields[37]),
                    "high": safe_float(fields[33]),
                    "low": safe_float(fields[34]),
                    "open": safe_float(fields[5]),
                    "pre_close": safe_float(fields[4]),
                }
                logger.debug(f"[stock_realtime] {code} 腾讯接口成功: 价格={price}, 耗时={time.time()-t0:.2f}s")
                return result
        logger.warning(f"[stock_realtime] {code} 腾讯接口返回数据解析失败: {text[:80]}")
    except Exception as e:
        logger.warning(f"[stock_realtime] {code} 腾讯接口失败: {e}")

    # 兜底: 历史K线最后一行收盘价
    try:
        logger.info(f"[stock_realtime] {code} 腾讯接口失败，尝试历史K线兜底")
        hist = fetch_stock_history(code)
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            price = safe_float(last["收盘"])
            logger.info(f"[stock_realtime] {code} 历史K线兜底成功: 收盘价={price}, 耗时={time.time()-t0:.2f}s")
            return {
                "price": price,
                "change_pct": safe_float(last.get("涨跌幅")),
                "volume": safe_float(last.get("成交量")),
                "amount": safe_float(last.get("成交额")),
                "high": safe_float(last.get("最高")),
                "low": safe_float(last.get("最低")),
                "open": safe_float(last.get("开盘")),
                "pre_close": None,
            }
    except Exception as e:
        logger.warning(f"[stock_realtime] {code} 历史K线兜底失败: {e}")

    logger.error(f"[stock_realtime] {code} 实时数据获取失败(全部接口不可用), 耗时={time.time()-t0:.2f}s")
    return None


def _fetch_history_tencent(code: str, asset_type: str) -> pd.DataFrame | None:
    """
    通用历史K线拉取（腾讯财经前复权日K线）
    asset_type: 'stock' 或 'etf'
    """
    prefix = _exchange_prefix(code)
    params = {
        "param": f"{prefix}{code},day,2023-01-01,,320,qfq",
        "_": int(time.time() * 1000),
    }
    try:
        resp = _get(_TENCENT_HISTORY_URL, params=params)
        data = resp.json()
        symbol_key = f"{prefix}{code}"
        qfq = (
            data.get("data", {}).get(symbol_key, {}).get("qfqday")
            or data.get("data", {}).get(symbol_key, {}).get("day")
        )
        if not qfq:
            return None
        rows = []
        for item in qfq:
            # [日期, 开, 收, 高, 低, 成交量]
            rows.append({
                "日期": pd.to_datetime(item[0]),
                "开盘": safe_float(item[1]),
                "收盘": safe_float(item[2]),
                "最高": safe_float(item[3]),
                "最低": safe_float(item[4]),
                "成交量": safe_float(item[5]),
            })
        df = pd.DataFrame(rows).sort_values("日期").reset_index(drop=True)
        return df
    except Exception as e:
        logger.warning(f"[history_tencent] {code} 腾讯K线失败: {e}")
        return None


def _fetch_history_sina(code: str) -> pd.DataFrame | None:
    """备用：新浪财经历史K线"""
    prefix = _exchange_prefix(code)
    params = {
        "symbol": f"{prefix}{code}",
        "type": "D",
        "dateback": 0,
        "num": 800,
        "start": "20230101",
        "end": "30000101",
    }
    try:
        resp = _get(_SINA_HISTORY_URL, params=params)
        data = resp.json()
        if not data:
            return None
        rows = []
        for item in data:
            rows.append({
                "日期": pd.to_datetime(item["d"]),
                "开盘": safe_float(item["o"]),
                "收盘": safe_float(item["c"]),
                "最高": safe_float(item["h"]),
                "最低": safe_float(item["l"]),
                "成交量": safe_float(item["v"]),
            })
        df = pd.DataFrame(rows).sort_values("日期").reset_index(drop=True)
        return df
    except Exception as e:
        logger.warning(f"[history_sina] {code} 新浪K线失败: {e}")
        return None


def fetch_stock_history(code: str) -> pd.DataFrame | None:
    """获取个股历史日K线（带重试）"""
    logger.debug(f"[stock_history] 开始获取历史K线 {code}")
    t0 = time.time()
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = _fetch_history_tencent(code, "stock")
            if df is not None and not df.empty:
                logger.debug(f"[stock_history] {code} 腾讯接口成功: {len(df)} 行, 耗时={time.time()-t0:.2f}s")
                return df
            logger.warning(f"[stock_history] {code} 腾讯接口数据为空 (第 {attempt}/{MAX_RETRIES} 次)，尝试新浪备用")
            df = _fetch_history_sina(code)
            if df is not None and not df.empty:
                logger.debug(f"[stock_history] {code} 新浪备用接口成功: {len(df)} 行, 耗时={time.time()-t0:.2f}s")
                return df
            logger.warning(f"[stock_history] {code} 新浪备用接口数据也为空 (第 {attempt}/{MAX_RETRIES} 次)")
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
    主接口: 腾讯财经 qt.gtimg.cn
    备用接口: 历史K线最后一行
    """
    logger.debug(f"[etf_realtime] 开始获取ETF实时行情 {code}")
    t0 = time.time()

    prefix = _exchange_prefix(code)
    url = _TENCENT_REALTIME_URL.format(prefix=prefix, code=code)
    try:
        resp = _get(url)
        text = resp.text
        m = re.search(r'"([^"]+)"', text)
        if m:
            fields = m.group(1).split("~")
            if len(fields) > 37:
                price = safe_float(fields[3])
                result = {
                    "price": price,
                    "change_pct": safe_float(fields[31]),
                }
                logger.debug(f"[etf_realtime] {code} 腾讯接口成功: 价格={price}, 耗时={time.time()-t0:.2f}s")
                return result
        logger.warning(f"[etf_realtime] {code} 腾讯接口返回数据解析失败: {text[:80]}")
    except Exception as e:
        logger.warning(f"[etf_realtime] {code} 腾讯接口失败: {e}")

    # 备用: 历史K线最后一行
    try:
        logger.info(f"[etf_realtime] {code} 腾讯接口失败，尝试历史K线兜底")
        hist = fetch_etf_history(code)
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            price = safe_float(last["收盘"])
            logger.info(f"[etf_realtime] {code} 历史K线兜底成功: 收盘价={price}, 耗时={time.time()-t0:.2f}s")
            return {
                "price": price,
                "change_pct": safe_float(last.get("涨跌幅")),
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
            df = _fetch_history_tencent(code, "etf")
            if df is not None and not df.empty:
                logger.debug(f"[etf_history] {code} 腾讯接口成功: {len(df)} 行, 耗时={time.time()-t0:.2f}s")
                return df
            logger.warning(f"[etf_history] {code} 腾讯接口数据为空 (第 {attempt}/{MAX_RETRIES} 次)，尝试新浪备用")
            df = _fetch_history_sina(code)
            if df is not None and not df.empty:
                logger.debug(f"[etf_history] {code} 新浪备用接口成功: {len(df)} 行, 耗时={time.time()-t0:.2f}s")
                return df
            logger.warning(f"[etf_history] {code} 新浪备用接口数据也为空 (第 {attempt}/{MAX_RETRIES} 次)")
        except Exception as e:
            last_exc = e
            logger.warning(f"[etf_history] {code} 第 {attempt}/{MAX_RETRIES} 次失败: {e}")
        if attempt < MAX_RETRIES:
            time.sleep(_RETRY_INTERVAL)
    logger.error(f"[etf_history] {code} 历史数据获取失败, 耗时={time.time()-t0:.2f}s", exc_info=last_exc)
    return None


# ==================== 场外基金 (OTC) ====================

def fetch_otc_estimation(code: str) -> dict | None:
    """获取场外基金实时估值（天天基金 JSONP 接口）"""
    logger.debug(f"[otc_estimation] 开始获取场外估值 {code}")
    t0 = time.time()
    url = _TIANTIAN_ESTIMATION_URL.format(code=code)
    try:
        resp = _get(url)
        text = resp.text
        # 格式: jsonpgz({"fundcode":"...","name":"...","gsz":"1.234","gszzl":"0.56","gztime":"..."})
        m = re.search(r'jsonpgz\((\{.*\})\)', text)
        if not m:
            logger.warning(f"[otc_estimation] {code} 天天基金接口返回数据解析失败: {text[:80]}")
            return None
        obj = json.loads(m.group(1))
        nav = safe_float(obj.get("gsz"))
        growth_rate = safe_float(obj.get("gszzl"))
        est_time = str(obj.get("gztime", ""))
        logger.debug(f"[otc_estimation] {code} 获取成功: 估算净值={nav}, 估算增长率={growth_rate}%, 耗时={time.time()-t0:.2f}s")
        return {
            "nav": nav,
            "growth_rate": growth_rate,
            "time": est_time,
        }
    except Exception as e:
        logger.error(f"[otc_estimation] {code} 场外估值获取失败, 耗时={time.time()-t0:.2f}s", exc_info=True)
        return None


def fetch_otc_history_nav(code: str) -> dict | None:
    """获取场外基金最近一天确认净值（天天基金历史净值接口）"""
    logger.debug(f"[otc_history_nav] 开始获取场外历史净值 {code}")
    t0 = time.time()
    params = {
        "fundCode": code,
        "pageIndex": 1,
        "pageSize": 1,
        "type": "lsjz",
    }
    headers = {"Referer": "https://fundf10.eastmoney.com/"}
    try:
        resp = _get(_TIANTIAN_HISTORY_URL, params=params, headers=headers)
        data = resp.json()
        records = data.get("Data", {}).get("LSJZList", [])
        if not records:
            logger.warning(f"[otc_history_nav] {code} 场外历史净值为空")
            return None
        last = records[0]
        nav = safe_float(last.get("DWJZ"))
        date = str(last.get("FSRQ", ""))
        logger.debug(f"[otc_history_nav] {code} 获取成功: 净值={nav}, 日期={date}, 耗时={time.time()-t0:.2f}s")
        return {
            "nav": nav,
            "date": date,
        }
    except Exception as e:
        logger.error(f"[otc_history_nav] {code} 场外历史净值获取失败, 耗时={time.time()-t0:.2f}s", exc_info=True)
        return None