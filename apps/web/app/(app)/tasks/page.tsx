"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, Card, DataTable, Dialog, EmptyState, Kanban, SegmentedControl, Sheet, notify, type Column, type KanbanItem } from "@sendora/ui-kit";
import { LoadError, ListSkeleton, PageHead, Textarea } from "@/components/Parts";
import { Reminders } from "@/components/Reminders";
import { TagBadge } from "@/components/TagBadge";
import { get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Owner, Stuck, Task } from "@/lib/types";

const COLS = [
  { id: "proposed", title: "Proposed" }, { id: "open", title: "Open" }, { id: "in_progress", title: "In progress" }, { id: "blocked", title: "Blocked" }, { id: "done", title: "Done" },
];
type Item = Omit<Task, "id"> & KanbanItem & { taskId: number };

export default function TasksPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["tasks"], queryFn: () => get<Task[]>("/tasks?limit=10000") });
  const stuck = useQuery({ queryKey: ["stuck"], queryFn: () => get<Stuck[]>("/stuck") });
  const owners = useQuery({ queryKey: ["owners"], queryFn: () => get<Owner[]>("/owners") });
  const [openId, setOpenId] = useState<number | null>(null);
  const [blockFor, setBlockFor] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [onlyStuck, setOnlyStuck] = useState(false);
  const [view, setView] = useState<"board" | "table">("board");
  const { canWrite } = useRole();
  useEffect(() => { const n = Number(new URLSearchParams(window.location.search).get("open")); if (n) setOpenId(n); }, []);
  const stuckIds = new Set((stuck.data ?? []).flatMap((s) => (s.task_id ? [s.task_id] : [])));
  const refresh = () => { qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["stuck"] }); qc.invalidateQueries({ queryKey: ["overview"] }); qc.invalidateQueries({ queryKey: ["task"] }); };
  const undo = (id: number) => post(`/tasks/${id}/undo`).then(refresh).catch((e: Error) => notify.error("Could not undo", e.message));

  const approve = useMutation({ mutationFn: (t: Task) => post(`/tasks/${t.id}/approve`, { owner_id: t.owner_id }), onSuccess: (_r, t) => { refresh(); notify.undo(`Approved: ${t.title}`, () => void undo(t.id)); }, onError: (e: Error) => notify.error("Could not approve", e.message) });
  const reject = useMutation({ mutationFn: (t: Task) => post(`/tasks/${t.id}/reject`, { reason: "Not an action" }), onSuccess: (_r, t) => { refresh(); notify.undo(`Rejected: ${t.title}`, () => void undo(t.id)); }, onError: (e: Error) => notify.error("Could not reject", e.message) });
  const move = useMutation({ mutationFn: ({ id, status, note }: { id: number; status: string; note?: string }) => post(`/tasks/${id}/status`, { status, note: note ?? "" }), onSuccess: (_r, v) => { refresh(); notify.undo("Task moved", () => void undo(v.id)); }, onError: (e: Error) => notify.error("Could not move the task", e.message) });

  const proposedCount = (q.data ?? []).filter((t) => t.status === "proposed").length;
  const bulk = useMutation({ mutationFn: () => post<{ approved: number[] }>("/tasks/bulk-approve", { ids: (q.data ?? []).filter((t) => t.status === "proposed").map((t) => t.id).slice(0, 200) }), onSuccess: (r) => { refresh(); notify.undo(`Approved ${r.approved?.length ?? 0} tasks`, () => void Promise.all((r.approved ?? []).map((i) => undo(i)))); }, onError: (e: Error) => notify.error("Could not approve them", e.message) });
  const items: Item[] = (q.data ?? []).filter((t) => t.status !== "rejected" && (!onlyStuck || stuckIds.has(t.id))).map((t) => ({ ...t, id: String(t.id), taskId: t.id, columnId: t.status }));
  const onMove = (id: string, to: string, from: string) => {
    if (!canWrite) return notify.error("You can read tasks but not change them", "Only the owner and leadership move tasks.");
    const n = Number(id);
    if (from === "proposed") return to === "open" ? approve.mutate((q.data ?? []).find((t) => t.id === n)!) : notify.info("Approve a proposed task first.");
    if (to === "proposed") return notify.info("A task cannot go back to proposed.");
    if (to === "blocked") { setBlockFor(n); return; }
    move.mutate({ id: n, status: to });
  };
  const cols: Column<Item>[] = [
    { key: "title", header: "Task", width: "2fr", render: (t) => t.title, sortValue: (t) => t.title },
    { key: "status", header: "Status", width: "120px", render: (t) => t.status.replace("_", " "), sortValue: (t) => t.status },
    { key: "owner", header: "Owner", width: "150px", render: (t) => t.owner || "None", sortValue: (t) => t.owner },
    { key: "due", header: "Due", width: "110px", render: (t) => t.due_on ?? "", sortValue: (t) => t.due_on ?? "" },
  ];
  const detail = (q.data ?? []).find((t) => t.id === openId) ?? null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return (
    <div className="cx-page">
      <PageHead title="Tasks" sub="Tasks found in meetings wait in Proposed until a person approves them. Nothing becomes a task by itself." actions={<><SegmentedControl label="View" value={view} onChange={setView} options={[{ value: "board", label: "Board" }, { value: "table", label: "Table" }]} />{canWrite && proposedCount ? <Button variant="primary" onClick={async () => { await bulk.mutateAsync(); }}>{`Approve all proposed (${proposedCount})`}</Button> : null}<Button variant={onlyStuck ? "primary" : "ghost"} feedback={false} onClick={() => setOnlyStuck((v) => !v)}>{onlyStuck ? "Showing stuck work" : `Stuck work (${stuckIds.size})`}</Button></>} />
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="tasks" /> : !q.data ? <ListSkeleton rows={6} /> : items.length === 0 ? <EmptyState title="No tasks to show" body="Import a meeting transcript and Lorefern will propose the action items it finds." actionLabel="Open meetings" onAction={() => window.location.assign("/meetings")} /> : view === "table" || items.length > 400 ? (
        <Card><DataTable label="Task table" rows={items} rowKey={(t) => String(t.taskId)} columns={cols} height={560} onRowOpen={(t) => setOpenId(t.taskId)} /></Card>
      ) : (
        <Kanban label="Task board" columns={COLS} items={items} onMove={onMove} onOpen={(t) => setOpenId(t.taskId)} cardLabel={(t) => `task ${t.title}`} renderCard={(t) => {
          const late = t.due_on && new Date(t.due_on) < today && t.status !== "done";
          return (
            <div className="cx-card" onClick={() => setOpenId(t.taskId)} role="presentation">
              <span className="cx-card__title">{t.title}</span>
              <div className="cx-card__meta"><span>{t.owner || "No owner"}</span>{t.due_on ? <span className={late ? "cx-due--late" : ""}>{late ? "Overdue " : "Due "}{t.due_on}</span> : null}{stuckIds.has(t.taskId) ? <Badge tone="warning">Stuck</Badge> : null}</div>
            </div>
          );
        }} />
      )}
      {q.data ? <Reminders /> : null}
      <Sheet open={!!detail} onOpenChange={(o) => !o && setOpenId(null)} title={detail?.title ?? "Task"} description={detail ? `${detail.status.replace("_", " ")} · ${detail.owner || "no owner"} · ${detail.due_on ? `due ${detail.due_on}` : "no due date"}` : ""}>
        {detail ? <TaskDetail id={detail.id} owners={owners.data ?? []} canWrite={canWrite} onChange={refresh} onApprove={async () => { await approve.mutateAsync(detail); setOpenId(null); }} onReject={async () => { await reject.mutateAsync(detail); setOpenId(null); }} /> : null}
      </Sheet>
      <Dialog open={blockFor !== null} onOpenChange={(o) => { if (!o) { setBlockFor(null); setReason(""); } }} title="What is it blocked by?" description="A blocked task needs a reason so the next person knows what to unblock."
        actions={<><Button variant="ghost" feedback={false} onClick={() => setBlockFor(null)}>Cancel</Button><Button variant="primary" disabled={!reason.trim()} disabledReason="Write the reason first" onClick={async () => { await move.mutateAsync({ id: blockFor!, status: "blocked", note: reason }); setBlockFor(null); setReason(""); }}>Mark blocked</Button></>}>
        <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Dialog>
    </div>
  );
}

function TaskDetail({ id, owners, canWrite, onChange, onApprove, onReject }: { id: number; owners: Owner[]; canWrite: boolean; onChange: () => void; onApprove: () => Promise<unknown>; onReject: () => Promise<unknown> }) {
  const q = useQuery({ queryKey: ["task", id], queryFn: () => get<Task>(`/tasks/${id}`) });
  const [note, setNote] = useState("");
  const t = q.data;
  if (!t) return <ListSkeleton rows={3} />;
  return (
    <div className="cx-stack">
      <div className="cx-toolbar"><TagBadge tag={t.tag} /><Badge>{Math.round(t.confidence * 100)}% sure</Badge></div>
      {t.quote ? <blockquote className="cx-quote">&ldquo;{t.quote}&rdquo;<br /><span className="cx-mini">From {t.meeting_title || "a meeting"}</span></blockquote> : null}
      {canWrite && t.status === "proposed" ? <div className="cx-card__acts"><Button variant="primary" onClick={async () => { await onApprove(); }}>Approve</Button><Button onClick={async () => { await onReject(); }}>Reject</Button></div> : null}
      {canWrite ? (
        <>
          <label className="sx-label" htmlFor="owner-sel">Owner</label>
          <select id="owner-sel" className="cx-select" value={t.owner_id ?? ""} onChange={async (e) => { await post(`/tasks/${id}/reassign`, { owner_id: Number(e.target.value) }); onChange(); notify.success("Owner changed"); }}>
            <option value="" disabled>Choose an owner</option>{owners.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <Textarea label="Add an update" value={note} onChange={(e) => setNote(e.target.value)} />
          <Button disabled={!note.trim()} disabledReason="Write the update first" onClick={async () => { await post(`/tasks/${id}/update`, { note }); setNote(""); onChange(); notify.success("Update added"); }}>Add update</Button>
        </>
      ) : null}
      <h3 className="sx-label">History</h3>
      <ul className="cx-list">{(t.events ?? []).map((e) => <li key={e.id} className="cx-item"><span className="cx-item__top"><strong>{e.kind.replace("_", " ")}</strong><span className="cx-mini">{e.at.slice(0, 10)}</span></span><span className="cx-item__line">{e.actor}{e.note ? `: ${e.note}` : ""}</span></li>)}</ul>
    </div>
  );
}
