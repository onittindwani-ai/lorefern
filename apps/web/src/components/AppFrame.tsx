"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenCheck, CalendarClock, CheckSquare, ClipboardCheck, FileText, FolderTree, Gavel, Layers, LogOut, MessageCircleQuestion, Pause, Plug, ShieldCheck } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell, Badge, Button, ConfirmDialog, notify, useTheme } from "@sendora/ui-kit";
import { api, get, post } from "@/lib/api";
import { useLiveRefresh, useMe, useRole, useSettings } from "@/lib/hooks";
import { getViewAs, setViewAs } from "@/lib/viewas";
import { cycleMessage } from "@/lib/labels";
import type { Overview } from "@/lib/types";
import { AskBar, type CommandItem } from "./AskBar";

const NAV = [
  { id: "/", label: "Ask", icon: MessageCircleQuestion },
  { id: "/tasks", label: "Tasks", icon: CheckSquare },
  { id: "/meetings", label: "Meetings", icon: CalendarClock },
  { id: "/sops", label: "SOP map", icon: Layers },
  { id: "/review", label: "Weekly review", icon: FileText },
  { id: "/decisions", label: "Decisions", icon: Gavel },
  { id: "/sources", label: "Sources", icon: BookOpenCheck },
  { id: "/folder", label: "Company folder", icon: FolderTree },
  { id: "/integrations", label: "Integrations", icon: Plug },
  { id: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { id: "/audit", label: "Audit log", icon: ShieldCheck },
];
const LEADER_ONLY = new Set(["/folder", "/approvals", "/audit"]);

export function AppFrame({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const me = useMe();
  const settings = useSettings();
  const overview = useQuery({ queryKey: ["overview", getViewAs()], queryFn: () => get<Overview>("/overview") });
  const killOn = !!settings.data?.kill_switch;
  const [askOpen, setAskOpen] = useState(false);
  const [confirmKill, setConfirmKill] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const { owner: isOwner, canWrite, leader, preview } = useRole();
  const { setChoice, resolved } = useTheme();
  useLiveRefresh();
  // A file dropped on the page must not make the browser open it and leave the app. Lorefern reads pasted text, so a dropped file is ignored.
  useEffect(() => {
    const stop = (e: DragEvent) => { if (e.dataTransfer?.types.includes("Files")) e.preventDefault(); };
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => { window.removeEventListener("dragover", stop); window.removeEventListener("drop", stop); };
  }, []);

  const real = me.data?.audience ?? "staff";
  const nav = NAV.filter((n) => !LEADER_ONLY.has(n.id) || leader);
  const active = nav.find((n) => (n.id === "/" ? path === "/" : path.startsWith(n.id)))?.id ?? "/";
  const demo = me.data?.demo_mode ?? false;
  const refresh = () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });

  const run = useMutation({
    mutationFn: () => post<Parameters<typeof cycleMessage>[0]>("/demo/tick"),
    onSuccess: (r) => { notify.success(cycleMessage(r)); refresh(); },
    onError: (e: Error) => notify.error("The run failed", e.message),
  });
  const advance = useMutation({ mutationFn: (hours: number) => post<{ now: string }>("/demo/advance", { hours }), onSuccess: (r) => { notify.info(`The demo clock now reads ${(r.now ?? "").slice(0, 10)}.`); refresh(); }, onError: (e: Error) => notify.error("Could not move the clock", e.message) });
  const toggleKill = useMutation({
    mutationFn: (on: boolean) => post("/settings", { kill_switch: on }),
    onSuccess: (_r, on) => { refresh(); qc.invalidateQueries({ queryKey: ["settings"] }); notify.info(on ? "Kill switch on. Nothing is changed or sent until you turn it off." : "Kill switch off. Work can carry on."); },
    onError: (e: Error) => notify.error("Could not change the kill switch", e.message),
  });
  const reset = useMutation({ mutationFn: () => post("/demo/reset"), onSuccess: () => { notify.success("Demo data reset."); refresh(); }, onError: (e: Error) => notify.error("Could not reset", e.message) });

  const goItems = useMemo(() => nav.map((n) => ({ id: n.id, label: `Go to ${n.label}` })), [nav.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const signOut = async () => { await api("/session", { method: "DELETE" }).catch(() => null); setViewAs(""); window.location.assign("/login"); };
  const demoOn = (me.data?.demo_mode ?? false) && !preview;
  const commands: CommandItem[] = [
    ...(demoOn && canWrite && !killOn ? [{ id: "run", label: "Run every job now", onSelect: () => run.mutate() }, { id: "adv", label: "Move the demo clock forward one day", onSelect: () => advance.mutate(24) }] : []),
    ...(isOwner && !preview ? [killOn ? { id: "kill", label: "Turn the kill switch off", onSelect: () => toggleKill.mutate(false) } : { id: "kill", label: "Pause everything (kill switch)", onSelect: () => setConfirmKill(true) }] : []),
    ...(demoOn && isOwner ? [{ id: "reset", label: "Reset the demo data", onSelect: () => setConfirmReset(true) }] : []),
    { id: "theme", label: resolved === "dark" ? "Switch to light theme" : "Switch to dark theme", onSelect: () => setChoice(resolved === "dark" ? "light" : "dark") },
    { id: "signout", label: "Sign out", onSelect: () => void signOut() },
  ];

  const changePreview = (v: string) => { setViewAs(v); qc.clear(); window.location.reload(); };
  const s = settings.data;
  const o = overview.data;
  return (
    <>
      {s?.kill_switch ? (
        <div className="cx-banner cx-banner--danger" role="status"><strong>Kill switch is on.</strong> <span className="cx-hide-sm cx-grow">Nothing is sent and nothing is changed until it is turned off.</span><span className="cx-grow show-sm-only" /> <Button size="sm" variant="ghost" disabled={!isOwner || !!preview} disabledReason={preview ? "Go back to the owner view first" : "Only the owner can turn it off"} onClick={async () => { await toggleKill.mutateAsync(false); }}>Turn it off</Button></div>
      ) : preview ? (
        <div className="cx-banner" role="status"><strong>Previewing as {preview}.</strong> <span className="cx-hide-sm cx-grow">You see only what that audience sees. Nothing can be changed in a preview.</span> <Button size="sm" onClick={async () => changePreview("")}>Back to owner view</Button></div>
      ) : s && demo ? (
        <div className="cx-banner cx-banner--info" role="status"><strong>Demo mode.</strong> <span className="cx-grow cx-hide-sm">Sample company, sample people. A rules based stand in reads the text, not a language model.</span><span className="cx-grow show-sm-only" />
          <Button size="sm" variant="primary" disabled={!canWrite} disabledReason="Your sign in can read but not change things" onClick={async () => { await run.mutateAsync(); }}>Run now</Button>
          <Button size="sm" disabled={!canWrite} disabledReason="Your sign in can read but not change things" onClick={async () => { await advance.mutateAsync(24); }}>+1 day</Button></div>
      ) : s?.effective_mode === "draft" ? (
        <div className="cx-banner" role="status"><strong>Draft mode.</strong> <span className="cx-hide-sm">Reminders are drafted and never sent. Proposed tasks wait for a person.</span></div>
      ) : s ? (
        <div className="cx-banner cx-banner--live" role="status"><strong>Live.</strong> <span className="cx-hide-sm">Reminders go out only after another person approves them.</span></div>
      ) : (
        <div className="cx-banner cx-banner--info" role="status">Checking the mode...</div>
      )}
      <AppShell
        productName="Lorefern"
        nav={nav.map((n) => ({ ...n, count: n.id === "/tasks" ? o?.proposed || undefined : n.id === "/sops" ? o?.processes_gap || undefined : n.id === "/decisions" ? o?.proposed_decisions || undefined : n.id === "/approvals" ? o?.pending_approvals || undefined : undefined }))}
        activeId={active}
        onNavigate={(id) => router.push(id)}
        onOpenPalette={() => setAskOpen(true)}
        breadcrumbs={["Lorefern", nav.find((n) => n.id === active)?.label ?? ""]}
        topRight={
          <>
            {isOwner && !preview ? (
              <select className="cx-select cx-hide-sm" aria-label="Preview as" value="" onChange={(e) => e.target.value && changePreview(e.target.value)}>
                <option value="">View as...</option><option value="leadership">leadership</option><option value="finance">finance</option><option value="staff">staff</option>
              </select>
            ) : null}
            {isOwner && !preview ? <Button size="sm" variant="ghost" feedback={false} className="cx-iconify" aria-label={killOn ? "Turn the kill switch off" : "Pause all"} onClick={() => (killOn ? toggleKill.mutate(false) : setConfirmKill(true))}><Pause size={14} aria-hidden /><span className="cx-hide-sm">{killOn ? "Turn it off" : "Pause all"}</span></Button> : null}
            {me.data ? <span className="cx-hide-sm"><Badge tone="accent">{preview || real}</Badge></span> : null}
            <Button size="sm" variant="ghost" feedback={false} className="cx-iconify" aria-label="Sign out" onClick={() => void signOut()}><LogOut size={14} aria-hidden /><span className="cx-hide-sm">Sign out</span></Button>
          </>
        }
      >
        {children}
      </AppShell>
      <AskBar open={askOpen} onOpenChange={setAskOpen} go={goItems} commands={commands} />
      <ConfirmDialog open={confirmKill} onOpenChange={setConfirmKill} title="Pause everything?" description="The kill switch stops every send and every change at once, including the background jobs. You can turn it off again from the banner or the top bar." confirmLabel="Pause all" destructive onConfirm={() => void toggleKill.mutateAsync(true)} />
      <ConfirmDialog open={confirmReset} onOpenChange={setConfirmReset} title="Reset the demo?" description="This puts the sample seed data back and clears everything you did in the demo." confirmLabel="Reset" destructive onConfirm={() => void reset.mutateAsync()} />
    </>
  );
}
