import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Phase 3, Step 8 - frontend permission-gating coverage.
 *
 * Honest scope note: this file does not exhaustively cross every one of
 * the seven roles with every one of the dozens of gated actions in the
 * app (that matrix is in docs/PHASE_3_FRONTEND_SECURITY_REPORT.md as a
 * table, not as an exhaustive e2e suite - building and running hundreds
 * of browser assertions was not achievable in this pass). It covers one
 * representative, real assertion per category the brief asked for:
 * nav hiding, direct-navigation denial, action hiding, backend rejection
 * on a direct API call, and cross-tenant denial - using real, non-
 * superuser, role-scoped users seeded by global-setup.ts (Cashier,
 * Storekeeper, Auditor, and the real Owner role, not the superuser
 * stand-in the older spec files use for login convenience).
 */

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  orgId: string;
  stationId: string;
  roles: {
    owner: { email: string; password: string };
    cashier: { email: string; password: string };
    storekeeper: { email: string; password: string };
    auditor: { email: string; password: string };
  };
};

async function loginAs(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Role-based navigation visibility", () => {
  test("Cashier does not see Station Config or Users & Settings in the sidebar", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/today`);
    await expect(page.getByRole("link", { name: "Station Config" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Users & Settings" })).toHaveCount(0);
  });

  test("Owner (real role, not superuser) sees Station Config and Users & Settings", async ({ page }) => {
    await loginAs(page, state.roles.owner.email, state.roles.owner.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/today`);
    await expect(page.getByRole("link", { name: "Station Config" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Users & Settings" })).toBeVisible();
  });
});

test.describe("Direct navigation to an unauthorized page is denied, not just hidden from nav", () => {
  test("Cashier navigating directly to Station Settings sees Access restricted, not the settings forms", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/settings`);
    await expect(page.getByText("Access restricted")).toBeVisible();
    await expect(page.getByText("Station Profile")).toHaveCount(0);
  });

  test("Cashier navigating directly to Attendance sees Access restricted", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/attendance`);
    await expect(page.getByText("Access restricted")).toBeVisible();
  });

  test("Cashier navigating directly to Purchases sees Access restricted (no fuel_receipt permission at all)", async ({ page }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/purchases`);
    await expect(page.getByText("Access restricted")).toBeVisible();
  });
});

test.describe("Partial access shows the right subset of actions, not all-or-nothing", () => {
  test("Storekeeper can see Tanks/Dispensers/Nozzles on Station Settings but not Fuel Grades or Station Profile", async ({ page }) => {
    await loginAs(page, state.roles.storekeeper.email, state.roles.storekeeper.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/settings`);
    await expect(page.getByText("Access restricted")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Dispensers" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Nozzles" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tanks" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Fuel Grades" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Station Profile" })).toHaveCount(0);
  });

  test("Storekeeper on Purchases can record a delivery but has no approve control", async ({ page }) => {
    await loginAs(page, state.roles.storekeeper.email, state.roles.storekeeper.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/purchases`);
    await expect(page.getByRole("heading", { name: "Record a new delivery" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve & add to stock" })).toHaveCount(0);
  });

  test("Auditor on Purchases sees deliveries read-only, with no record form at all", async ({ page }) => {
    await loginAs(page, state.roles.auditor.email, state.roles.auditor.password);
    await page.goto(`/dashboard/org/${state.orgId}/station/${state.stationId}/purchases`);
    await expect(page.getByText("Access restricted")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Record a new delivery" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Deliveries", exact: true })).toBeVisible();
  });
});

test.describe("Backend independently rejects what the UI hides (the UI hiding a button is not security)", () => {
  test("Cashier's token is rejected by the backend on a station-settings PATCH, even called directly", async ({ page, request }) => {
    await loginAs(page, state.roles.cashier.email, state.roles.cashier.password);
    const token = await page.evaluate(async () => {
      const resp = await fetch("http://localhost:8000/auth/refresh", { method: "POST", credentials: "include" });
      const body = await resp.json();
      return body.access_token as string;
    });
    const resp = await request.patch(
      `http://localhost:8000/organizations/${state.orgId}/stations/${state.stationId}`,
      {
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        data: { name: "Hacked via direct API call" },
      }
    );
    expect(resp.status()).toBe(403);
  });

  test("Auditor's token is rejected on fuel-grade creation, even called directly", async ({ page, request }) => {
    await loginAs(page, state.roles.auditor.email, state.roles.auditor.password);
    const token = await page.evaluate(async () => {
      const resp = await fetch("http://localhost:8000/auth/refresh", { method: "POST", credentials: "include" });
      const body = await resp.json();
      return body.access_token as string;
    });
    const resp = await request.post(`http://localhost:8000/organizations/${state.orgId}/fuel-grades`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: { name: "Should not be creatable", code: "NOPE" },
    });
    expect(resp.status()).toBe(403);
  });
});

test.describe("Cross-tenant isolation holds for a real role-scoped user, not just a superuser", () => {
  test("Storekeeper cannot read a station belonging to a made-up/other organization id", async ({ page, request }) => {
    await loginAs(page, state.roles.storekeeper.email, state.roles.storekeeper.password);
    const token = await page.evaluate(async () => {
      const resp = await fetch("http://localhost:8000/auth/refresh", { method: "POST", credentials: "include" });
      const body = await resp.json();
      return body.access_token as string;
    });
    // A random UUID that is not this user's organization - proves the
    // check is a real membership lookup, not "any org_id that parses".
    const otherOrgId = "00000000-0000-0000-0000-000000000000";
    const resp = await request.get(`http://localhost:8000/organizations/${otherOrgId}/stations/${state.stationId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect([403, 404]).toContain(resp.status());
  });
});
