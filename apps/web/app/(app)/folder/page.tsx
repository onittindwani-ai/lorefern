"use client";
import { useQuery } from "@tanstack/react-query";
import { Badge, Button, Card, EmptyState, Stat } from "@sendora/ui-kit";
import { LeaderGate, LoadError, ListSkeleton, PageHead } from "@/components/Parts";
import { TagBadge } from "@/components/TagBadge";
import { get } from "@/lib/api";
import type { FolderCheck } from "@/lib/types";

export default function FolderPage() {
  return <LeaderGate title="Company folder"><FolderView /></LeaderGate>;
}

function FolderView() {
  const q = useQuery({ queryKey: ["folder"], queryFn: () => get<FolderCheck>("/company-folder") });
  const f = q.data;
  return (
    <div className="cx-page">
      <PageHead title="Company folder" sub="The folder Lorefern learns from. This page checks it against the template: a README in every folder, an owner and review date on every document, and no broken links." actions={<Button onClick={async () => { await q.refetch(); }}>Check again</Button>} />
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="the company folder" /> : !f ? <ListSkeleton rows={6} /> : (
        <>
          <div className="cx-stats"><Stat label="Documents" value={f.documents_visible} /><Stat label="Errors" value={f.errors} /><Stat label="Warnings" value={f.warnings} /></div>
          <div className="cx-two">
            <Card title="Folders"><div className="cx-ftree">{f.tree.length === 0 ? <EmptyState title="Nothing to show" body="No folder matches the template yet." /> : f.tree.map((t) => (
              <details key={t.folder} open={t.documents.length < 6}><summary><span>{t.folder}</span><Badge>{t.documents.length}</Badge></summary>
                <ul>{t.documents.map((d) => <li key={d.path}><span>{d.path.split("/").pop()}</span> <span className="cx-mini">owner {d.owner || "none"} · review by {d.review_by || "not set"}</span> <TagBadge tag={d.visibility || "company"} /></li>)}</ul></details>))}</div></Card>
            <Card title={f.ok ? "Check passed" : "Check results"}>
              {f.findings.length === 0 ? <p>No problems found.</p> : <div className="cx-stack">{f.findings.slice(0, 60).map((x, i) => <div key={i} className={`cx-find ${x.severity === "error" ? "cx-find--error" : ""}`}><strong>{x.code.replace(/_/g, " ")}</strong><span>{x.message}</span><span className="cx-mini">{x.path}</span></div>)}</div>}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
