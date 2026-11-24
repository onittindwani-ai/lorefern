"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ConnectionWizard, Dialog, EmptyState, Field, notify, type WizardStep } from "@sendora/ui-kit";
import { LoadError, ListSkeleton, PageHead } from "@/components/Parts";
import { TagBadge } from "@/components/TagBadge";
import { api, get, post } from "@/lib/api";
import { useRole } from "@/lib/hooks";
import type { Owner, SourceRow } from "@/lib/types";

const TAGS = ["company", "clients", "finance", "people", "leadership"];
const WHO: Record<string, string> = { company: "everyone", clients: "staff, finance, leadership", finance: "finance, leadership", people: "owner only", leadership: "leadership" };

export default function SourcesPage() {
  const qc = useQueryClient();
  const { owner: realOwner, preview } = useRole();
  const owner = realOwner && !preview;
  const q = useQuery({ queryKey: ["sources"], queryFn: () => get<SourceRow[]>("/sources") });
  const sync = useMutation({ mutationFn: (id: number) => post<Record<string, number>>(`/sources/${id}/sync`), onSuccess: (r) => { qc.invalidateQueries(); notify.success(`Read again: ${Object.entries(r).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ") || "nothing to read"}.`); }, onError: (e: Error) => notify.error("Could not read the source", e.message) });
  const retag = useMutation({ mutationFn: ({ id, tag }: { id: number; tag: string }) => api<{ changed: number }>(`/sources/${id}`, { method: "PATCH", json: { default_tag: tag } }), onSuccess: (r) => { qc.invalidateQueries(); notify.success(r.changed ? `Visibility changed. ${r.changed} ${r.changed === 1 ? "item was" : "items were"} re tagged.` : "Visibility saved. Nothing needed re tagging."); }, onError: (e: Error) => notify.error("Could not change visibility", e.message) });
  const people = useQuery({ queryKey: ["owners"], queryFn: () => get<Owner[]>("/owners") });
  const [addSrc, setAddSrc] = useState(false);
  const [kind, setKind] = useState("folder");
  const [sname, setSname] = useState("");
  const [suri, setSuri] = useState("");
  const [stag, setStag] = useState("company");
  const [pname, setPname] = useState("");
  const [prole, setProle] = useState("");
  const addSource = useMutation({ mutationFn: () => post("/sources", { kind, name: sname, uri: suri, default_tag: stag }), onSuccess: () => { qc.invalidateQueries(); notify.success("Source added. Press Read again to bring its documents in."); setAddSrc(false); setSname(""); setSuri(""); }, onError: (e: Error) => notify.error("Could not add the source", e.message) });
  const addPerson = useMutation({ mutationFn: () => post("/owners", { name: pname, role: prole }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["owners"] }); notify.success("Person added. They can now own tasks."); setPname(""); setProle(""); }, onError: (e: Error) => notify.error("Could not add the person", e.message) });
  const steps: WizardStep[] = [
    { id: "pick", title: "1. Choose where the knowledge lives", description: "A company folder on this machine, a Drive or Notion workspace, a Slack export, or meeting transcripts from a recorder.", status: q.data?.length ? "ok" : "todo" },
    { id: "tag", title: "2. Choose who may see it", description: "Every source has a visibility tag. A restricted source fixes the tag of every document in it. Source permissions are not copied from Drive or Notion.", status: q.data?.length ? "ok" : "todo" },
    { id: "read", title: "3. Read it into the index", description: "Reading takes a few seconds for a folder. Documents are split into passages and indexed with their tag.", status: q.data?.some((s) => s.documents > 0) ? "ok" : "todo" },
  ];
  return (
    <div className="cx-page">
      <PageHead title="Sources" sub="Where Lorefern reads from, who may see each source, and whether its index is current. Visibility is set here by tag. Lorefern does not copy the permissions of Drive, Notion or Slack." actions={owner ? <Button variant="primary" feedback={false} onClick={() => setAddSrc(true)}>Add a source</Button> : null} />
      <Card title="Set up"><ConnectionWizard steps={steps} /></Card>
      {q.isError ? <LoadError error={q.error} onRetry={() => q.refetch()} what="sources" /> : !q.data ? <ListSkeleton /> : q.data.length === 0 ? <EmptyState title="No sources visible" body="Nothing you may see has been connected yet." /> : (
        <div className="cx-cols">{q.data.map((s) => (
          <Card key={s.id} title={s.name}>
            <div className="cx-stack">
              <div className="cx-toolbar"><Badge>{s.kind}</Badge><TagBadge tag={s.default_tag} /><Badge tone={s.status === "ready" ? "success" : "warning"}>{s.status}</Badge></div>
              <p className="cx-mini">{s.documents} documents · last read {s.last_synced_at?.slice(0, 10) ?? "never"} · visible to {WHO[s.default_tag] ?? ""}</p>
              {s.error ? <p role="alert">{s.error}</p> : null}
              {owner ? (
                <div className="cx-toolbar">
                  <select className="cx-select" aria-label={`Visibility of ${s.name}`} value={s.default_tag} onChange={(e) => retag.mutate({ id: s.id, tag: e.target.value })}>{TAGS.map((t) => <option key={t} value={t}>{t}</option>)}</select>
                  <Button onClick={async () => { await sync.mutateAsync(s.id); }}>Read again</Button>
                </div>
              ) : null}
            </div>
          </Card>))}</div>
      )}
      <Card title="People who can own work">
        <div className="cx-stack">
          <p className="cx-mini">Task owners must come from this list, so a name spoken in a meeting can be matched to a person.</p>
          <div className="cx-toolbar" aria-label="People">{(people.data ?? []).map((p) => <span key={p.id} className="cx-chip" title={p.role}>{p.name}</span>)}</div>
          {owner ? (
            <div className="cx-toolbar">
              <Field label="Name" value={pname} onChange={setPname} maxLength={120} />
              <Field label="Role (optional)" value={prole} onChange={setProle} maxLength={120} />
              <Button disabled={pname.trim().length < 2} disabledReason="Type a name first" onClick={async () => { await addPerson.mutateAsync(); }}>Add person</Button>
            </div>
          ) : null}
        </div>
      </Card>
      <Dialog open={addSrc} onOpenChange={setAddSrc} title="Add a source" description="A folder or a Slack export is a path inside the folder set in KNOWLEDGE_DIR. Drive and Notion need their token set first (doc 04)."
        actions={<><Button variant="ghost" feedback={false} onClick={() => setAddSrc(false)}>Cancel</Button><Button variant="primary" disabled={sname.trim().length < 2} disabledReason="Give the source a name" onClick={async () => { await addSource.mutateAsync(); }}>Add</Button></>}>
        <div className="cx-stack">
          <label className="sx-label" htmlFor="src-kind">Kind</label>
          <select id="src-kind" className="cx-select" value={kind} onChange={(e) => setKind(e.target.value)}>{["folder", "slack", "drive", "notion"].map((k) => <option key={k} value={k}>{k}</option>)}</select>
          <Field label="Name" value={sname} onChange={setSname} maxLength={120} />
          <Field label="Path inside KNOWLEDGE_DIR (folder or Slack export)" value={suri} onChange={setSuri} hint="Leave empty for the whole folder" />
          <label className="sx-label" htmlFor="src-tag">Who may see it</label>
          <select id="src-tag" className="cx-select" value={stag} onChange={(e) => setStag(e.target.value)}>{TAGS.map((t) => <option key={t} value={t}>{t}: {WHO[t]}</option>)}</select>
        </div>
      </Dialog>
    </div>
  );
}
