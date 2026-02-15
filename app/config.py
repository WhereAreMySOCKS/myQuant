from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 邮件配置
    SMTP_SERVER: str = "smtp.qq.com"
    SMTP_PORT: int = 465
    SENDER_EMAIL: str
    EMAIL_PASSWORD: str
    RECEIVER_EMAIL: str

    # 监控轮询间隔（秒）
    # akshare 免费接口有频率限制，标的少可以 3~5 秒，多的话 10~15 秒
    POLL_INTERVAL_SECONDS: int = 5

    # SQLite 数据库路径
    DATABASE_URL: str = "sqlite:///./data/investment_guard.db"

    class Config:
        env_file = ".env"


settings = Settings()