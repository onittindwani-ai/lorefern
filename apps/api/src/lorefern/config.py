"""Lorefern settings. Subclass of the base settings with this system's variables (names only, never values, in docs)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from lorefern import util
from sendora_core.auth import clean_email
from sendora_core.settings import BaseAppSettings, Mode


def _is_local(host: str) -> bool:
    return host.strip().lower() in {"localhost", "127.0.0.1", "::1"}


ACTOR_MAX = 80  # the width of the actor columns of the shared audit log and approvals tables


class Settings(BaseAppSettings):
    app_name: str = "lorefern"
    database_url: str = "sqlite:///./lorefern.sqlite3"

    owner_email: str = "owner@example.test"
    owner_password_hash: str | None = Field(default=None, repr=False)  # hashes and the members list never show in a printed settings object or a log
    approver_email: str | None = None
    approver_password_hash: str | None = Field(default=None, repr=False)
    login_burst: int = Field(default=5, ge=1, le=1000)  # sign in tries in a row before a short wait; the browser tests raise it

    company_name: str = "Pinegate Works"  # shown at the top of every page. The default is the fictional demo company: set your own before MODE=live
    timezone: str = "UTC"  # the zone in which "today" is worked out (due dates, reminders, the weekly review). A name such as Europe/Berlin or America/Chicago
    knowledge_adapter: str = "seed"  # seed, drive, notion
    meetings_adapter: str = "seed"  # seed, fireflies, fathom, file
    email_adapter: str = "seed"  # seed or smtp (task reminders)
    knowledge_dir: str = ""  # a folder of markdown, text and PDF files
    seed_dir: str = ""

    # Who may sign in as which audience. JSON object of email to audience. Nobody is added by default outside demo mode: the implementer lists the client's people.
    members_json: str = Field(default="", repr=False)
    drive_token: str = Field(default="", repr=False)  # one short lived access token, for a first try only
    drive_service_account_json: str = Field(default="", repr=False)  # the text of a service account key file
    drive_service_account_file: str = ""  # or the path to that file
    drive_client_id: str = ""
    drive_client_secret: str = Field(default="", repr=False)
    drive_refresh_token: str = Field(default="", repr=False)
    drive_subject: str = ""  # optional: a user to act as, with domain wide delegation
    drive_scope: str = "https://www.googleapis.com/auth/drive.readonly"
    drive_token_uri: str = "https://oauth2.googleapis.com/token"
    drive_base_url: str = "https://www.googleapis.com"
    notion_token: str = Field(default="", repr=False)
    notion_base_url: str = "https://api.notion.com"
    fireflies_token: str = Field(default="", repr=False)
    fireflies_base_url: str = "https://api.fireflies.ai"
    fathom_token: str = Field(default="", repr=False)
    fathom_base_url: str = "https://api.fathom.ai"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = Field(default="", repr=False)
    smtp_use_tls: bool = True
    email_from: str = "lorefern@example.test"  # the From address of task reminders. The default is a placeholder: set your own before MODE=live
    allowed_email_domains: str = ""  # comma separated domains task reminders may be sent to and task owners may have. Empty: only the domains of the people who sign in (OWNER_EMAIL, APPROVER_EMAIL, MEMBERS_JSON)

    # What a language model may do when LLM_BACKEND is fixture or anthropic (with LLM_BACKEND=offline, the default, none of these call anything). Live use is UNVERIFIED.
    answer_writer: Literal["rules", "model"] = "model"  # ANSWER_WRITER=model writes the answer sentences with the model when a model backend is on; the groundedness check still runs on every sentence
    meeting_extractor: Literal["rules", "model"] = "rules"  # MEETING_EXTRACTOR=model lets the model propose action items and decisions (code checks every quote); a person still approves each one
    process_wording: Literal["rules", "model"] = "rules"  # PROCESS_WORDING=model lets the model name the recurring processes that code counted
    review_writer: Literal["rules", "model"] = "rules"  # REVIEW_WRITER=model adds a two sentence intro, from the review's numbers only, at the top of the weekly review

    # Task rules. Decided defaults (a normal Monday to Friday week); the implementer changes them per client.
    working_days: str = "Mon,Tue,Wed,Thu,Fri"
    stuck_no_update_days: int = 10
    stuck_blocked_days: int = 5
    overload_open_tasks: int = 8
    overload_due_soon: int = 5
    sop_review_days: int = 180
    weekly_review_weekday: int = 0  # Monday

    def _members_raw(self) -> dict:
        import json

        try:
            raw = json.loads(self.members_json) if self.members_json else {}
        except ValueError:
            return {}
        return {clean_email(str(k)): v for k, v in raw.items()} if isinstance(raw, dict) else {}

    def member_hashes(self) -> dict[str, str]:
        """Password hashes for people added in MEMBERS_JSON as {"email": {"audience": "staff", "password_hash": "..."}}."""
        return {e: v["password_hash"] for e, v in self._members_raw().items() if isinstance(v, dict) and v.get("password_hash")}

    def members(self) -> dict[str, str]:
        base = {clean_email(self.owner_email): "owner"}
        if self.approver_email:
            base[clean_email(self.approver_email)] = "leadership"
        if self.demo_shortcuts:  # the made up people exist only in a demo with no owner password, never next to a real owner
            base.update({"approver@example.test": "leadership", "finance@example.test": "finance", "staff@example.test": "staff"})
        for email, v in self._members_raw().items():
            aud = v.get("audience") if isinstance(v, dict) else v
            if aud in ("leadership", "finance", "staff") and email != clean_email(self.owner_email):
                base[email] = aud
        return base

    def email_domains(self) -> set[str]:
        """The domains an owner's address may be on: ALLOWED_EMAIL_DOMAINS when it is set, otherwise the domains of everyone who can sign in."""
        named = {d.strip().lower().lstrip("@") for d in self.allowed_email_domains.split(",") if d.strip()}
        return named or {e.rsplit("@", 1)[1] for e in self.members() if "@" in e}

    def email_allowed(self, email: str) -> bool:
        """True when the address is on one of the company's domains (or a sub domain of one). An address that is not a plain `name@domain` is never allowed."""
        e = clean_email(email)
        name, at, domain = e.rpartition("@")
        if not (name and at and domain and "@" not in name and not any(c.isspace() for c in e) and len(e) <= 254):
            return False
        return any(domain == d or domain.endswith("." + d) for d in self.email_domains())

    def drive_credentials(self) -> bool:
        return bool(self.drive_service_account_json or self.drive_service_account_file or (self.drive_client_id and self.drive_client_secret and self.drive_refresh_token) or self.drive_token)

    def placeholder_problems(self) -> list[str]:
        """Identity settings still on the demo values. They are a problem for a real install and are never a problem for a demo."""
        out = []
        if self.company_name.strip() in {"", "Pinegate Works"}:
            out.append("COMPANY_NAME is still the fictional demo company (Pinegate Works). Set your own company name.")
        if self.email_from.strip().lower().endswith("@example.test"):
            out.append("EMAIL_FROM is still the example address. Set the address task reminders are sent from.")
        if util.zone(self.timezone) is None:
            out.append(f"TIMEZONE {self.timezone!r} is not a time zone name. Use a name such as Europe/Berlin.")
        return out

    def runtime_errors(self) -> list[str]:
        """Problems that stop the app from starting. Beyond the shared ones: MODE=live with the demo identity still in place, and a demo with public logins next to a real folder of documents."""
        out = list(super().runtime_errors())
        if self.mode is Mode.LIVE and not self.demo_mode:
            out += self.placeholder_problems()
        if any(len(e) > ACTOR_MAX for e in self.members()):
            out.append(f"A sign in email is longer than {ACTOR_MAX} characters. The audit log and approval columns of the shared base hold {ACTOR_MAX}, so every change that person made would fail on Postgres. Use a shorter address.")
        if self.demo_shortcuts and self.knowledge_dir:
            out.append("KNOWLEDGE_DIR is set while the public demo password is on. Real documents would sit behind a login anyone can read in the repository. Set OWNER_PASSWORD_HASH (and DEMO_MODE=false), or leave KNOWLEDGE_DIR empty.")
        return list(dict.fromkeys(out))

    def problems(self) -> list[str]:
        out = [p for p in super().problems() if not (self.demo_mode and p.startswith("MODE is live while DEMO_MODE"))]
        if not self.demo_mode and not self.owner_password_hash:
            out.append("OWNER_PASSWORD_HASH is empty. Create one with tools/hash_password.py and set it before you run outside demo mode.")
        if self.demo_mode and self.owner_password_hash:
            out.append("DEMO_MODE is on although OWNER_PASSWORD_HASH is set. The public demo logins are off, but the clock, the demo bar and the offline adapters are still demo. Set DEMO_MODE=false.")
        if not self.demo_mode:
            out += self.placeholder_problems()
        if self.smtp_host and not self.smtp_use_tls and not _is_local(self.smtp_host):
            out.append("SMTP_USE_TLS is off for a mail server that is not on this machine. The password would travel in plain text. Turn it on.")
        need = {"drive": (self.drive_credentials(), "DRIVE_SERVICE_ACCOUNT_JSON, DRIVE_SERVICE_ACCOUNT_FILE, DRIVE_CLIENT_ID with DRIVE_CLIENT_SECRET and DRIVE_REFRESH_TOKEN, or DRIVE_TOKEN"), "notion": (self.notion_token, "NOTION_TOKEN")}
        if self.knowledge_adapter in need and not need[self.knowledge_adapter][0]:
            out.append(f"KNOWLEDGE_ADAPTER is {self.knowledge_adapter} but {need[self.knowledge_adapter][1]} is empty.")
        mneed = {"fireflies": (self.fireflies_token, "FIREFLIES_TOKEN"), "fathom": (self.fathom_token, "FATHOM_TOKEN")}
        if self.meetings_adapter in mneed and not mneed[self.meetings_adapter][0]:
            out.append(f"MEETINGS_ADAPTER is {self.meetings_adapter} but {mneed[self.meetings_adapter][1]} is empty.")
        if self.email_adapter == "smtp" and not (self.smtp_host and self.smtp_user):
            out.append("EMAIL_ADAPTER is smtp but SMTP_HOST or SMTP_USER is empty.")
        return out
