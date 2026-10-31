import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  ownerEmail: string;
  ownerPassword: string;
  orgId: string;
  stationId2: string;
};

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.fill("#email", state.ownerEmail);
  await page.fill("#password", state.ownerPassword);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Daily Entry workspace", () => {
  test("a full business day can be entered, closed, reconciled and approved end to end", async ({ page }) => {
    await login(page);
    // station2 (unlike the main e2e station) has never had a shift
    // created on it at all, so "today" is genuinely empty here - this
    // exercises the real empty-day -> approved-day path, not a
    // pre-seeded one. The date picker already defaults to today.
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId2}/daily-entry`);

    await expect(page.getByText("Nothing recorded for this business date")).toBeVisible();
    await page.getByRole("button", { name: "Start today's entry" }).click();
    await expect(page.getByText("open", { exact: false }).first()).toBeVisible();

    // --- Pump readings ---
    await page.getByRole("tab", { name: "Pump Readings" }).click();

    // Tank opening/closing dip - required before the shift can close, in
    // addition to the nozzle readings below (closing a shift checks both).
    const tankRow = page.locator("tr", { hasText: "T1" });
    await tankRow.getByPlaceholder("Opening dip").fill("10000");
    await tankRow.getByRole("button", { name: "Save" }).click();
    await expect(tankRow.getByPlaceholder("Closing dip")).toBeVisible();
    await tankRow.getByPlaceholder("Closing dip").fill("9900");
    await tankRow.getByRole("button", { name: "Save" }).click();

    await expect(page.getByText("D1 / N1")).toBeVisible();
    // Opening totalizer: no prior closing reading exists for this nozzle
    // in global-setup's fresh station, so the field is editable, not
    // pre-filled - fill a known value and save.
    // The per-nozzle card is the innermost "div.rounded-lg.border" that
    // contains this nozzle's label (an outer ancestor div also "has" the
    // text, which previously made .first() ambiguous between the two).
    const openingRow = page.locator("div.rounded-lg.border", { has: page.getByText("D1 / N1") });
    await openingRow.getByPlaceholder("Opening totalizer").fill("0");
    await openingRow.getByRole("button", { name: "Save" }).click();
    await expect(openingRow.getByText("Closing reading")).toBeVisible();
    await openingRow.getByPlaceholder("Closing totalizer").fill("100");
    await openingRow.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("100.000 L sold today")).toBeVisible();

    await page.getByRole("button", { name: "Close today's readings" }).click();
    await expect(page.getByText("closed", { exact: false }).first()).toBeVisible();

    // --- Sales & collections: 100L * 280.00/L = 28000.00 ---
    await page.getByRole("tab", { name: "Sales & Collections" }).click();
    await page.locator("select").first().selectOption({ label: "Cash (Cash)" });
    await page.getByPlaceholder("Amount").fill("28000");
    await page.getByRole("button", { name: "Record" }).click();
    await expect(page.getByRole("cell", { name: "28000.00" })).toBeVisible();

    // --- Expenses ---
    await page.getByRole("tab", { name: "Expenses" }).click();
    await page.getByLabel("Category").fill("Electricity");
    await page.getByLabel("Description").fill("Daily generator fuel");
    await page.getByLabel("Amount").fill("500");
    await page.getByRole("button", { name: "Record expense" }).click();
    await expect(page.getByText("Daily generator fuel")).toBeVisible();

    // --- Cash closing ---
    await page.getByRole("tab", { name: "Cash Closing" }).click();
    await expect(page.getByLabel("Actual cash counted")).toBeVisible();
    await page.getByLabel("Actual cash counted").fill("28000");
    await page.getByRole("button", { name: "Close cash for today" }).click();
    await expect(page.getByText("Expected revenue")).toBeVisible();
    await expect(page.getByText("28000.00").first()).toBeVisible();

    // --- Review & submit ---
    await page.getByRole("tab", { name: "Review & Submit" }).click();
    await expect(page.getByText("Today's readings closed for every nozzle")).toBeVisible();
    await page.getByRole("button", { name: "Approve today's entry" }).click();
    await expect(page.getByText("stock and cash records are final")).toBeVisible();
  });
});
