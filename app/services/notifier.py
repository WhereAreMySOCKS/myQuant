import smtplib
import time
from email.mime.text import MIMEText
from email.header import Header
from app.config import settings
import logging
from email.utils import formataddr

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
SMTP_TIMEOUT_SECONDS = 15


def _mask_email(email: str) -> str:
    """脱敏邮件地址，例如 abcdef@qq.com -> ab***@qq.com"""
    if not email or '@' not in email:
        return email
    local, domain = email.split('@', 1)
    masked_local = local[:2] + '***' if len(local) > 2 else local[0] + '***'
    return f"{masked_local}@{domain}"


def send_email(subject: str, content: str):
    """通过 QQ 邮箱 SMTP 发送报警邮件（带重试）"""
    message = MIMEText(content, 'plain', 'utf-8')

    sender_name = str(Header("Investment Guard", 'utf-8'))
    message['From'] = formataddr((sender_name, settings.SENDER_EMAIL))
    receiver_name = str(Header("Investor", 'utf-8'))
    message['To'] = formataddr((receiver_name, settings.RECEIVER_EMAIL))
    message['Subject'] = Header(subject, 'utf-8')
    msg_bytes = len(message.as_bytes())
    receiver_masked = _mask_email(settings.RECEIVER_EMAIL)
    logger.info(f"[notifier] 准备发送邮件: 主题={subject!r}, 收件人={receiver_masked}, 大小={msg_bytes}B")

    t0 = time.time()
    last_exc = None
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
            logger.info(f"[notifier] 邮件已发送: {subject!r}, 耗时={time.time()-t0:.2f}s")
            return  # 成功则直接返回
        except smtplib.SMTPAuthenticationError as e:
            # 认证失败不重试
            logger.error(f"[notifier] 邮件认证失败（不重试）: {e}", exc_info=True)
            return
        except Exception as e:
            last_exc = e
            logger.warning(
                f"[notifier] 邮件发送失败 (第 {attempt}/{MAX_RETRIES} 次): {e}"
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error(
        f"[notifier] 邮件发送最终失败，已重试 {MAX_RETRIES} 次: {subject!r}, 耗时={time.time()-t0:.2f}s",
        exc_info=last_exc,
    )