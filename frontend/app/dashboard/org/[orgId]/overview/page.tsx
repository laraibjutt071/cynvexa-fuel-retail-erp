"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Banknote, Fuel, Receipt, UserCheck, Users, Wallet } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { formatLitres, formatMoney, formatNumber } from "@/lib/format";
import { DateRangeFilter, defaultDateRange } from "@/components/DateRangeFilter";
import { Card } from "@/components/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { StatCard, StatCardGrid } from "@/components/ui/StatCard";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { StationBarChart } from "@/components/charts/StationBarChart";
import type {
  OrgAttendanceReport,
  OrgExpenseReport,
  OrgRevenueReport,
  OrgSalesReport,
  OrgStationPerformanceReport,
  OrgStockReport,
  StationPerformanceRow,
} from "@/lib/types";

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
    return <main className="flex-1 px-6 py-10 text-sm text-ink-soft">Loading…</main>;
  }

  if (!can("report:read")) {
    return (
      <main className="flex-1">
        <PageHeader title="Company Overview" breadcrumbs={[{ label: "Dashboard" }, { label: "Company Overview" }]} />
        <div className="mx-auto max-w-3xl px-6 py-10">
          <AccessDenied message="Your role does not include organization-wide report visibility." />
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1">
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
    </main>
  );
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
  const [sales, setSales] = useState<OrgSalesReport | null>(null);
  const [revenue, setRevenue] = useState<OrgRevenueReport | null>(null);
  const [expenses, setExpenses] = useState<OrgExpenseReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // A date-range change can fire this effect again before the previous
    // run's requests have resolved (e.g. two quick edits to "From" and
    // "To") - without this guard, an earlier, now-stale response (or its
    // error, from a momentarily invalid intermediate range) could resolve
    // after the latest one and overwrite its correct result.
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSales(null);
    setRevenue(null);
    setExpenses(null);
    setError(null);
    (async () => {
      const qs = `?date_from=${dateFrom}&date_to=${dateTo}`;
      const [salesResp, revenueResp, expensesResp] = await Promise.all([
        authFetch(`/organizations/${orgId}/reports/sales${qs}`),
        authFetch(`/organizations/${orgId}/reports/revenue${qs}`),
        authFetch(`/organizations/${orgId}/reports/expenses${qs}`),
      ]);
      if (cancelled) return;
      if (!salesResp.ok || !revenueResp.ok || !expensesResp.ok) {
        setError("Could not load the company overview for this date range.");
        return;
      }
      const [salesBody, revenueBody, expensesBody] = await Promise.all([
        salesResp.json(),
        revenueResp.json(),
        expensesResp.json(),
      ]);
      if (cancelled) return;
      setSales(salesBody);
      setRevenue(revenueBody);
      setExpenses(expensesBody);
    })();
    return () => {
      cancelled = true;
    };
  }, [authFetch, orgId, dateFrom, dateTo]);

  if (error) return <p className="text-sm text-danger-600">{error}</p>;
  if (!sales || !revenue || !expenses) {
    return (
      <StatCardGrid>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card-glow h-24 animate-pulse rounded-xl bg-surface-muted" />
        ))}
      </StatCardGrid>
    );
  }

  return (
    <div className="space-y-6">
      <StatCardGrid>
        <StatCard label="Total fuel sold" value={formatLitres(sales.total_litres_sold)} icon={Fuel} tone="brand" />
        <StatCard
          label="Total revenue"
          value={formatMoney(revenue.total_recognized_revenue)}
          icon={Wallet}
          tone="success"
          subtitle="Litres x price, never cash collected"
        />
        <StatCard
          label="Cash collected"
          value={formatMoney(revenue.cash_amount)}
          icon={Banknote}
          tone="neutral"
          subtitle={`of ${formatMoney(revenue.total_tender_amount)} total tendered`}
        />
        <StatCard label="Approved expenses" value={formatMoney(expenses.grand_approved)} icon={Receipt} tone="warning" />
      </StatCardGrid>

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
              <p className="mt-1 text-lg font-semibold tabular-nums text-ink">{formatMoney(row.value)}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Expense categories" description={`Grand total ${formatMoney(expenses.grand_total)} (includes reversed entries); approved ${formatMoney(expenses.grand_approved)}.`}>
        {expenses.by_category.length === 0 ? (
          <p className="text-sm text-ink-soft">No expenses recorded in this range.</p>
        ) : (
          <ul className="divide-y divide-border">
            {expenses.by_category.map((row) => (
              <li key={row.category} className="flex items-center justify-between py-2 text-sm">
                <span className="text-ink">{row.category}</span>
                <span className="tabular-nums text-ink-soft">
                  {formatMoney(row.approved_amount)} approved / {formatMoney(row.total_amount)} total
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
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
    { key: "revenue", header: "Expected revenue", align: "right", sortable: true, sortValue: (r) => Number(r.expected_revenue), render: (r) => formatMoney(r.expected_revenue) },
    { key: "tender", header: "Tendered", align: "right", sortable: true, sortValue: (r) => Number(r.total_tender_amount), render: (r) => formatMoney(r.total_tender_amount) },
    { key: "expenses", header: "Approved expenses", align: "right", sortable: true, sortValue: (r) => Number(r.approved_expenses), render: (r) => formatMoney(r.approved_expenses) },
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
          formatValue={(v) => formatMoney(v)}
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
