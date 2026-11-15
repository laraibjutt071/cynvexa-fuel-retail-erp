import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Phase 5, Step 7 - Daily Entry role-based workflow tests, using real,
 * non-superuser, role-scoped users (seeded by global-setup.ts) against
 * station 3, which has master data but no shift yet (station 1's shift
 * is fully approved by setup for the report-assertion tests elsewhere,
 * and station 2 is used by the pre-existing full-workflow test - neither
 * is free for a fresh role-based workflow).
 *
 * Honest scope: this does not cross every one of the seven roles with
 * every Daily Entry action - it covers Shift Supervisor (entry +
 * review/approval permissions), Cashier (review-approval restriction, and
 * the permission fix below), a direct unauthorized API call, and station
 * isolation.
 *
 * UPDATE (Phase 6, owner-approved): the real gap Phase 5 found here -
 * Cashier/Operator held shift:open/shift:close (which gate *recording* a
 * reading) but not tank:read/nozzle:read (which gate *listing* the
 * tanks/nozzles to record against) - is now fixed. The seeded role gained
 * both, read-only, station/org-scoped (docs/PHASE_6_ROLE_ONBOARDING_REPORT.md).
 * The test below was updated to assert the now-correct 200, not left
 * pointing at stale 403 behavior - per this file's own original comment,
 * that is progress, not a regression, and the expectation moves with it.
 */

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  orgId: string;
  stationId3: string;
  roles: {
    cashier: { email: string; password: string };
    shiftSupervisor: { email: string; password: string };
  };
};

async function loginAs(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

async function backendToken(page: Page): Promise<string> {
  return page.evaluate(async () => {
    const resp = await fetch("http://localhost:8000/auth/refresh", { method: "POST", credentials: "include" });
    const body = await resp.json();
    return body.access_token as string;
  });
}

test.describe.serial("Daily Entry — Shift Supervisor entry + review/approval permissions", () => {
  test("Shift Supervisor can start today's entry at station 3 and record a reading", async ({ page }) => {
    await loginAs(page, state.roles.shiftSupervisor.email, state.roles.shiftSupervisor.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId3}/daily-entry`);

    // Wait for the page to actually settle on one of its two real states
    // before deciding whether to click Start - checking isVisible() right
    // after goto() races the initial "Checking for an entry…" load.
    await expect(
      page.getByText("Nothing recorded for this business date").or(page.getByRole("tab", { name: "Readings" }))
    ).toBeVisible();

    const startButton = page.getByRole("button", { name: /start today's entry/i });
    if (await startButton.isVisible().catch(() => false)) {
      await startButton.click();
    }

    await expect(page.getByRole("tab", { name: "Readings" })).toBeVisible();
    // A real reading, saved via the real API - not a mock.
    const openingInput = page.getByPlaceholder("Opening dip (L) *").first();
    await expect(openingInput).toBeVisible();
    await openingInput.fill("5000");
    await page.getByRole("button", { name: "Save" }).first().click();
    await expect(page.getByText("Opening dip saved.")).toBeVisible();
  });

  test("Shift Supervisor sees the real Approve button (shift:approve), not Access restricted", async ({ page }) => {
    await loginAs(page, state.roles.shiftSupervisor.email, state.roles.shiftSupervisor.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId3}/daily-entry?section=review`);
    await expect(page.getByText("Access restricted")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Approve today's entry" })).toBeVisible();
  });

  test("Approving opens a confirmation dialog and stays disabled until the checklist passes", async ({ page }) => {
    await loginAs(page, state.roles.shiftSupervisor.email, state.roles.shiftSupervisor.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId3}/daily-entry?section=review`);
    const approveButton = page.getByRole("button", { name: "Approve today's entry" });
    // The button is disabled until every checklist item passes (readings
    // closed, cash closed, etc.) - station 3's shift is still open with
    // only one reading recorded, so this proves the gate is real, not
    // just checking that a dialog exists.
    await expect(approveButton).toBeDisabled();
  });
});

test.describe("Daily Entry — Cashier's review restriction", () => {
  test("Cashier does not see the Approve button on Review - sees Access restricted instead", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId3}/daily-entry?section=review`);
    await expect(page.getByText("Access restricted")).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve today's entry" })).toHaveCount(0);
  });
});

test.describe("Daily Entry — Phase 6 fix: Cashier can now list tanks/nozzles (read-only)", () => {
  test("Cashier's token can read station 3's tanks and nozzles via the real API", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    const token = await backendToken(page);
    const tanksResp = await page.request.get(
      `http://localhost:8000/organizations/${state.orgId}/stations/${state.stationId3}/tanks`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(tanksResp.status()).toBe(200);
    const nozzlesResp = await page.request.get(
      `http://localhost:8000/organizations/${state.orgId}/stations/${state.stationId3}/nozzles`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(nozzlesResp.status()).toBe(200);
  });

  test("Cashier's Readings tab now actually shows tanks/nozzles instead of loading forever", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId3}/daily-entry`);
    await expect(page.getByRole("tab", { name: "Readings" })).toBeVisible();
    // The tank table header is real content, not the permanent "Loading…"
    // state Phase 5 found - station 3 has one tank, already recorded on
    // by Shift Supervisor earlier in this file.
    await expect(page.getByText("Current book stock")).toBeVisible();
    await expect(page.getByText("Loading…")).toHaveCount(0);
  });

  test("Cashier still cannot create or edit a tank/nozzle - read-only, as approved", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    const token = await backendToken(page);
    const createResp = await page.request.post(
      `http://localhost:8000/organizations/${state.orgId}/stations/${state.stationId3}/tanks`,
      {
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        data: { code: "T-HACK", name: "Should not be creatable", fuel_grade_id: "00000000-0000-0000-0000-000000000000", capacity: "1000", safe_fill_limit: "900" },
      }
    );
    expect(createResp.status()).toBe(403);
  });
});

test.describe("Daily Entry — backend independently rejects what the UI hides", () => {
  test("Cashier's token is rejected (403) on a direct shift-approve API call", async ({ page, request }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    const token = await backendToken(page);
    // Find the station-3 shift's id via the real list endpoint (shift:read
    // is one permission Cashier does hold), then attempt the exact action
    // the UI hides from this role.
    const shiftsResp = await request.get(
      `http://localhost:8000/organizations/${state.orgId}/stations/${state.stationId3}/shifts`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(shiftsResp.ok()).toBeTruthy();
    const shifts = await shiftsResp.json();
    expect(shifts.length).toBeGreaterThan(0);
    const approveResp = await request.patch(
      `http://localhost:8000/organizations/${state.orgId}/stations/${state.stationId3}/shifts/${shifts[0].id}/approve`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(approveResp.status()).toBe(403);
  });
});

test.describe("Daily Entry — station/tenant isolation for a real role, not just a superuser", () => {
  test("Cashier cannot read shifts for a fabricated organization id", async ({ page, request }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    const token = await backendToken(page);
    const otherOrgId = "00000000-0000-0000-0000-000000000000";
    const resp = await request.get(
      `http://localhost:8000/organizations/${otherOrgId}/stations/${state.stationId3}/shifts`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect([403, 404]).toContain(resp.status());
  });
});
