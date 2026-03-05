import json
import logging
import smtplib
from email.message import EmailMessage
from html import escape
from urllib import error as url_error
from urllib import request as url_request

from app.core.config import settings

logger = logging.getLogger(__name__)


def _html_from_text(text: str) -> str:
    return "<br/>".join(escape(line) for line in str(text or "").splitlines())


def _send_via_zeptomail(*, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    api_key = str(settings.ZEPTOMAIL_API_KEY or "").strip()
    if not api_key:
        logger.info("ZeptoMail email skipped (ZEPTOMAIL_API_KEY unset). to=%s", to_email)
        return False

    from_email = (
        str(settings.ZEPTOMAIL_FROM_EMAIL or "").strip()
        or str(settings.SMTP_FROM or "").strip()
        or str(settings.SMTP_USERNAME or "").strip()
    )
    if not from_email:
        logger.warning("ZeptoMail email skipped (missing sender address). to=%s", to_email)
        return False

    from_name = str(settings.ZEPTOMAIL_FROM_NAME or "").strip()
    payload: dict[str, object] = {
        "from": {"address": from_email},
        "to": [{"email_address": {"address": to_email}}],
        "subject": subject,
        "textbody": text_body,
        "htmlbody": html_body or _html_from_text(text_body),
    }
    if from_name:
        payload["from"]["name"] = from_name  # type: ignore[index]

    req = url_request.Request(
        str(settings.ZEPTOMAIL_API_URL).strip(),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Zoho-enczapikey {api_key}",
        },
    )
    try:
        with url_request.urlopen(req, timeout=int(settings.SMTP_CONNECT_TIMEOUT_SECONDS)) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
            if not (200 <= int(resp.status) < 300):
                logger.error(
                    "ZeptoMail non-2xx response status=%s reason=%s url=%s from=%s to=%s body=%s",
                    resp.status,
                    getattr(resp, "reason", ""),
                    settings.ZEPTOMAIL_API_URL,
                    from_email,
                    to_email,
                    response_body[:1200],
                )
                raise RuntimeError(f"ZeptoMail HTTP {resp.status}: {response_body[:500]}")
    except url_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        headers = {k: v for k, v in (exc.headers.items() if exc.headers else [])}
        logger.error(
            "ZeptoMail HTTP error code=%s reason=%s url=%s from=%s to=%s headers=%s body=%s",
            exc.code,
            getattr(exc, "reason", ""),
            settings.ZEPTOMAIL_API_URL,
            from_email,
            to_email,
            headers,
            body[:1200],
        )
        raise RuntimeError(f"ZeptoMail HTTP {exc.code}: {body[:500]}") from exc
    except url_error.URLError as exc:
        logger.error(
            "ZeptoMail URL error reason=%s url=%s from=%s to=%s",
            getattr(exc, "reason", exc),
            settings.ZEPTOMAIL_API_URL,
            from_email,
            to_email,
        )
        raise
    except Exception:
        logger.exception(
            "Unexpected ZeptoMail error url=%s from=%s to=%s",
            settings.ZEPTOMAIL_API_URL,
            from_email,
            to_email,
        )
        raise
    return True


def _send_via_smtp(*, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    if not settings.SMTP_HOST:
        logger.info("SMTP email skipped (SMTP_HOST unset). to=%s", to_email)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USERNAME or "no-reply@localhost"
    msg["To"] = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=int(settings.SMTP_CONNECT_TIMEOUT_SECONDS)) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    return True


def send_transactional_email(*, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    provider = str(settings.EMAIL_PROVIDER or "smtp").strip().lower()
    if provider == "zeptomail":
        return _send_via_zeptomail(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
    return _send_via_smtp(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )


def send_welcome_email(*, to_email: str, tenant_name: str, login_url: str | None = None) -> bool:
    subject = f"Welcome to {tenant_name}"
    lines = [
        f"Welcome to {tenant_name}.",
        "",
        "Your account has been created successfully.",
    ]
    if login_url:
        lines.extend(["", f"Sign in: {login_url}"])
    lines.extend(["", "If you did not expect this, please contact support."])
    text_body = "\n".join(lines)
    return send_transactional_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=None,
    )
