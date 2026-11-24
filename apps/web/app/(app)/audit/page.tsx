"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, DataTable, EmptyState, Sheet, TableSkeleton, notify, type Column } from "@sendora/ui-kit";
import { LeaderGate, LoadError, PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import { auditAction, auditTarget } from "@/lib/labels";
import type { AuditRow } from "@/lib/types";

export default function AuditPage() {
  return <LeaderGate title="Audit log"><AuditView /></LeaderGate>;
}

type Verify = { ok: boolean; first_bad_id: number | null };

function AuditView() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => get<AuditRow[]>("/audit?limit=500") });
  const v = useQuery({ queryKey: ["audit-verify"], queryFn: () => get<Verify>("/audit/verify") });
  const check = useMutation({
    mutationFn: () => get<Verify>("/audit/verify"),
    onSuccess: (r) => { void v.refetch(); if (r.ok) notify.success("The audit log is intact. No entry was changed or removed."); else notify.error("The audit log was changed", `The first bad entry is number ${r.first_bad_id}.`); },
    onError: (e: Error) => notify.error("Could not check the chain", e.message),
  });
  const [open, setOpen] = useState<AuditRow | null>(null);
  const columns: Column<AuditRow>[] = [
    { key: "id", header: "No.", width: "70px", align: "right", sortValue: (r) => r.id },
    { key: "at", header: "When", width: "180px", render: (r) => r.at.replace("T", " ").slice(0, 19), sortValue: (r) => r.at },
    { key: "actor", header: "Who", width: "1fr", sortValue: (r) => r.actor },
    { key: "action", header: "What", width: "1.4fr", render: (r) => auditAction(r.action), sortValue: (r) => auditAction(r.action) },
    { key: "target", header: "About", width: "1fr", render: (r) => auditTarget(r.target), sortValue: (r) => r.target ?? "" },
  ];
  return (
    <div className="cx-page">
      <PageHead title="Audit log" sub="Every change, who made it and when. Each line is chained to the one before, so an edit after the fact shows. Press a row, or Enter on it, to read the details." actions={<Button onClick={async () => { await check.mutateAsync(); }}>Check the chain</Button>} />
      <Card>{v.isError ? <Badge tone="danger">Could not check</Badge> : v.data ? <Badge tone={v.data.ok ? "success" : "danger"}>{v.data.ok ? "Chain intact" : `Chain broken at entry ${v.data.first_bad_id}`}</Badge> : <Badge>Checking</Badge>}</Card>
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="the audit log" /> : !q.data ? <TableSkeleton rows={8} columns={5} /> : q.data.length === 0 ? <Card><EmptyState title="Nothing logged yet" body="Approvals, imports and other changes show up here as they happen." /></Card>
        : <DataTable label="Audit log" rows={q.data} rowKey={(r) => String(r.id)} columns={columns} height={520} onRowOpen={setOpen} rowActions={(r) => <Button size="sm" feedback={false} onClick={() => setOpen(r)}>Open</Button>} />}
      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open ? auditAction(open.action) : "Entry"} description={open ? `Entry number ${open.id}` : undefined}>
        {open ? (
          <dl className="cx-stack" style={{ margin: 0 }}>
            <div><dt className="cx-mini">When</dt><dd style={{ margin: 0 }}>{open.at.replace("T", " ").slice(0, 19)}</dd></div>
            <div><dt className="cx-mini">Who</dt><dd style={{ margin: 0 }}>{open.actor}</dd></div>
            <div><dt className="cx-mini">About</dt><dd style={{ margin: 0 }}>{auditTarget(open.target) || "Nothing in particular"}</dd></div>
            <div><dt className="cx-mini">Details</dt><dd style={{ margin: 0 }}>{Object.keys(open.detail).length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{Object.entries(open.detail).map(([k, d]) => <li key={k}><strong>{k.replace(/_/g, " ")}</strong>: {typeof d === "object" ? JSON.stringify(d) : String(d)}</li>)}</ul> : "None recorded"}</dd></div>
          </dl>
        ) : null}
      </Sheet>
    </div>
  );
}
