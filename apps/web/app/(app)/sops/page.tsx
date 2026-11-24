"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState, notify } from "@sendora/ui-kit";
import { LoadError, ListSkeleton, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Process, SopMap } from "@/lib/types";

const WORD = { covered: "Covered", stale: "Needs review", gap: "No SOP" } as const;

/** Tile size follows how often the process shows up; the grid is 12 columns, sized in steps. */
function span(p: Process, max: number) { return Math.max(3, Math.min(6, Math.round((p.mentions / Math.max(max, 1)) * 6))); }

export default function SopsPage() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const q = useQuery({ queryKey: ["sops"], queryFn: () => get<SopMap>("/sops") });
  const [sel, setSel] = useState<number | null>(null);
  useEffect(() => { const n = Number(new URLSearchParams(window.location.search).get("open")); if (n) setSel(n); }, []);
  const refresh = useMutation({ mutationFn: () => post("/sops/refresh"), onSuccess: () => { qc.invalidateQueries({ queryKey: ["sops"] }); qc.invalidateQueries({ queryKey: ["overview"] }); notify.success("Looked for recurring work again."); }, onError: (e: Error) => notify.error("Could not refresh", e.message) });
  const ps = q.data?.processes ?? [];
  const max = Math.max(1, ...ps.map((p) => p.mentions));
  const cur = ps.find((p) => p.id === sel) ?? ps[0] ?? null;
  return (
    <div className="cx-page">
      <PageHead title="SOP map" sub="Work that keeps coming up in tasks and meetings, matched against the written procedures. A gap is work people repeat that nobody has written down." actions={canWrite ? <Button onClick={async () => { await refresh.mutateAsync(); }}>Look again</Button> : null} />
      <div className="cx-legend" aria-label="Legend">{(["covered", "stale", "gap"] as const).map((k) => <span key={k}><span className="cx-dot" data-cov={k} />{WORD[k]}</span>)}</div>
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="the SOP map" /> : !q.data ? <ListSkeleton /> : ps.length === 0 ? <EmptyState title="No recurring work found yet" body="Import more meetings or tasks. A process appears here when it comes up in at least 3 meetings over 2 weeks." /> : (
        <div className="cx-two">
          <div className="cx-tree" role="list" aria-label="Recurring processes">
            {ps.map((p) => (
              <button key={p.id} type="button" role="listitem" className="cx-tile" data-cov={p.coverage} data-on={cur?.id === p.id} style={{ gridColumn: `span ${span(p, max)}`, gridRow: `span ${p.mentions > max / 2 ? 2 : 1}` }} onClick={() => setSel(p.id)} aria-label={`${p.label}, ${WORD[p.coverage]}, seen ${p.mentions} times`}>
                <strong>{p.label}</strong><span className="cx-mini">{WORD[p.coverage]} · {p.mentions} times</span>
              </button>))}
          </div>
          {cur ? (
            <Card title={cur.label}>
              <div className="cx-stack">
                <Badge tone={cur.coverage === "covered" ? "success" : cur.coverage === "stale" ? "warning" : "danger"}>{WORD[cur.coverage]}</Badge>
                {cur.sop ? <p>Written procedure: <strong>{cur.sop.title}</strong>, owner {cur.sop.owner || "none"}, review by {cur.sop.review_by || "not set"}.</p> : <p>No written procedure matches this work.</p>}
                <h3 className="sx-label">Evidence</h3>
                <ul className="cx-list">{cur.evidence.map((e, i) => <li key={i} className="cx-item"><span className="cx-item__top"><span>{e.text}</span><span className="cx-mini">{e.on}</span></span><span className="cx-item__line">{e.kind}</span></li>)}</ul>
              </div>
            </Card>
          ) : null}
        </div>
      )}
      {q.data?.unmatched_sops.length ? <Card title="Procedures nothing points at"><ul className="cx-list">{q.data.unmatched_sops.map((s) => <li key={s.id} className="cx-item"><span>{s.title}</span><span className="cx-item__line">Owner {s.owner || "none"} · review by {s.review_by || "not set"}</span></li>)}</ul></Card> : null}
    </div>
  );
}
