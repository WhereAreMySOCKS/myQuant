from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # 应用信息
    APP_NAME: str = "myQuant"
    APP_VERSION: str = "3.0.0"
    APP_ENV: Literal["dev", "test", "prod"] = "dev"

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["text", "json"] = "text"

    # 邮件配置
    SMTP_SERVER: str = "smtp.qq.com"
    SMTP_PORT: int = 465
    SENDER_EMAIL: str = ""
    EMAIL_PASSWORD: str = ""
    RECEIVER_EMAIL: str = ""

    # 监控轮询间隔（秒）
    # akshare 免费接口有频率限制，标的少可以 3~5 秒，多的话 10~15 秒
    POLL_INTERVAL_SECONDS: int = 30
    # 并发处理标的数
    MONITOR_CONCURRENCY: int = 5
    # 历史数据回溯月数
    HISTORY_LOOKBACK_MONTHS: int = 18

    # SQLite 数据库路径
    DATABASE_URL: str = "sqlite:///./data/investment_guard.db"

    model_config = {"env_file": ".env"}


settings = Settings()
