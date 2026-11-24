"use client";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Sheet, Skeleton } from "@sendora/ui-kit";
import { get } from "@/lib/api";
import { TagBadge } from "./TagBadge";
import type { DocRow } from "@/lib/types";

/** The document as it is stored, with the passage the answer used marked. Opens from any citation card. */
export function SourceViewer({ docId, start, end, onClose }: { docId: number | null; start: number; end: number; onClose: () => void }) {
  const q = useQuery({ queryKey: ["document", docId], queryFn: () => get<DocRow>(`/documents/${docId}`), enabled: docId !== null });
  const mark = useRef<HTMLElement | null>(null);
  useEffect(() => { mark.current?.scrollIntoView({ block: "center" }); }, [q.data, start]);
  const text = q.data?.text ?? "";
  const ok = end > start && end <= text.length;
  return (
    <Sheet open={docId !== null} onOpenChange={(o) => !o && onClose()} title={q.data?.title ?? "Source"} description={q.data ? `${q.data.doc_type} · owner ${q.data.owner || "none"} · updated ${q.data.updated_on ?? "unknown"}` : "Opening the document"}>
      {q.isError ? <p role="alert">This document is not available to you.</p> : !q.data ? <Skeleton height={240} /> : (
        <div className="cx-source" tabIndex={0} aria-label="Document text">
          <div className="cx-source__head"><span className="cx-mini">{q.data.path}</span><TagBadge tag={q.data.tag} /></div>
          <div className="cx-source__body">
            {ok ? <>{text.slice(0, start)}<mark className="cx-mark" ref={(n) => { mark.current = n; }}>{text.slice(start, end)}</mark>{text.slice(end)}</> : text}
          </div>
        </div>
      )}
    </Sheet>
  );
}
