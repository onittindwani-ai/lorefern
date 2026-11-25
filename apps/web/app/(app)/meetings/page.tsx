"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, Field, notify } from "@sendora/ui-kit";
import { LoadError, ListSkeleton, PageHead, Textarea } from "@/components/Parts";
import { TagBadge } from "@/components/TagBadge";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { MeetingRow } from "@/lib/types";

export default function MeetingsPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const q = useQuery({ queryKey: ["meetings"], queryFn: () => get<MeetingRow[]>("/meetings") });
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [held, setHeld] = useState("2026-12-01");
  const [text, setText] = useState("");
  const [vis, setVis] = useState("");
  const dateOk = /^\d{4}-\d{2}-\d{2}$/.test(held.trim()) && !Number.isNaN(Date.parse(held.trim()));
  const add = useMutation({
    mutationFn: () => post<{ id: number; tasks: number; decisions: number }>("/meetings", { title: title.trim(), held_on: held.trim(), text, provider: "file", visibility: vis || undefined }),
    onSuccess: (r) => { notify.success(r.tasks || r.decisions ? `Transcript imported and read: ${r.tasks} ${r.tasks === 1 ? "task" : "tasks"} and ${r.decisions} ${r.decisions === 1 ? "decision" : "decisions"} wait for a person to approve.` : "Transcript imported and read. No action items or decisions were found in it."); setOpen(false); setText(""); setTitle(""); qc.invalidateQueries(); },
    onError: (e: Error) => notify.error("Could not import the transcript", e.message),
  });
  return (
    <div className="cx-page">
      <PageHead title="Meetings" sub="Each transcript is read for action items and decisions. Every item quotes the exact words, and a person approves it before it becomes a task." actions={canWrite ? <Button variant="primary" feedback={false} onClick={() => setOpen(true)}>Import a transcript</Button> : null} />
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="meetings" /> : !q.data ? <ListSkeleton /> : q.data.length === 0 ? <EmptyState title="No meetings yet" body="Paste a transcript or connect a recorder on the Sources page." actionLabel="Import a transcript" onAction={() => setOpen(true)} /> : (
        <Card><ul className="cx-list">{q.data.map((m) => (
          <li key={m.id}><Link href={`/meetings/${m.id}`} className="cx-item" style={{ textDecoration: "none" }}>
            <span className="cx-item__top"><strong>{m.title}</strong><span className="cx-mini">{m.held_on}</span></span>
            <span className="cx-item__line">{m.attendees.join(", ") || "No attendees listed"}</span>
            <span className="cx-toolbar"><TagBadge tag={m.tag} /><Badge>{m.tasks} {m.tasks === 1 ? "task" : "tasks"}</Badge>{m.proposed ? <Badge tone="accent">{m.proposed} to approve</Badge> : null}{m.flagged ? <Badge tone="warning">{m.flagged} {m.flagged === 1 ? "line" : "lines"} ignored</Badge> : null}</span>
          </Link></li>))}</ul></Card>
      )}
      <Dialog open={open} onOpenChange={setOpen} title="Import a transcript" description="Paste the text. It is stored as data and read for proposals. Instructions written inside a transcript are ignored."
        actions={<><Button variant="ghost" feedback={false} onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" disabled={!title.trim() || text.trim().length < 10 || !dateOk} disabledReason={!dateOk ? "Write the date as year-month-day, for example 2026-12-01" : "Add a title and the transcript text"} onClick={async () => { await add.mutateAsync(); }}>Import</Button></>}>
        <div className="cx-stack"><Field label="Title" value={title} onChange={setTitle} maxLength={200} /><Field label="Meeting date (year-month-day)" value={held} onChange={setHeld} validate={(v) => (/^\d{4}-\d{2}-\d{2}$/.test(v.trim()) && !Number.isNaN(Date.parse(v.trim())) ? null : "Write the date as year-month-day, for example 2026-12-01")} /><div className="sx-field"><label className="sx-label" htmlFor="m-vis">Who may see it</label><select id="m-vis" className="cx-select" value={vis} onChange={(e) => setVis(e.target.value)}><option value="">Only the narrowest group I may see (the safe choice)</option>{["company", "clients", "finance", "people", "leadership"].map((t) => <option key={t} value={t}>{t}</option>)}</select></div><Textarea label="Transcript" value={text} onChange={(e) => setText(e.target.value)} hint="Speaker lines look like: Name: what they said" /></div>
      </Dialog>
    </div>
  );
}
