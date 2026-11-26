# Specification

What Lorefern is, what is in and what is out.

## Purpose

A company brain and operations helper for a **small company**, set up by an **implementer**. It reads the company's written knowledge and its meetings, answers questions with sources, proposes tasks and decisions for a person to approve, keeps work moving, maps procedures and writes a weekly review.

## Entities

Source, Document, Chunk (passage), Meeting, Transcript, Task, Decision, SOP (as a document type and a Process coverage record), Owner, Question, WeeklyReview. Tables are prefixed `cx_`.

## Rules that hold everywhere

1. **Single tenant.** One company per install.
2. **Visibility.** Five tags, four audiences, filtered inside every query, fail closed. Restricted looks the same as missing.
3. **Per user source permissions are not mirrored.** Tags are set in Lorefern.
4. **Content is untrusted.** Transcripts, documents, Slack and pages are data. Instruction like lines are flagged and ignored.
5. **People decide.** A proposal becomes a task or a decision only when an owner or leadership audience approves. Sending reminders needs a second person.
6. **Every answer cites.** A sentence with no supporting passage is dropped. No support means "not found".
7. **Draft mode is the default.** Nothing is sent. The app can never switch itself to live.

## Pipeline

connectors (folder, Slack export, Drive, Notion, transcripts by file, Fireflies, Fathom) then an index with a tag on every passage, then answers, then meetings to proposals, then reminders, stuck work, the SOP map, the weekly review and the decision log.

## Not in this release

A language model writer, per user source permissions, multi tenant, webhooks, mobile apps, editing documents inside Lorefern, email in (only email out for reminders), Teams, Zoom and calendar tools.

## Seed data

A sample company with 59 files of documents (including READMEs, a PDF agreement and three planted conflicts), 12 sample meeting transcripts, a Slack export, 35 planted tasks with an answer key, an answer key for stuck work, restricted documents under every tag, and held out sets (56 questions, 8 transcripts). Counts are in `data/counts.json`.

## Quality bars

Visibility boundary tests with zero leaks, quote validity 100 percent, every claim of the weekly review linked (checked by code), held out numbers reported as measured, 80 percent test coverage, browser tests for the demo path and the quality gates.
