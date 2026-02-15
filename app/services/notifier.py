import smtplib
from email.mime.text import MIMEText
from email.header import Header
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def send_email(subject: str, content: str):
    """通过 QQ 邮箱 SMTP 发送报警邮件"""
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = Header("Investment Guard", 'utf-8')
    message['To'] = Header("Investor", 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP_SSL(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.login(settings.SENDER_EMAIL, settings.EMAIL_PASSWORD)
        server.sendmail(
            settings.SENDER_EMAIL,
            settings.RECEIVER_EMAIL,
            message.as_string()
        )
        server.quit()
        logger.info(f"邮件已发送: {subject}")
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")