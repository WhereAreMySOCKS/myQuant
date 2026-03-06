import asyncio
import time
import logging

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.target import Target
from app.utils.time_utils import is_trading_time
from app.services.data_fetcher import (
    fetch_stock_realtime, fetch_etf_realtime,
    fetch_otc_estimation,
)
from app.services.analyzer import compute_indicators, check_signal
from app.services.notifier import send_email
from app.services.cache import HistoryCache, AlertStateManager

logger = logging.getLogger(__name__)

# 单例缓存与报警管理器
_history_cache = HistoryCache()
_alert_state = AlertStateManager()


def _load_targets_from_db():
    """从数据库加载所有监控标的列表。"""
    db = SessionLocal()
    try:
        rows = db.query(Target).all()
        return [
            {
                "code": r.code,
                "name": r.name,
                "type": r.type.value,
                "buy_bias_rate": r.buy_bias_rate,
                "sell_bias_rate": r.sell_bias_rate,
                "buy_growth_rate": r.buy_growth_rate,
                "sell_growth_rate": r.sell_growth_rate,
            }
            for r in rows
        ]
    finally:
        db.close()


async def _process_target(t: dict, semaphore: asyncio.Semaphore) -> list[str]:
    """处理单个监控标的，返回触发的报警消息列表。

    Args:
        t: 标的信息字典。
        semaphore: 并发控制信号量。

    Returns:
        触发的报警消息列表（通常为空列表或含一条消息）。
    """
    async with semaphore:
        code = t["code"]
        name = t["name"]
        t_type = t["type"]

        if t_type in ("stock", "etf"):
            if t_type == "stock":
                rt = await asyncio.to_thread(fetch_stock_realtime, code)
            else:
                rt = await asyncio.to_thread(fetch_etf_realtime, code)
            if not rt:
                logger.warning(f"[monitor] {name}({code}) 实时数据获取失败，跳过")
                return []

            price = rt["price"]
            hist_df = await asyncio.to_thread(_history_cache.get, code, t_type)
            if hist_df is None:
                logger.warning(f"[monitor] {name}({code}) 历史K线获取失败，跳过")
                return []

            indicators = compute_indicators(hist_df, price, code=code)
            if not indicators:
                logger.warning(f"[monitor] {name}({code}) 指标计算失败（数据不足），跳过")
                return []

            signal = check_signal(
                indicators,
                buy_bias_rate=t["buy_bias_rate"],
                sell_bias_rate=t["sell_bias_rate"],
            )
            logger.debug(
                f"[monitor] {name}({code}) 价格={price}, MA250={indicators['ma250']}, "
                f"乖离率={indicators['bias_percent']}, 信号={signal}"
            )

            if signal and not _alert_state.is_alerted(code, signal):
                emoji = "🟢 BUY" if signal == "BUY" else "🔴 SELL"
                label = "个股" if t_type == "stock" else "ETF"
                msg = (
                    "【{}信号 {}】{}({})\n"
                    "现价: {} / 年线: {}\n"
                    "乖离度: {}\n"
                ).format(
                    emoji, label, name, code,
                    price, indicators["ma250"],
                    indicators["bias_percent"],
                )
                _alert_state.mark_alerted(code, signal)
                logger.info(
                    f"[monitor] {name}({code}) 触发{signal}信号: 价格={price}, "
                    f"乖离率={indicators['bias_percent']}"
                )
                return [msg]

        elif t_type == "otc":
            est = await asyncio.to_thread(fetch_otc_estimation, code)
            if not est:
                logger.warning(f"[monitor] {name}({code}) 场外估值获取失败，跳过")
                return []

            otc_indicators = {"growth_rate": est["growth_rate"]}
            signal = check_signal(
                otc_indicators,
                buy_growth_rate=t["buy_growth_rate"],
                sell_growth_rate=t["sell_growth_rate"],
            )
            logger.debug(
                f"[monitor] {name}({code}) 场外估算净值={est['nav']}, "
                f"估算增长率={est['growth_rate']}%, 信号={signal}"
            )

            if signal and not _alert_state.is_alerted(code, signal):
                emoji = "🟢 BUY" if signal == "BUY" else "🔴 SELL"
                msg = (
                    "【{}信号 场外】{}({})\n"
                    "实时估值: {}\n"
                    "估算涨跌: {}%\n"
                    "更新时间: {}\n"
                ).format(
                    emoji, name, code,
                    est["nav"],
                    est["growth_rate"],
                    est["time"],
                )
                _alert_state.mark_alerted(code, signal)
                logger.info(
                    f"[monitor] {name}({code}) 场外触发{signal}信号: "
                    f"估算增长率={est['growth_rate']}%"
                )
                return [msg]

        return []


async def monitor_loop():
    """主监控循环：按 POLL_INTERVAL_SECONDS 轮询，并发处理所有标的。"""
    while True:
        if not is_trading_time():
            await asyncio.sleep(60)
            continue

        scan_start = time.time()
        targets = await asyncio.to_thread(_load_targets_from_db)
        total = len(targets)
        logger.info(f"[monitor] 开始新一轮扫描，共 {total} 个标的")

        if not targets:
            logger.info("[monitor] 暂无关注标的，等待下一轮...")
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
            continue

        semaphore = asyncio.Semaphore(settings.MONITOR_CONCURRENCY)
        tasks = [_process_target(t, semaphore) for t in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        alerts: list[str] = []
        errors = 0
        for r in results:
            if isinstance(r, Exception):
                errors += 1
                logger.error(f"[monitor] 标的处理出错: {r}", exc_info=r)
            else:
                alerts.extend(r)

        scan_elapsed = time.time() - scan_start
        cache_stats = _history_cache.stats()
        alert_stats = _alert_state.stats()
        logger.info(
            f"[monitor] 本轮扫描完成: 总耗时={scan_elapsed:.2f}s, "
            f"处理={total - errors}, 出错={errors}, 触发信号={len(alerts)} | "
            f"缓存={cache_stats} | 报警状态={alert_stats}"
        )

        if alerts:
            subject = "【交易信号】发现 {} 个信号".format(len(alerts))
            logger.info(
                f"[monitor] 发送报警邮件: {subject}, "
                f"信号摘要={[a.splitlines()[0] for a in alerts]}"
            )
            await asyncio.to_thread(
                send_email,
                subject,
                "\n" + ("-" * 30 + "\n").join(alerts),
            )

        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
