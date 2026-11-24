import { expect, type Page } from "@playwright/test";

export const PAGES = ["/", "/tasks", "/meetings", "/sops", "/review", "/decisions", "/sources", "/folder", "/integrations", "/approvals", "/audit"];

export function watch(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("response", (r) => r.status() >= 400 && errors.push(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`));
  return errors;
}

export async function login(page: Page, email = "owner@example.test") {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("demo-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Ask", exact: true })).toBeVisible();
}

export const call = (page: Page, path: string, json?: unknown) => page.request.post(`/api${path}`, { headers: { "x-lorefern": "1", "content-type": "application/json" }, data: json ?? {} });

export async function resetDemo(page: Page) {
  // A reset drops and recreates the tables. Let the page's own first requests finish, or one of them lands on a missing table and answers 500.
  await page.waitForLoadState("networkidle");
  const r = await call(page, "/demo/reset");
  expect(r.ok()).toBeTruthy();
}

export interface T { id: number; external_id: string; outcome: string; status: string; subject: string; flags: string[] }
export async function tickets(page: Page): Promise<T[]> {
  return (await (await page.request.get("/api/tickets?limit=500")).json()) as T[];
}
