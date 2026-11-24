"""Offline adapters used in demo mode. Nothing leaves this machine."""

from __future__ import annotations

from lorefern.adapters.base import RemoteDoc, RemoteMeeting


class SeedKnowledge:
    def __init__(self, settings=None):
        self.settings = settings

    def list_documents(self) -> list[RemoteDoc]:
        return []

    def healthcheck(self):
        return True, "Offline. The seed folder is read by the folder source."


class SeedMeetings:
    def __init__(self, settings=None):
        self.settings = settings

    def list_meetings(self) -> list[RemoteMeeting]:
        return []

    def healthcheck(self):
        return True, "Offline. Seed transcripts are read from files."


class SeedEmail:
    """Reminders are drafted into the database. This sender only records what it was asked to send."""

    def __init__(self, settings=None):
        self.settings, self.sent = settings, []

    def send(self, *, to, subject, body) -> str:
        from sendora_core.safety import guard_write

        guard_write(self.settings, "email.send")
        self.sent.append((to, subject))
        return f"seed-mail-{len(self.sent)}"

    def healthcheck(self):
        return True, "Offline. Nothing leaves this machine."
