import smtplib
import time
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, formatdate
from app.core.config import settings
import logging

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


def _build_message(subject: str, content: str) -> MIMEText:
    """每次调用都生成一个全新的 MIMEText 对象，避免 header 重复叠加。"""
    message = MIMEText(content, 'plain', 'utf-8')

    # ── 关键修复：构造符合 RFC5322 的 From / To ──
    # formataddr 的 name 部分如果含非 ASCII，需要先用 Header 编码为 RFC2047 字符串
    # 再传给 formataddr，这样最终输出类似:
    #   =?utf-8?q?Investment_Guard?= <sender@qq.com>
    sender_name = Header("Investment Guard", 'utf-8').encode()
    message['From'] = formataddr((sender_name, settings.SENDER_EMAIL))

    receiver_name = Header("Investor", 'utf-8').encode()
    message['To'] = formataddr((receiver_name, settings.RECEIVER_EMAIL))

    message['Subject'] = Header(subject, 'utf-8')
    message['Date'] = formatdate(localtime=True)

    return message


def send_email(subject: str, content: str):
    """通过 QQ 邮箱 SMTP 发送报警邮件（带重试）"""

    # 前置校验
    if not settings.SENDER_EMAIL or not settings.RECEIVER_EMAIL:
        logger.error("[notifier] SENDER_EMAIL 或 RECEIVER_EMAIL 未配置，跳过发送")
        return

    # 先构建一次，仅用于日志打印大小
    sample_msg = _build_message(subject, content)
    msg_bytes = len(sample_msg.as_bytes())
    receiver_masked = _mask_email(settings.RECEIVER_EMAIL)
    logger.info(
        f"[notifier] 准备发送邮件: 主题={subject!r}, "
        f"收件人={receiver_masked}, 大小={msg_bytes}B"
    )

    t0 = time.time()
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # ── 每次重试都重新构建消息，防止 header 被污染 ──
            message = _build_message(subject, content)

            server = smtplib.SMTP_SSL(
                settings.SMTP_SERVER,
                settings.SMTP_PORT,
                timeout=SMTP_TIMEOUT_SECONDS,
            )
            server.login(settings.SENDER_EMAIL, settings.EMAIL_PASSWORD)
            server.sendmail(
                settings.SENDER_EMAIL,        # envelope sender
                [settings.RECEIVER_EMAIL],     # envelope recipient (list)
                message.as_string(),
            )
            server.quit()

            logger.info(
                f"[notifier] 邮件已发送: {subject!r}, "
                f"耗时={time.time() - t0:.2f}s"
            )
            return  # 成功则直接返回

        except smtplib.SMTPAuthenticationError as e:
            # 认证失败不重试
            logger.error(
                f"[notifier] 邮件认证失败（不重试）: {e}", exc_info=True
            )
            return

        except Exception as e:
            last_exc = e
            logger.warning(
                f"[notifier] 邮件发送失败 "
                f"(第 {attempt}/{MAX_RETRIES} 次): {e}"
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error(
        f"[notifier] 邮件发送最终失败，已重试 {MAX_RETRIES} 次: "
        f"{subject!r}, 耗时={time.time() - t0:.2f}s",
        exc_info=last_exc,
    )