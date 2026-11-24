"use client";
import { ExternalLink } from "lucide-react";
import { Button } from "@sendora/ui-kit";
import { plainPassage } from "@/lib/labels";
import type { Citation } from "@/lib/types";

/** One cited passage: where it comes from, the exact words, and a way to open the document at that spot. */
export function CitationCard({ c, index, onOpen }: { c: Citation; index: number; onOpen: (c: Citation) => void }) {
  return (
    <article className="cx-cite" aria-label={`Source ${index}: ${c.title}`}>
      <div className="cx-cite__head">
        <span className="cx-cite__title">{index}. {c.title}</span>
        <span className="cx-mini">{c.section || c.doc_type}</span>
      </div>
      <p className="cx-cite__passage">&ldquo;{plainPassage(c.passage)}&rdquo;</p>
      <div className="cx-toolbar" style={{ justifyContent: "space-between" }}>
        <span className="cx-mini">{c.owner ? `Owner ${c.owner}` : "No owner named"} · updated {c.updated_on || "unknown"}</span>
        <Button size="sm" variant="ghost" feedback={false} onClick={() => onOpen(c)}><ExternalLink size={14} aria-hidden />Open in source</Button>
      </div>
    </article>
  );
}
