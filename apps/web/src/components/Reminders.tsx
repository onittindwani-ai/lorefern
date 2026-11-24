"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, notify } from "@sendora/ui-kit";
import { get, post } from "@/lib/api";
import { useRole, useSettings } from "@/lib/hooks";
import type { ApprovalRow, ReminderRow } from "@/lib/types";

const KIND: Record<string, string> = { due_soon: "Due tomorrow", overdue: "Overdue", no_update: "No update" };
const SHOWN = 8;

/** Reminder drafts. Nothing is sent from here: a person asks, and a different person approves on the Approvals page. */
export function Reminders() {
  const qc = useQueryClient();
  const { canWrite } = useRole();
  const settings = useSettings();
  const q = useQuery({ queryKey: ["reminders"], queryFn: () => get<ReminderRow[]>("/reminders") });
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: () => get<ApprovalRow[]>("/approvals"), enabled: canWrite });
  const waiting = new Set((approvals.data ?? []).filter((a) => a.status === "pending" && a.action === "reminders.send").flatMap((a) => (a.payload.ids as number[] | undefined) ?? []));
  const plan = useMutation({
    mutationFn: () => post<{ drafted: number }>("/reminders/plan"),
    onSuccess: (r) => { notify.success(r.drafted ? `${r.drafted} new reminder ${r.drafted === 1 ? "draft" : "drafts"} added.` : "No new reminders are due today."); void qc.invalidateQueries({ queryKey: ["reminders"] }); },
    onError: (e: Error) => notify.error("Could not draft reminders", e.message),
  });
  const send = useMutation({
    mutationFn: (ids: number[]) => post("/reminders/request-send", { ids }),
    onSuccess: () => { notify.success("Sent for approval. A different person must approve it on the Approvals page."); void qc.invalidateQueries(); },
    onError: (e: Error) => notify.error("Could not ask for approval", e.message),
  });
  const drafted = (q.data ?? []).filter((r) => r.status === "drafted");
  const unasked = drafted.filter((r) => !waiting.has(r.id));
  return (
    <Card title={`Reminder drafts (${drafted.length})`} className="cx-reminders">
      <div className="cx-stack">
        <p className="cx-mini">{settings.data?.effective_mode === "draft" ? "Draft mode is on: reminders are written here and never sent." : "Reminders go out only after a different person approves them."}</p>
        {q.isError ? <p role="alert">The reminders could not be loaded: {(q.error as Error).message}</p> : null}
        {drafted.slice(0, SHOWN).map((r) => (
          <div key={r.id} className="cx-reminder"><span className="cx-item__top"><strong>{r.owner || "No owner"}</strong><Badge tone={r.kind === "overdue" ? "warning" : "neutral"}>{KIND[r.kind] ?? r.kind}</Badge></span><span className="cx-item__line">{r.body}</span></div>
        ))}
        {drafted.length > SHOWN ? <p className="cx-mini">And {drafted.length - SHOWN} more.</p> : null}
        {q.data && drafted.length === 0 ? <p className="cx-mini">No reminders are waiting. They are drafted on working days for work that is due tomorrow or overdue.</p> : null}
        {canWrite ? (
          <div className="cx-toolbar">
            <Button onClick={async () => { await plan.mutateAsync(); }}>Draft today&apos;s reminders</Button>
            <Button variant="primary" disabled={unasked.length === 0} disabledReason={drafted.length === 0 ? "There are no reminder drafts to send" : "Already waiting for a second person on the Approvals page"} onClick={async () => { await send.mutateAsync(unasked.map((r) => r.id)); }}>{`Ask to send ${unasked.length}`}</Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
