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

  // Phase 5b closed the is_superuser bypass for tenant business-data
  // reads/writes - a bare superuser can no longer create stations, fuel
  // masters, shifts, etc. directly. The organization and its owner are
  // provisioned the same way a real platform admin would ("Create Petrol
  // Pump", app/api/platform.py::onboard_organization), which needs a
  // Plan to exist; tolerate a 409 from an earlier test run having already
  // created it (the plan catalog is global, not per-run).
  try {
    await json(`${API_BASE}/platform/plans`, {
      method: "POST",
      headers: adminAuth,
      body: JSON.stringify({
        code: "starter",
        name: "Starter",
        price_monthly: "15000.00",
        price_annual: "150000.00",
        max_stations: 50,
        max_users: 200,
      }),
    });
  } catch (err) {
    if (!(err instanceof Error) || !err.message.includes("409")) throw err;
  }

  const onboarding = await json<{ organization_id: string; station_id: string }>(
    `${API_BASE}/platform/organizations`,
    {
      method: "POST",
      headers: adminAuth,
      body: JSON.stringify({
        company_name: `E2E Fuel Co ${RUN_ID}`,
        station_name: "E2E Station",
        owner_full_name: "E2E Owner",
        owner_email: OWNER_EMAIL,
        owner_password: OWNER_PASSWORD,
        plan_code: "starter",
      }),
    }
  );
  const org = { id: onboarding.organization_id };
  const station = { id: onboarding.station_id };

  // Every call below acts on this organization's own business data, so it
  // authenticates as its real Owner (who holds every permission in their
  // own org) rather than the platform superuser, which no longer bypasses
  // tenant RBAC (Phase 5b) - this also exercises the real role-based
  // permission path every other tenant user goes through.
  const ownerLogin = await json<{ access_token: string }>(`${API_BASE}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email: OWNER_EMAIL, password: OWNER_PASSWORD }),
  });
  const ownerAuth = { Authorization: `Bearer ${ownerLogin.access_token}` };

  const fuelGrade = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/fuel-grades`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ name: "E2E Petrol", code: `EP${RUN_ID.slice(-4)}` }),
  });

  const tank = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations/${station.id}/tanks`, {
    method: "POST",
    headers: ownerAuth,
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
    { method: "POST", headers: ownerAuth, body: JSON.stringify({ code: "D1", name: "Dispenser 1" }) }
  );

  const nozzle = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station.id}/dispensers/${dispenser.id}/nozzles`,
    { method: "POST", headers: ownerAuth, body: JSON.stringify({ code: "N1", tank_id: tank.id }) }
  );

  await json(`${API_BASE}/organizations/${org.id}/stations/${station.id}/fuel-prices`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({
      fuel_grade_id: fuelGrade.id,
      price_per_litre: "280.00",
      effective_from: "2020-01-01T00:00:00Z",
    }),
  });

  const paymentMethod = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/payment-methods`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ name: "Cash", code: "CASH", category: "cash" }),
  });

  // Stock the tank via a full tanker-receipt lifecycle (never write stock
  // directly - the same append-only ledger rule the backend itself
  // enforces).
  const supplier = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/suppliers`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ name: "E2E Supplier" }),
  });
  const receipt = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station.id}/tanker-receipts`,
    {
      method: "POST",
      headers: ownerAuth,
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
    headers: ownerAuth,
    body: JSON.stringify({ post_receipt_tank_reading: "10000" }),
  });
  await json(`${API_BASE}/organizations/${org.id}/stations/${station.id}/tanker-receipts/${receipt.id}/approve`, {
    method: "PATCH",
    headers: ownerAuth,
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
  const shift = await json<{ id: string }>(shiftsBase, { method: "POST", headers: ownerAuth, body: JSON.stringify({}) });
  await json(`${shiftsBase}/${shift.id}/tank-readings/opening`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ tank_id: tank.id, dip_reading: "10000" }),
  });
  const nozzleReading = await json<{ id: string }>(`${shiftsBase}/${shift.id}/nozzle-readings`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ nozzle_id: nozzle.id, opening_totalizer: "0" }),
  });
  await json(`${shiftsBase}/${shift.id}/nozzle-readings/${nozzleReading.id}/close`, {
    method: "PATCH",
    headers: ownerAuth,
    body: JSON.stringify({ closing_totalizer: "500" }),
  });
  await json(`${shiftsBase}/${shift.id}/tank-readings/closing`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ tank_id: tank.id, dip_reading: "9500" }),
  });
  await json(`${shiftsBase}/${shift.id}/close`, { method: "PATCH", headers: ownerAuth, body: "{}" });
  await json(`${shiftsBase}/${shift.id}/tenders`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ payment_method_id: paymentMethod.id, amount: "140000" }),
  });
  await json(`${shiftsBase}/${shift.id}/reconciliation`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ actual_physical_cash: "140000" }),
  });
  await json(`${shiftsBase}/${shift.id}/approve`, { method: "PATCH", headers: ownerAuth, body: "{}" });

  // An inventory item for the inventory-movement workflow test.
  const inventoryItem = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station.id}/inventory-items`,
    {
      method: "POST",
      headers: ownerAuth,
      body: JSON.stringify({ sku: "E2E-OIL", name: "E2E Engine Oil", unit: "bottle", reorder_level: "5" }),
    }
  );

  // A pending expense for the approve-via-UI workflow test.
  await json(`${API_BASE}/organizations/${org.id}/expenses`, {
    method: "POST",
    headers: ownerAuth,
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
    headers: ownerAuth,
    body: JSON.stringify({ name: "E2E Station 2", code: `E2E2-${RUN_ID}` }),
  });
  const fuelGrade2 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/fuel-grades`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ name: "E2E Diesel", code: `ED${RUN_ID.slice(-4)}` }),
  });
  const tank2 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations/${station2.id}/tanks`, {
    method: "POST",
    headers: ownerAuth,
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
    { method: "POST", headers: ownerAuth, body: JSON.stringify({ code: "D1", name: "Dispenser 1" }) }
  );
  await json(`${API_BASE}/organizations/${org.id}/stations/${station2.id}/dispensers/${dispenser2.id}/nozzles`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ code: "N1", tank_id: tank2.id }),
  });
  await json(`${API_BASE}/organizations/${org.id}/stations/${station2.id}/fuel-prices`, {
    method: "POST",
    headers: ownerAuth,
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
    headers: ownerAuth,
    body: JSON.stringify({ name: "E2E Supplier 2" }),
  });
  const receipt2 = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station2.id}/tanker-receipts`,
    {
      method: "POST",
      headers: ownerAuth,
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
    { method: "PATCH", headers: ownerAuth, body: JSON.stringify({ post_receipt_tank_reading: "10000" }) }
  );
  await json(
    `${API_BASE}/organizations/${org.id}/stations/${station2.id}/tanker-receipts/${receipt2.id}/approve`,
    {
      method: "PATCH",
      headers: ownerAuth,
      body: JSON.stringify({
        accepted_quantity: "10000",
        payable_quantity_basis: "invoice_quantity",
        payable_quantity: "10000",
      }),
    }
  );

  // A third station, dedicated to Phase 5's role-based Daily Entry tests
  // (e2e/daily-entry-roles.spec.ts) - station 2 above is already used by
  // the pre-existing full-workflow test (e2e/daily-entry.spec.ts), which
  // starts and closes "today's" shift there; sharing it with the
  // role-based tests would race on the same one-shift-per-day slot.
  const station3 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ name: "E2E Station 3", code: `E2E3-${RUN_ID}` }),
  });
  const fuelGrade3 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/fuel-grades`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ name: "E2E Kerosene", code: `EK${RUN_ID.slice(-4)}` }),
  });
  const tank3 = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/stations/${station3.id}/tanks`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({
      code: "T1",
      name: "Tank 1",
      fuel_grade_id: fuelGrade3.id,
      capacity: "20000",
      safe_fill_limit: "18000",
    }),
  });
  const dispenser3 = await json<{ id: string }>(
    `${API_BASE}/organizations/${org.id}/stations/${station3.id}/dispensers`,
    { method: "POST", headers: ownerAuth, body: JSON.stringify({ code: "D1", name: "Dispenser 1" }) }
  );
  await json(`${API_BASE}/organizations/${org.id}/stations/${station3.id}/dispensers/${dispenser3.id}/nozzles`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({ code: "N1", tank_id: tank3.id }),
  });
  await json(`${API_BASE}/organizations/${org.id}/stations/${station3.id}/fuel-prices`, {
    method: "POST",
    headers: ownerAuth,
    body: JSON.stringify({
      fuel_grade_id: fuelGrade3.id,
      price_per_litre: "280.00",
      effective_from: "2020-01-01T00:00:00Z",
    }),
  });

  // Real, role-scoped users, created through the real API (POST
  // .../users, then POST .../users/{id}/roles) using the real Owner's own
  // token - the same way an Owner would add staff in production - so
  // frontend permission-gating tests see real role data.
  const roles = await json<{ id: string; name: string }[]>(`${API_BASE}/roles`, { headers: ownerAuth });
  const roleId = (name: string) => {
    const role = roles.find((r) => r.name === name);
    if (!role) throw new Error(`Seed role "${name}" not found - was permissions-roles seeded?`);
    return role.id;
  };

  const ROLE_PASSWORD = "E2eRolePass!23";
  async function createRoleUser(roleName: string, stationScoped: boolean): Promise<{ email: string; password: string }> {
    const slug = roleName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
    const email = `e2e-role-${slug}-${RUN_ID}@e2e-dev.com`;
    const created = await json<{ id: string }>(`${API_BASE}/organizations/${org.id}/users`, {
      method: "POST",
      headers: ownerAuth,
      body: JSON.stringify({ email, full_name: `E2E ${roleName}`, password: ROLE_PASSWORD }),
    });
    await json(`${API_BASE}/organizations/${org.id}/users/${created.id}/roles`, {
      method: "POST",
      headers: ownerAuth,
      body: JSON.stringify({ role_id: roleId(roleName), station_id: stationScoped ? station.id : null }),
    });
    if (stationScoped) {
      // Also grant the same role at station 3 - the station dedicated to
      // Phase 5's role-based Daily Entry tests (see station3's own
      // comment above for why not station 1 or 2).
      await json(`${API_BASE}/organizations/${org.id}/users/${created.id}/roles`, {
        method: "POST",
        headers: ownerAuth,
        body: JSON.stringify({ role_id: roleId(roleName), station_id: station3.id }),
      });
    }
    return { email, password: ROLE_PASSWORD };
  }

  const realOwner = await createRoleUser("Owner", false);
  const stationManager = await createRoleUser("Station Manager", true);
  const shiftSupervisor = await createRoleUser("Shift Supervisor", true);
  const cashier = await createRoleUser("Cashier / Operator", true);
  const accountant = await createRoleUser("Accountant", true);
  const storekeeper = await createRoleUser("Storekeeper / Technician", true);
  const auditor = await createRoleUser("Auditor / Viewer", true);

  const state = {
    adminEmail: SUPERUSER_EMAIL,
    adminPassword: SUPERUSER_PASSWORD,
    ownerEmail: OWNER_EMAIL,
    ownerPassword: OWNER_PASSWORD,
    orgId: org.id,
    stationId: station.id,
    stationId2: station2.id,
    stationId3: station3.id,
    inventoryItemId: inventoryItem.id,
    roles: {
      owner: realOwner,
      stationManager,
      shiftSupervisor,
      cashier,
      accountant,
      storekeeper,
      auditor,
    },
  };
  writeFileSync(path.join(__dirname, ".e2e-state.json"), JSON.stringify(state, null, 2));
}
