import asyncio
import random
import threading
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Set

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db, SessionLocal, Target
from app.utils import is_trading_time, get_current_time
from app.services.data_fetcher import (
    fetch_stock_realtime, fetch_stock_history,
    fetch_etf_realtime, fetch_etf_history,
    fetch_otc_estimation, safe_float,
)
from app.services.analyzer import compute_indicators, check_signal
from app.services.notifier import send_email
from app.services.code_resolver import init_security_info
from app.routes import target as target_router
from app.routes import quote as quote_router

# ========== 全局注入浏览器 Headers，随机 UA 轮换 ==========
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]

_BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)


def _patch_requests_headers():
    """
    Monkey-patch requests.Session：随机 User-Agent + urllib3 自动重试
    """
    _original_init = requests.Session.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        headers = dict(_BASE_HEADERS)
        headers["User-Agent"] = random.choice(_USER_AGENTS)
        self.headers.update(headers)
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    requests.Session.__init__ = _patched_init


# 启动时立即执行 patch
_patch_requests_headers()

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
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


# ========== 核心监控循环 ==========
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


# ========== FastAPI 生命周期 ==========
@asynccontextmanager
async def lifespan(the_app: FastAPI):
    # 1. 建表
    init_db()
    logger.info("数据库表结构初始化完成")

    # 2. 初始化标的信息缓存（首次启动会拉取全量数据，耗时约 10~15 秒）
    logger.info("检查标的信息缓存表...")
    await asyncio.to_thread(init_security_info)

    # 3. 启动监控
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