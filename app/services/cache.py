"""历史K线缓存与报警去重管理。"""

import threading
import logging
from typing import Optional, Dict, Any

import pandas as pd

from app.utils.time_utils import get_current_time
from app.services.data_fetcher import fetch_stock_history, fetch_etf_history

logger = logging.getLogger(__name__)


class HistoryCache:
    """按交易日自动刷新的历史K线缓存（线程安全）。

    每个新交易日首次访问时自动清空缓存，确保使用当日最新数据。
    只缓存成功获取的结果；失败时直接返回 None，不影响缓存状态。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_date: Optional[str] = None

    def _today(self) -> str:
        return get_current_time().strftime("%Y-%m-%d")

    def _maybe_refresh(self) -> None:
        """若已跨日则清空缓存（调用方须持有锁）。"""
        today = self._today()
        if self._cache_date != today:
            self._cache = {}
            self._cache_date = today
            logger.info("历史K线缓存已刷新（新交易日: %s）", today)

    def get(self, code: str, t_type: str) -> Optional[pd.DataFrame]:
        """获取指定代码的历史K线，未命中则实时拉取并缓存。

        Args:
            code: 证券代码，例如 '600000'。
            t_type: 资产类型，'stock' 或 'etf'。

        Returns:
            历史K线 DataFrame，获取失败时返回 None。
        """
        with self._lock:
            self._maybe_refresh()
            if code in self._cache:
                logger.debug("[HistoryCache] 缓存命中: %s", code)
                return self._cache[code]

        # 缓存未命中，在锁外拉取（避免阻塞其他线程）
        hist: Optional[pd.DataFrame] = None
        if t_type == "stock":
            hist = fetch_stock_history(code)
        elif t_type == "etf":
            hist = fetch_etf_history(code)
        else:
            logger.warning("[HistoryCache] 不支持的资产类型: %s (code=%s)", t_type, code)

        with self._lock:
            # 二次检查，防止并发时重复写入
            self._maybe_refresh()
            if hist is not None and code not in self._cache:
                self._cache[code] = hist
                logger.debug("[HistoryCache] 写入缓存: %s (%d 行)", code, len(hist))

        return hist

    def clear(self) -> None:
        """强制清空缓存。"""
        with self._lock:
            self._cache = {}
            self._cache_date = None
            logger.info("[HistoryCache] 缓存已强制清空")

    def stats(self) -> Dict[str, Any]:
        """返回缓存统计信息。

        Returns:
            包含 ``date``、``size`` 的字典。
        """
        with self._lock:
            return {
                "date": self._cache_date,
                "size": len(self._cache),
            }


class AlertStateManager:
    """报警去重管理器（线程安全）。

    每个标的每天的每类信号只触发一次报警；跨日自动重置。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: Dict[str, Dict[str, Any]] = {}

    def _today(self) -> str:
        return get_current_time().strftime("%Y-%m-%d")

    def is_alerted(self, code: str, signal: str) -> bool:
        """判断今日该代码的该信号是否已触发过报警。

        Args:
            code: 证券代码。
            signal: 信号类型，'BUY' 或 'SELL'。

        Returns:
            若今日已报警则返回 True，否则 False。
        """
        today = self._today()
        with self._lock:
            rec = self._history.get(code)
            return (
                rec is not None
                and rec["date"] == today
                and signal in rec["signals"]
            )

    def mark_alerted(self, code: str, signal: str) -> None:
        """标记今日该代码的该信号已报警。

        Args:
            code: 证券代码。
            signal: 信号类型，'BUY' 或 'SELL'。
        """
        today = self._today()
        with self._lock:
            if code not in self._history or self._history[code]["date"] != today:
                self._history[code] = {"date": today, "signals": set()}
            self._history[code]["signals"].add(signal)
            logger.debug("[AlertStateManager] 标记已报警: code=%s signal=%s", code, signal)

    def clear(self) -> None:
        """强制清空所有报警记录。"""
        with self._lock:
            self._history = {}
            logger.info("[AlertStateManager] 报警记录已清空")

    def stats(self) -> Dict[str, Any]:
        """返回报警状态统计信息。

        Returns:
            包含 ``total_codes``、``today_alerted`` 的字典。
        """
        today = self._today()
        with self._lock:
            today_alerted = sum(
                1 for rec in self._history.values() if rec["date"] == today
            )
            return {
                "total_codes": len(self._history),
                "today_alerted": today_alerted,
            }
