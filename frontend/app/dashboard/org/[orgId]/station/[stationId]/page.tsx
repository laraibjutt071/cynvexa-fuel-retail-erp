"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { ExportButton } from "@/components/ExportButton";
import { DateRangeFilter, defaultDateRange } from "@/components/DateRangeFilter";
import { SalesOverTimeChart } from "@/components/charts/SalesOverTimeChart";
import { VarianceTrendChart } from "@/components/charts/VarianceTrendChart";
import { ReconciliationHistoryChart } from "@/components/charts/ReconciliationHistoryChart";
import { RevenueDonut } from "@/components/charts/RevenueDonut";
import { InventoryLevelsChart } from "@/components/charts/InventoryLevelsChart";
import { KpiStrip } from "@/components/dashboard/KpiStrip";
import { formatMoney, formatNumber } from "@/lib/format";
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
      <div className="flex flex-1 items-center justify-center">
        <p className="text-ink-soft">Loading…</p>
      </div>
    );
  }

  return (
    <div className="flex-1">
      <PageHeader
        title="Station dashboard"
        breadcrumbs={[
          { label: "Organizations", href: "/dashboard" },
          { label: "Station" },
        ]}
      />

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {availableTabs.length === 0 ? (
          <p className="text-sm text-ink-soft">
            Your role does not include dashboard visibility for this station.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Tabs
                tabs={availableTabs.map((t) => ({ id: t.id, label: t.label }))}
                active={activeTab ?? availableTabs[0].id}
                onChange={(id) => setActiveTab(id as Tab)}
              />
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
    </div>
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

  const gradeRevenue = new Map<string, number>();
  let totalLitresAll = 0;
  let totalRevenueAll = 0;
  let totalTenderAll = 0;
  let totalShifts = 0;
  for (const d of days ?? []) {
    totalShifts += d.shift_count;
    totalTenderAll += Number(d.total_tender_amount);
    for (const g of d.grades) {
      totalLitresAll += Number(g.litres_sold);
      totalRevenueAll += Number(g.expected_revenue);
      gradeRevenue.set(g.fuel_grade_name, (gradeRevenue.get(g.fuel_grade_name) ?? 0) + Number(g.expected_revenue));
    }
  }
  const dayCount = days?.length ?? 0;
  const avgLitresPerDay = dayCount > 0 ? totalLitresAll / dayCount : 0;

  return (
    <div className="space-y-6">
      {days && days.length > 0 && (
        <>
          <KpiStrip
            title="Sales snapshot"
            badge="live"
            items={[
              { label: "Total litres sold", value: `${formatNumber(totalLitresAll)} L` },
              { label: "Total expected revenue", value: `PKR ${formatMoney(totalRevenueAll)}` },
              { label: "Total tender received", value: `PKR ${formatMoney(totalTenderAll)}` },
              { label: "Approved shifts", value: formatNumber(totalShifts) },
              { label: "Days in range", value: formatNumber(dayCount) },
              { label: "Avg litres / day", value: `${formatNumber(Math.round(avgLitresPerDay))} L` },
            ]}
          />
          <RevenueDonut
            title="Revenue by fuel grade"
            centerLabel="total revenue"
            data={Array.from(gradeRevenue, ([label, value]) => ({ label, value }))}
          />
        </>
      )}

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
    </div>
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

  const withinCount = rows?.filter((r) => r.within_tolerance === true).length ?? 0;
  const outsideCount = rows?.filter((r) => r.within_tolerance === false).length ?? 0;
  const variancePercents = (rows ?? [])
    .map((r) => (r.closing_variance_percent === null ? null : Number(r.closing_variance_percent)))
    .filter((v): v is number => v !== null);
  const avgVariance = variancePercents.length > 0 ? variancePercents.reduce((s, v) => s + v, 0) / variancePercents.length : null;

  return (
    <div className="space-y-6">
      {rows && rows.length > 0 && (
        <KpiStrip
          title="Variance snapshot"
          badge="live"
          items={[
            { label: "Readings in range", value: String(rows.length) },
            { label: "Within tolerance", value: String(withinCount) },
            { label: "Outside tolerance", value: String(outsideCount) },
            { label: "Average variance", value: avgVariance === null ? null : `${avgVariance.toFixed(2)}%` },
          ]}
        />
      )}
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
    </div>
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

  const totalExpected = rows?.reduce((s, r) => s + Number(r.expected_fuel_revenue), 0) ?? 0;
  const totalTender = rows?.reduce((s, r) => s + Number(r.total_tender_amount), 0) ?? 0;
  const totalShortageExcess = rows?.reduce((s, r) => s + Number(r.cash_shortage_excess), 0) ?? 0;
  const needsAuthCount = rows?.filter((r) => r.requires_authorization && !r.authorized_at).length ?? 0;

  return (
    <div className="space-y-6">
      {rows && rows.length > 0 && (
        <KpiStrip
          title="Reconciliation snapshot"
          badge="live"
          items={[
            { label: "Shifts in range", value: formatNumber(rows.length) },
            { label: "Expected revenue", value: `PKR ${formatMoney(totalExpected)}` },
            { label: "Tender received", value: `PKR ${formatMoney(totalTender)}` },
            {
              label: "Shortage / excess",
              value: `PKR ${formatMoney(Math.abs(totalShortageExcess))}`,
              sublabel: totalShortageExcess < 0 ? "Shortage" : totalShortageExcess > 0 ? "Excess" : "Balanced",
            },
            { label: "Needs authorization", value: formatNumber(needsAuthCount) },
          ]}
        />
      )}
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
    </div>
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
  const [itemForm, setItemForm] = useState({
    sku: "",
    name: "",
    category: "other",
    unit: "pcs",
    reorder_level: "0",
    unit_cost: "",
    selling_price: "",
  });
  const [itemError, setItemError] = useState<string | null>(null);
  const [creatingItem, setCreatingItem] = useState(false);

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

  const lowStockCount = items?.filter((it) => it.below_reorder_level).length ?? 0;

  async function submitNewItem(e: React.FormEvent) {
    e.preventDefault();
    if (creatingItem) return;
    setCreatingItem(true);
    setItemError(null);
    try {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/inventory-items`, {
        method: "POST",
        body: JSON.stringify({
          sku: itemForm.sku,
          name: itemForm.name,
          category: itemForm.category,
          unit: itemForm.unit,
          reorder_level: itemForm.reorder_level || "0",
          unit_cost: itemForm.unit_cost || "0",
          selling_price: itemForm.selling_price || "0",
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not create this item." }));
        setItemError(body.detail ?? "Could not create this item.");
        return;
      }
      setItemForm({ sku: "", name: "", category: "other", unit: "pcs", reorder_level: "0", unit_cost: "", selling_price: "" });
      await load();
    } finally {
      setCreatingItem(false);
    }
  }

  return (
    <div className="space-y-6">
      {items && items.length > 0 && (
        <KpiStrip
          title="Inventory snapshot"
          badge="live"
          items={[
            { label: "Items tracked", value: String(items.length) },
            { label: "Below reorder level", value: String(lowStockCount) },
            { label: "Recent movements", value: movements ? String(movements.length) : null },
            { label: "Total stock value", value: `PKR ${formatMoney(items.reduce((sum, it) => sum + Number(it.stock_value), 0))}` },
          ]}
        />
      )}
      {items && items.length > 0 && <InventoryLevelsChart items={items} title="On-hand stock by item" />}

      {canManage && (
        <Card title="Add a lubricant / shop item" description="Create a new catalogue entry - motor oil, grease, filters, or any other shop item this station stocks.">
          <form onSubmit={submitNewItem} className="flex flex-wrap items-end gap-3">
            <label className="text-sm text-ink-soft">
              SKU
              <input
                required
                value={itemForm.sku}
                onChange={(e) => setItemForm({ ...itemForm, sku: e.target.value })}
                placeholder="e.g. OIL-5W30-1L"
                className="ml-2 w-36 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink-soft">
              Name
              <input
                required
                value={itemForm.name}
                onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })}
                placeholder="e.g. Engine Oil 5W-30 1L"
                className="ml-2 w-48 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink-soft">
              Category
              <select
                value={itemForm.category}
                onChange={(e) => setItemForm({ ...itemForm, category: e.target.value })}
                className="ml-2 rounded-md border border-border px-2 py-1.5 text-sm"
              >
                <option value="lubricant">Lubricant</option>
                <option value="filter">Filter</option>
                <option value="battery">Battery</option>
                <option value="accessory">Accessory</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label className="text-sm text-ink-soft">
              Unit
              <input
                required
                value={itemForm.unit}
                onChange={(e) => setItemForm({ ...itemForm, unit: e.target.value })}
                placeholder="pcs, litres, kg…"
                className="ml-2 w-24 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink-soft">
              Reorder level
              <input
                type="number"
                step="0.001"
                min="0"
                value={itemForm.reorder_level}
                onChange={(e) => setItemForm({ ...itemForm, reorder_level: e.target.value })}
                className="ml-2 w-28 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink-soft">
              Unit cost (PKR)
              <input
                type="number"
                step="0.01"
                min="0"
                value={itemForm.unit_cost}
                onChange={(e) => setItemForm({ ...itemForm, unit_cost: e.target.value })}
                placeholder="0.00"
                className="ml-2 w-28 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink-soft">
              Selling price (PKR)
              <input
                type="number"
                step="0.01"
                min="0"
                value={itemForm.selling_price}
                onChange={(e) => setItemForm({ ...itemForm, selling_price: e.target.value })}
                placeholder="0.00"
                className="ml-2 w-28 rounded-md border border-border px-2 py-1.5 text-sm"
              />
            </label>
            <button
              type="submit"
              disabled={creatingItem}
              className="rounded-md bg-brand-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {creatingItem ? "Adding…" : "Add item"}
            </button>
          </form>
          {itemError && <p className="mt-2 text-sm text-danger-600">{itemError}</p>}
        </Card>
      )}

      <Card title="On-hand stock" description="Always derived from the movement ledger, never hand-edited.">
        {!items ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-ink-soft">
            {canManage ? "No inventory items yet - add one above to get started." : "No inventory items yet."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-soft">
                <th className="py-2 pr-2">SKU</th>
                <th className="py-2 pr-2">Name</th>
                <th className="py-2 pr-2">Category</th>
                <th className="py-2 pr-2">On hand</th>
                <th className="py-2 pr-2">Reorder level</th>
                <th className="py-2 pr-2">Unit cost</th>
                <th className="py-2 pr-2">Stock value</th>
                <th className="py-2 pr-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-b border-border">
                  <td className="py-2 pr-2 text-ink">{it.sku}</td>
                  <td className="py-2 pr-2 text-ink">{it.name}</td>
                  <td className="py-2 pr-2 text-ink-soft capitalize">{it.category}</td>
                  <td className="py-2 pr-2 text-ink">
                    {it.on_hand} {it.unit}
                  </td>
                  <td className="py-2 pr-2 text-ink">{it.reorder_level}</td>
                  <td className="py-2 pr-2 text-ink">PKR {formatMoney(it.unit_cost)}</td>
                  <td className="py-2 pr-2 text-ink">PKR {formatMoney(it.stock_value)}</td>
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
