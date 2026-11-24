"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Badge, Button, Card, notify } from "@sendora/ui-kit";
import { LoadError, ListSkeleton, PageHead } from "@/components/Parts";
import { TagBadge } from "@/components/TagBadge";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Decision, MeetingDetail, Task } from "@/lib/types";

interface Span { start: number; end: number; kind: "task" | "decision" | "flag"; id?: number }

/** Cut the transcript into plain and marked pieces. Marks come from the stored quote offsets, so they sit on the exact words. */
function pieces(text: string, spans: Span[]) {
  const ok = spans.filter((s) => s.end > s.start && s.end <= text.length).sort((a, b) => a.start - b.start);
  const out: { t: string; span?: Span }[] = [];
  let at = 0;
  for (const s of ok) {
    if (s.start < at) continue;
    if (s.start > at) out.push({ t: text.slice(at, s.start) });
    out.push({ t: text.slice(s.start, s.end), span: s });
    at = s.end;
  }
  if (at < text.length) out.push({ t: text.slice(at) });
  return out;
}

export default function MeetingPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const q = useQuery({ queryKey: ["meeting", id], queryFn: () => get<MeetingDetail>(`/meetings/${id}`) });
  const [sel, setSel] = useState<number | null>(null);
  const m = q.data;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["meeting", id] }); qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["overview"] }); };
  const undo = (tid: number) => post(`/tasks/${tid}/undo`).then(refresh);
  const approve = useMutation({ mutationFn: (t: Task) => post(`/tasks/${t.id}/approve`, { owner_id: t.owner_id }), onSuccess: (_r, t) => { refresh(); notify.undo(`Approved: ${t.title}`, () => void undo(t.id)); }, onError: (e: Error) => notify.error("Could not approve", e.message) });
  const reject = useMutation({ mutationFn: (t: Task) => post(`/tasks/${t.id}/reject`, { reason: "Not an action" }), onSuccess: (_r, t) => { refresh(); notify.undo(`Rejected: ${t.title}`, () => void undo(t.id)); }, onError: (e: Error) => notify.error("Could not reject", e.message) });
  const decide = useMutation({ mutationFn: ({ d, ok }: { d: Decision; ok: boolean }) => post(`/decisions/${d.id}/${ok ? "confirm" : "reject"}`), onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["decisions"] }); notify.success("Decision recorded"); } });
  const extract = useMutation({ mutationFn: () => post(`/meetings/${id}/extract`), onSuccess: () => { refresh(); notify.success("Read the transcript again. New proposals were added; nothing was approved."); } });

  const parts = useMemo(() => {
    if (!m) return [];
    const spans: Span[] = [
      ...m.tasks.filter((t) => t.status !== "rejected").map((t) => ({ start: t.quote_start, end: t.quote_start + t.quote.length, kind: "task" as const, id: t.id })),
      ...m.decisions.map((d) => ({ start: d.quote_start, end: d.quote_start + d.quote.length, kind: "decision" as const, id: d.id })),
    ];
    for (const f of m.flagged_lines) { const at = m.transcript.indexOf(f); if (at >= 0) spans.push({ start: at, end: at + f.length, kind: "flag" }); }
    return pieces(m.transcript, spans);
  }, [m]);
  if (q.isError) return <LoadError error={q.error} onRetry={() => q.refetch()} what="this meeting" />;
  if (!m) return <ListSkeleton rows={6} />;
  return (
    <div className="cx-page">
      <PageHead title={m.title} sub={`${m.held_on} · ${m.provider} · ${m.attendees.join(", ")}`} actions={canWrite ? <Button feedback onClick={async () => { await extract.mutateAsync(); }}>Read again</Button> : null} />
      <div className="cx-two">
        <Card title="Transcript"><div className="cx-transcript" tabIndex={0} aria-label="Transcript with action items marked">
          <p className="cx-pre">{parts.map((p, i) => p.span ? (
            <button key={i} type="button" data-on={sel === p.span.id && p.span.kind === "task"} className={`cx-hl ${p.span.kind === "decision" ? "cx-hl--decision" : p.span.kind === "flag" ? "cx-hl--flag" : ""}`} title={p.span.kind === "flag" ? "Looks like an instruction to the system, ignored" : p.span.kind === "decision" ? "Decision" : "Action item"} onClick={() => setSel(p.span!.id ?? null)}>{p.t}</button>
          ) : <span key={i}>{p.t}</span>)}</p></div></Card>
        <div className="cx-stack">
          <Card title={`Action items (${m.tasks.length})`}>
            {m.tasks.length === 0 ? <p className="cx-mini">No action items found in this transcript.</p> : <ul className="cx-list">{m.tasks.map((t) => (
              <li key={t.id} className="cx-item" aria-current={sel === t.id} onMouseEnter={() => setSel(t.id)}>
                <span className="cx-item__top"><strong>{t.title}</strong><Badge tone={t.status === "proposed" ? "accent" : t.status === "rejected" ? "neutral" : "success"}>{t.status.replace("_", " ")}</Badge></span>
                <span className="cx-item__line">{t.owner || "No owner named"}{t.due_on ? ` · due ${t.due_on}` : t.due_raw ? ` · "${t.due_raw}"` : ""}</span>
                {t.status === "proposed" && canWrite ? <span className="cx-card__acts"><Button size="sm" variant="primary" onClick={async () => { await approve.mutateAsync(t); }}>Approve</Button><Button size="sm" onClick={async () => { await reject.mutateAsync(t); }}>Reject</Button></span> : null}
              </li>))}</ul>}
          </Card>
          <Card title={`Decisions (${m.decisions.length})`}>
            {m.decisions.length === 0 ? <p className="cx-mini">No decisions found.</p> : <ul className="cx-list">{m.decisions.map((d) => (
              <li key={d.id} className="cx-item"><span className="cx-item__top"><strong>{d.title}</strong><Badge tone={d.status === "confirmed" ? "success" : "accent"}>{d.status}</Badge></span>
                {d.status === "proposed" && canWrite ? <span className="cx-card__acts"><Button size="sm" variant="primary" onClick={async () => { await decide.mutateAsync({ d, ok: true }); }}>Confirm</Button><Button size="sm" onClick={async () => { await decide.mutateAsync({ d, ok: false }); }}>Reject</Button></span> : null}</li>))}</ul>}
          </Card>
          {m.flagged_lines.length ? <Card title="Lines that were ignored"><p className="cx-mini">These lines read like instructions to the system. They are shown, never acted on.</p><ul className="cx-list">{m.flagged_lines.map((f, i) => <li key={i} className="cx-find">{f}</li>)}</ul></Card> : null}
          <div className="cx-toolbar"><TagBadge tag={m.tag} /></div>
        </div>
      </div>
    </div>
  );
}
