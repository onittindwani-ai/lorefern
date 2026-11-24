"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, Button, Card, DataTable, EmptyState, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { LoadError, PageHead } from "@/components/Parts";
import { TagBadge } from "@/components/TagBadge";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Decision } from "@/lib/types";

export default function DecisionsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["decisions"], queryFn: () => get<Decision[]>("/decisions") });
  const act = useMutation({ mutationFn: ({ id, ok }: { id: number; ok: boolean }) => post(`/decisions/${id}/${ok ? "confirm" : "reject"}`), onSuccess: () => { qc.invalidateQueries(); notify.success("Decision recorded"); }, onError: (e: Error) => notify.error("Could not record it", e.message) });
  const { canWrite } = useRole();
  const columns: Column<Decision>[] = [
    { key: "date", header: "Decided", width: "110px", render: (d) => d.decided_on ?? "", sortValue: (d) => d.decided_on ?? "" },
    { key: "title", header: "Decision", width: "1.4fr", render: (d) => <span><strong>{d.title}</strong>{d.why ? <span className="cx-mini"> · {d.why}</span> : null}</span>, sortValue: (d) => d.title },
    { key: "by", header: "By", width: "140px", render: (d) => d.decided_by, sortValue: (d) => d.decided_by },
    { key: "src", header: "Meeting", width: "1fr", render: (d) => d.meeting_id ? <Link href={`/meetings/${d.meeting_id}`}>{d.meeting_title || "Open"}</Link> : "" },
    { key: "tag", header: "Visible to", width: "110px", render: (d) => <TagBadge tag={d.tag} /> },
    { key: "st", header: "Status", width: canWrite ? "230px" : "110px", render: (d) => d.status === "proposed" && canWrite ? <span className="cx-card__acts"><Button size="sm" variant="primary" onClick={async () => { await act.mutateAsync({ id: d.id, ok: true }); }}>Confirm</Button><Button size="sm" onClick={async () => { await act.mutateAsync({ id: d.id, ok: false }); }}>Reject</Button></span> : <Badge tone={d.status === "confirmed" ? "success" : d.status === "proposed" ? "accent" : "neutral"}>{d.status}</Badge> },
  ];
  return (
    <div className="cx-page">
      <PageHead title="Decisions" sub="What was decided, by whom, and why, with the exact words from the meeting. A decision found in a transcript waits for a person to confirm it." />
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="decisions" /> : !q.data ? <TableSkeleton rows={6} columns={5} /> : q.data.length === 0 ? <EmptyState title="No decisions recorded" body="Decisions found in meeting transcripts appear here for you to confirm." /> : <Card className="cx-noopen"><DataTable label="Decision log" rows={q.data} rowKey={(d) => String(d.id)} columns={columns} height={520} /></Card>}
    </div>
  );
}
