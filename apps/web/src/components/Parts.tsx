"use client";
import { forwardRef, type ReactNode, type TextareaHTMLAttributes } from "react";
import { EmptyState, ErrorState, Skeleton } from "@sendora/ui-kit";
import { ApiError } from "@/lib/api";
import { useRole } from "@/lib/hooks";

export function PageHead({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div className="cx-head">
      <div>
        <h1 className="cx-title">{title}</h1>
        {sub ? <p className="cx-sub">{sub}</p> : null}
      </div>
      {actions ? <div className="sx-row">{actions}</div> : null}
    </div>
  );
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string | null }>(function Textarea({ label, hint, error, id, ...rest }, ref) {
  const tid = id ?? `ta-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="sx-field">
      <label className="sx-label" htmlFor={tid}>{label}</label>
      <textarea ref={ref} id={tid} className="cx-textarea" aria-invalid={error ? true : undefined} aria-describedby={error ? `${tid}-e` : hint ? `${tid}-h` : undefined} {...rest} />
      {error ? <span id={`${tid}-e`} className="sx-field__error" role="alert">{error}</span> : hint ? <span id={`${tid}-h`} className="sx-field__hint">{hint}</span> : null}
    </div>
  );
}) ;

export function LoadError({ error, onRetry, what }: { error: unknown; onRetry: () => void; what: string }) {
  const msg = error instanceof ApiError ? error.message : "Something went wrong.";
  return <ErrorState title={`Could not load ${what}`} whatHappened={msg} howToFix="Check that the API is running and you are signed in, then try again." onRetry={onRetry} />;
}

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: "grid", gap: 13, padding: 8 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} style={{ display: "grid", gap: 8 }}><Skeleton height={16} width="45%" /><Skeleton height={13} width="80%" /></div>)}
    </div>
  );
}

/** Pages for the owner and leadership. Anyone else (and a preview of a narrower audience) gets a plain note and no request is sent, so nothing answers 403. */
export function LeaderGate({ title, children }: { title: string; children: ReactNode }) {
  const { known, leader } = useRole();
  if (!known) return <div className="cx-page"><PageHead title={title} /><ListSkeleton rows={4} /></div>;
  if (!leader) return <div className="cx-page"><PageHead title={title} /><EmptyState title="This page is for the owner and leadership" body="Your audience does not see it. If you are previewing a narrower audience, use Back to owner view in the banner." /></div>;
  return <>{children}</>;
}
