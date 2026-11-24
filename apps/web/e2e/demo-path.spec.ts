import { expect, test } from "@playwright/test";
import { call, login, resetDemo } from "./helpers";

/** The path a new owner takes on day one, with the demo data and no accounts. */
test("demo path: ask, approve with undo, see the map, build a review, and check the visibility boundary", async ({ page, browser }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  await page.goto("/");

  // 1. The ask bar opens from the keyboard and answers with a source.
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Ask anything" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Ask anything about the company").fill("Did Larkspur Group make an offer to buy the company?");
  await dialog.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(dialog.getByRole("article").first()).toBeVisible();
  await dialog.getByRole("button", { name: "Open in source" }).first().click();
  await expect(page.locator("mark.cx-mark")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");

  // 2. Run the jobs, then approve a proposed task and undo it.
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText("Ran every job")).toBeVisible();
  await page.goto("/tasks");
  const proposed = page.locator('section[aria-label="Proposed"] .cx-card');
  await expect(proposed.first()).toBeVisible();
  const proposedBefore = await proposed.count();
  await proposed.first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/^Approved:/)).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(proposed).toHaveCount(proposedBefore);

  // 3. A meeting shows its action items marked inside the transcript.
  await page.goto("/meetings");
  await page.getByRole("link").filter({ hasText: "to approve" }).first().click();
  await expect(page.locator("button.cx-hl").first()).toBeVisible();

  // 4. The SOP map shows a gap with its evidence.
  await page.goto("/sops");
  await page.locator('button.cx-tile[data-cov="gap"]').first().click();
  await expect(page.getByText("Evidence")).toBeVisible();

  // 5. The weekly review builds, and every claim is linked.
  await page.goto("/review");
  await page.getByRole("button", { name: "Generate now" }).first().click();
  await expect(page.locator("article.cx-doc h2").first()).toBeVisible();
  await expect(page.locator("article.cx-doc")).toContainText(/\d+ of \d+ claims link to a source/);

  // 6. Staff cannot reach restricted material, and cannot tell it exists.
  const ctx = await browser.newContext({ baseURL: "http://localhost:3000" });
  const staff = await ctx.newPage();
  await login(staff, "staff@example.test");
  const ask = await call(staff, "/ask", { question: "What did the Larkspur Group propose?" });
  const body = await ask.json();
  expect(body.outcome).toBe("not_found");
  expect(body.citations).toHaveLength(0);
  expect((await staff.request.get("/api/company-folder")).status()).toBe(403);
  await expect(staff.getByRole("link", { name: "Audit log" })).toHaveCount(0);
  await ctx.close();

  // 7. The person who asks for a send cannot approve their own request.
  const plan = await call(page, "/reminders/plan");
  expect(plan.ok()).toBeTruthy();
  const reminders = (await (await page.request.get("/api/reminders")).json()) as { id: number }[];
  if (reminders.length) {
    const req = await call(page, "/reminders/request-send", { ids: reminders.slice(0, 1).map((r) => r.id) });
    expect(req.ok()).toBeTruthy();
    const pending = ((await (await page.request.get("/api/approvals")).json()) as { id: number; status: string }[]).filter((a) => a.status === "pending");
    const own = await call(page, `/approvals/${pending[0]!.id}/decide`, { approve: true });
    expect(own.status()).toBe(409);
  }
});
