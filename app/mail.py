"""邮件发送：smtplib 发送倍率变化告警通知。"""
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from . import config

logger = logging.getLogger("price_monitor.mail")


def send_alert_email(
    subject: str,
    body_html: str,
    to_addrs: list[str],
) -> bool:
    """发送告警邮件。SMTP 配置全部为空则跳过。"""
    if not config.SMTP_USER or not config.SMTP_PASSWORD or not to_addrs:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    # From: 有显示名则 RFC 2047 编码，否则直接用邮箱
    display_name = config.SMTP_FROM.replace(config.SMTP_USER, "").strip().strip("<> ")
    if display_name and display_name != config.SMTP_USER:
        msg["From"] = formataddr((str(Header(display_name, "utf-8")), config.SMTP_USER))
    else:
        msg["From"] = config.SMTP_USER
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        if config.SMTP_USE_TLS:
            server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        # sendmail 的 envelope from 必须用纯邮箱地址
        server.sendmail(config.SMTP_USER, to_addrs, msg.as_string())
        server.quit()
        logger.info("告警邮件已发送至 %s", to_addrs)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("发送告警邮件失败: %s", e)
        return False
