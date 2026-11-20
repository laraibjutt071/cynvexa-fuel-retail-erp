import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Phase 10C — Payroll Frontend. Payroll is entirely station-scoped (no
 * org-wide endpoint exists on the backend), so this uses its own
 * dedicated station (created here, like meter-events.spec.ts and
 * suppliers.spec.ts before it) rather than one already used by another
 * spec. No fuel master data (tanks/dispensers/nozzles) is needed at all
 * - payroll only touches users and attendance records.
 */

const API_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  ownerEmail: string;
  ownerPassword: string;
  orgId: string;
  stationId: string;
  roles: {
    cashier: { email: string; password: string };
    stationManager: { email: string; password: string };
  };
};

async function apiLogin(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${API_BASE}/auth/login`, {
    data: { email: state.ownerEmail, password: state.ownerPassword },
  });
  const body = await resp.json();
  return body.access_token as string;
}

async function uiLogin(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Phase 10C — Payroll", () => {
  test("a payroll rule, attendance-driven salary generation, and finalization all work end to end with flat per-occurrence deductions", async ({
    page,
    request,
  }) => {
    const token = await apiLogin(request);
    const auth = { Authorization: `Bearer ${token}` };
    const runId = Date.now().toString(36);

    const station = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations`, {
        headers: auth,
        data: { name: "E2E Payroll Station", code: `E2EPR-${runId}` },
      })
    ).json();

    const employeeEmail = `e2e-payroll-emp-${runId}@e2e-dev.com`;
    const employee = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/users`, {
        headers: auth,
        data: { email: employeeEmail, full_name: `E2E Payroll Employee ${runId}`, password: "E2eEmpPass!23" },
      })
    ).json();
    // GET /organizations/{org}/users inner-joins on UserStationRole - a user
    // with no role assignment at all never appears in the employee picker,
    // same as every other staff member in this app.
    const roles = await (await request.get(`${API_BASE}/roles`, { headers: auth })).json();
    const cashierRole = roles.find((r: { name: string }) => r.name === "Cashier / Operator");
    await request.post(`${API_BASE}/organizations/${state.orgId}/users/${employee.id}/roles`, {
      headers: auth,
      data: { role_id: cashierRole.id, station_id: station.id },
    });

    // A controlled attendance mix for a fixed period: 2 present, 1 absent,
    // 2 late, 1 half-day, 1 on approved leave - chosen so the expected flat
    // per-occurrence deduction total is unambiguous and easy to verify in
    // the UI: 2 x late + 1 x absent + 1 x half-day, leave never deducted.
    const period = [
      { date: "2026-01-05", status: "present" },
      { date: "2026-01-06", status: "present" },
      { date: "2026-01-07", status: "absent" },
      { date: "2026-01-08", status: "late" },
      { date: "2026-01-09", status: "late" },
      { date: "2026-01-12", status: "half_day" },
      { date: "2026-01-13", status: "leave" },
    ];
    const attendanceBase = `${API_BASE}/organizations/${state.orgId}/stations/${station.id}/attendance`;
    for (const day of period) {
      const resp = await request.post(attendanceBase, {
        headers: auth,
        data: { user_id: employee.id, attendance_date: day.date, status: day.status },
      });
      expect(resp.ok()).toBeTruthy();
    }

    await uiLogin(page, state.ownerEmail, state.ownerPassword);
    await page.goto(`/dashboard/org/${state.orgId}/station/${station.id}/payroll`);
    await expect(page.getByRole("heading", { name: "Payroll" })).toBeVisible();

    // --- Payroll Rules: a flat per-occurrence rule ---
    await page.getByRole("tab", { name: "Payroll Rules" }).click();
    await page.getByRole("button", { name: "Add rule" }).first().click();
    await page.getByRole("dialog").getByLabel("Rule name").fill("E2E Standard Shift");
    await page.getByRole("dialog").getByLabel("Shift start time").fill("09:00");
    await page.getByRole("dialog").getByLabel("Late deduction").fill("150");
    await page.getByRole("dialog").getByLabel("Absent deduction").fill("1000");
    await page.getByRole("dialog").getByLabel("Half-day deduction").fill("500");
    await page.getByRole("dialog").getByRole("button", { name: "Create rule" }).click();
    await expect(page.getByText("Payroll rule created.")).toBeVisible();
    await expect(page.locator("table tbody tr", { hasText: "E2E Standard Shift" })).toBeVisible();

    // --- Generate salary for the controlled attendance period ---
    await page.getByRole("tab", { name: "Generate Salary" }).click();
    await expect(page.getByText(/Active rule "E2E Standard Shift"/)).toBeVisible();
    await page.getByLabel("Employee").selectOption({ label: `E2E Payroll Employee ${runId}` });
    await page.getByLabel("Base salary (PKR)").fill("50000");
    await page.getByLabel("Period start").fill("2026-01-05");
    await page.getByLabel("Period end").fill("2026-01-13");
    await page.getByRole("button", { name: "Generate salary" }).click();
    await page.getByRole("button", { name: "Yes, generate salary" }).click();
    await expect(page.getByText("Salary generated.")).toBeVisible();

    // Flat per-occurrence math, not per-minute/per-hour: 2 late x 150 = 300,
    // 1 absent x 1000 = 1000, 1 half-day x 500 = 500 -> 1800 total, leave
    // never deducted, net = 50000 - 1800 = 48200.00.
    await expect(page.getByText("PKR 1,800.00").first()).toBeVisible();
    await expect(page.getByText("PKR 48,200.00").first()).toBeVisible();
    const breakdownRows = page.locator("table tbody tr");
    const lateRow = breakdownRows.filter({ hasText: "Late" });
    await expect(lateRow).toContainText("2");
    await expect(lateRow).toContainText("PKR 150.00");
    await expect(lateRow).toContainText("PKR 300.00");
    const absentRow = breakdownRows.filter({ hasText: "Absent" });
    await expect(absentRow).toContainText("1");
    await expect(absentRow).toContainText("PKR 1,000.00");
    const halfDayRow = breakdownRows.filter({ hasText: "Half-day" });
    await expect(halfDayRow).toContainText("1");
    await expect(halfDayRow).toContainText("PKR 500.00");
    await expect(page.getByText("Approved leave (not deducted): 1")).toBeVisible();

    // --- History: the record appears, can be opened as a statement, and finalized ---
    await page.getByRole("tab", { name: "History" }).click();
    const historyRow = page.locator("table tbody tr", { hasText: "48,200.00" });
    await expect(historyRow).toBeVisible();
    await expect(historyRow.getByText("Pending", { exact: true })).toBeVisible();

    await historyRow.getByRole("button", { name: "Statement" }).click();
    await expect(page.getByRole("dialog").getByText("Salary statement")).toBeVisible();
    await expect(page.getByRole("dialog").getByText(`E2E Payroll Employee ${runId}`)).toBeVisible();
    await page.getByRole("button", { name: /^Close dialog$/ }).click();

    await historyRow.getByRole("button", { name: "Finalize" }).click();
    await page.getByRole("button", { name: "Yes, finalize" }).click();
    await expect(page.getByText("Salary record finalized.")).toBeVisible();
    await expect(historyRow.getByText("Finalized", { exact: true })).toBeVisible();
    await expect(historyRow.getByRole("button", { name: "Finalize" })).toHaveCount(0);

    // --- Dashboard: totals reflect this one real record ---
    await page.getByRole("tab", { name: "Dashboard" }).click();
    await expect(page.getByText("PKR 50,000.00")).toBeVisible();
    await expect(page.getByText("PKR 1,800.00").first()).toBeVisible();
  });

  test("Cashier (no payroll:manage) sees Access restricted on the Payroll page", async ({ page, request }) => {
    const token = await apiLogin(request);
    const auth = { Authorization: `Bearer ${token}` };
    const station = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations`, {
        headers: auth,
        data: { name: "E2E Payroll Cashier Station", code: `E2EPRC-${Date.now().toString(36)}` },
      })
    ).json();

    await uiLogin(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${station.id}/payroll`);
    await expect(page.getByText("Access restricted")).toBeVisible();
  });

  test("a Station Manager scoped to other stations cannot access this station's payroll (station isolation)", async ({
    page,
    request,
  }) => {
    const token = await apiLogin(request);
    const auth = { Authorization: `Bearer ${token}` };
    const unrelatedStation = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations`, {
        headers: auth,
        data: { name: "E2E Payroll Isolation Station", code: `E2EPRI-${Date.now().toString(36)}` },
      })
    ).json();

    // state.roles.stationManager holds payroll:manage, but only at station 1
    // and station 3 (global-setup.ts) - never at this brand-new station.
    await uiLogin(page, state.roles.stationManager.email, state.roles.stationManager.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${unrelatedStation.id}/payroll`);
    await expect(page.getByText("Access restricted")).toBeVisible();
  });

  test("the same Station Manager DOES have payroll access at station 1, where their role is actually granted", async ({
    page,
  }) => {
    await uiLogin(page, state.roles.stationManager.email, state.roles.stationManager.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/payroll`);
    await expect(page.getByText("Access restricted")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Payroll" })).toBeVisible();
  });
});
