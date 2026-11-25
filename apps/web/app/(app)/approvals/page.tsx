"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, EmptyState, notify } from "@sendora/ui-kit";
import { LeaderGate, ListSkeleton, LoadError, PageHead } from "@/components/Parts";
import { get, post } from "@/lib/api";
import { useRole, useSettings } from "@/lib/hooks";
import type { ApprovalRow } from "@/lib/types";

interface SendItem { id: number; task: string; to: string; subject: string; body: string; outside: boolean }
/** The messages a send approval would put out: who gets each one and the exact text. The person who approves reads this, not only the summary. */
const itemsOf = (a: ApprovalRow): SendItem[] => (Array.isArray(a.payload.items) ? (a.payload.items as SendItem[]) : []);

export default function ApprovalsPage() {
  return <LeaderGate title="Approvals"><ApprovalsView /></LeaderGate>;
}

function ApprovalsView() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const settings = useSettings();
  const q = useQuery({ queryKey: ["approvals"], queryFn: () => get<ApprovalRow[]>("/approvals") });
  const decide = useMutation({
    mutationFn: (v: { id: number; approve: boolean }) => post(`/approvals/${v.id}/decide`, { approve: v.approve, note: "" }),
    onSuccess: (_r, v) => { notify.success(v.approve ? "Approved." : "Rejected."); qc.invalidateQueries(); },
    onError: (e: Error) => notify.error("Could not decide", e.message),
  });
  if (q.isError) return <div className="cx-page"><PageHead title="Approvals" /><LoadError error={q.error} onRetry={() => q.refetch()} what="approvals" /></div>;
  if (!q.data) return <div className="cx-page"><PageHead title="Approvals" /><ListSkeleton /></div>;
  const pending = q.data.filter((a) => a.status === "pending");
  const past = q.data.filter((a) => a.status !== "pending");
  return (
    <div className="cx-page">
      <PageHead title="Approvals" sub="Anything that reaches outside this app waits here for a person. The person who asked cannot approve their own request." />
      {settings.data?.effective_mode === "draft" ? <p className="cx-mini" role="note">Draft mode is on, so approving a send is refused until the go live checklist is done. Nothing leaves this app.</p> : null}
      <Card title={`Waiting (${pending.length})`}>{pending.length === 0 ? <EmptyState title="Nothing waiting" body="Risky actions such as sending a reminder show up here." /> : (
        <div className="cx-stack">{pending.map((a) => (
          <div key={a.id} className="cx-field" style={{ gridTemplateColumns: "1fr auto" }}>
            <span><strong>{a.summary}</strong> <Badge tone={a.risk === "high" ? "danger" : "warning"}>{a.risk} risk</Badge><br /><span className="cx-mini" style={{ fontSize: "var(--sx-text-caption)", color: "var(--sx-ink-2)" }}>Asked by {a.requested_by} on {a.created_at.slice(0, 10)}</span>
              {itemsOf(a).length > 0 ? (
                <ul className="cx-stack" aria-label={`Messages that approval ${a.id} would send`} style={{ margin: "var(--sx-space-2) 0 0", paddingLeft: "var(--sx-space-4)" }}>
                  {itemsOf(a).map((i) => (
                    <li key={i.id} className="cx-mini">To {i.to || "nobody (no address, so it is not sent)"} {i.outside ? <Badge tone="danger">outside the company's email domains</Badge> : null}<br />{i.subject}: {i.body}</li>
                  ))}
                </ul>
              ) : null}
              {a.payload.changed === true ? <span className="cx-mini" role="alert"><br />This changed after it was asked for (a person, an address or a text is different). Reject it and ask again.</span> : null}</span>
            <span className="sx-row"><Button size="sm" variant="primary" disabled={!canWrite || a.payload.changed === true} disabledReason={a.payload.changed === true ? "It changed after it was asked for" : "Your sign in can read but not change things"} onClick={async () => { await decide.mutateAsync({ id: a.id, approve: true }); }}>Approve</Button><Button size="sm" disabled={!canWrite} disabledReason="Your sign in can read but not change things" onClick={async () => { await decide.mutateAsync({ id: a.id, approve: false }); }}>Reject</Button></span>
          </div>))}</div>)}</Card>
      <Card title="Decided">{past.length === 0 ? <EmptyState title="No history yet" body="Decisions appear here." /> : <div className="cx-stack">{past.map((a) => <div key={a.id} className="cx-field" style={{ gridTemplateColumns: "1fr auto" }}><span>{a.summary}</span><Badge tone={a.status === "approved" ? "success" : "neutral"}>{a.status} by {a.decided_by}</Badge></div>)}</div>}</Card>
    </div>
  );
}
