"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/Card";
import { ExportButton } from "@/components/ExportButton";
import { DateRangeFilter, defaultDateRange } from "@/components/DateRangeFilter";
import { SalesOverTimeChart } from "@/components/charts/SalesOverTimeChart";
import { VarianceTrendChart } from "@/components/charts/VarianceTrendChart";
import { ReconciliationHistoryChart } from "@/components/charts/ReconciliationHistoryChart";
import type {
  DailyFuelSalesDay,
  InventoryItemWithStock,
  InventoryMovement,
  ShiftReconciliationReportRow,
  TankVarianceReportRow,
} from "@/lib/types";

type Tab = "sales" | "variance" | "reconciliation" | "inventory";

const TABS: { id: Tab; label: string; permission: string }[] = [
  { id: "sales", label: "Daily fuel sales", permission: "report:read" },
  { id: "variance", label: "Tank variance", permission: "report:read" },
  { id: "reconciliation", label: "Shift & cash reconciliation", permission: "report:read" },
  { id: "inventory", label: "Shop / lubricant inventory", permission: "inventory_item:read" },
];

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function StationDashboardPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const isSuperuser = user?.is_superuser ?? false;

  // A superuser bypasses every server-side permission check (see
  // app/api/deps.py::require_permission) - `can()`, not this raw set, is
  // what every visibility decision on this page must go through, so a
  // superuser also sees fine-grained actions like "adjust" or "manage"
  // that aren't tied to a tab.
  const permissions = useMemo(() => {
    const perms = new Set<string>();
    for (const role of user?.station_roles ?? []) {
      if (role.organization_id === orgId && (role.station_id === null || role.station_id === stationId)) {
        role.permissions.forEach((p) => perms.add(p));
      }
    }
    return perms;
  }, [user, orgId, stationId]);
  const can = useCallback(
    (code: string) => isSuperuser || permissions.has(code),
    [isSuperuser, permissions]
  );

  const availableTabs = TABS.filter((t) => can(t.permission));
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") as Tab | null;
  const [activeTab, setActiveTab] = useState<Tab | null>(null);
  const [range, setRange] = useState(defaultDateRange());

  useEffect(() => {
    // Intentional: picks the tab a deep link asked for (?tab=variance,
    // used by the sidebar), falling back to the first visible tab, once
    // permissions are known - not synchronizing with an external system.
    if (!activeTab && availableTabs.length > 0) {
      const wanted = requestedTab && availableTabs.some((t) => t.id === requestedTab) ? requestedTab : availableTabs[0].id;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveTab(wanted);
    }
  }, [activeTab, availableTabs, requestedTab]);

  if (loading || !user) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-ink-soft">Loading…</p>
      </main>
    );
  }

  return (
    <main className="flex-1">
      <header className="border-b border-border bg-surface px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <Link href="/dashboard" className="text-xs text-brand-500 hover:underline">
              ← Back to organizations
            </Link>
            <h1 className="text-lg font-semibold text-ink">Station dashboard</h1>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {availableTabs.length === 0 ? (
          <p className="text-sm text-ink-soft">
            Your role does not include dashboard visibility for this station.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-1">
              <div className="flex gap-2" role="tablist">
                {availableTabs.map((t) => (
                  <button
                    key={t.id}
                    role="tab"
                    aria-selected={activeTab === t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`border-b-2 px-3 py-2 text-sm font-medium ${
                      activeTab === t.id
                        ? "border-brand-500 text-brand-500"
                        : "border-transparent text-ink-soft hover:text-ink"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              {activeTab !== "inventory" && <DateRangeFilter dateFrom={range.dateFrom} dateTo={range.dateTo} onChange={setRange} />}
            </div>

            {activeTab === "sales" && (
              <DailyFuelSalesTab orgId={orgId} stationId={stationId} authFetch={authFetch} range={range} />
            )}
            {activeTab === "variance" && (
              <TankVarianceTab orgId={orgId} stationId={stationId} authFetch={authFetch} range={range} />
            )}
            {activeTab === "reconciliation" && (
              <ReconciliationTab orgId={orgId} stationId={stationId} authFetch={authFetch} range={range} />
            )}
            {activeTab === "inventory" && (
              <InventoryTab
                orgId={orgId}
                stationId={stationId}
                authFetch={authFetch}
                canAdjust={can("inventory_movement:adjust")}
                canManage={can("inventory_item:manage")}
              />
            )}
          </>
        )}
      </div>
    </main>
  );
}

function DailyFuelSalesTab({
  orgId,
  stationId,
  authFetch,
  range,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  range: { dateFrom: string; dateTo: string };
}) {
  const [days, setDays] = useState<DailyFuelSalesDay[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const qs = `date_from=${range.dateFrom}&date_to=${range.dateTo}`;

  useEffect(() => {
    (async () => {
      setError(null);
      const resp = await authFetch(
        `/organizations/${orgId}/stations/${stationId}/reports/daily-fuel-sales?${qs}`
      );
      if (!resp.ok) {
        setError("Could not load the daily fuel sales report.");
        return;
      }
      setDays(await resp.json());
    })();
  }, [orgId, stationId, authFetch, qs]);

  return (
    <Card
      title="Daily fuel sales and litres"
      description="Derived from approved shifts' stock-ledger sale postings and expected revenue - never fabricated."
      action={
        <ExportButton
          path={`/organizations/${orgId}/stations/${stationId}/reports/daily-fuel-sales/export?${qs}`}
          filename="daily-fuel-sales.csv"
        />
      }
    >
      {error && <p className="text-sm text-danger-600">{error}</p>}
      {!days && !error && <p className="text-sm text-ink-soft">Loading…</p>}
      {days && days.length === 0 && <p className="text-sm text-ink-soft">No approved shifts in this range.</p>}
      {days && days.length > 0 && (
        <div className="mb-6">
          <SalesOverTimeChart days={days} title="Litres sold over time" />
        </div>
      )}
      {days && days.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-soft">
              <th className="py-2 pr-2">Date</th>
              <th className="py-2 pr-2">Shifts</th>
              <th className="py-2 pr-2">Fuel grade</th>
              <th className="py-2 pr-2">Litres sold</th>
              <th className="py-2 pr-2">Expected revenue</th>
              <th className="py-2 pr-2">Tender received</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) =>
              d.grades.map((g, i) => (
                <tr key={`${d.sale_date}-${g.fuel_grade_id}`} className="border-b border-border">
                  <td className="py-2 pr-2 text-ink">{i === 0 ? d.sale_date : ""}</td>
                  <td className="py-2 pr-2 text-ink">{i === 0 ? d.shift_count : ""}</td>
                  <td className="py-2 pr-2 text-ink">{g.fuel_grade_name}</td>
                  <td className="py-2 pr-2 text-ink">{g.litres_sold}</td>
                  <td className="py-2 pr-2 text-ink">{g.expected_revenue}</td>
                  <td className="py-2 pr-2 text-ink">{i === 0 ? d.total_tender_amount : ""}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function TankVarianceTab({
  orgId,
  stationId,
  authFetch,
  range,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  range: { dateFrom: string; dateTo: string };
}) {
  const [rows, setRows] = useState<TankVarianceReportRow[] | null>(null);
  const qs = `date_from=${range.dateFrom}&date_to=${range.dateTo}`;

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/reports/tank-variance?${qs}`);
      if (resp.ok) setRows(await resp.json());
    })();
  }, [orgId, stationId, authFetch, qs]);

  return (
    <Card
      title="Tank book-versus-physical variance"
      description="Every approved shift's projected book stock against its own closing physical reading."
      action={
        <ExportButton
          path={`/organizations/${orgId}/stations/${stationId}/reports/tank-variance/export?${qs}`}
          filename="tank-variance.csv"
        />
      }
    >
      {!rows ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-soft">No approved shifts in this range.</p>
      ) : (
        <>
        <div className="mb-6">
          <VarianceTrendChart rows={rows} title="Variance trend" />
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-soft">
              <th className="py-2 pr-2">Shift date</th>
              <th className="py-2 pr-2">Tank</th>
              <th className="py-2 pr-2">Closing book stock</th>
              <th className="py-2 pr-2">Physical reading</th>
              <th className="py-2 pr-2">Variance %</th>
              <th className="py-2 pr-2">Within tolerance</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-border">
                <td className="py-2 pr-2 text-ink">{r.shift_date}</td>
                <td className="py-2 pr-2 text-ink">{r.tank_code}</td>
                <td className="py-2 pr-2 text-ink">{r.closing_book_stock}</td>
                <td className="py-2 pr-2 text-ink">{r.physical_closing_reading ?? "—"}</td>
                <td className="py-2 pr-2 text-ink">{r.closing_variance_percent ?? "—"}</td>
                <td className="py-2 pr-2">
                  {r.within_tolerance === null ? (
                    "—"
                  ) : r.within_tolerance ? (
                    <span className="text-success-600">Yes</span>
                  ) : (
                    <span className="font-medium text-danger-600">No</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </>
      )}
    </Card>
  );
}

function ReconciliationTab({
  orgId,
  stationId,
  authFetch,
  range,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  range: { dateFrom: string; dateTo: string };
}) {
  const [rows, setRows] = useState<ShiftReconciliationReportRow[] | null>(null);
  const qs = `date_from=${range.dateFrom}&date_to=${range.dateTo}`;

  useEffect(() => {
    (async () => {
      const resp = await authFetch(
        `/organizations/${orgId}/stations/${stationId}/reports/shift-reconciliation?${qs}`
      );
      if (resp.ok) setRows(await resp.json());
    })();
  }, [orgId, stationId, authFetch, qs]);

  return (
    <Card
      title="Shift and cash reconciliation"
      description="Persisted figures from each shift's own reconciliation record - expected revenue, tender, and shortage/excess."
      action={
        <ExportButton
          path={`/organizations/${orgId}/stations/${stationId}/reports/shift-reconciliation/export?${qs}`}
          filename="shift-reconciliation.csv"
        />
      }
    >
      {!rows ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-soft">No shifts with a reconciliation in this range.</p>
      ) : (
        <>
        <div className="mb-6">
          <ReconciliationHistoryChart rows={rows} title="Expected vs. collected, per shift" />
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-soft">
              <th className="py-2 pr-2">Opened</th>
              <th className="py-2 pr-2">Status</th>
              <th className="py-2 pr-2">Expected revenue</th>
              <th className="py-2 pr-2">Tender</th>
              <th className="py-2 pr-2">Cash shortage/excess</th>
              <th className="py-2 pr-2">Needs authorization</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.shift_id} className="border-b border-border">
                <td className="py-2 pr-2 text-ink">{new Date(r.opened_at).toLocaleString()}</td>
                <td className="py-2 pr-2 text-ink">{r.status}</td>
                <td className="py-2 pr-2 text-ink">{r.expected_fuel_revenue}</td>
                <td className="py-2 pr-2 text-ink">{r.total_tender_amount}</td>
                <td className="py-2 pr-2 text-ink">{r.cash_shortage_excess}</td>
                <td className="py-2 pr-2">
                  {r.requires_authorization ? (
                    r.authorized_at ? (
                      <span className="text-success-600">Authorized</span>
                    ) : (
                      <span className="font-medium text-danger-600">Yes</span>
                    )
                  ) : (
                    "No"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </>
      )}
    </Card>
  );
}

function InventoryTab({
  orgId,
  stationId,
  authFetch,
  canAdjust,
  canManage,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  canAdjust: boolean;
  canManage: boolean;
}) {
  const [items, setItems] = useState<InventoryItemWithStock[] | null>(null);
  const [movements, setMovements] = useState<InventoryMovement[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ inventory_item_id: "", movement_type: "receipt", quantity: "", amount: "", reason: "" });

  const load = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/inventory-items`);
    if (resp.ok) setItems(await resp.json());
    const mResp = await authFetch(`/organizations/${orgId}/stations/${stationId}/inventory-movements?limit=50`);
    if (mResp.ok) setMovements(await mResp.json());
  }, [orgId, stationId, authFetch]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function submitMovement(e: React.FormEvent) {
    e.preventDefault();
    // Guards against a double-click/double-tap recording the same
    // movement twice - there is no server-side idempotency key for this
    // endpoint yet (see docs/ASSUMPTIONS.md), so this is the only thing
    // standing between one click and two ledger rows today.
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, string> = {
        inventory_item_id: form.inventory_item_id,
        movement_type: form.movement_type,
        quantity: form.quantity,
      };
      if (form.amount) payload.amount = form.amount;
      if (form.reason) payload.reason = form.reason;
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/inventory-movements`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not record this movement." }));
        setError(body.detail ?? "Could not record this movement.");
        return;
      }
      setForm({ ...form, quantity: "", amount: "", reason: "" });
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  const isAdjustment = form.movement_type.startsWith("adjustment");

  return (
    <div className="space-y-6">
      <Card title="On-hand stock" description="Always derived from the movement ledger, never hand-edited.">
        {!items ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-ink-soft">
            No inventory items yet{canManage ? " - add one via the API to get started." : "."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-soft">
                <th className="py-2 pr-2">SKU</th>
                <th className="py-2 pr-2">Name</th>
                <th className="py-2 pr-2">On hand</th>
                <th className="py-2 pr-2">Reorder level</th>
                <th className="py-2 pr-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-b border-border">
                  <td className="py-2 pr-2 text-ink">{it.sku}</td>
                  <td className="py-2 pr-2 text-ink">{it.name}</td>
                  <td className="py-2 pr-2 text-ink">
                    {it.on_hand} {it.unit}
                  </td>
                  <td className="py-2 pr-2 text-ink">{it.reorder_level}</td>
                  <td className="py-2 pr-2">
                    {it.below_reorder_level ? (
                      <span className="font-medium text-warning-600">Low stock</span>
                    ) : (
                      <span className="text-success-600">OK</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {items && items.length > 0 && (
        <Card title="Record a movement" description="Receipt, issue, sale, or (with the adjust permission) a stock adjustment.">
          <form onSubmit={submitMovement} className="flex flex-wrap items-end gap-3">
            <label className="text-sm text-ink-soft">
              Item
              <select
                required
                value={form.inventory_item_id}
                onChange={(e) => setForm({ ...form, inventory_item_id: e.target.value })}
                className="ml-2 rounded-md border border-border px-2 py-1.5 text-sm"
              >
                <option value="" disabled>
                  Select…
                </option>
                {items.map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.sku}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-ink-soft">
              Type
              <select
                value={form.movement_type}
                onChange={(e) => setForm({ ...form, movement_type: e.target.value })}
                className="ml-2 rounded-md border border-border px-2 py-1.5 text-sm"
              >
                <option value="receipt">Receipt</option>
                <option value="issue">Issue</option>
                <option value="sale">Sale</option>
                {canAdjust && <option value="adjustment_increase">Adjustment (increase)</option>}
                {canAdjust && <option value="adjustment_decrease">Adjustment (decrease)</option>}
              </select>
            </label>
            <label className="text-sm text-ink-soft">
              Quantity
              <input
                required
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: e.target.value })}
                className="ml-2 w-24 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink-soft">
              Amount
              <input
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
                placeholder="optional"
                className="ml-2 w-28 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            {isAdjustment && (
              <label className="text-sm text-ink-soft">
                Reason
                <input
                  required
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  className="ml-2 w-48 rounded-md border border-border px-2 py-1.5 text-sm"
                />
              </label>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="rounded-md bg-brand-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {submitting ? "Recording…" : "Record"}
            </button>
          </form>
          {error && <p className="mt-2 text-sm text-danger-600">{error}</p>}
        </Card>
      )}

      <Card title="Recent movements">
        {!movements ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : movements.length === 0 ? (
          <p className="text-sm text-ink-soft">No movements recorded yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-soft">
                <th className="py-2 pr-2">When</th>
                <th className="py-2 pr-2">Type</th>
                <th className="py-2 pr-2">Quantity</th>
                <th className="py-2 pr-2">Amount</th>
                <th className="py-2 pr-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {movements.map((m) => (
                <tr key={m.id} className="border-b border-border">
                  <td className="py-2 pr-2 text-ink">{new Date(m.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-2 text-ink">{m.movement_type}</td>
                  <td className="py-2 pr-2 text-ink">{m.quantity}</td>
                  <td className="py-2 pr-2 text-ink">{m.amount ?? "—"}</td>
                  <td className="py-2 pr-2 text-ink">{m.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
