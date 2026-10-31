import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";

// Overridable via E2E_API_BASE_URL for a machine where :8000 is already
// taken by something else - see playwright.config.ts's own E2E_BASE_URL.
const API_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
const RUN_ID = Date.now().toString(36);

const SUPERUSER_EMAIL = `e2e-admin-${RUN_ID}@cynvexa-platform-dev.com`;
const SUPERUSER_PASSWORD = "E2eSuperuserPass!23";
const OWNER_EMAIL = `e2e-owner-${RUN_ID}@e2e-dev.com`;
const OWNER_PASSWORD = "E2eOwnerPass!23";

async function json<T>(url: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${init.method ?? "GET"} ${url} -> ${resp.status}: ${body}`);
  }
  return (await resp.json()) as T;
}

/**
 * Seeds a dedicated, uniquely-named organization/station/user/fuel master
 * data and one fully approved shift (so the dashboard's reports have real
 * data to show) through the actual API - not fixtures or a direct DB
 * write - so this exercises the same code path a real admin would.
 */
export default async function globalSetup() {
  const repoRoot = path.resolve(__dirname, "..", "..");

  // The backend/frontend containers must already be running
  // (docker compose up -d) - this just seeds data into them.
  execSync(
    `docker compose exec -T backend python -m app.seed superuser --email ${SUPERUSER_EMAIL} --password "${SUPERUSER_PASSWORD}" --full-name "E2E Admin"`,
    { cwd: repoRoot, stdio: "inherit" }
  );
  execSync("docker compose exec -T backend python -m app.seed permissions-roles", {
    cwd: repoRoot,
    stdio: "inherit",
  });

  const adminLogin = await json<{ access_token: string }>(`${API_BASE}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email: SUPERUSER_EMAIL, password: SUPERUSER_PASSWORD }),
  });
  const adminAuth = { Authorization: `Bearer ${adminLogin.access_token}` };

  const org = await json<{ id: string }>(`${API_BASE}/organizations`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: `E2E Fuel Co ${RUN_ID}` }),
  });

  // Create the owner user directly against Postgres via the seed CLI would
  // need its own subcommand; instead, reuse the superuser to create the org
  // and a station, then bootstrap a second superuser as the "owner" so the
  // UI tests can sign in with a normal login - simplest path that still
  // exercises the real login/dashboard code, not a shortcut around auth.
  execSync(
    `docker compose exec -T backend python -m app.seed superuser --email ${OWNER_EMAIL} --password "${OWNER_PASSWORD}" --full-name "E2E Owner"`,
    { cwd: repoRoot, stdio: "inherit" }
  );

  const station = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: "E2E Station", code: `E2E-${RUN_ID}` }),
  });

  const fuelGrade = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/fuel-grades`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: "E2E Petrol", code: `EP${RUN_ID.slice(-4)}` }),
  });

  const tank = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations/${station.id}/tanks`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({
      code: "T1",
      name: "Tank 1",
      fuel_grade_id: fuelGrade.id,
      capacity: "20000",
      safe_fill_limit: "18000",
    }),
  });

  const dispenser = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station.id}/dispensers`,
    { method: "POST", headers: adminAuth, body: JSON.stringify({ code: "D1", name: "Dispenser 1" }) }
  );

  const nozzle = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station.id}/dispensers/${dispenser.id}/nozzles`,
    { method: "POST", headers: adminAuth, body: JSON.stringify({ code: "N1", tank_id: tank.id }) }
  );

  await json(`${API_BASE}/organizations/${org.id}/stations/${station.id}/fuel-prices`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({
      fuel_grade_id: fuelGrade.id,
      price_per_litre: "280.00",
      effective_from: "2020-01-01T00:00:00Z",
    }),
  });

  const paymentMethod = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/payment-methods`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: "Cash", code: "CASH", category: "cash" }),
  });

  // Stock the tank via a full tanker-receipt lifecycle (never write stock
  // directly - the same append-only ledger rule the backend itself
  // enforces).
  const supplier = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/suppliers`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: "E2E Supplier" }),
  });
  const receipt = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station.id}/tanker-receipts`,
    {
      method: "POST",
      headers: adminAuth,
      body: JSON.stringify({
        tank_id: tank.id,
        supplier_id: supplier.id,
        tanker_registration: "E2E-TRK",
        invoice_quantity: "10000",
        dispatched_quantity: "10000",
        pre_receipt_tank_reading: "0",
      }),
    }
  );
  await json(`${API_BASE}/organizations/${org.id}/stations/${station.id}/tanker-receipts/${receipt.id}/record-unload`, {
    method: "PATCH",
    headers: adminAuth,
    body: JSON.stringify({ post_receipt_tank_reading: "10000" }),
  });
  await json(`${API_BASE}/organizations/${org.id}/stations/${station.id}/tanker-receipts/${receipt.id}/approve`, {
    method: "PATCH",
    headers: adminAuth,
    body: JSON.stringify({
      accepted_quantity: "10000",
      payable_quantity_basis: "invoice_quantity",
      payable_quantity: "10000",
    }),
  });

  // A full shift lifecycle - open, read, close, tender, reconcile,
  // approve - so the daily-fuel-sales / tank-variance / reconciliation
  // report tabs have real rows to assert on.
  const shiftsBase = `${API_BASE}/organizations/${org.id}/stations/${station.id}/shifts`;
  const shift = await json<{ id: string }>(shiftsBase, { method: "POST", headers: adminAuth, body: JSON.stringify({}) });
  await json(`${shiftsBase}/${shift.id}/tank-readings/opening`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ tank_id: tank.id, dip_reading: "10000" }),
  });
  const nozzleReading = await json<{ id: string }>(`${shiftsBase}/${shift.id}/nozzle-readings`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ nozzle_id: nozzle.id, opening_totalizer: "0" }),
  });
  await json(`${shiftsBase}/${shift.id}/nozzle-readings/${nozzleReading.id}/close`, {
    method: "PATCH",
    headers: adminAuth,
    body: JSON.stringify({ closing_totalizer: "500" }),
  });
  await json(`${shiftsBase}/${shift.id}/tank-readings/closing`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ tank_id: tank.id, dip_reading: "9500" }),
  });
  await json(`${shiftsBase}/${shift.id}/close`, { method: "PATCH", headers: adminAuth, body: "{}" });
  await json(`${shiftsBase}/${shift.id}/tenders`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ payment_method_id: paymentMethod.id, amount: "140000" }),
  });
  await json(`${shiftsBase}/${shift.id}/reconciliation`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ actual_physical_cash: "140000" }),
  });
  await json(`${shiftsBase}/${shift.id}/approve`, { method: "PATCH", headers: adminAuth, body: "{}" });

  // An inventory item for the inventory-movement workflow test.
  const inventoryItem = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station.id}/inventory-items`,
    {
      method: "POST",
      headers: adminAuth,
      body: JSON.stringify({ sku: "E2E-OIL", name: "E2E Engine Oil", unit: "bottle", reorder_level: "5" }),
    }
  );

  // A pending expense for the approve-via-UI workflow test.
  await json(`${API_BASE}/organizations/${org.id}/expenses`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({
      category: "e2e",
      description: "E2E seeded expense",
      amount: "999",
      expense_date: "2026-01-01",
    }),
  });

  // A second, otherwise-identical station with no shift ever created on
  // it - station 1 above always has an approved "today" shift (needed by
  // the report tests), so it can never genuinely be "empty for today".
  // The Daily Entry workspace's own "start a new entry" flow needs a
  // station where today really has nothing yet.
  const station2 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: "E2E Station 2", code: `E2E2-${RUN_ID}` }),
  });
  const fuelGrade2 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/fuel-grades`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: "E2E Diesel", code: `ED${RUN_ID.slice(-4)}` }),
  });
  const tank2 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations/${station2.id}/tanks`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({
      code: "T1",
      name: "Tank 1",
      fuel_grade_id: fuelGrade2.id,
      capacity: "20000",
      safe_fill_limit: "18000",
    }),
  });
  const dispenser2 = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station2.id}/dispensers`,
    { method: "POST", headers: adminAuth, body: JSON.stringify({ code: "D1", name: "Dispenser 1" }) }
  );
  await json(`${API_BASE}/organizations/${org.id}/stations/${station2.id}/dispensers/${dispenser2.id}/nozzles`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ code: "N1", tank_id: tank2.id }),
  });
  await json(`${API_BASE}/organizations/${org.id}/stations/${station2.id}/fuel-prices`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({
      fuel_grade_id: fuelGrade2.id,
      price_per_litre: "280.00",
      effective_from: "2020-01-01T00:00:00Z",
    }),
  });
  // Give this tank real stock the same way Phase B always has - through
  // a full tanker-receipt lifecycle, never a direct ledger write.
  const supplier2 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/suppliers`, {
    method: "POST",
    headers: adminAuth,
    body: JSON.stringify({ name: "E2E Supplier 2" }),
  });
  const receipt2 = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station2.id}/tanker-receipts`,
    {
      method: "POST",
      headers: adminAuth,
      body: JSON.stringify({
        tank_id: tank2.id,
        supplier_id: supplier2.id,
        tanker_registration: "E2E-TRK-2",
        invoice_quantity: "10000",
        dispatched_quantity: "10000",
        pre_receipt_tank_reading: "0",
      }),
    }
  );
  await json(
    `${API_BASE}/organizations/${org.id}/stations/${station2.id}/tanker-receipts/${receipt2.id}/record-unload`,
    { method: "PATCH", headers: adminAuth, body: JSON.stringify({ post_receipt_tank_reading: "10000" }) }
  );
  await json(
    `${API_BASE}/organizations/${org.id}/stations/${station2.id}/tanker-receipts/${receipt2.id}/approve`,
    {
      method: "PATCH",
      headers: adminAuth,
      body: JSON.stringify({
        accepted_quantity: "10000",
        payable_quantity_basis: "invoice_quantity",
        payable_quantity: "10000",
      }),
    }
  );

  const state = {
    ownerEmail: OWNER_EMAIL,
    ownerPassword: OWNER_PASSWORD,
    orgId: org.id,
    stationId: station.id,
    stationId2: station2.id,
    inventoryItemId: inventoryItem.id,
  };
  writeFileSync(path.join(__dirname, ".e2e-state.json"), JSON.stringify(state, null, 2));
}
