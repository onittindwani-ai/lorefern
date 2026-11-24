"use client";
import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Badge, Button } from "@sendora/ui-kit";
import { post } from "@/lib/api";
import { CitationCard } from "./CitationCard";
import { Meter } from "./Meter";
import { SourceViewer } from "./SourceViewer";
import type { Answer, Citation } from "@/lib/types";

const TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = { answer: "success", conflict: "warning", not_found: "neutral", refuse: "danger", tasks: "success" };
const LABEL: Record<string, string> = { answer: "Answer", conflict: "Documents disagree", not_found: "Not found", refuse: "Declined", tasks: "From the task list" };

/** The answer view shared by the Ask page and the Cmd+K bar. An answer with no source is never shown as an answer. */
export function AnswerView({ a }: { a: Answer }) {
  const [open, setOpen] = useState<Citation | null>(null);
  return (
    <div className="cx-stack" aria-live="polite">
      <div className="cx-toolbar"><Badge tone={TONE[a.outcome] ?? "neutral"}>{LABEL[a.outcome] ?? a.outcome}</Badge>{a.stale ? <Badge tone="warning">Source may be out of date</Badge> : null}</div>
      <p className={a.outcome === "answer" || a.outcome === "conflict" ? "cx-answer" : "cx-answer cx-answer--plain"}>{a.text}</p>
      {a.reason && a.outcome !== "answer" ? <p className="cx-mini">{a.reason}</p> : null}
      {a.conflict?.length ? (
        <div className="cx-stack">{a.conflict.map((c) => <div key={c.title} className="cx-find"><strong>{c.title}</strong><span>{c.says}</span><span className="cx-mini">Owner {c.owner || "none"} · updated {c.updated_on}</span></div>)}</div>
      ) : null}
      {a.items?.length ? <ul className="cx-list">{a.items.map((i, k) => <li key={k} className="cx-item"><span>{i.evidence}</span></li>)}</ul> : null}
      {a.citations.length ? (
        <>
          <Meter retrieval={a.retrieval} groundedness={a.groundedness} />
          <div className="cx-stack">{a.citations.map((c, i) => <CitationCard key={c.chunk_id} c={c} index={i + 1} onOpen={setOpen} />)}</div>
        </>
      ) : null}
      <SourceViewer docId={open?.document_id ?? null} start={open?.start ?? 0} end={open?.end ?? 0} onClose={() => setOpen(null)} />
    </div>
  );
}

export const SUGGESTIONS = ["How much annual leave do I get?", "When does the weekly operating review happen?", "What is the first reply promise for support questions?", "What is blocked right now?"];

export function useAsk() {
  return useMutation({ mutationFn: (question: string) => post<Answer>("/ask", { question }) });
}

export function AskBox({ onAsk, busy, initial = "", autoFocus = false }: { onAsk: (q: string) => void; busy: boolean; initial?: string; autoFocus?: boolean }) {
  const [q, setQ] = useState(initial);
  const id = useId();
  const submit = () => { const t = q.trim(); if (t) onAsk(t); };
  return (
    <form className="cx-askrow" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <div className="sx-field">
        <label className="sx-label" htmlFor={id}>Ask anything about the company</label>
        <input id={id} className="sx-input" autoFocus={autoFocus} value={q} maxLength={1000} onChange={(e) => setQ(e.target.value)} placeholder="For example: how are databases backed up?" />
      </div>
      <Button variant="primary" type="button" loading={busy} disabled={!q.trim()} disabledReason="Type a question first" onClick={async () => submit()}>Ask</Button>
    </form>
  );
}
