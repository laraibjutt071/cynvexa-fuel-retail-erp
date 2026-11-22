"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  Banknote,
  Bell,
  Clock,
  Fuel,
  Receipt,
  RefreshCw,
  UserCheck,
  Users,
  Wallet,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { formatLitres, formatMoney, formatNumber } from "@/lib/format";
import { DateRangeFilter, defaultDateRange } from "@/components/DateRangeFilter";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { StatCard, StatCardGrid } from "@/components/ui/StatCard";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { StationBarChart } from "@/components/charts/StationBarChart";
import { DailySalesTrendChart } from "@/components/charts/DailySalesTrendChart";
import type {
  AuditLogEntry,
  OrgAttendanceReport,
  OrgDailySalesReport,
  OrgExpenseReport,
  OrgRevenueReport,
  OrgSalesReport,
  OrgStationPerformanceReport,
  OrgStockReport,
  OrgUser,
  PendingApprovalsReport,
  StationPerformanceRow,
  SupplierBalance,
} from "@/lib/types";

const AUTO_REFRESH_INTERVAL_MS = 60_000;

type Tab = "overview" | "stock" | "attendance" | "comparison";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "stock", label: "Stock" },
  { id: "attendance", label: "Attendance" },
  { id: "comparison", label: "Station Comparison" },
];

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function CompanyOverviewPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { authFetch } = useAuth();
  const { can, loading: permLoading } = usePermissions(orgId);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [{ dateFrom, dateTo }, setRange] = useState(defaultDateRange());

  if (permLoading) {
    return <div className="flex-1 px-6 py-10 text-sm text-ink-soft">Loading…</div>;
  }

  if (!can("report:read")) {
    return (
      <div className="flex-1">
        <PageHeader title="Company Overview" breadcrumbs={[{ label: "Dashboard" }, { label: "Company Overview" }]} />
        <div className="mx-auto max-w-3xl px-6 py-10">
          <AccessDenied message="Your role does not include organization-wide report visibility." />
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1">
      <PageHeader
        title="Company Overview"
        description="Combined figures across every station you're authorized to see."
        breadcrumbs={[{ label: "Dashboard" }, { label: "Company Overview" }]}
        action={<DateRangeFilter dateFrom={dateFrom} dateTo={dateTo} onChange={setRange} />}
      />
      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Tabs tabs={TABS} active={activeTab} onChange={(id) => setActiveTab(id as Tab)} />
        {activeTab === "overview" && <OverviewTab orgId={orgId} authFetch={authFetch} dateFrom={dateFrom} dateTo={dateTo} />}
        {activeTab === "stock" && <StockTab orgId={orgId} authFetch={authFetch} />}
        {activeTab === "attendance" && <AttendanceTab orgId={orgId} authFetch={authFetch} dateFrom={dateFrom} dateTo={dateTo} />}
        {activeTab === "comparison" && <ComparisonTab orgId={orgId} authFetch={authFetch} dateFrom={dateFrom} dateTo={dateTo} />}
      </div>
    </div>
  );
}

interface OverviewData {
  sales: OrgSalesReport;
  revenue: OrgRevenueReport;
  expenses: OrgExpenseReport;
  dailySales: OrgDailySalesReport;
  supplierBalances: SupplierBalance[] | null;
  pendingApprovals: PendingApprovalsReport | null;
}

function OverviewTab({
  orgId,
  authFetch,
  dateFrom,
  dateTo,
}: {
  orgId: string;
  authFetch: AuthFetch;
  dateFrom: string;
  dateTo: string;
}) {
  const { can } = usePermissions(orgId);
  const canReadSuppliers = can("supplier_ledger:read");
  const canReadAudit = can("audit:read");

  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Prevents two overlapping fetch cycles (a manual click landing mid-way
  // through the 60s auto-refresh) within one date-range "generation", and
  // - critically - lets a date-range change invalidate any request still
  // in flight from the PREVIOUS generation, so its late response can never
  // overwrite newer data. A single shared boolean isn't enough for this:
  // if a background refresh is in flight exactly when dateFrom/dateTo
  // changes, resetting that boolean for the new generation would let the
  // stale request's own completion still win a race to write state. Each
  // request instead captures and checks its own generation number.
  const inFlightRef = useRef(false);
  const generationRef = useRef(0);

  const load = useCallback(
    async (isInitial: boolean) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      const myGeneration = generationRef.current;
      if (isInitial) {
        setError(null);
        setData(null);
      } else {
        setRefreshing(true);
      }
      try {
        const qs = `?date_from=${dateFrom}&date_to=${dateTo}`;
        const requests: Promise<Response>[] = [
          authFetch(`/organizations/${orgId}/reports/sales${qs}`),
          authFetch(`/organizations/${orgId}/reports/revenue${qs}`),
          authFetch(`/organizations/${orgId}/reports/expenses${qs}`),
          authFetch(`/organizations/${orgId}/reports/daily-sales${qs}`),
        ];
        const [salesResp, revenueResp, expensesResp, dailySalesResp] = await Promise.all(requests);
        if (generationRef.current !== myGeneration) return;
        if (!salesResp.ok || !revenueResp.ok || !expensesResp.ok || !dailySalesResp.ok) {
          const message = "Could not load the company overview for this date range.";
          if (isInitial) setError(message);
          else setRefreshError(message);
          return;
        }
        const [sales, revenue, expenses, dailySales] = await Promise.all([
          salesResp.json(),
          revenueResp.json(),
          expensesResp.json(),
          dailySalesResp.json(),
        ]);
        if (generationRef.current !== myGeneration) return;

        // Supplier balances and pending approvals are optional extras -
        // their own permission may not be held by every role that can see
        // the rest of this dashboard, so a missing grant degrades to
        // "section omitted", never a hard error for the whole page.
        const [supplierResp, pendingResp] = await Promise.all([
          canReadSuppliers ? authFetch(`/organizations/${orgId}/suppliers/balances`) : Promise.resolve(null),
          authFetch(`/organizations/${orgId}/reports/pending-approvals`),
        ]);
        if (generationRef.current !== myGeneration) return;
        const supplierBalances = supplierResp && supplierResp.ok ? await supplierResp.json() : null;
        const pendingApprovals = pendingResp.ok ? await pendingResp.json() : null;

        setData({ sales, revenue, expenses, dailySales, supplierBalances, pendingApprovals });
        setRefreshError(null);
        setLastUpdated(new Date());
      } finally {
        inFlightRef.current = false;
        setRefreshing(false);
      }
    },
    [authFetch, orgId, dateFrom, dateTo, canReadSuppliers]
  );

  useEffect(() => {
    // Starts a new generation - any request still in flight from the
    // previous one will find this mismatched when it resolves and quietly
    // discard its result instead of overwriting the new range's data.
    // Safe to also reset inFlightRef here: a stale in-flight request no
    // longer blocks the new generation's own load from starting, and that
    // stale request's generation check above still stops it from ever
    // writing state.
    generationRef.current += 1;
    inFlightRef.current = false;
    load(true);
    const interval = window.setInterval(() => load(false), AUTO_REFRESH_INTERVAL_MS);
    return () => {
      generationRef.current += 1;
      window.clearInterval(interval);
    };
    // Re-running on dateFrom/dateTo change intentionally restarts both the
    // initial load and the refresh timer for the new range.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, dateFrom, dateTo]);

  if (error) return <p className="text-sm text-danger-600">{error}</p>;
  if (!data) {
    return (
      <StatCardGrid>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card-glow h-24 animate-pulse rounded-xl bg-surface-muted" />
        ))}
      </StatCardGrid>
    );
  }

  const { sales, revenue, expenses, dailySales, supplierBalances, pendingApprovals } = data;
  const totalSupplierOutstanding = supplierBalances
    ? supplierBalances.reduce((sum, b) => sum + Number(b.balance), 0)
    : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-faint">
        <span className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" aria-hidden />
          {lastUpdated
            ? `Last updated ${lastUpdated.toLocaleTimeString()} - refreshes automatically every 60s`
            : "Loading…"}
          {refreshing && <span className="text-accent">Refreshing…</span>}
        </span>
        <Button size="sm" variant="secondary" onClick={() => load(false)} busy={refreshing}>
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          Refresh now
        </Button>
      </div>

      {refreshError && (
        <p className="flex items-center gap-2 rounded-lg border border-caution-200 bg-caution-50 px-3 py-2 text-xs text-caution-700">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          {refreshError} Showing the last successful figures below.
        </p>
      )}

      <StatCardGrid>
        <StatCard label="Total fuel sold" value={formatLitres(sales.total_litres_sold)} icon={Fuel} tone="brand" />
        <StatCard
          label="Total revenue"
          value={`PKR ${formatMoney(revenue.total_recognized_revenue)}`}
          icon={Wallet}
          tone="success"
          subtitle="Litres x price, never cash collected"
        />
        <StatCard
          label="Cash collected"
          value={`PKR ${formatMoney(revenue.cash_amount)}`}
          icon={Banknote}
          tone="neutral"
          subtitle={`of PKR ${formatMoney(revenue.total_tender_amount)} total tendered`}
        />
        <StatCard label="Approved expenses" value={`PKR ${formatMoney(expenses.grand_approved)}`} icon={Receipt} tone="warning" />
        {totalSupplierOutstanding !== null && (
          <StatCard
            label="Supplier outstanding balance"
            value={`PKR ${formatMoney(totalSupplierOutstanding)}`}
            icon={Wallet}
            tone={totalSupplierOutstanding > 0 ? "danger" : "success"}
            subtitle="Across every supplier, this organization"
          />
        )}
      </StatCardGrid>

      <Card
        title="Daily sales trend"
        description="Expected revenue per day from approved shifts, across every authorized station - refreshes automatically with the rest of this page."
      >
        <DailySalesTrendChart days={dailySales.days} />
      </Card>

      {pendingApprovals && <PendingApprovalsCard orgId={orgId} report={pendingApprovals} />}

      <Card
        title="Revenue by payment method"
        description="Cash, card, digital and credit are kept separate - credit sales are revenue, not cash in hand."
      >
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: "Cash", value: revenue.cash_amount, tone: "success" as const },
            { label: "Card", value: revenue.card_amount, tone: "brand" as const },
            { label: "Digital", value: revenue.digital_amount, tone: "neutral" as const },
            { label: "Credit", value: revenue.credit_amount, tone: "warning" as const },
          ].map((row) => (
            <div key={row.label} className="rounded-lg border border-border bg-surface-elevated p-3">
              <p className="text-xs text-ink-soft">{row.label}</p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-ink">PKR {formatMoney(row.value)}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Expense categories" description={`Grand total PKR ${formatMoney(expenses.grand_total)} (includes reversed entries); approved PKR ${formatMoney(expenses.grand_approved)}.`}>
        {expenses.by_category.length === 0 ? (
          <p className="text-sm text-ink-soft">No expenses recorded in this range.</p>
        ) : (
          <ul className="divide-y divide-border">
            {expenses.by_category.map((row) => (
              <li key={row.category} className="flex items-center justify-between py-2 text-sm">
                <span className="text-ink">{row.category}</span>
                <span className="tabular-nums text-ink-soft">
                  PKR {formatMoney(row.approved_amount)} approved / PKR {formatMoney(row.total_amount)} total
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {canReadAudit && <RecentActivityCard orgId={orgId} authFetch={authFetch} />}
    </div>
  );
}

const PENDING_APPROVAL_ITEMS: {
  key: keyof PendingApprovalsReport;
  label: string;
  linkLabel: string;
}[] = [
  { key: "shifts_awaiting_approval", label: "Shifts awaiting approval", linkLabel: "Review stations" },
  { key: "tanker_receipts_awaiting_approval", label: "Fuel receipts awaiting approval", linkLabel: "Review stations" },
  { key: "unapproved_meter_events", label: "Unapproved meter events", linkLabel: "Review stations" },
  { key: "reconciliations_requiring_authorization", label: "Cash discrepancies needing authorization", linkLabel: "Review stations" },
  { key: "unapproved_decreasing_cash_movements", label: "Cash movements awaiting approval", linkLabel: "Review stations" },
  { key: "pending_expenses", label: "Pending expenses", linkLabel: "Go to Expenses" },
  { key: "unapproved_supplier_payments", label: "Unapproved supplier payments", linkLabel: "Go to Suppliers" },
  { key: "low_stock_inventory_items", label: "Low-stock inventory items", linkLabel: "Review stations" },
];

function PendingApprovalsCard({ orgId, report }: { orgId: string; report: PendingApprovalsReport }) {
  const total = PENDING_APPROVAL_ITEMS.reduce((sum, item) => sum + report[item.key], 0);

  const linkFor = (key: keyof PendingApprovalsReport) => {
    if (key === "pending_expenses") return `/dashboard/org/${orgId}?tab=expenses`;
    if (key === "unapproved_supplier_payments") return `/dashboard/org/${orgId}/suppliers`;
    return `/dashboard/org/${orgId}/stations`;
  };

  return (
    <Card
      title="Pending approvals & attention centre"
      description="Everything awaiting a decision across every station you're authorized to see. Counts only - open the linked workflow to act."
      action={
        <span className="flex items-center gap-1.5 text-xs font-medium text-ink-soft">
          <Bell className="h-3.5 w-3.5" aria-hidden />
          {total} total
        </span>
      }
    >
      {total === 0 ? (
        <p className="text-sm text-ink-soft">Nothing is waiting on you right now.</p>
      ) : (
        <ul className="divide-y divide-border">
          {PENDING_APPROVAL_ITEMS.filter((item) => report[item.key] > 0).map((item) => (
            <li key={item.key} className="flex items-center justify-between py-2 text-sm">
              <span className="text-ink">{item.label}</span>
              <span className="flex items-center gap-3">
                <span className="rounded-full bg-caution-50 px-2 py-0.5 text-xs font-semibold text-caution-700">
                  {report[item.key]}
                </span>
                <Link href={linkFor(item.key)} className="text-xs font-medium text-accent hover:underline">
                  {item.linkLabel}
                </Link>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const ACTIVITY_ACTION_LABELS: Record<string, string> = {
  "shift.approve": "Shift approved",
  "shift.close": "Shift closed",
  "expense.approve": "Expense approved",
  "expense.create": "Expense recorded",
  "supplier_payment.approve": "Supplier payment approved",
  "supplier_payment.create": "Supplier payment recorded",
  "supplier_invoice.create": "Supplier invoice recorded",
  "shift.nozzle_reading.approve_meter_event": "Meter event approved",
  "shift.nozzle_reading.close": "Meter event flagged",
  "salary.generate": "Salary generated",
  "salary.finalize": "Salary finalized",
  "tanker_receipt.approve": "Fuel receipt approved",
};

function humanizeAction(action: string): string {
  return ACTIVITY_ACTION_LABELS[action] ?? action.replace(/[._]/g, " ");
}

function RecentActivityCard({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null);
  const [users, setUsers] = useState<OrgUser[]>([]);

  useEffect(() => {
    (async () => {
      const [logResp, usersResp] = await Promise.all([
        authFetch(`/organizations/${orgId}/audit-log?limit=8`),
        authFetch(`/organizations/${orgId}/users`),
      ]);
      if (logResp.ok) setEntries(await logResp.json());
      if (usersResp.ok) setUsers(await usersResp.json());
    })();
  }, [authFetch, orgId]);

  const nameFor = (userId: string | null) => {
    if (!userId) return "System";
    return users.find((u) => u.id === userId)?.full_name ?? userId.slice(0, 8);
  };

  return (
    <Card title="Recent activity" description="The latest recorded actions across every station you're authorized to see.">
      {!entries ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-ink-soft">No recent activity recorded yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {entries.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="flex items-center gap-2 text-ink">
                <Activity className="h-3.5 w-3.5 flex-shrink-0 text-ink-faint" aria-hidden />
                {humanizeAction(e.action)}
              </span>
              <span className="whitespace-nowrap text-xs text-ink-faint">
                {nameFor(e.actor_user_id)} · {new Date(e.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function StockTab({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const [stock, setStock] = useState<OrgStockReport | null>(null);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/reports/stock`);
      if (resp.ok) setStock(await resp.json());
    })();
  }, [authFetch, orgId]);

  const columns: Column<OrgStockReport["tanks"][number]>[] = [
    { key: "station", header: "Station", render: (r) => r.station_name },
    { key: "tank", header: "Tank", render: (r) => r.tank_code },
    { key: "grade", header: "Fuel grade", render: (r) => r.fuel_grade_name },
    { key: "book", header: "Book stock", align: "right", render: (r) => formatLitres(r.book_stock) },
    {
      key: "dip",
      header: "Last physical dip",
      align: "right",
      render: (r) =>
        r.last_physical_dip_reading !== null ? (
          <span title={r.last_physical_dip_at ?? undefined}>{formatLitres(r.last_physical_dip_reading)}</span>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <Card title="Fuel stock, by fuel grade" description="Book stock (ledger projection) across every authorized station - never summed with a physical dip reading.">
        {!stock ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : stock.by_fuel_grade.length === 0 ? (
          <p className="text-sm text-ink-soft">No tanks configured yet.</p>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {stock.by_fuel_grade.map((g) => (
              <div key={g.fuel_grade_id} className="rounded-lg border border-border bg-surface-elevated p-3">
                <p className="text-xs text-ink-soft">{g.fuel_grade_name}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums text-ink">{formatLitres(g.total_book_stock)}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card title="Tank-by-tank overview">
        <DataTable columns={columns} data={stock?.tanks ?? null} keyFn={(r) => r.tank_id} emptyMessage="No tanks found." />
      </Card>
    </div>
  );
}

function AttendanceTab({
  orgId,
  authFetch,
  dateFrom,
  dateTo,
}: {
  orgId: string;
  authFetch: AuthFetch;
  dateFrom: string;
  dateTo: string;
}) {
  const [report, setReport] = useState<OrgAttendanceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Stale-response guard - see OverviewTab's identical comment above.
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReport(null);
    setError(null);
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/reports/attendance?date_from=${dateFrom}&date_to=${dateTo}`);
      if (cancelled) return;
      if (!resp.ok) {
        setError("Could not load attendance for this date range.");
        return;
      }
      const body = await resp.json();
      if (cancelled) return;
      setReport(body);
    })();
    return () => {
      cancelled = true;
    };
  }, [authFetch, orgId, dateFrom, dateTo]);

  if (error) return <p className="text-sm text-danger-600">{error}</p>;
  if (!report) return <p className="text-sm text-ink-soft">Loading…</p>;

  const totals = report.days.reduce(
    (acc, d) => ({
      present: acc.present + d.present_count,
      absent: acc.absent + d.absent_count,
      late: acc.late + d.late_count,
      half_day: acc.half_day + d.half_day_count,
      leave: acc.leave + d.leave_count,
    }),
    { present: 0, absent: 0, late: 0, half_day: 0, leave: 0 }
  );

  const stationColumns: Column<OrgAttendanceReport["by_station"][number]>[] = [
    { key: "station", header: "Station", render: (r) => r.station_name },
    { key: "present", header: "Present", align: "right", render: (r) => formatNumber(r.present_count) },
    { key: "late", header: "Late", align: "right", render: (r) => formatNumber(r.late_count) },
    { key: "half_day", header: "Half day", align: "right", render: (r) => formatNumber(r.half_day_count) },
    { key: "leave", header: "Leave", align: "right", render: (r) => formatNumber(r.leave_count) },
    { key: "absent", header: "Absent", align: "right", render: (r) => formatNumber(r.absent_count) },
  ];

  return (
    <div className="space-y-6">
      <StatCardGrid>
        <StatCard label="Total employees" value={formatNumber(report.total_employees)} icon={Users} tone="brand" />
        <StatCard label="Present (range total)" value={formatNumber(totals.present)} icon={UserCheck} tone="success" />
        <StatCard label="Late (range total)" value={formatNumber(totals.late)} icon={UserCheck} tone="warning" />
        <StatCard label="Absent (range total)" value={formatNumber(totals.absent)} icon={UserCheck} tone="danger" />
      </StatCardGrid>
      <Card
        title="By station"
        description="Not deduplicated across stations - each station's own attendance record, same as its own attendance page would show."
      >
        <DataTable columns={stationColumns} data={report.by_station} keyFn={(r) => r.station_id} emptyMessage="No attendance recorded in this range." />
      </Card>
    </div>
  );
}

function ComparisonTab({
  orgId,
  authFetch,
  dateFrom,
  dateTo,
}: {
  orgId: string;
  authFetch: AuthFetch;
  dateFrom: string;
  dateTo: string;
}) {
  const [report, setReport] = useState<OrgStationPerformanceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Stale-response guard - see OverviewTab's identical comment above.
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReport(null);
    setError(null);
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/reports/station-performance?date_from=${dateFrom}&date_to=${dateTo}`);
      if (cancelled) return;
      if (!resp.ok) {
        setError("Could not load the station comparison for this date range.");
        return;
      }
      const body = await resp.json();
      if (cancelled) return;
      setReport(body);
    })();
    return () => {
      cancelled = true;
    };
  }, [authFetch, orgId, dateFrom, dateTo]);

  if (error) return <p className="text-sm text-danger-600">{error}</p>;
  if (!report) return <p className="text-sm text-ink-soft">Loading…</p>;

  if (report.rows.length === 0) {
    return <p className="text-sm text-ink-soft">No authorized stations with activity in this range yet.</p>;
  }

  const columns: Column<StationPerformanceRow>[] = [
    { key: "station", header: "Station", render: (r) => r.station_name },
    { key: "litres", header: "Litres sold", align: "right", sortable: true, sortValue: (r) => Number(r.litres_sold), render: (r) => formatLitres(r.litres_sold) },
    { key: "revenue", header: "Expected revenue", align: "right", sortable: true, sortValue: (r) => Number(r.expected_revenue), render: (r) => `PKR ${formatMoney(r.expected_revenue)}` },
    { key: "tender", header: "Tendered", align: "right", sortable: true, sortValue: (r) => Number(r.total_tender_amount), render: (r) => `PKR ${formatMoney(r.total_tender_amount)}` },
    { key: "expenses", header: "Approved expenses", align: "right", sortable: true, sortValue: (r) => Number(r.approved_expenses), render: (r) => `PKR ${formatMoney(r.approved_expenses)}` },
    { key: "stock", header: "Current stock", align: "right", sortable: true, sortValue: (r) => Number(r.total_book_stock), render: (r) => formatLitres(r.total_book_stock) },
    { key: "employees", header: "Employees", align: "right", render: (r) => formatNumber(r.employee_count) },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <StationBarChart
          title="Litres sold by station"
          valueLabel="Litres"
          data={report.rows.map((r) => ({ label: r.station_name, value: Number(r.litres_sold) }))}
          formatValue={(v) => formatLitres(v)}
        />
        <StationBarChart
          title="Expected revenue by station"
          valueLabel="Revenue"
          data={report.rows.map((r) => ({ label: r.station_name, value: Number(r.expected_revenue) }))}
          formatValue={(v) => `PKR ${formatMoney(v)}`}
        />
      </div>
      <Card
        title="Side-by-side comparison"
        description="Independent metrics only - no profit/margin figure is shown, since this system has no cost-of-goods-sold data to support one."
      >
        <DataTable columns={columns} data={report.rows} keyFn={(r) => r.station_id} emptyMessage="No stations to compare." />
      </Card>
    </div>
  );
}
