import { expect, test, type Browser, type Page } from "@playwright/test";
import { call, login, resetDemo, watch } from "./helpers";

const BASE = () => `http://localhost:${process.env.WEB_PORT ?? "3000"}`;
async function as(browser: Browser, email: string, width = 1440, height = 900) {
  const ctx = await browser.newContext({ baseURL: BASE(), viewport: { width, height } });
  const page = await ctx.newPage();
  const errors = watch(page);
  await login(page, email);
  return { ctx, page, errors };
}
const get = async (page: Page, path: string) => (await page.request.get(`/api${path}`)).json();

test("count up: a number that ends whole never shows decimals on the way, after load and after a reset", async ({ page }) => {
  await login(page);
  const sample = async () => page.evaluate(() => new Promise<string[]>((done) => {
    const seen: string[] = [];
    const t = setInterval(() => { const el = document.querySelector(".cx-stats"); if (el) seen.push((el as HTMLElement).innerText); }, 30);
    setTimeout(() => { clearInterval(t); done(seen); }, 2200);
  }));
  await page.goto("/");
  const first = await sample();
  expect(first.length).toBeGreaterThan(20);
  await resetDemo(page);
  await page.reload();
  const second = await sample();
  for (const text of [...first, ...second]) expect(text, text).not.toMatch(/\d\.\d/);
  expect(new Set(first.concat(second)).size).toBeGreaterThan(2);
});

test("the kill switch says what it does, can be turned off from the top bar and the palette, and stops changes", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "Pause all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Pause all" }).click();
  await expect(page.locator(".cx-banner")).toContainText("Nothing is sent and nothing is changed");
  await expect(page.getByRole("button", { name: "Turn the kill switch off" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause all" })).toHaveCount(0);
  const proposed = (await get(page, "/tasks?status=proposed"))[0];
  const r = await call(page, `/tasks/${proposed.id}/approve`);
  expect(r.status()).toBe(409);
  expect((await r.json()).error.message).toContain("kill switch is on");
  await page.keyboard.press("Control+k");
  await page.getByRole("dialog").getByRole("button", { name: /Turn the kill switch off/ }).click();
  await expect(page.locator(".cx-banner")).not.toContainText("Kill switch is on");
  expect((await call(page, `/tasks/${proposed.id}/approve`)).ok()).toBeTruthy();
});

for (const email of ["finance@example.test", "staff@example.test"]) {
  test(`a read only sign in (${email.split("@")[0]}) sees no write control that answers 403 and no leader page error`, async ({ browser }) => {
    const { ctx, page, errors } = await as(browser, email);
    await expect(page.getByRole("button", { name: "Run now" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "+1 day" })).toBeDisabled();
    await page.goto("/integrations");
    await expect(page.getByRole("button", { name: "Test the one in use" }).first()).toBeDisabled();
    for (const p of ["/folder", "/approvals", "/audit"]) {
      await page.goto(p);
      await expect(page.getByText("This page is for the owner and leadership")).toBeVisible();
    }
    await page.goto("/tasks");
    await expect(page.getByRole("button", { name: /Draft today|Ask to send/ })).toHaveCount(0);
    expect(errors.filter((e) => !/events\/stream/.test(e))).toEqual([]);
    await ctx.close();
  });
}

test("previewing a narrower audience hides the leader pages and does not break the first paint", async ({ page }) => {
  await login(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.evaluate(() => sessionStorage.setItem("cx-view-as", "staff"));
  await page.goto("/tasks");
  await expect(page.locator(".cx-banner")).toContainText("Previewing as staff");
  for (const n of ["Company folder", "Approvals", "Audit log"]) await expect(page.getByRole("button", { name: n })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Pause all" })).toHaveCount(0);
  await page.goto("/folder");
  await expect(page.getByText("This page is for the owner and leadership")).toBeVisible();
  await page.evaluate(() => sessionStorage.removeItem("cx-view-as"));
  expect(errors).toEqual([]);
});

test("on a 390 px phone Pause all and Sign out are reachable and work", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(page.getByRole("button", { name: "Pause all" })).toBeVisible();
  const box = await page.getByRole("button", { name: "Sign out" }).boundingBox();
  expect(box && box.width >= 36 && box.x + box.width <= 390).toBeTruthy();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
});

test("signing in returns to the page that was asked for, and ignores an address on another site", async ({ browser }) => {
  const ctx = await browser.newContext({ baseURL: BASE() });
  const page = await ctx.newPage();
  await page.goto("/tasks");
  await expect(page).toHaveURL(/\/login\?next=%2Ftasks/);
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password").fill("demo-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/tasks$/);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/login?next=//example.org");
  await page.getByLabel("Email").fill("owner@example.test");
  await page.getByLabel("Password").fill("demo-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Ask", exact: true })).toBeVisible();
  expect(new URL(page.url()).host).toBe(new URL(BASE()).host);
  await ctx.close();
});

test("the palette moves with the arrow keys and can reset the demo", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/");
  await page.keyboard.press("Control+k");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/tasks$/);
  const id = (await get(page, "/tasks?status=proposed"))[0].id;
  await call(page, `/tasks/${id}/approve`);
  await page.keyboard.press("Control+k");
  await page.getByRole("dialog").getByRole("button", { name: /Reset the demo data/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reset" }).click();
  await expect(page.getByText("Demo data reset.")).toBeVisible();
  await expect.poll(async () => (await get(page, "/tasks?status=proposed")).some((t: { id: number }) => t.id === id)).toBeTruthy();
});

test("Run now says what it did, and the reminder drafts can be asked for once", async ({ page, browser }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText(/Ran every job: no new transcripts to read, \d+ reminder drafts? added, \d+ recurring processes checked/)).toBeVisible();
  await expect(page.getByText(/Reminder drafts \(2\)/i)).toBeVisible();
  await page.getByRole("button", { name: "Ask to send 2" }).click();
  await expect(page.getByText("Sent for approval")).toBeVisible();
  await expect(page.getByRole("button", { name: /Ask to send/ })).toBeDisabled();
  await page.goto("/approvals");
  await expect(page.getByText("Send 2 task reminders")).toBeVisible();
  const lead = await as(browser, "approver@example.test");
  await lead.page.goto("/approvals");
  await lead.page.getByRole("button", { name: "Approve" }).first().click();
  await expect(lead.page.getByText("Approved.", { exact: true })).toBeVisible(); // the end to end run is in live mode, so the second person's yes goes through
  await expect(lead.page.getByText("Nothing waiting")).toBeVisible();
  await lead.ctx.close();
});

test("importing a transcript reads it at once, explains a bad date and refuses a repeat", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  await page.goto("/meetings");
  await page.getByRole("button", { name: "Import a transcript" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Title").fill("Board prep");
  await dialog.getByLabel("Meeting date (year-month-day)").fill("tomorrow");
  await dialog.getByLabel("Transcript").fill("Priya Nair: I will send the board report on Friday.\nLeo Fischer: We decided to move the review to Thursday.");
  await expect(dialog.getByText("Write the date as year-month-day")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Import" })).toBeDisabled();
  await dialog.getByLabel("Meeting date (year-month-day)").fill("2026-12-01");
  await dialog.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText(/Transcript imported and read: \d+ tasks? and \d+ decisions? wait/)).toBeVisible();
  await expect(page.getByRole("link").filter({ hasText: "Board prep" })).toContainText("to approve");
  await page.getByRole("button", { name: "Import a transcript" }).click();
  await dialog.getByLabel("Title").fill("Board prep");
  await dialog.getByLabel("Transcript").fill("Priya Nair: I will send the board report on Friday.\nLeo Fischer: We decided to move the review to Thursday.");
  await dialog.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText(/already imported/)).toBeVisible();
});

test("the audit log uses plain words, opens a detail sheet and says what the chain check found", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  const id = (await get(page, "/tasks?status=proposed"))[0].id;
  await call(page, `/tasks/${id}/approve`);
  await page.goto("/audit");
  await expect(page.getByText("Task approved").first()).toBeVisible();
  await expect(page.locator("main")).not.toContainText("task.approve");
  await page.getByRole("button", { name: "Open" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Entry number");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Check the chain" }).click();
  await expect(page.getByText("The audit log is intact")).toBeVisible();
});

test("a source set to another visibility and back gets every tag back, and the Slack source reads again", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  const tags = async () => { const d = await get(page, "/documents?limit=500"); return d.reduce((a: Record<string, number>, x: { tag: string }) => ({ ...a, [x.tag]: (a[x.tag] ?? 0) + 1 }), {}); };
  const before = await tags();
  await page.goto("/sources");
  const pick = page.getByLabel("Visibility of Company folder");
  await pick.selectOption("finance");
  await expect(page.getByText(/Visibility changed\. \d+ items were re tagged\./)).toBeVisible();
  expect(await tags()).not.toEqual(before);
  await pick.selectOption("company");
  await expect(page.getByText(/Visibility changed/).last()).toBeVisible();
  await expect.poll(tags).toEqual(before);
  await page.getByRole("button", { name: "Read again" }).nth(1).click();
  await expect(page.getByText(/^Read again: /)).toBeVisible();
});

test("an answer shows the passage without the markdown marks of its document, and a table that opens nothing does not say enter opens", async ({ page }) => {
  await login(page);
  await page.goto("/");
  await page.getByLabel("Ask anything about the company").first().fill("How are databases backed up?");
  await page.locator(".cx-askrow").first().getByRole("button", { name: "Ask", exact: true }).click();
  const quote = page.locator(".cx-cite__passage").first();
  await expect(quote).toContainText("Databases are backed up every night");
  await expect(quote).not.toContainText("#");
  await page.goto("/decisions");
  await expect(page.locator(".cx-noopen .sx-table__footer")).toBeVisible();
  expect(await page.locator(".cx-noopen .sx-table__footer > span:last-child").evaluate((e) => getComputedStyle(e, "::after").content)).toContain("j k move");
});

test("a meeting page opens for an owner and for a read only sign in, and its approve button undoes", async ({ page, browser }) => {
  await login(page);
  await resetDemo(page);
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  const proposed = (await get(page, "/tasks?status=proposed"))[0];
  await page.goto(`/meetings/${proposed.meeting_id}`);
  await expect(page.getByRole("button", { name: "Approve" }).first()).toBeVisible();
  const before = await page.getByRole("button", { name: "Approve" }).count();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(before);
  const staff = await as(browser, "staff@example.test");
  await staff.page.goto(`/meetings/${proposed.meeting_id}`);
  await expect(staff.page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(staff.page.getByRole("button", { name: "Approve" })).toHaveCount(0);
  expect(pageErrors).toEqual([]);
  await staff.ctx.close();
});

test("a file dropped on a page is ignored and the browser does not leave the app", async ({ page }) => {
  await login(page);
  await page.goto("/meetings");
  const prevented = await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(new File(["hello"], "notes.txt", { type: "text/plain" }));
    const over = new DragEvent("dragover", { dataTransfer: dt, bubbles: true, cancelable: true });
    document.body.dispatchEvent(over);
    const drop = new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true });
    document.body.dispatchEvent(drop);
    return over.defaultPrevented && drop.defaultPrevented;
  });
  expect(prevented).toBe(true);
  await expect(page).toHaveURL(/\/meetings$/);
});
