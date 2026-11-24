"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { get } from "./api";
import { getViewAs } from "./viewas";
import type { Me, Settings } from "./types";

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => get<Me>("/auth/me"), staleTime: 60_000 });
/** The audience the owner is previewing. Read after the page has loaded, so the first paint matches what the server sent. */
export function useViewAs(): string {
  const [v, setV] = useState("");
  useEffect(() => setV(getViewAs()), []);
  return v;
}
/** What the signed in person may do. The server refuses the rest; the screens hide or disable it first so nothing answers 403. */
export function useRole() {
  const me = useMe();
  const preview = useViewAs();
  const real = me.data?.audience;
  const effective = preview || real;
  return {
    known: !!real, real, effective, preview,
    owner: real === "owner",
    canWrite: !!me.data?.can_write && !preview,
    leader: effective === "owner" || effective === "leadership",
  };
}
export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/settings") });

/** Listen to the live event stream. Any event refreshes the numbers on screen, at most once a second. */
export function useLiveRefresh() {
  const qc = useQueryClient();
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const es = new EventSource("/api/events/stream");
    es.onmessage = () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      }, 1000);
    };
    return () => {
      es.close();
      if (timer) clearTimeout(timer);
    };
  }, [qc]);
}
