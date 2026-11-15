import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  ownerEmail: string;
  ownerPassword: string;
  orgId: string;
  stationId: string;
};

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.fill("#email", state.ownerEmail);
  await page.fill("#password", state.ownerPassword);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Day 2 — Tank management page", () => {
  test("loads and shows tank configuration heading", async ({ page }) => {
    await login(page);
    await page.goto(
      `/dashboard/org/${state.orgId}/station/${state.stationId}/tanks`
    );
    await expect(page.getByText("Tank configuration")).toBeVisible();
  });

  test("displays tank cards or empty message", async ({ page }) => {
    await login(page);
    await page.goto(
      `/dashboard/org/${state.orgId}/station/${state.stationId}/tanks`
    );
    // Root cause of this test's past flakiness (investigated in Phase 6,
    // not just re-tracked): `.isVisible()` with no wait snapshots the page
    // immediately, which can land while the tank list is still showing
    // "Loading…" - landing on neither branch and then timing out waiting
    // for "No tanks configured" (which never appears, because tanks do
    // exist). Waiting for either real end state first removes the race
    // without weakening what's actually asserted.
    const tankCard = page.getByText("Capacity:").first();
    const emptyState = page.getByText("No tanks configured");
    await expect(tankCard.or(emptyState)).toBeVisible();
    if (!(await tankCard.isVisible().catch(() => false))) {
      await expect(emptyState).toBeVisible();
    }
  });
});

test.describe("Day 2 — Reading corrections page", () => {
  test("loads and shows reading corrections heading", async ({ page }) => {
    await login(page);
    await page.goto(
      `/dashboard/org/${state.orgId}/station/${state.stationId}/reading-corrections`
    );
    await expect(page.getByText("Reading corrections")).toBeVisible();
  });
});

test.describe("Day 2 — Credit customers page", () => {
  test("loads and shows credit customers heading", async ({ page }) => {
    await login(page);
    await page.goto(`/dashboard/org/${state.orgId}/credit-customers`);
    // Root cause investigated in Phase 6, not just re-tracked: the page
    // genuinely has two elements with this text by design - the page's
    // own <h1> title and a <h2> card title for the customer list below
    // it (not a bug; a page titled "Credit customers" containing a
    // "Credit customers" list card is reasonable structure). The test
    // just wasn't scoped to the one it actually meant.
    await expect(page.getByRole("heading", { level: 1, name: "Credit customers" })).toBeVisible();
  });

  test("shows customer list or empty state", async ({ page }) => {
    await login(page);
    await page.goto(`/dashboard/org/${state.orgId}/credit-customers`);
    // Same race-condition class fixed above for the tanks page - wait for
    // a real end state instead of snapshotting immediately after goto().
    const table = page.locator("table").first();
    const emptyState = page.getByText("No credit customers");
    await expect(table.or(emptyState)).toBeVisible();
    if (!(await table.isVisible().catch(() => false))) {
      await expect(emptyState).toBeVisible();
    }
  });
});
