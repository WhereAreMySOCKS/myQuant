import datetime
import logging
import threading
import pytz
from chinese_calendar import is_workday

SHANGHAI_TZ = pytz.timezone('Asia/Shanghai')
logger = logging.getLogger(__name__)

_last_trading_state = None
_trading_state_lock = threading.Lock()


def get_current_time():
    """获取当前的上海时间"""
    return datetime.datetime.now(SHANGHAI_TZ)


def is_trading_time() -> bool:
    """
    判断当前是否为 A股 交易时间
    规则: 工作日（排除法定节假日） 09:30-11:30, 13:00-15:00
    """
    global _last_trading_state
    now = get_current_time()

    # 工作日判断（包含法定节假日排除 + 调休补班）
    if not is_workday(now.date()):
        result = False
    else:
        current_time = now.time()
        am_start = datetime.time(9, 30)
        am_end = datetime.time(11, 30)
        pm_start = datetime.time(13, 0)
        pm_end = datetime.time(15, 0)
        result = (am_start <= current_time <= am_end) or (pm_start <= current_time <= pm_end)

    with _trading_state_lock:
        if _last_trading_state is None:
            logger.info(f"[is_trading_time] 初始交易状态: {'交易时间' if result else '非交易时间'}")
            _last_trading_state = result
        elif _last_trading_state != result:
            if result:
                logger.info("[is_trading_time] 交易状态变化: 非交易时间 -> 交易时间")
            else:
                logger.info("[is_trading_time] 交易状态变化: 交易时间 -> 非交易时间")
            _last_trading_state = result

    return result
