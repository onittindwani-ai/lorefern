"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyEvent } from "react";
import { Dialog, Kbd } from "@sendora/ui-kit";
import { AnswerView, AskBox, SUGGESTIONS, useAsk } from "./AskPanel";

export interface GoItem { id: string; label: string }
export interface CommandItem { id: string; label: string; onSelect: () => void }

/** The signature: Cmd or Ctrl K opens an ask bar on every screen. Empty it lists places to go and things to do; with a question it answers with sources. Up and Down move through the list, Enter opens the one in focus. */
export function AskBar({ open, onOpenChange, go, commands = [] }: { open: boolean; onOpenChange: (o: boolean) => void; go: GoItem[]; commands?: CommandItem[] }) {
  const router = useRouter();
  const ask = useAsk();
  const [asked, setAsked] = useState(false);
  const list = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); e.stopPropagation(); onOpenChange(true); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onOpenChange]);
  useEffect(() => { if (!open) { ask.reset(); setAsked(false); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const items = () => Array.from(list.current?.querySelectorAll<HTMLButtonElement>("button[data-item]") ?? []);
  /** Down from the question box enters the list, then Up and Down move inside it. Up from the first item returns to the box. */
  const move = (e: ReactKeyEvent<HTMLElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const all = items();
    if (!all.length) return;
    const at = all.findIndex((b) => b === document.activeElement);
    if (at === -1 && e.key === "ArrowDown") { e.preventDefault(); all[0]?.focus(); return; }
    if (at === -1) return;
    e.preventDefault();
    if (e.key === "ArrowUp" && at === 0) { (document.getElementById("cx-ask-input") ?? document.querySelector<HTMLInputElement>("[role=dialog] input"))?.focus(); return; }
    all[Math.max(0, Math.min(all.length - 1, at + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
  };
  const row = (id: string, label: string, hint: string, onSelect: () => void) => (
    <li key={id}><button type="button" data-item onClick={onSelect}>{label}<Kbd>{hint}</Kbd></button></li>
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Ask anything" description="Answers come only from documents you are allowed to see, and every sentence shows its source. Press Down to reach the places and actions below.">
      <div onKeyDown={move}>
        <AskBox autoFocus busy={ask.isPending} onAsk={(q) => { setAsked(true); ask.mutate(q); }} />
        <div className="cx-askbar-results" ref={list}>
          {ask.isError ? <p role="alert">The question could not be answered: {(ask.error as Error).message}</p> : null}
          {ask.data ? <AnswerView a={ask.data} /> : null}
          {!asked ? (
            <>
              <div className="cx-stack"><span className="cx-mini">Try one of these</span>
                <div className="cx-toolbar">{SUGGESTIONS.slice(0, 3).map((s) => <button key={s} type="button" className="cx-chip" onClick={() => { setAsked(true); ask.mutate(s); }}>{s}</button>)}</div></div>
              <ul className="cx-nav" aria-label="Go to">
                {go.map((g) => row(`go-${g.id}`, g.label, "Go", () => { onOpenChange(false); router.push(g.id); }))}
              </ul>
              {commands.length ? <ul className="cx-nav" aria-label="Actions">{commands.map((c) => row(c.id, c.label, "Do", () => { onOpenChange(false); c.onSelect(); }))}</ul> : null}
            </>
          ) : null}
        </div>
      </div>
    </Dialog>
  );
}
