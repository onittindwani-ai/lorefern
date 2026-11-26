"""Runtime context shared by the API and the worker: settings, database, adapters, writer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from lorefern import clock, model_tasks, util
from lorefern.config import Settings
from lorefern.models import State
from lorefern.offline_llm import OfflineBackend
from lorefern.registry import AdapterSet, build_adapters, build_registry
from sendora_core.costs import CostTracker
from sendora_core.llm import LLM, build_llm
from sendora_core.settings import LLMBackendKind, Mode


@dataclass
class Ctx:
    settings: Settings
    factory: sessionmaker[Session]
    adapters: AdapterSet | Any = None
    registry: Any = None
    writer: Any = None  # a Writer for answers; None means the offline rules writer

    def __post_init__(self) -> None:
        self.registry = self.registry or build_registry(self.settings)
        if self.adapters is None:
            self.adapters = build_adapters(self.settings, self.registry)

    def effective(self, session: Session) -> Settings:
        """The kill switch can be turned on in the app, and the mode can be pulled back to draft. Neither can go the other way."""
        kill, force = session.get(State, "kill_switch"), session.get(State, "force_draft")
        upd: dict[str, Any] = {}
        if kill and kill.value == "1":
            upd["kill_switch"] = True
        if force and force.value == "1":
            upd["mode"] = Mode.DRAFT
        return self.settings.model_copy(update=upd) if upd else self.settings

    def now(self, session: Session):
        return clock.now(session, self.settings.demo_mode)

    def today(self, session: Session) -> date:
        """Today's date in the company's time zone (TIMEZONE). A demo uses its own fixed clock in UTC."""
        n = clock.now(session, self.settings.demo_mode)
        tz = None if self.settings.demo_mode else util.zone(self.settings.timezone)
        return (n.astimezone(tz) if tz else n).date()

    def llm(self, session: Session) -> LLM:
        # LLM_BACKEND=offline (default) | fixture | anthropic. The offline stand in is the zero account default.
        # The anthropic path is UNVERIFIED against the real service. The jobs behind it are in model_tasks.py.
        return build_llm(self.effective(session), CostTracker(session), offline=OfflineBackend())

    def model_on(self) -> bool:
        """True when a model backend (recorded fixtures or the real API) is selected. With LLM_BACKEND=offline nothing below calls a model, so the default behaviour does not change."""
        return self.settings.effective_llm_backend is not LLMBackendKind.OFFLINE

    def answer_writer(self, session: Session):
        """The writer of answer sentences: the model writer when a model backend is on, else None (the extractive rules writer). The groundedness check runs on its output either way."""
        if self.settings.answer_writer == "model" and self.model_on():
            return model_tasks.ModelWriter(self.llm(session))
        return None

    def proposer(self, session: Session):
        """A meeting reader that uses the model, or None for the rules reader."""
        return model_tasks.ModelProposer(self.llm(session)) if self.settings.meeting_extractor == "model" and self.model_on() else None

    def wording(self, session: Session):
        """A function that names a recurring process with the model, or None."""
        if self.settings.process_wording != "model" or not self.model_on():
            return None
        llm = self.llm(session)
        return lambda label, evidence: model_tasks.process_wording(llm, label, evidence)

    def review_intro(self, session: Session, facts: dict) -> dict | None:
        if self.settings.review_writer != "model" or not self.model_on():
            return None
        return model_tasks.review_intro(self.llm(session), facts)


def set_state(session: Session, key: str, value: str) -> None:
    row = session.get(State, key)
    if row is None:
        session.add(State(key=key, value=value))
    else:
        row.value = value


def get_state(session: Session, key: str, default: str = "") -> str:
    row = session.get(State, key)
    return row.value if row else default
