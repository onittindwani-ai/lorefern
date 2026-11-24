"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, EmptyState, Stat } from "@sendora/ui-kit";
import { AnswerView, AskBox, SUGGESTIONS, useAsk } from "@/components/AskPanel";
import { PageHead } from "@/components/Parts";
import { get } from "@/lib/api";
import type { Overview } from "@/lib/types";

export default function AskPage() {
  const ask = useAsk();
  const [last, setLast] = useState("");
  const o = useQuery({ queryKey: ["overview-ask"], queryFn: () => get<Overview>("/overview") });
  const go = (q: string) => { setLast(q); ask.mutate(q); };
  return (
    <div className="cx-page">
      <PageHead title="Ask" sub="Ask a question in plain words. Lorefern answers from the company documents you may see, shows the exact passage, and says so when it cannot find an answer." />
      <div className="cx-two">
        <div className="cx-stack">
          <Card><div className="cx-ask">
            <AskBox busy={ask.isPending} onAsk={go} />
            <div className="cx-toolbar" aria-label="Example questions">{SUGGESTIONS.map((s) => <button key={s} type="button" className="cx-chip" onClick={() => go(s)}>{s}</button>)}</div>
          </div></Card>
          {ask.isError ? <Card><p role="alert">The question could not be answered: {(ask.error as Error).message}</p></Card> : null}
          {ask.data ? <Card title={last}><AnswerView a={ask.data} /></Card> : !ask.isPending ? <EmptyState title="Nothing asked yet" body="Try one of the example questions above, or press Cmd K (Ctrl K on Windows) from any page." /> : <Card><p aria-busy="true">Searching the documents...</p></Card>}
        </div>
        <div className="cx-stack">
          <div className="cx-stats">
            <Stat label="Documents" value={o.data?.documents ?? 0} />
            <Stat label="Open tasks" value={o.data?.open_tasks ?? 0} />
            <Stat label="Stuck" value={o.data?.stuck ?? 0} />
            <Stat label="Decisions" value={o.data?.decisions ?? 0} />
          </div>
          <Card title="What to know"><p className="cx-mini">Lorefern reads only what you are allowed to see. A question about something outside your access gets the same answer as a question about something that does not exist. Source permissions from Drive, Notion or Slack are not copied; visibility here is set by tag on the Sources page.</p></Card>
        </div>
      </div>
    </div>
  );
}
