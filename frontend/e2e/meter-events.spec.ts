import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Phase 10a — Meter Event Management UI. Uses its own, dedicated station
 * (created here via the real API, the same way global-setup.ts seeds its
 * other stations) rather than station 2 or 3, which are already used by
 * daily-entry.spec.ts and daily-entry-roles.spec.ts and would race on the
 * same one-shift-per-day slot.
 */

const API_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

const state = JSON.parse(readFileSync(path.join(__dirname, ".e2e-state.json"), "utf-8")) as {
  ownerEmail: string;
  ownerPassword: string;
  orgId: string;
  stationId2: string;
};

async function apiLogin(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${API_BASE}/auth/login`, {
    data: { email: state.ownerEmail, password: state.ownerPassword },
  });
  const body = await resp.json();
  return body.access_token as string;
}

async function uiLogin(page: Page) {
  await page.goto("/login");
  await page.fill("#email", state.ownerEmail);
  await page.fill("#password", state.ownerPassword);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe("Meter event management", () => {
  test("a flagged meter event blocks shift approval until an authorized user approves it, and appears in the Meter Events history", async ({
    page,
    request,
  }) => {
    const token = await apiLogin(request);
    const auth = { Authorization: `Bearer ${token}` };
    const runId = Date.now().toString(36);

    const station = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations`, {
        headers: auth,
        data: { name: "E2E Meter Events Station", code: `E2EME-${runId}` },
      })
    ).json();
    const fuelGrade = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/fuel-grades`, {
        headers: auth,
        data: { name: "E2E ME Petrol", code: `EMP${runId.slice(-4)}` },
      })
    ).json();
    const tank = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations/${station.id}/tanks`, {
        headers: auth,
        data: { code: "T1", name: "Tank 1", fuel_grade_id: fuelGrade.id, capacity: "20000", safe_fill_limit: "18000" },
      })
    ).json();
    const dispenser = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations/${station.id}/dispensers`, {
        headers: auth,
        data: { code: "D1", name: "Dispenser 1" },
      })
    ).json();
    await request.post(
      `${API_BASE}/organizations/${state.orgId}/stations/${station.id}/dispensers/${dispenser.id}/nozzles`,
      { headers: auth, data: { code: "N1", tank_id: tank.id } }
    );
    await request.post(`${API_BASE}/organizations/${state.orgId}/stations/${station.id}/fuel-prices`, {
      headers: auth,
      data: { fuel_grade_id: fuelGrade.id, price_per_litre: "280.00", effective_from: "2020-01-01T00:00:00Z" },
    });

    // Stock via a full tanker-receipt lifecycle - never a direct ledger
    // write, same append-only rule the backend itself enforces.
    const supplier = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/suppliers`, {
        headers: auth,
        data: { name: "E2E ME Supplier" },
      })
    ).json();
    const receipt = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations/${station.id}/tanker-receipts`, {
        headers: auth,
        data: {
          tank_id: tank.id,
          supplier_id: supplier.id,
          tanker_registration: "E2E-ME-TRK",
          invoice_quantity: "10000",
          dispatched_quantity: "10000",
          pre_receipt_tank_reading: "0",
        },
      })
    ).json();
    await request.patch(
      `${API_BASE}/organizations/${state.orgId}/stations/${station.id}/tanker-receipts/${receipt.id}/record-unload`,
      { headers: auth, data: { post_receipt_tank_reading: "10000" } }
    );
    await request.patch(
      `${API_BASE}/organizations/${state.orgId}/stations/${station.id}/tanker-receipts/${receipt.id}/approve`,
      {
        headers: auth,
        data: { accepted_quantity: "10000", payable_quantity_basis: "invoice_quantity", payable_quantity: "10000" },
      }
    );

    await uiLogin(page);
    await page.goto(`/dashboard/org/${state.orgId}/station/${station.id}/daily-entry`);
    await expect(page.getByText("Nothing recorded for this business date")).toBeVisible();
    await page.getByRole("button", { name: "Start today's entry" }).click();
    await page.getByRole("tab", { name: "Pump Readings" }).click();

    const nozzleRow = page.locator("div.rounded-lg.border", { has: page.getByText("D1 / N1") });
    await nozzleRow.getByPlaceholder("Opening totalizer").fill("500");
    await nozzleRow.getByRole("button", { name: "Save" }).click();
    await expect(nozzleRow.getByText("Closing reading")).toBeVisible();

    // A meter rollover: the fresh totalizer value (100) is lower than the
    // opening reading (500) - the UI's own warning should surface first.
    await nozzleRow.getByPlaceholder("Closing totalizer").fill("100");
    await expect(page.getByText("This reading is lower than the opening reading")).toBeVisible();

    await nozzleRow.getByText("This meter was reset, replaced, or rolled over mid-shift").click();
    await nozzleRow.getByLabel("Meter event type").selectOption("rollover");
    await nozzleRow.getByPlaceholder("Pre-event reading *").fill("999");
    await nozzleRow.getByPlaceholder("Post-event reading *").fill("0");
    await nozzleRow.getByPlaceholder("Notes (optional)").fill("E2E rollover test");
    await nozzleRow.getByRole("button", { name: "Save" }).click();
    await page.getByRole("button", { name: "Yes, flag this meter event" }).click();
    await expect(page.getByText("L sold today", { exact: false })).toBeVisible();

    // Review tab: the unapproved event both blocks approval and now shows
    // its own inline approve action (the Phase 9 audit's specific gap).
    // Exact match: the pre-existing static checklist label "No flagged
    // meter events awaiting approval" contains this same substring, and
    // getByText's default match is case-insensitive substring.
    await page.getByRole("tab", { name: "Review & Submit" }).click();
    const meterEventsCardTitle = page.getByText("Meter events awaiting approval", { exact: true });
    await expect(meterEventsCardTitle).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve today's entry" })).toBeDisabled();
    await page.getByRole("button", { name: "Approve event" }).click();
    // The approve call refetches every Review tab data source (nozzle
    // readings, cash movements, reconciliation, tenders, expenses) before
    // the card unmounts - slower than the default 5s under load.
    await expect(meterEventsCardTitle).toHaveCount(0, { timeout: 15000 });

    // The dedicated Meter Events history page shows the same event, now approved.
    await page.goto(`/dashboard/org/${state.orgId}/station/${station.id}/meter-events`);
    await expect(page.getByRole("table").getByText("Meter rollover", { exact: true })).toBeVisible();
    await expect(page.getByRole("table").getByText("Approved", { exact: true }).first()).toBeVisible();
  });

  test("a user scoped only to a different station sees Access restricted on this station's Meter Events page", async ({
    page,
    request,
  }) => {
    const token = await apiLogin(request);
    const auth = { Authorization: `Bearer ${token}` };

    const unrelatedStation = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/stations`, {
        headers: auth,
        data: { name: "E2E Meter Events Isolation Station", code: `E2EMEI-${Date.now().toString(36)}` },
      })
    ).json();

    const roles = await (await request.get(`${API_BASE}/roles`, { headers: auth })).json();
    const cashierRole = roles.find((r: { name: string }) => r.name === "Cashier / Operator");
    const runId = Date.now().toString(36);
    const email = `e2e-me-isolation-${runId}@e2e-dev.com`;
    const password = "E2eMeIsolation!23";
    const created = await (
      await request.post(`${API_BASE}/organizations/${state.orgId}/users`, {
        headers: auth,
        data: { email, full_name: "E2E ME Isolation", password },
      })
    ).json();
    // Granted at station 2 only - never at the unrelated station below -
    // so require_permission's own station-scoping (not just hidden nav) is
    // what this test actually proves.
    await request.post(`${API_BASE}/organizations/${state.orgId}/users/${created.id}/roles`, {
      headers: auth,
      data: { role_id: cashierRole.id, station_id: state.stationId2 },
    });

    await page.goto("/login");
    await page.fill("#email", email);
    await page.fill("#password", password);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto(`/dashboard/org/${state.orgId}/station/${unrelatedStation.id}/meter-events`);
    await expect(page.getByText("Access restricted")).toBeVisible();
  });
});
