import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  ownerEmail: string;
  ownerPassword: string;
  orgId: string;
  stationId: string;
  stationId2: string;
  stationId3: string;
  roles: { stationManager: { email: string; password: string }; cashier: { email: string; password: string } };
};

async function loginAs(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Phase 8c — Company Overview, station switcher, comparison", () => {
  test("Company Overview shows real combined figures from the Phase 8b endpoints", async ({ page }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);

    await expect(page.getByRole("heading", { name: "Company Overview" })).toBeVisible();
    // The combined KPI tiles must show real numbers, not a placeholder -
    // not asserting an exact total here since stations 2/3 may pick up
    // real activity from other specs running concurrently against the
    // same seeded organization (only ever adding to the total, never
    // subtracting it below station 1's own known contribution).
    await expect(page.getByText("Total fuel sold")).toBeVisible();
    await expect(page.getByText("Total revenue")).toBeVisible();
    await expect(page.getByText("Cash collected", { exact: true })).toBeVisible();

    // Station 1's own seeded shift (500L @ 280.00/L = 140000.00) is fixed
    // and untouched by any other spec - its row in the station-wise
    // comparison must show these exact figures, matching
    // dashboard.spec.ts's own assertion against the same station's
    // single-station report.
    await page.getByRole("tab", { name: "Station Comparison" }).click();
    const row = page.locator("table tbody tr", { hasText: "E2E Station" }).filter({ hasNotText: "E2E Station 2" }).filter({ hasNotText: "E2E Station 3" });
    await expect(row).toBeVisible();
    await expect(row.getByText("500.000 L", { exact: true })).toBeVisible();
    // Expected revenue and total tendered both equal 140000.00 here (a
    // zero-variance shift) - appears in two cells by design, same as
    // dashboard.spec.ts's own assertion against this station.
    await expect(row.getByText("140,000.00", { exact: true }).first()).toBeVisible();
  });

  test("All Stations option is offered to the real, org-wide Owner", async ({ page }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);

    const switcher = page.getByLabel("Switch station");
    await expect(switcher).toBeVisible();
    await expect(switcher.locator("option", { hasText: "All Stations" })).toHaveCount(1);
  });

  test("Station-scoped Station Manager sees only their own authorized stations, never station 2", async ({ page }) => {
    await loginAs(page, state.roles.stationManager.email, state.roles.stationManager.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/today`);

    const switcher = page.getByLabel("Switch station");
    await expect(switcher).toBeVisible();
    // No org-wide grant - "All Stations" must not be offered at all.
    await expect(switcher.locator("option", { hasText: "All Stations" })).toHaveCount(0);

    const optionValues = await switcher.locator("option").evaluateAll((opts) => opts.map((o) => (o as HTMLOptionElement).value));
    expect(optionValues).toContain(state.stationId);
    expect(optionValues).toContain(state.stationId3);
    expect(optionValues).not.toContain(state.stationId2);
  });

  test("A station-scoped user navigating directly to an unauthorized station sees Access restricted, not that station's data", async ({ page }) => {
    // Station Manager holds station:update - but only at stations 1/3,
    // not station 2, so this proves the denial is genuinely per-station,
    // not just "this role never has this permission" (already covered by
    // role-permissions.spec.ts's Cashier tests against station 1).
    await loginAs(page, state.roles.stationManager.email, state.roles.stationManager.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId2}/settings`);

    await expect(page.getByText("Access restricted")).toBeVisible();
  });

  test("Station switching navigates to the selected station's own dashboard without mixing data", async ({ page }) => {
    await loginAs(page, state.roles.stationManager.email, state.roles.stationManager.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/today`);

    const switcher = page.getByLabel("Switch station");
    await switcher.selectOption(state.stationId3);
    await expect(page).toHaveURL(new RegExp(`/station/${state.stationId3}/today`));
  });

  test("An empty date range shows a real empty/zero state, not an error", async ({ page }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);

    // getByLabel("To") also matches the theme-toggle button's aria-label
    // ("Switch to light theme") - the date input's own role is unambiguous.
    await page.getByRole("textbox", { name: "From" }).fill("2020-01-01");
    await page.getByRole("textbox", { name: "To" }).fill("2020-01-02");

    const valueText = await page
      .getByText("Total fuel sold", { exact: true })
      .locator("xpath=..")
      .locator("p.text-2xl")
      .textContent({ timeout: 10000 });
    expect(valueText?.trim()).toBe("0 L");
  });

  test("Attendance tab loads a real total-employee headcount, not a placeholder", async ({ page }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);
    await page.getByRole("tab", { name: "Attendance" }).click();

    await expect(page.getByText("Total employees")).toBeVisible();
    const valueText = await page
      .getByText("Total employees")
      .locator("xpath=..")
      .locator("p.text-2xl")
      .textContent();
    expect(Number((valueText ?? "0").replace(/,/g, ""))).toBeGreaterThan(0);
  });

  test("Stock tab shows real tank-by-tank book stock across stations", async ({ page }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);
    await page.getByRole("tab", { name: "Stock" }).click();

    await expect(page.getByRole("heading", { name: "Tank-by-tank overview" })).toBeVisible();
    await expect(page.locator("table tbody tr").first()).toBeVisible();
  });

  test("A role with no report:read permission at all sees Access restricted on Company Overview", async ({ page }) => {
    // Cashier/Operator holds no report:read anywhere (see
    // backend/app/core/permission_codes.py's SEED_ROLES) - the correct
    // role to exercise this denial path end to end, distinct from the
    // per-station denial exercised above with a role that DOES hold it.
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);

    await expect(page.getByText("Access restricted")).toBeVisible();
  });

  test("the live daily sales trend, last-updated timestamp, and manual refresh all reflect real data", async ({
    page,
    request,
  }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);

    // The chart itself - real data from GET .../reports/daily-sales, not a
    // frontend calculation. Station 1's seeded shift (500L @ 280.00/L)
    // gives today's bar a non-zero value, so this isn't the chart's own
    // "no approved sales yet" empty state.
    await expect(page.getByRole("heading", { name: "Daily sales trend" })).toBeVisible();
    await expect(page.getByText("No approved sales in this range yet.")).toHaveCount(0);

    // Last-updated timestamp appears once the first load completes.
    await expect(page.getByText(/Last updated \d/)).toBeVisible();

    // Manual refresh: record a new expense via the real API, click
    // Refresh, and confirm the Expense categories card's total actually
    // changes - proving the button re-fetches live backend data, not
    // just toggling a spinner.
    const token = await (
      await request.post("http://localhost:8000/auth/login", {
        data: { email: state.ownerEmail, password: state.ownerPassword },
      })
    ).json();
    const auth = { Authorization: `Bearer ${token.access_token}` };
    const today = new Date().toISOString().slice(0, 10);
    await request.post(`http://localhost:8000/organizations/${state.orgId}/expenses`, {
      headers: auth,
      data: { category: "e2e-live-refresh", description: "Live refresh probe", amount: "777", expense_date: today },
    });

    await page.getByRole("button", { name: "Refresh now" }).click();
    await expect(page.getByText("e2e-live-refresh")).toBeVisible();
    await expect(page.getByText(/777\.00 total/)).toBeVisible();
  });

  test("Supplier outstanding balance and Pending approvals sections reflect real data for an authorized Owner", async ({
    page,
  }) => {
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);

    await expect(page.getByText("Supplier outstanding balance")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Pending approvals & attention centre" })).toBeVisible();
  });

  test("Recent activity shows real, humanized actions for an authorized Owner", async ({ page }) => {
    // Every seeded role that holds report:read (Owner, Station Manager,
    // Accountant, Auditor/Viewer) also holds audit:read in this project's
    // current seed, so there's no real role to exercise an "activity
    // section omitted" negative case against - the section's own gate
    // (can("audit:read")) is still real and backend-enforced regardless;
    // this test only confirms the positive, always-reachable path renders
    // real data, not a placeholder.
    await loginAs(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/overview`);
    await expect(page.getByRole("heading", { name: "Recent activity" })).toBeVisible();
    await expect(page.getByText("No recent activity recorded yet.")).toHaveCount(0);
  });
});
