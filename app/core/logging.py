import logging
import json as _json
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """将日志格式化为单行 JSON 对象"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)
        return _json.dumps(log_obj, ensure_ascii=False)


def setup_logging(settings) -> None:
    """
    根据 settings 配置全局日志体系。
    在 app 启动时调用一次即可。
    """
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    if settings.LOG_FORMAT == "json":
        formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Remove existing handlers to avoid duplicate output
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
