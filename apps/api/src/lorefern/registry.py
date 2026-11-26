"""One registry of every adapter, with its tier. Demo mode can only build the offline seed adapters."""

from __future__ import annotations

from dataclasses import dataclass

from lorefern.adapters import seed
from lorefern.adapters.meetings import FathomMeetings, FirefliesMeetings, FileMeetings
from lorefern.adapters.smtp import SmtpEmail
from lorefern.adapters.sources import DriveSource, NotionSource
from sendora_core.adapters import AdapterError, AdapterRegistry, AdapterSpec

CATEGORIES = ("knowledge", "meetings", "email")
ENV_VARS = {
    ("knowledge", "drive"): ["DRIVE_SERVICE_ACCOUNT_JSON", "DRIVE_SERVICE_ACCOUNT_FILE", "DRIVE_CLIENT_ID", "DRIVE_CLIENT_SECRET", "DRIVE_REFRESH_TOKEN", "DRIVE_TOKEN", "DRIVE_SUBJECT"],
    ("knowledge", "notion"): ["NOTION_TOKEN"],
    ("meetings", "fireflies"): ["FIREFLIES_TOKEN"],
    ("meetings", "fathom"): ["FATHOM_TOKEN"],
    ("email", "smtp"): ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"],
}


def missing_settings(settings, category: str, name: str) -> list[str]:
    """Names of the variables still empty for an adapter. Drive accepts any one of three sign in ways, so it is judged as a whole."""
    if (category, name) == ("knowledge", "drive"):
        return [] if settings.drive_credentials() else ["DRIVE_SERVICE_ACCOUNT_JSON (or DRIVE_SERVICE_ACCOUNT_FILE), or DRIVE_CLIENT_ID with DRIVE_CLIENT_SECRET and DRIVE_REFRESH_TOKEN, or DRIVE_TOKEN"]
    return [v for v in ENV_VARS.get((category, name), []) if not getattr(settings, v.lower(), "")]


def build_registry(settings) -> AdapterRegistry:
    reg = AdapterRegistry(settings)
    add = lambda c, n, t, f, notes="": reg.register(AdapterSpec(c, n, t, f, False, notes))  # noqa: E731
    add("knowledge", "seed", "A", seed.SeedKnowledge, "Offline. The seed folder is read by the folder source.")
    add("knowledge", "folder", "A", lambda s: None, "A local folder of markdown, text and PDF files. Run by the Sources page.")
    add("knowledge", "drive", "B", DriveSource, "Read only. Signs in with a service account key or an OAuth refresh token and renews its own access token (docs 03). Written from Google's public docs, tested against a local mock token server and mock Drive only (UNVERIFIED live). Per user Drive permissions are not mirrored.")
    add("knowledge", "notion", "B", NotionSource, "Read only. From memory of public docs. Tested against a mock. Per user Notion permissions are not mirrored.")
    add("knowledge", "slack_export", "A", lambda s: None, "A Slack export folder or zip. Tested on a sample export.")
    add("meetings", "seed", "A", seed.SeedMeetings, "Offline. Transcript files are read from a folder.")
    add("meetings", "file", "A", FileMeetings, "Transcript files in the Otter text layout, the Meetily style 'Speaker: words' layout, or any 'Speaker: words' text. Otter and Meetily layouts are UNVERIFIED.")
    add("meetings", "fireflies", "B", FirefliesMeetings, "GraphQL fields read from the Fireflies docs on 2026-11-23. Tested against a mock only.")
    add("meetings", "fathom", "B", FathomMeetings, "REST fields read from the Fathom docs on 2026-11-23. Tested against a mock only.")
    add("email", "seed", "A", seed.SeedEmail, "Offline. Reminders are drafted, nothing is sent.")
    add("email", "smtp", "A", SmtpEmail, "Reminder sending goes through the SMTP settings. Refused in draft mode.")
    return reg


@dataclass
class AdapterSet:
    knowledge: object
    meetings: object
    email: object


def build_adapters(settings, registry: AdapterRegistry | None = None) -> AdapterSet:
    reg = registry or build_registry(settings)
    choice = {c: getattr(settings, f"{c}_adapter") for c in CATEGORIES}
    if settings.demo_mode:
        bad = {c: n for c, n in choice.items() if n != "seed"}
        if bad:
            raise AdapterError(f"DEMO_MODE is on, so only offline adapters can be used. Change {', '.join(f'{c.upper()}_ADAPTER' for c in bad)} or turn DEMO_MODE off.")
    return AdapterSet(**{c: reg.get(c, n) for c, n in choice.items()})
