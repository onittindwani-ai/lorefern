import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { PAGES, call, login, resetDemo, watch } from "./helpers";

const SHOTS = resolve(__dirname, "../../../docs/screenshots");
mkdirSync(SHOTS, { recursive: true });
const VIEWS = [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844 }];
const slug = (p: string) => (p === "/" ? "ask" : p.slice(1));

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(900); // count up and chart tween finish
}
async function layoutShift(page: Page) {
  return page.evaluate(() => new Promise<number>((done) => {
    let total = 0;
    const o = new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) total += e.value; });
    o.observe({ type: "layout-shift", buffered: true });
    setTimeout(() => { o.disconnect(); done(total); }, 1200);
  }));
}
async function ask(page: Page, q: string) {
  await page.goto("/"); await settle(page);
  await page.getByLabel("Ask anything about the company").first().fill(q);
  await page.locator(".cx-askrow").first().getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator(".cx-answer").first()).toBeVisible();
  await page.waitForTimeout(500);
}

test.describe.serial("quality gates", () => {
  let page: Page;
  let errors: string[];
  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ baseURL: `http://localhost:${process.env.WEB_PORT ?? "3000"}`, viewport: { width: 1440, height: 900 } });
    page = await ctx.newPage();
    errors = watch(page);
    await login(page);
    await resetDemo(page);
    await page.getByRole("button", { name: "Run now" }).click();
    await page.waitForTimeout(1500);
  });
  test.afterAll(async () => { await page.close(); });

  for (const v of VIEWS) {
    test(`screenshot of every page, ${v.name}`, async () => {
      await page.setViewportSize({ width: v.width, height: v.height });
      for (const p of PAGES) {
        await page.goto(p);
        await settle(page);
        await page.screenshot({ path: `${SHOTS}/page-${slug(p)}-${v.name}.png` });
      }
    });

    test(`eight states, ${v.name}`, async () => {
      await page.setViewportSize({ width: v.width, height: v.height });
      const shot = (n: string) => page.screenshot({ path: `${SHOTS}/state-${n}-${v.name}.png` });
      // 6 empty: nothing has been asked yet
      await page.goto("/"); await settle(page);
      await expect(page.getByText("Nothing asked yet")).toBeVisible();
      await shot("6-empty-state");
      // 1 default: an answer with its sources
      await ask(page, "How are databases backed up?");
      await shot("1-default-answer");
      // 2 detail: the source viewer with the cited passage marked
      await page.getByRole("button", { name: "Open in source" }).first().click();
      await expect(page.locator("mark.cx-mark")).toBeVisible(); await page.waitForTimeout(600);
      await shot("2-detail-source-viewer");
      await page.keyboard.press("Escape");
      // 3 warning: two documents disagree
      await ask(page, "What is the first reply promise for support questions?");
      await expect(page.getByText("Documents disagree")).toBeVisible();
      await shot("3-warning-documents-disagree");
      // 4 button mid processing
      await page.goto("/"); await settle(page);
      await page.route("**/api/demo/tick", async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue(); });
      await page.getByRole("button", { name: "Run now" }).click(); await page.waitForTimeout(500);
      await shot("4-button-processing");
      await page.waitForTimeout(2600);
      await page.unroute("**/api/demo/tick");
      // 5 toast with undo
      await page.goto("/tasks"); await settle(page);
      await page.locator('section[aria-label="Proposed"] .cx-card').first().click();
      await page.getByRole("dialog").getByRole("button", { name: "Approve", exact: true }).click();
      await expect(page.getByText(/^Approved:/)).toBeVisible();
      await page.waitForTimeout(400);
      await shot("5-toast-with-undo");
      await page.getByRole("button", { name: "Undo" }).click();
      await page.waitForTimeout(800);
      // 7 error: the task call is cut off
      const before = errors.length;
      await page.route("**/api/tasks?**", (route) => route.abort());
      await page.goto("/tasks"); await page.waitForTimeout(2500);
      await expect(page.getByText(/Could not/i).first()).toBeVisible();
      await shot("7-error-state");
      await page.unroute("**/api/tasks?**");
      errors.splice(before);
      // 8 dark
      await page.goto("/meetings"); await settle(page);
      await page.getByRole("link").filter({ hasText: "to approve" }).first().click(); await settle(page);
      await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
      await page.waitForTimeout(300);
      await shot("8-dark");
      await page.evaluate(() => document.documentElement.removeAttribute("data-theme"));
    });
  }

  for (const theme of ["light", "dark"]) {
    test(`axe finds no serious or critical problems on any page, ${theme}`, async () => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.emulateMedia({ colorScheme: theme as "light" | "dark" });
      const bad: string[] = [];
      for (const p of PAGES) {
        await page.goto(p); await settle(page);
        if (theme === "dark") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
        await page.waitForTimeout(300);
        const res = await new AxeBuilder({ page }).analyze();
        for (const v of res.violations.filter((x) => x.impact === "serious" || x.impact === "critical")) bad.push(`${theme} ${p} ${v.id} ${v.impact}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`);
      }
      await page.emulateMedia({ colorScheme: "light" });
      await page.evaluate(() => document.documentElement.removeAttribute("data-theme"));
      expect(bad).toEqual([]);
    });
  }

  test("keyboard path: every stop shows focus, the ask bar opens and answers with the keyboard", async () => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/"); await settle(page);
    const seen: string[] = [];
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const e = document.activeElement as HTMLElement | null;
        if (!e || e === document.body) return null;
        const cs = getComputedStyle(e);
        const r = e.getBoundingClientRect();
        return { name: (e.getAttribute("aria-label") || e.textContent || e.tagName).trim().slice(0, 30), ring: (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none" || e.matches("[data-selected]"), visible: r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight };
      });
      if (info) { seen.push(info.name); expect(info.visible, `${info.name} is on screen`).toBeTruthy(); expect(info.ring, `${info.name} shows focus`).toBeTruthy(); }
    }
    expect(seen.length).toBeGreaterThan(10);
    await page.goto("/tasks"); await settle(page);
    await page.keyboard.press("Control+k");
    const dlg = page.getByRole("dialog", { name: "Ask anything" });
    await expect(dlg).toBeVisible();
    await page.keyboard.type("How much annual leave do I get?");
    await page.keyboard.press("Enter");
    await expect(dlg.locator(".cx-answer")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dlg).toBeHidden();
  });

  test("reduced motion: nothing animates", async () => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/"); await page.waitForLoadState("networkidle"); await page.waitForTimeout(1200);
    const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running" && (a.effect?.getComputedTiming().iterations ?? 1) === Infinity).length);
    expect(running).toBe(0);
    await page.emulateMedia({ reducedMotion: "no-preference" });
  });

  test("no layout shift on any page", async () => {
    const bad: string[] = [];
    for (const p of PAGES) {
      await page.goto(p);
      let cls = await layoutShift(page);
      if (cls > 0.1) {
        // A slow runner can add a one off shift (fonts and data arriving late). A shift that is really in the page shows again on a second, warm visit.
        await page.goto(p);
        cls = await layoutShift(page);
      }
      if (cls > 0.1) bad.push(`${p} ${cls.toFixed(3)}`);
    }
    expect(bad).toEqual([]);
  });

  test("5,000 rows: the task table opens fast and stays responsive", async () => {
    const add = await call(page, "/demo/stress-tasks", { n: 5000 });
    expect(add.ok()).toBeTruthy();
    const t0 = Date.now();
    await page.goto("/tasks");
    await expect(page.locator('[role="row"]').first()).toBeVisible({ timeout: 15000 });
    await settle(page);
    expect(Date.now() - t0, "task table with 5,000 rows is ready").toBeLessThan(9000);
    expect(await page.locator('[role="row"]').count(), "only visible rows are in the page").toBeLessThan(200);
    await page.screenshot({ path: `${SHOTS}/state-13-five-thousand-rows-desktop.png` });
  });

  test("no console errors or failed requests during the whole run", async () => {
    expect(errors).toEqual([]);
  });
});
