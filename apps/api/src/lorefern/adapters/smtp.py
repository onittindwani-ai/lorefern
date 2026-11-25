"""Send task reminders by SMTP. Refused in draft mode and when the kill switch is on (write_action)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from lorefern.util import clean_header
from sendora_core.adapters import AdapterError
from sendora_core.safety import write_action


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class SmtpEmail:
    def __init__(self, settings):
        self.settings = settings

    def _smtp(self):
        s = self.settings
        if not s.smtp_use_tls and s.smtp_host.strip().lower() not in LOCAL_HOSTS:
            raise AdapterError("SMTP_USE_TLS is off for a mail server that is not on this machine. The password would travel in plain text, so nothing is sent. Turn it on.")
        c = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        if s.smtp_use_tls:
            c.starttls(context=ssl.create_default_context())  # the server's certificate is checked against the system's trusted list and its host name
        if s.smtp_user:
            c.login(s.smtp_user, s.smtp_password)
        return c

    @write_action("email.send")
    def send(self, *, to: str, subject: str, body: str) -> str:
        if not self.settings.smtp_host:
            raise AdapterError("SMTP_HOST is empty.")
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = clean_header(self.settings.email_from), clean_header(to), clean_header(subject)
        m["Message-ID"] = make_msgid(domain=self.settings.email_from.rsplit("@", 1)[-1] or "localhost")
        m.set_content(body)
        try:
            with self._smtp() as c:
                c.send_message(m)
        except ssl.SSLCertVerificationError as exc:
            raise AdapterError("The mail server's certificate could not be verified, so nothing was sent.") from exc
        except smtplib.SMTPAuthenticationError as exc:
            raise AdapterError("The mail server rejected the user name or password. For Gmail use an app password.") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise AdapterError(f"Could not send through {self.settings.smtp_host}: {type(exc).__name__}.") from exc
        return m["Message-ID"]

    def healthcheck(self) -> tuple[bool, str]:
        try:
            if not self.settings.smtp_host:
                return False, "SMTP_HOST is empty."
            with self._smtp() as c:
                c.noop()
            return True, "Connected to the mail server."
        except Exception as exc:
            return False, f"Could not connect: {type(exc).__name__}."
