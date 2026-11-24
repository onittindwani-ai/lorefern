/** The owner can preview the app as a narrower audience. The choice lives in this browser tab only and is added to every call as ?as=. */
const KEY = "cx-view-as";
export function getViewAs(): string {
  try { return typeof window === "undefined" ? "" : window.sessionStorage.getItem(KEY) ?? ""; } catch { return ""; }
}
export function setViewAs(v: string) {
  try { if (v) window.sessionStorage.setItem(KEY, v); else window.sessionStorage.removeItem(KEY); } catch { /* storage can be blocked, the preview then simply does not stick */ }
}
