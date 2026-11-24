/** Plain words for things the server names with codes, and the one sentence a job run reports. */

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export interface CycleResult {
  read?: { proposed_tasks?: number; proposed_decisions?: number; processes?: number; reminders?: number };
  review?: { built?: number };
}

/** What "Run now" did, from the numbers the server returned, so a tick never says more than happened. */
export function cycleMessage(r: CycleResult): string {
  const a = r.read ?? {};
  const tasks = a.proposed_tasks ?? 0;
  const decisions = a.proposed_decisions ?? 0;
  const parts = [
    tasks || decisions ? `read new transcripts: ${plural(tasks, "task", "tasks")} and ${plural(decisions, "decision", "decisions")} proposed` : "no new transcripts to read",
    `${plural(a.reminders ?? 0, "reminder draft", "reminder drafts")} added`,
    `${plural(a.processes ?? 0, "recurring process", "recurring processes")} checked`,
  ];
  if (r.review?.built) parts.push(`${plural(r.review.built, "weekly review", "weekly reviews")} built`);
  return `Ran every job: ${parts.join(", ")}.`;
}

export const AUDIT_ACTION: Record<string, string> = {
  "task.approve": "Task approved", "task.reject": "Task rejected", "task.create": "Task added by hand", "task.undo": "Last task change undone", "task.reassign": "Task owner changed",
  "task.done": "Task marked done", "task.blocked": "Task marked blocked", "task.open": "Task reopened", "task.in_progress": "Task started",
  "decision.confirm": "Decision confirmed", "decision.reject": "Decision rejected", "meeting.import": "Transcript imported", "meeting.extract": "Transcript read again",
  "review.generate": "Weekly review built", "sops.refresh": "Recurring work looked for again", "source.sync": "Source read again", "source.retag": "Who may see a source changed",
  "source.add": "Source added", "owner.add": "Person added", "settings.kill_switch": "Kill switch changed", "settings.force_draft": "Draft mode changed",
  "reminders.sent": "Reminders sent", "approval.requested": "Approval asked for", "approval.approved": "Approval granted", "approval.rejected": "Approval refused",
};
/** "task.approve" becomes "Task approved"; a code not in the list is still made readable. */
export const auditAction = (a: string): string => AUDIT_ACTION[a] ?? a.replace(/[._]/g, " ").replace(/^./, (c) => c.toUpperCase());
/** "task:37" becomes "Task 37". */
export const auditTarget = (t: string | null): string => (t ? t.replace(/_/g, " ").replace(":", " ").replace(/^./, (c) => c.toUpperCase()) : "");

/** A passage is shown without the markdown marks of the document it came from. */
export const plainPassage = (p: string): string => p.replace(/^\s*#{1,6}\s+/gm, "").replace(/\s+/g, " ").trim();
