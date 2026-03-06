import asyncio
import time
import threading
import logging

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.target import Target
from app.utils.time_utils import is_trading_time, get_current_time
from app.services.data_fetcher import (
    fetch_stock_realtime, fetch_stock_history,
    fetch_etf_realtime, fetch_etf_history,
    fetch_otc_estimation,
)
from app.services.analyzer import compute_indicators, check_signal
from app.services.notifier import send_email

logger = logging.getLogger(__name__)

# ========== 报警状态管理 ==========
ALERT_HISTORY = {}
ALERT_LOCK = threading.Lock()

# 历史K线缓存
HIST_CACHE = {}
HIST_CACHE_DATE = None
HIST_CACHE_LOCK = threading.Lock()


def _is_alerted(code, signal):
    today = get_current_time().strftime("%Y-%m-%d")
    with ALERT_LOCK:
        rec = ALERT_HISTORY.get(code)
        return rec is not None and rec["date"] == today and signal in rec["signals"]


def _mark_alerted(code, signal):
    today = get_current_time().strftime("%Y-%m-%d")
    with ALERT_LOCK:
        if code not in ALERT_HISTORY or ALERT_HISTORY[code]["date"] != today:
            ALERT_HISTORY[code] = {"date": today, "signals": set()}
        ALERT_HISTORY[code]["signals"].add(signal)


def _get_history(code, t_type):
    global HIST_CACHE, HIST_CACHE_DATE
    today = get_current_time().strftime("%Y-%m-%d")

    with HIST_CACHE_LOCK:
        if HIST_CACHE_DATE != today:
            HIST_CACHE = {}
            HIST_CACHE_DATE = today
            logger.info("历史K线缓存已刷新（新交易日）")

        if code in HIST_CACHE:
            return HIST_CACHE[code]

    hist = None
    if t_type == "stock":
        hist = fetch_stock_history(code)
    elif t_type == "etf":
        hist = fetch_etf_history(code)

    with HIST_CACHE_LOCK:
        if hist is not None:  # 只缓存成功结果
            HIST_CACHE[code] = hist

    return hist


def _load_targets_from_db():
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


async def monitor_loop():
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

        alerts = []
        processed = 0
        skipped = 0
        errors = 0

        for t in targets:
            code = t["code"]
            name = t["name"]
            t_type = t["type"]

            try:
                if t_type in ("stock", "etf"):
                    if t_type == "stock":
                        rt = await asyncio.to_thread(fetch_stock_realtime, code)
                    else:
                        rt = await asyncio.to_thread(fetch_etf_realtime, code)
                    if not rt:
                        logger.warning(f"[monitor] {name}({code}) 实时数据获取失败，跳过")
                        skipped += 1
                        continue

                    price = rt["price"]
                    hist_df = await asyncio.to_thread(_get_history, code, t_type)
                    if hist_df is None:
                        logger.warning(f"[monitor] {name}({code}) 历史K线获取失败，跳过")
                        skipped += 1
                        continue

                    indicators = compute_indicators(hist_df, price, code=code)
                    if not indicators:
                        logger.warning(f"[monitor] {name}({code}) 指标计算失败（数据不足），跳过")
                        skipped += 1
                        continue

                    signal = check_signal(
                        indicators,
                        buy_bias_rate=t["buy_bias_rate"],
                        sell_bias_rate=t["sell_bias_rate"],
                    )
                    logger.debug(
                        f"[monitor] {name}({code}) 价格={price}, MA250={indicators['ma250']}, "
                        f"乖离率={indicators['bias_percent']}, 信号={signal}"
                    )

                    if signal and not _is_alerted(code, signal):
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
                        alerts.append(msg)
                        _mark_alerted(code, signal)
                        logger.info(f"[monitor] {name}({code}) 触发{signal}信号: 价格={price}, 乖离率={indicators['bias_percent']}")

                elif t_type == "otc":
                    est = await asyncio.to_thread(fetch_otc_estimation, code)
                    if not est:
                        logger.warning(f"[monitor] {name}({code}) 场外估值获取失败，跳过")
                        skipped += 1
                        continue

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

                    if signal and not _is_alerted(code, signal):
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
                        alerts.append(msg)
                        _mark_alerted(code, signal)
                        logger.info(f"[monitor] {name}({code}) 场外触发{signal}信号: 估算增长率={est['growth_rate']}%")

                processed += 1

            except Exception as e:
                errors += 1
                logger.error(f"[monitor] {name}({code}) 处理出错: {e}", exc_info=True)

        scan_elapsed = time.time() - scan_start
        logger.info(
            f"[monitor] 本轮扫描完成: 总耗时={scan_elapsed:.2f}s, "
            f"处理={processed}, 跳过={skipped}, 出错={errors}, 触发信号={len(alerts)}"
        )

        if alerts:
            subject = "【交易信号】发现 {} 个信号".format(len(alerts))
            logger.info(f"[monitor] 发送报警邮件: {subject}, 信号摘要={[a.splitlines()[0] for a in alerts]}")
            await asyncio.to_thread(
                send_email,
                subject,
                "\n" + ("-" * 30 + "\n").join(alerts),
            )

        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
