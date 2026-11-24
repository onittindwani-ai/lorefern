"""Lorefern tables (prefix cx_). They sit on the shared Base.

Every row that holds content carries a visibility `tag` (company, clients, finance, people, leadership). Reads are filtered by the tags a person's audience may see.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sendora_core.db import Base, UTCDateTime, utcnow

TAGS = ("company", "clients", "finance", "people", "leadership")
TASK_STATUSES = ("proposed", "open", "in_progress", "blocked", "done", "rejected")
DECISION_STATUSES = ("proposed", "confirmed", "rejected")


class State(Base):
    __tablename__ = "cx_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Owner(Base):
    """A person who can own work. Not a login: logins come from settings."""

    __tablename__ = "cx_owner"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    email: Mapped[str] = mapped_column(String(254), default="")
    role: Mapped[str] = mapped_column(String(120), default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)  # first name, nickname


class Source(Base):
    __tablename__ = "cx_source"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # folder, drive, notion, slack, meetings
    name: Mapped[str] = mapped_column(String(120))
    uri: Mapped[str] = mapped_column(String(500), default="")
    default_tag: Mapped[str] = mapped_column(String(20), default="company")
    reliability: Mapped[str] = mapped_column(String(20), default="B")  # A direct record, B owner stated, C inference
    owner: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="new")
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    documents: Mapped[list[Document]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "cx_document"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("cx_source.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(300), index=True)
    slug: Mapped[str] = mapped_column(String(160), default="", index=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(12), default="md")  # md, txt, pdf, slack, transcript
    doc_type: Mapped[str] = mapped_column(String(20), default="")  # sop, decision, meeting_note, client_brief, readme, policy, other
    tag: Mapped[str] = mapped_column(String(20), default="company", index=True)
    owner: Mapped[str] = mapped_column(String(120), default="")
    updated_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="")  # current, superseded, draft
    content_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    outdated: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)  # holds instruction like text aimed at the system
    source: Mapped[Source] = relationship(back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan", order_by="Chunk.ordinal")


class Chunk(Base):
    __tablename__ = "cx_chunk"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("cx_document.id"), index=True)
    tag: Mapped[str] = mapped_column(String(20), default="company", index=True)  # copy of the document tag, so search filters inside the query
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(300), default="")
    context: Mapped[str] = mapped_column(String(400), default="")
    text: Mapped[str] = mapped_column(Text)
    start: Mapped[int] = mapped_column(Integer, default=0)
    end: Mapped[int] = mapped_column(Integer, default=0)
    stems: Mapped[str] = mapped_column(Text, default="")
    vec: Mapped[dict] = mapped_column(JSON, default=dict)  # hashed bag of words, NOT a language model embedding
    document: Mapped[Document] = relationship(back_populates="chunks")


class Meeting(Base):
    __tablename__ = "cx_meeting"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("cx_source.id"), nullable=True)
    external_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    provider: Mapped[str] = mapped_column(String(20), default="file")  # fireflies, fathom, otter, meetily, file
    title: Mapped[str] = mapped_column(String(300))
    held_on: Mapped[date] = mapped_column(Date)
    tag: Mapped[str] = mapped_column(String(20), default="company", index=True)
    attendees: Mapped[list] = mapped_column(JSON, default=list)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("cx_document.id"), nullable=True)  # the transcript is also indexed as a document
    extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_lines: Mapped[list] = mapped_column(JSON, default=list)  # lines that look like instructions to the system, never acted on
    transcript: Mapped[Transcript | None] = relationship(back_populates="meeting", uselist=False, cascade="all, delete-orphan")


class Transcript(Base):
    __tablename__ = "cx_transcript"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("cx_meeting.id"), unique=True)
    text: Mapped[str] = mapped_column(Text)  # "Speaker: words" per line, exactly as imported
    meeting: Mapped[Meeting] = relationship(back_populates="transcript")


class Task(Base):
    __tablename__ = "cx_task"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("cx_owner.id"), nullable=True, index=True)
    owner_raw: Mapped[str] = mapped_column(String(120), default="")  # what the transcript said when no known owner matched
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_raw: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(12), default="proposed", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    quote: Mapped[str] = mapped_column(Text, default="")  # verbatim from the transcript, checked by code
    quote_start: Mapped[int] = mapped_column(Integer, default=-1)
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("cx_meeting.id"), nullable=True, index=True)
    tag: Mapped[str] = mapped_column(String(20), default="company", index=True)
    process_key: Mapped[str] = mapped_column(String(80), default="")
    blocked_reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    owner: Mapped[Owner | None] = relationship()
    meeting: Mapped[Meeting | None] = relationship()
    events: Mapped[list[TaskEvent]] = relationship(back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.id")


class TaskEvent(Base):
    __tablename__ = "cx_task_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("cx_task.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # created, approved, rejected, update, blocked, done, reopened, edited, reminder
    note: Mapped[str] = mapped_column(String(500), default="")
    actor: Mapped[str] = mapped_column(String(120), default="")
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    task: Mapped[Task] = relationship(back_populates="events")


class Reminder(Base):
    __tablename__ = "cx_reminder"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("cx_task.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # due_soon, overdue, no_update
    on_date: Mapped[date] = mapped_column(Date)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="drafted")  # drafted, sent


class Decision(Base):
    __tablename__ = "cx_decision"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    decided_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(200), default="")
    why: Mapped[str] = mapped_column(Text, default="")
    quote: Mapped[str] = mapped_column(Text, default="")
    quote_start: Mapped[int] = mapped_column(Integer, default=-1)
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("cx_meeting.id"), nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("cx_document.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="proposed")
    tag: Mapped[str] = mapped_column(String(20), default="company", index=True)
    stems: Mapped[str] = mapped_column(Text, default="")


class Process(Base):
    """A recurring process found in meetings and tasks. `sop_id` empty means a gap."""

    __tablename__ = "cx_process"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    label: Mapped[str] = mapped_column(String(160))
    area: Mapped[str] = mapped_column(String(60), default="")  # the numbered folder the evidence mostly sits in
    mentions: Mapped[int] = mapped_column(Integer, default=0)
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # [{kind, id, text}]
    sop_id: Mapped[int | None] = mapped_column(ForeignKey("cx_document.id"), nullable=True)
    coverage: Mapped[str] = mapped_column(String(12), default="gap")  # covered, stale, gap
    tag: Mapped[str] = mapped_column(String(20), default="company")


class Question(Base):
    __tablename__ = "cx_question"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    asker: Mapped[str] = mapped_column(String(120), default="")
    audience: Mapped[str] = mapped_column(String(20), default="staff")
    outcome: Mapped[str] = mapped_column(String(20), default="")  # answer, not_found, refuse, conflict
    answer: Mapped[dict] = mapped_column(JSON, default=dict)
    asked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WeeklyReview(Base):
    __tablename__ = "cx_weekly_review"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    scope_tag: Mapped[str] = mapped_column(String(20), default="company")  # the highest tag its evidence may carry
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    sections: Mapped[list] = mapped_column(JSON, default=list)
    claims: Mapped[int] = mapped_column(Integer, default=0)
    linked: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
