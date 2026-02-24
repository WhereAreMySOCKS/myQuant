import asyncio
import threading
import logging
from typing import Optional, Dict, Set

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db, SessionLocal, Target
from app.utils import is_trading_time, get_current_time
from app.services.data_fetcher import (
    fetch_stock_realtime, fetch_stock_history,
    fetch_etf_realtime, fetch_etf_history,
    fetch_otc_estimation,
)
from app.services.analyzer import compute_indicators, check_signal
from app.services.notifier import send_email
from app.routes import target as target_router
from app.routes import quote as quote_router

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ========== 报警状态管理 ==========
ALERT_HISTORY = {}
ALERT_LOCK = threading.Lock()

# 历史K线缓存（加锁保护）
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
    """获取历史K线（带线程安全缓存，每日刷新）"""
    global HIST_CACHE, HIST_CACHE_DATE
    today = get_current_time().strftime("%Y-%m-%d")

    with HIST_CACHE_LOCK:
        if HIST_CACHE_DATE != today:
            HIST_CACHE = {}
            HIST_CACHE_DATE = today
            logger.info("历史K线缓存已刷新（新交易日）")

        if code in HIST_CACHE:
            return HIST_CACHE[code]

    # 在锁外执行耗时的网络请求
    hist = None
    if t_type == "stock":
        hist = fetch_stock_history(code)
    elif t_type == "etf":
        hist = fetch_etf_history(code)

    with HIST_CACHE_LOCK:
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


# ========== 核心监控循环 ==========
async def monitor_loop():
    while True:
        if not is_trading_time():
            await asyncio.sleep(60)
            continue

        logger.info("执行一轮扫描...")
        targets = await asyncio.to_thread(_load_targets_from_db)

        if not targets:
            logger.info("暂无关注标的，等待下一轮...")
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
            continue

        alerts = []

        for t in targets:
            code = t["code"]
            name = t["name"]
            t_type = t["type"]

            try:
                # ====== 个股 / ETF ======
                if t_type in ("stock", "etf"):
                    if t_type == "stock":
                        rt = await asyncio.to_thread(fetch_stock_realtime, code)
                    else:
                        rt = await asyncio.to_thread(fetch_etf_realtime, code)
                    if not rt:
                        continue

                    price = rt["price"]
                    hist_df = await asyncio.to_thread(_get_history, code, t_type)
                    if hist_df is None:
                        continue

                    indicators = compute_indicators(hist_df, price)
                    if not indicators:
                        continue

                    signal = check_signal(
                        indicators,
                        buy_bias_rate=t["buy_bias_rate"],
                        sell_bias_rate=t["sell_bias_rate"],
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

                # ====== 场外基金 ======
                elif t_type == "otc":
                    est = await asyncio.to_thread(fetch_otc_estimation, code)
                    if not est:
                        continue

                    otc_indicators = {"growth_rate": est["growth_rate"]}
                    signal = check_signal(
                        otc_indicators,
                        buy_growth_rate=t["buy_growth_rate"],
                        sell_growth_rate=t["sell_growth_rate"],
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

            except Exception as e:
                logger.error("监控 {}({}) 出错: {}".format(name, code, e))

        if alerts:
            await asyncio.to_thread(
                send_email,
                "【交易信号】发现 {} 个信号".format(len(alerts)),
                "\n" + ("-" * 30 + "\n").join(alerts),
            )

        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)


# ========== FastAPI 生命周期 ==========
@asynccontextmanager
async def lifespan(the_app: FastAPI):
    init_db()
    logger.info("数据库初始化完成")
    task = asyncio.create_task(monitor_loop())
    logger.info("系统启动: 高频监控已启动，间隔 %d 秒", settings.POLL_INTERVAL_SECONDS)
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("系统关闭: 监控已停止")


app = FastAPI(
    lifespan=lifespan,
    title="Investment Guard V3",
    description="A股投资监控系统 - 个股/ETF/场外基金 实时监控 + 买卖信号报警",
    version="3.0.0",
)

# 注册路由
app.include_router(target_router.router)
app.include_router(quote_router.router)


@app.get("/", tags=["系统"])
def root():
    db = SessionLocal()
    try:
        count = db.query(Target).count()
    finally:
        db.close()
    return {
        "status": "active",
        "trading_time": is_trading_time(),
        "monitored_count": count,
    }