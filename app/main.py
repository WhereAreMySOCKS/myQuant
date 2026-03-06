import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.database import SessionLocal, init_db
from app.core.exceptions import AppException
from app.models.target import Target  # noqa: F401 — register ORM model
from app.utils import http_client  # noqa: F401 — auto-patch requests on import
from app.utils.time_utils import is_trading_time
from app.routes import target as target_router
from app.routes import quote as quote_router
from app.routes import backtest as backtest_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(the_app: FastAPI):
    # 0. 配置日志
    setup_logging(settings)

    # 1. 建表
    init_db()
    logger.info("数据库表结构初始化完成")

    # 2. 初始化标的信息缓存（首次启动会拉取全量数据，耗时约 10~15 秒）
    from app.services.code_resolver import init_security_info
    logger.info("检查标的信息缓存表...")
    await asyncio.to_thread(init_security_info)

    # 3. 启动监控
    from app.services.monitor import monitor_loop
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
    title=settings.APP_NAME,
    description="A股投资监控系统 - 个股/ETF/场外基金 实时监控 + 买卖信号报警",
    version=settings.APP_VERSION,
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": exc.error_code,
            "message": exc.message,
            "detail": exc.detail,
        },
    )


app.include_router(target_router.router)
app.include_router(quote_router.router)
app.include_router(backtest_router.router)


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
