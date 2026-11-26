"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Button, Card, EmptyState, SegmentedControl, notify } from "@sendora/ui-kit";
import { LoadError, ListSkeleton, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { ReviewDoc, ReviewRow } from "@/lib/types";

const LINK = /\[([^\]]+)\]\((\/(?:tasks|decisions|meetings|sops)\?open=\d+)\)/g;

/** Inline links point only at the records a review is built from (a task, a decision, a meeting or a process), never anywhere else. A meeting link goes to the meeting page. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let at = 0;
  for (const m of text.matchAll(LINK)) {
    const i = m.index ?? 0;
    if (i > at) out.push(text.slice(at, i));
    const href = (m[2] ?? "").replace(/^\/meetings\?open=(\d+)$/, "/meetings/$1");
    out.push(<Link key={i} href={href}>{m[1]}</Link>);
    at = i + m[0].length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

/** Turn the review's small markdown into elements. */
function render(body: string): ReactNode[] {
  const out: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => { if (list.length) { out.push(<ul key={`u${out.length}`}>{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>); list = []; } };
  body.split("\n").forEach((line, i) => {
    if (line.startsWith("# ")) { flush(); out.push(<h1 key={i}>{line.slice(2)}</h1>); }
    else if (line.startsWith("## ")) { flush(); out.push(<h2 key={i}>{line.slice(3)}</h2>); }
    else if (line.startsWith("- ")) list.push(line.slice(2));
    else if (line.trim()) { flush(); out.push(<p key={i}>{inline(line)}</p>); }
  });
  flush();
  return out;
}

export default function ReviewPage() {
  const qc = useQueryClient();
  const { canWrite, leader } = useRole();
  const list = useQuery({ queryKey: ["reviews"], queryFn: () => get<ReviewRow[]>("/reviews") });
  const [sel, setSel] = useState<number | null>(null);
  const [scope, setScope] = useState<"company" | "leadership">("company");
  const id = sel ?? list.data?.[0]?.id ?? null;
  const doc = useQuery({ queryKey: ["review", id], queryFn: () => get<ReviewDoc>(`/reviews/${id}`), enabled: id !== null });
  const gen = useMutation({ mutationFn: () => post<{ id: number }>("/reviews/generate", { scope }), onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["reviews"] }); setSel(r.id); notify.success("Weekly review built. Every line links to its source."); }, onError: (e: Error) => notify.error("Could not build the review", e.message) });
  return (
    <div className="cx-page">
      <PageHead title="Weekly review" sub="Built by code from last week's tasks, decisions and meetings. Every claim carries a link to the record it came from, and the page checks that none is missing." actions={canWrite ? <>{leader ? <SegmentedControl label="Scope" value={scope} onChange={setScope} options={[{ value: "company", label: "Company" }, { value: "leadership", label: "Leadership" }]} /> : null}<Button variant="primary" onClick={async () => { await gen.mutateAsync(); }}>Generate now</Button></> : null} />
      {list.isError ? <LoadError error={list.error} onRetry={() => list.refetch()} what="reviews" /> : !list.data ? <ListSkeleton /> : list.data.length === 0 ? <EmptyState title="No weekly review yet" body="Generate one for last week. It takes a second." actionLabel={canWrite ? "Generate now" : undefined} onAction={canWrite ? async () => { await gen.mutateAsync(); } : undefined} /> : (
        <div className="cx-two cx-two--rev">
          <Card title="History"><ul className="cx-list">{list.data.map((r) => <li key={r.id}><button type="button" className="cx-item" aria-current={r.id === id} onClick={() => setSel(r.id)}><span className="cx-item__top"><strong>Week of {r.week_start}</strong><span className="cx-mini">{r.scope}</span></span><span className="cx-item__line">{r.linked} of {r.claims} claims linked</span></button></li>)}</ul></Card>
          {doc.data ? <article className="cx-doc" aria-label={doc.data.title}>{render(doc.data.body)}<p className="cx-mini">{doc.data.linked} of {doc.data.claims} claims link to a source. Built {doc.data.generated_at.slice(0, 10)}.</p></article> : <ListSkeleton rows={6} />}
        </div>
      )}
    </div>
  );
}
