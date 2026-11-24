import { expect, test } from "@playwright/test";
import { PAGES, login, resetDemo, watch } from "./helpers";

test("every page loads without console errors", async ({ page }) => {
  const errors = watch(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  for (const p of PAGES) {
    await page.goto(p);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1").first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("task board by keyboard: focus a card, press Enter, approve from the sheet", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  await page.goto("/tasks");
  await page.waitForLoadState("networkidle");
  const card = page.locator('section[aria-label="Proposed"] [aria-label^="task "]').first();
  await expect(card).toBeVisible();
  await card.focus();
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("button", { name: "Approve", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  // The Open button inside the card is a real button in the tab order.
  await card.getByRole("button", { name: /^Open task/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog").getByRole("button", { name: "Approve", exact: true })).toBeVisible();
});
