import type { ReactNode } from "react";

const HELP: Record<string, string> = {
  company: "Everyone in the company can see this",
  clients: "Staff, finance and leadership",
  finance: "Finance and leadership",
  people: "Owner only",
  leadership: "Leadership only",
};

export function TagBadge({ tag }: { tag: string }): ReactNode {
  return <span className="cx-tag" data-tag={tag} title={HELP[tag] ?? ""}>{tag}</span>;
}
