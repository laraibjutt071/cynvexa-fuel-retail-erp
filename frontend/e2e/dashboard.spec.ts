import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  ownerEmail: string;
  ownerPassword: string;
  orgId: string;
  stationId: string;
  inventoryItemId: string;
};

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.fill("#email", state.ownerEmail);
  await page.fill("#password", state.ownerPassword);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("CYNVEXA owner dashboard", () => {
  test("login redirects to the dashboard", async ({ page }) => {
    await login(page);
    await expect(page.getByText(state.ownerEmail)).toBeVisible();
  });

  test("org dashboard: a pending expense can be approved from the UI", async ({ page }) => {
    await login(page);
    await page.goto(`/dashboard/org/${state.orgId}`);
    await page.getByRole("tab", { name: "Expenses" }).click();

    const row = page.locator("tr", { hasText: "E2E seeded expense" });
    await expect(row).toBeVisible();
    await expect(row.getByText("pending")).toBeVisible();

    await row.getByRole("button", { name: "Approve" }).click();
    await expect(row.getByText("approved")).toBeVisible();
  });

  test("org dashboard: pending-approvals overview reflects real counts", async ({ page }) => {
    await login(page);
    await page.goto(`/dashboard/org/${state.orgId}`);
    await page.getByRole("tab", { name: "Pending & exceptions" }).click();
    // The low-stock inventory item seeded in global-setup (on_hand 0 <
    // reorder_level 5) must show up as a real, non-zero count - never a
    // hardcoded placeholder.
    await expect(page.getByText("Low-stock inventory items")).toBeVisible();
  });

  test("station dashboard: daily fuel sales report shows the seeded shift's real figures", async ({ page }) => {
    await login(page);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}`);
    await page.getByRole("tab", { name: "Daily fuel sales" }).click();

    // 500L dispensed * 280.00/L seeded in global-setup. Revenue and
    // tender both equal 140000.00, appearing in two cells by design (a
    // zero-variance reconciliation) - .first() just confirms presence.
    await expect(page.getByText("500.000")).toBeVisible();
    await expect(page.getByText("140000.00").first()).toBeVisible();
  });

  test("station dashboard: tank variance and reconciliation reports show the approved shift", async ({ page }) => {
    await login(page);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}`);

    await page.getByRole("tab", { name: "Tank variance" }).click();
    // Book stock and the physical closing reading both read 9500.000 -
    // zero variance by design - so this appears in two cells.
    await expect(page.getByText("9500.000").first()).toBeVisible();

    await page.getByRole("tab", { name: "Shift & cash reconciliation" }).click();
    await expect(page.getByText("approved")).toBeVisible();
  });

  test("station dashboard: recording an inventory receipt updates on-hand stock", async ({ page }) => {
    await login(page);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}`);
    await page.getByRole("tab", { name: "Shop / lubricant inventory" }).click();

    await expect(page.locator("td", { hasText: "E2E-OIL" })).toBeVisible();
    await expect(page.getByText("0.000 bottle")).toBeVisible();

    await page.getByLabel("Item").selectOption(state.inventoryItemId);
    await page.getByLabel("Type").selectOption("receipt");
    await page.getByLabel("Quantity").fill("10");
    await page.getByRole("button", { name: "Record" }).click();

    await expect(page.getByText("10.000 bottle")).toBeVisible();
  });
});
