from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Dict, List

import httpx

from app.core.config import get_settings
from app.logging import get_logger
from app.models.notifier import Notifier
from app.models.notifier_event import NotifierEventType
from app.services.notify.base import NotifierProvider, NotifierSendError
from app.services.notify.email_templates import render_email_template

logger = get_logger()

_SMTP_TIMEOUT = 20.0
_SENDGRID_ENDPOINT = "https://api.sendgrid.com/v3/mail/send"


class EmailProvider(NotifierProvider):
    def __init__(self, notifier: Notifier) -> None:
        super().__init__(notifier)
        self._settings = get_settings()

    def send(self, event: NotifierEventType, payload: dict[str, Any]) -> None:
        email_payload = _EmailPayload.from_event_payload(payload)
        if not email_payload.recipients.to and not email_payload.recipients.cc and not email_payload.recipients.bcc:
            raise NotifierSendError("No email recipients configured")

        config = self.notifier.config or {}
        template_name = (email_payload.template or config.get("template") or event.value).strip()
        language = (email_payload.language or config.get("language") or "en").strip().lower()

        context = _prepare_context(payload)
        rendered = render_email_template(template_name, language, context)

        message = self._build_message(rendered, email_payload, config)
        provider = str(config.get("provider") or "smtp").strip().lower()

        if provider == "sendgrid":
            self._send_via_sendgrid(message, email_payload)
        elif provider == "mailgun":
            self._send_via_mailgun(message, email_payload, config)
        else:
            self._send_via_smtp(message, email_payload, config)

    def _build_message(
        self,
        rendered,
        email_payload: "_EmailPayload",
        config: dict[str, Any],
    ) -> EmailMessage:
        message = EmailMessage()
        from_email, from_name = _resolve_sender(self._settings, config)
        if not from_email:
            raise NotifierSendError("Sender email is not configured")

        if from_name:
            message["From"] = formataddr((from_name, from_email))
        else:
            message["From"] = from_email

        message["Subject"] = rendered.subject
        message["To"] = ", ".join(email_payload.recipients.to)
        if email_payload.recipients.cc:
            message["Cc"] = ", ".join(email_payload.recipients.cc)
        if email_payload.reply_to:
            message["Reply-To"] = email_payload.reply_to

        unsubscribe = config.get("unsubscribe")
        if isinstance(unsubscribe, str) and unsubscribe.strip():
            message["List-Unsubscribe"] = unsubscribe.strip()
        else:
            message["List-Unsubscribe"] = "<mailto:unsubscribe@example.com>"
        message["X-Auto-Response-Suppress"] = "OOF"
        message["Auto-Submitted"] = "auto-generated"

        message.set_content(rendered.text or "")
        message.add_alternative(rendered.html or "", subtype="html")
        return message

    def _send_via_smtp(
        self,
        message: EmailMessage,
        email_payload: "_EmailPayload",
        config: dict[str, Any],
    ) -> None:
        host = config.get("smtp_host") or self._settings.smtp_host
        if not host:
            raise NotifierSendError("SMTP host is not configured")

        port = int(config.get("smtp_port") or self._settings.smtp_port or 587)
        username = config.get("smtp_user") or self._settings.smtp_user
        password = config.get("smtp_password") or self._settings.smtp_password
        use_tls = _coerce_bool(config.get("smtp_tls"))
        if use_tls is None:
            use_tls = bool(self._settings.smtp_tls)

        recipients = email_payload.recipients.all_recipients()
        if not recipients:
            raise NotifierSendError("Cannot send SMTP email without recipients")

        try:
            if use_tls and port == 465:
                client = smtplib.SMTP_SSL(host=host, port=port, timeout=_SMTP_TIMEOUT)
            else:
                client = smtplib.SMTP(host=host, port=port, timeout=_SMTP_TIMEOUT)
            try:
                client.ehlo()
                if use_tls and port != 465:
                    client.starttls()
                    client.ehlo()
                if username and password:
                    client.login(username, password)
                client.send_message(message, from_addr=message["From"], to_addrs=recipients)
                logger.info(
                    "email_smtp_sent",
                    notifier_id=str(self.notifier.id),
                    provider="smtp",
                    recipients=len(recipients),
                )
            finally:
                try:
                    client.quit()
                except Exception:  # pragma: no cover - best effort
                    logger.debug("email_smtp_quit_failed", notifier_id=str(self.notifier.id))
        except smtplib.SMTPException as exc:
            logger.warning(
                "email_smtp_failed",
                notifier_id=str(self.notifier.id),
                provider="smtp",
                reason=str(exc),
            )
            raise NotifierSendError("SMTP delivery failed") from exc

    def _send_via_sendgrid(self, message: EmailMessage, email_payload: "_EmailPayload") -> None:
        api_key = self._settings.sendgrid_api_key
        if not api_key:
            raise NotifierSendError("SendGrid API key is not configured")

        from_name, from_email = parseaddr(str(message["From"]))
        if not from_email:
            raise NotifierSendError("Invalid sender address for SendGrid delivery")

        payload: Dict[str, Any] = {
            "personalizations": [
                {
                    "to": [{"email": email} for email in email_payload.recipients.to],
                }
            ],
            "from": {"email": from_email},
            "subject": str(message["Subject"]),
            "content": [
                {"type": "text/plain", "value": message.get_body(preferencelist=("plain",)).get_content()},
                {"type": "text/html", "value": message.get_body(preferencelist=("html",)).get_content()},
            ],
        }

        if from_name:
            payload["from"]["name"] = from_name

        if email_payload.recipients.cc:
            payload["personalizations"][0]["cc"] = [{"email": email} for email in email_payload.recipients.cc]
        if email_payload.recipients.bcc:
            payload["personalizations"][0]["bcc"] = [{"email": email} for email in email_payload.recipients.bcc]
        if message.get("Reply-To"):
            reply_name, reply_email = parseaddr(str(message.get("Reply-To")))
            if reply_email:
                payload["reply_to"] = {"email": reply_email}
                if reply_name:
                    payload["reply_to"]["name"] = reply_name

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(_SENDGRID_ENDPOINT, json=payload, headers=headers, timeout=_SMTP_TIMEOUT)
            response.raise_for_status()
            logger.info(
                "email_sendgrid_sent",
                notifier_id=str(self.notifier.id),
                recipients=len(email_payload.recipients.all_recipients()),
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "email_sendgrid_failed",
                notifier_id=str(self.notifier.id),
                status=getattr(exc.response, "status_code", None),
            )
            raise NotifierSendError("SendGrid delivery failed") from exc

    def _send_via_mailgun(
        self,
        message: EmailMessage,
        email_payload: "_EmailPayload",
        config: dict[str, Any],
    ) -> None:
        api_key = self._settings.mailgun_api_key
        if not api_key:
            raise NotifierSendError("Mailgun API key is not configured")
        domain = config.get("mailgun_domain")
        if not domain:
            raise NotifierSendError("Mailgun domain is not configured")

        endpoint = f"https://api.mailgun.net/v3/{domain}/messages"

        data: Dict[str, Any] = {
            "from": message["From"],
            "to": email_payload.recipients.to,
            "subject": message["Subject"],
            "text": message.get_body(preferencelist=("plain",)).get_content(),
            "html": message.get_body(preferencelist=("html",)).get_content(),
        }
        if email_payload.recipients.cc:
            data["cc"] = email_payload.recipients.cc
        if email_payload.recipients.bcc:
            data["bcc"] = email_payload.recipients.bcc
        if message.get("Reply-To"):
            data["h:Reply-To"] = message.get("Reply-To")
        if message.get("List-Unsubscribe"):
            data["h:List-Unsubscribe"] = message.get("List-Unsubscribe")

        try:
            response = httpx.post(endpoint, auth=("api", api_key), data=data, timeout=_SMTP_TIMEOUT)
            response.raise_for_status()
            logger.info(
                "email_mailgun_sent",
                notifier_id=str(self.notifier.id),
                recipients=len(email_payload.recipients.all_recipients()),
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "email_mailgun_failed",
                notifier_id=str(self.notifier.id),
                status=getattr(exc.response, "status_code", None),
            )
            raise NotifierSendError("Mailgun delivery failed") from exc

    def handle_bounce(self, details: dict[str, Any]) -> None:
        logger.info(
            "email_bounce_stub",
            notifier_id=str(self.notifier.id),
            details=details,
        )


def _prepare_context(payload: dict[str, Any]) -> dict[str, Any]:
    context = dict(payload)
    context.setdefault("summary", payload.get("summary") or {})
    context.setdefault("environment", payload.get("environment") or {})
    context.setdefault("failures", payload.get("failures") or [])
    context.setdefault("pass_rate", payload.get("pass_rate") or context["summary"].get("pass_rate"))
    context.setdefault("duration_ms", context["summary"].get("duration_ms"))
    context.setdefault("finished_at", payload.get("finished_at") or context["summary"].get("finished_at"))
    return context


def _resolve_sender(settings, config: dict[str, Any]) -> tuple[str | None, str | None]:
    from_email = config.get("from") or settings.smtp_from or settings.smtp_user
    from_name = config.get("from_name") or settings.smtp_from_name
    return from_email, from_name


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return None


class _RecipientSet:
    __slots__ = ("to", "cc", "bcc")

    def __init__(self, to: List[str] | None, cc: List[str] | None, bcc: List[str] | None) -> None:
        self.to = _unique_lower(to or [])
        self.cc = _unique_lower(cc or [])
        self.bcc = _unique_lower(bcc or [])

    def all_recipients(self) -> List[str]:
        recipients = self.to + [email for email in self.cc if email not in self.to] + [
            email for email in self.bcc if email not in self.to and email not in self.cc
        ]
        return recipients


class _EmailPayload:
    __slots__ = ("recipients", "template", "language", "reply_to")

    def __init__(self, recipients: _RecipientSet, template: str | None, language: str | None, reply_to: str | None) -> None:
        self.recipients = recipients
        self.template = template
        self.language = language
        self.reply_to = reply_to.strip() if isinstance(reply_to, str) and reply_to.strip() else None

    @classmethod
    def from_event_payload(cls, payload: dict[str, Any]) -> "_EmailPayload":
        email_block = payload.get("email") if isinstance(payload.get("email"), dict) else {}
        recipients_block = email_block.get("recipients") if isinstance(email_block, dict) else {}
        recipients = _RecipientSet(
            to=_safe_list(recipients_block.get("to")),
            cc=_safe_list(recipients_block.get("cc")),
            bcc=_safe_list(recipients_block.get("bcc")),
        )
        return cls(
            recipients=recipients,
            template=email_block.get("template") if isinstance(email_block, dict) else None,
            language=email_block.get("language") if isinstance(email_block, dict) else None,
            reply_to=email_block.get("reply_to") if isinstance(email_block, dict) else None,
        )


def _safe_list(value: Any) -> List[str]:
    result: List[str] = []
    if isinstance(value, str):
        candidates = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]
    else:
        candidates = []
    for email in candidates:
        lowered = email.lower()
        if lowered not in result:
            result.append(lowered)
    return result


def _unique_lower(items: List[str]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for item in items:
        email = item.lower()
        if email in seen:
            continue
        seen.add(email)
        normalized.append(email)
    return normalized


__all__ = ["EmailProvider"]
