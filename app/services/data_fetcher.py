import akshare as ak
import pandas as pd
import logging

logger = logging.getLogger(__name__)


# ==================== 个股 ====================

def fetch_stock_realtime(code: str) -> dict | None:
    """获取个股实时行情快照"""
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df['代码'] == code]
        if row.empty:
            return None
        row = row.iloc[0]
        return {
            'price': float(row['最新价']),
            'change_pct': float(row['涨跌幅']),
            'volume': float(row['��交量']),
            'amount': float(row['成交额']),
            'high': float(row['最高']),
            'low': float(row['最低']),
            'open': float(row['今开']),
            'pre_close': float(row['昨收']),
        }
    except Exception as e:
        logger.error(f"个股实时数据获取失败 {code}: {e}")
        return None


def fetch_stock_history(code: str) -> pd.DataFrame | None:
    """获取个股历史日K线"""
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date="20230101", adjust="qfq"
        )
        if df.empty:
            return None
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期').reset_index(drop=True)
        return df
    except Exception as e:
        logger.error(f"个股历史数据获取失败 {code}: {e}")
        return None


# ==================== 场内基金 (ETF) ====================

def fetch_etf_realtime(code: str) -> dict | None:
    """获取ETF实时行情快照"""
    try:
        df = ak.fund_etf_spot_em()
        row = df[df['代码'] == code]
        if row.empty:
            return None
        row = row.iloc[0]
        return {
            'price': float(row['最新价']),
            'change_pct': float(row['涨跌幅']),
        }
    except Exception as e:
        logger.error(f"ETF实时数据获取失败 {code}: {e}")
        return None


def fetch_etf_history(code: str) -> pd.DataFrame | None:
    """获取ETF历史日K线"""
    try:
        df = ak.fund_etf_hist_em(
            symbol=code, period="daily",
            start_date="20230101", adjust="qfq"
        )
        if df.empty:
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
        if df.empty:
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
        if df.empty:
            return None
        last = df.iloc[-1]
        return {
            "nav": float(last['单位净值']),
            "date": str(last['净值日期']),
        }
    except Exception as e:
        logger.error(f"场外历史净值获取失败 {code}: {e}")
        return None