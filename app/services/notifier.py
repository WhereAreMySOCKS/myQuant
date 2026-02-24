import smtplib
import time
from email.mime.text import MIMEText
from email.header import Header
from app.config import settings
import logging

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
SMTP_TIMEOUT_SECONDS = 15


def send_email(subject: str, content: str):
    """通过 QQ 邮箱 SMTP 发送报警邮件（带重试）"""
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = Header("Investment Guard", 'utf-8')
    message['To'] = Header("Investor", 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            server = smtplib.SMTP_SSL(
                settings.SMTP_SERVER,
                settings.SMTP_PORT,
                timeout=SMTP_TIMEOUT_SECONDS,
            )
            server.login(settings.SENDER_EMAIL, settings.EMAIL_PASSWORD)
            server.sendmail(
                settings.SENDER_EMAIL,
                settings.RECEIVER_EMAIL,
                message.as_string(),
            )
            server.quit()
            logger.info(f"邮件已发送: {subject}")
            return  # 成功则直接返回
        except smtplib.SMTPAuthenticationError as e:
            # 认证失败不重试
            logger.error(f"邮件认证失败（不重试）: {e}")
            return
        except Exception as e:
            logger.warning(
                f"邮件发送失败 (第 {attempt}/{MAX_RETRIES} 次): {e}"
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error(f"邮件发送最终失败，已重试 {MAX_RETRIES} 次: {subject}")