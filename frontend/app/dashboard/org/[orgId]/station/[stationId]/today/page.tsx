"use client";

import { AlertTriangle, Receipt, Truck, Clock } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import { stationDateIso } from "@/lib/date";
import { formatLitres, formatMoney, formatNumber } from "@/lib/format";
import { Card } from "@/components/Card";
import { LitresByGradeChart } from "@/components/charts/LitresByGradeChart";
import { type PaymentMethodSlice } from "@/components/charts/PaymentMethodBreakdownChart";
import { ActionQueueCard, type ActionQueueRow } from "@/components/dashboard/ActionQueueCard";
import { SectionHeading } from "@/components/dashboard/SectionHeading";
import { KpiStrip } from "@/components/dashboard/KpiStrip";
import { StockLevelBars } from "@/components/dashboard/StockLevelBars";
import { CashCollectedCard } from "@/components/dashboard/CashCollectedCard";
import { ModuleHealthGrid, type ModuleHealthItem } from "@/components/dashboard/ModuleHealthGrid";
import { LiveTrendChart, type LiveTrendPoint } from "@/components/dashboard/LiveTrendChart";
import type {
  AttendanceRecord,
  CreditCustomerBalance,
  DailyFuelSalesDay,
  FuelGrade,
  FuelPrice,
  PaymentMethod,
  PendingApprovalsReport,
  Shift,
  ShiftReconciliationReportRow,
  ShiftTender,
  Tank,
  TankerReceipt,
} from "@/lib/types";

// Lazy, client-only: this is a purely decorative hero accent, never part
// of the critical path for a page whose job is showing real financial
// numbers. Deferring it keeps it out of the initial bundle/SSR payload
// and means a failure here can never block the data this page exists to
// show (see components/decor/Hero3D.tsx for the depth/reduced-motion
// reasoning).
const Hero3D = dynamic(() => import("@/components/decor/Hero3D").then((m) => m.Hero3D), { ssr: false });

export default function TodayOverviewPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { user, authFetch } = useAuth();
  const { t } = useLanguage();
  // "Today" means the station's own business day (see
  // lib/date.ts::stationDateIso), not the viewer's browser timezone -
  // defaults to UTC only until the station's real timezone has loaded.
  const [stationTimezone, setStationTimezone] = useState("UTC");
  const [date, setDate] = useState(() => stationDateIso("UTC"));

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}`);
      if (!resp.ok) return;
      const station: { timezone: string } = await resp.json();
      setStationTimezone(station.timezone);
      setDate((current) => (current === stationDateIso("UTC") ? stationDateIso(station.timezone) : current));
    })();
  }, [authFetch, orgId, stationId]);
  const [sales, setSales] = useState<DailyFuelSalesDay | null>(null);
  const [recon, setRecon] = useState<ShiftReconciliationReportRow[] | null>(null);
  const [pending, setPending] = useState<PendingApprovalsReport | null>(null);
  const [tanks, setTanks] = useState<Tank[] | null>(null);
  const [credit, setCredit] = useState<CreditCustomerBalance[] | null>(null);
  const [fuelGrades, setFuelGrades] = useState<FuelGrade[]>([]);
  const [fuelPrices, setFuelPrices] = useState<FuelPrice[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [todaysTenders, setTodaysTenders] = useState<ShiftTender[]>([]);
  const [lastReceipt, setLastReceipt] = useState<TankerReceipt | null>(null);
  const [openShifts, setOpenShifts] = useState<Shift[] | null>(null);
  const [attendanceToday, setAttendanceToday] = useState<AttendanceRecord[] | null>(null);

  // Each request updates its own piece of state as soon as IT resolves,
  // rather than all 11 being gated behind one shared `await Promise.all` -
  // that previous shape meant every stat card sat on "Loading..." until
  // the single slowest endpoint answered, even when ten of the eleven
  // had already come back instantly. Still fired in parallel (the browser
  // issues all eleven requests at once either way); only the "wait for
  // the slowest one before showing anything" gate is removed.
  const load = useCallback(() => {
    const stationBase = `/organizations/${orgId}/stations/${stationId}`;

    authFetch(`${stationBase}/reports/daily-fuel-sales?date_from=${date}&date_to=${date}`).then(async (resp) => {
      if (!resp.ok) return;
      const days: DailyFuelSalesDay[] = await resp.json();
      setSales(days[0] ?? null);
    });

    authFetch(`${stationBase}/reports/shift-reconciliation?date_from=${date}&date_to=${date}`).then(async (resp) => {
      if (!resp.ok) return;
      const rows: ShiftReconciliationReportRow[] = await resp.json();
      setRecon(rows);
      // Today's shift(s) tenders, for the payment-method breakdown - the
      // reconciliation report rows already give us which shift(s) count as
      // "today," so this reuses that instead of guessing a shift id.
      const tenderLists = await Promise.all(
        rows.map((r) => authFetch(`${stationBase}/shifts/${r.shift_id}/tenders`).then((r2) => (r2.ok ? r2.json() : [])))
      );
      setTodaysTenders(tenderLists.flat());
    });

    authFetch(`/organizations/${orgId}/reports/pending-approvals`).then(async (resp) => {
      if (resp.ok) setPending(await resp.json());
    });

    authFetch(`${stationBase}/tanks`).then(async (resp) => {
      if (resp.ok) setTanks(await resp.json());
    });

    authFetch(`/organizations/${orgId}/credit-customers/balances`).then(async (resp) => {
      if (resp.ok) setCredit(await resp.json());
    });

    authFetch(`/organizations/${orgId}/fuel-grades`).then(async (resp) => {
      if (resp.ok) setFuelGrades(await resp.json());
    });

    authFetch(`${stationBase}/fuel-prices`).then(async (resp) => {
      if (resp.ok) setFuelPrices(await resp.json());
    });

    authFetch(`/organizations/${orgId}/payment-methods`).then(async (resp) => {
      if (resp.ok) setPaymentMethods(await resp.json());
    });

    authFetch(`${stationBase}/tanker-receipts`).then(async (resp) => {
      if (!resp.ok) return;
      const receipts: TankerReceipt[] = await resp.json();
      setLastReceipt(receipts[0] ?? null);
    });

    authFetch(`${stationBase}/shifts?status=open`).then(async (resp) => {
      setOpenShifts(resp.ok ? await resp.json() : null);
    });

    // Attendance is a permission (attendance:read) not every role holds -
    // a 403 here just means "don't show this widget," never an error.
    authFetch(`${stationBase}/attendance?date_from=${date}&date_to=${date}`).then(async (resp) => {
      setAttendanceToday(resp.ok ? await resp.json() : null);
    });
  }, [authFetch, orgId, stationId, date]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  // Live dashboard: re-fetch today's real figures on an interval so the
  // page reflects new shifts/sales/approvals without a manual reload.
  // Only viewing today's own business date auto-refreshes - looking at a
  // past date via the picker above would otherwise silently keep
  // "live"-polling a day that can no longer change.
  const isViewingToday = date === stationDateIso(stationTimezone);
  useEffect(() => {
    if (!isViewingToday) return;
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load, isViewingToday]);

  const [history, setHistory] = useState<LiveTrendPoint[]>([]);
  // The trend chart needs 2 real points before it can draw a line, and
  // the second one otherwise only arrives on the next 30s poll - leaving
  // a freshly opened dashboard stuck on "Collecting live data..." for up
  // to 30s for no good reason. This fires ONE extra real fetch a few
  // seconds after the very first point lands, purely to get the second
  // genuine measurement sooner; normal 30s-interval polling continues
  // unchanged afterward. Never fabricates a point - it's still a real
  // `load()` call, just not waiting out the full interval for it.
  const didBoosterFetch = useRef(false);

  const totalLitres = sales?.total_litres_sold ?? "0.000";
  const totalSalesValue = sales?.total_expected_revenue ?? "0.00";
  const totalCollected = recon?.reduce((sum, r) => sum + Number(r.total_tender_amount), 0) ?? 0;
  const expectedCash = recon?.reduce((sum, r) => sum + Number(r.expected_physical_cash), 0) ?? 0;
  const actualCash = recon?.reduce((sum, r) => sum + Number(r.actual_physical_cash), 0) ?? 0;
  const shortageExcess = recon?.reduce((sum, r) => sum + Number(r.cash_shortage_excess), 0) ?? 0;
  const outstandingCredit = credit?.reduce((sum, c) => sum + Number(c.balance), 0) ?? 0;
  const unresolvedCount = pending
    ? pending.reconciliations_requiring_authorization +
      pending.unapproved_decreasing_cash_movements +
      pending.unapproved_meter_events
    : 0;
  const pendingCount = pending
    ? pending.tanker_receipts_awaiting_approval + pending.shifts_awaiting_approval + pending.pending_expenses + pending.unapproved_supplier_payments
    : 0;

  // fuelPrices is already ordered by effective_from desc (server-side), so
  // the first row per grade is the current one - never averaged or guessed.
  const currentPriceByGrade = new Map<string, FuelPrice>();
  for (const price of fuelPrices) {
    if (!currentPriceByGrade.has(price.fuel_grade_id)) currentPriceByGrade.set(price.fuel_grade_id, price);
  }
  const gradeNameById = new Map(fuelGrades.map((g) => [g.id, g.name]));

  const activeTenders = todaysTenders.filter((t) => !t.reversed_at);
  const methodById = new Map(paymentMethods.map((m) => [m.id, m]));
  const categoryTotals = new Map<string, number>();
  for (const tender of activeTenders) {
    const category = methodById.get(tender.payment_method_id)?.category ?? "cash";
    categoryTotals.set(category, (categoryTotals.get(category) ?? 0) + Number(tender.amount));
  }
  const categoryLabel: Record<string, string> = { cash: "Cash", card: "Card", digital: "Digital / Bank", credit: "Credit" };
  const paymentBreakdown: PaymentMethodSlice[] = Array.from(categoryTotals, ([category, amount]) => ({
    label: categoryLabel[category] ?? category,
    amount,
  }));
  const transactionsCount = activeTenders.length;
  const avgTransaction = transactionsCount > 0 ? totalCollected / transactionsCount : 0;

  const overviewHref = `/dashboard/org/${orgId}?tab=overview`;
  const purchasesHref = `/dashboard/org/${orgId}/station/${stationId}/purchases`;
  const readingCorrectionsHref = `/dashboard/org/${orgId}/station/${stationId}/reading-corrections`;

  // Every row's count comes straight from PendingApprovalsReport - the
  // same real, server-computed numbers the Approvals & Alerts page
  // uses - never estimated here.
  const moduleHealthItems: ModuleHealthItem[] = pending
    ? [
        { key: "deliveries", label: t("today.module.deliveries"), count: pending.tanker_receipts_awaiting_approval, href: purchasesHref },
        { key: "shifts", label: t("today.module.shifts"), count: pending.shifts_awaiting_approval, href: overviewHref },
        { key: "meterEvents", label: t("today.module.meterEvents"), count: pending.unapproved_meter_events, href: readingCorrectionsHref },
        { key: "cashDiscrepancies", label: t("today.module.cashDiscrepancies"), count: pending.reconciliations_requiring_authorization, href: overviewHref },
        { key: "cashMovements", label: t("today.module.cashMovements"), count: pending.unapproved_decreasing_cash_movements, href: overviewHref },
        { key: "expenses", label: t("today.module.expenses"), count: pending.pending_expenses, href: `/dashboard/org/${orgId}?tab=expenses` },
        { key: "supplierPayments", label: t("today.module.supplierPayments"), count: pending.unapproved_supplier_payments, href: overviewHref },
        { key: "inventory", label: t("today.module.inventory"), count: pending.low_stock_inventory_items, href: overviewHref },
      ]
    : [];
  const actionQueueRows: ActionQueueRow[] = moduleHealthItems.map((m) => ({ module: m.label, count: m.count, href: m.href }));

  // Appends one point each time today's real reconciliation data actually
  // loads (initial load + every 30s poll above) - a genuine live trend of
  // this session's own refreshes, never a simulated tick. Gated on `recon`
  // alone, not `sales` too: the daily-fuel-sales report legitimately
  // returns [] (so `sales` stays null) on any day with zero approved
  // shifts so far - a brand-new station, or simply before today's first
  // shift closes - and gating on both meant the chart sat on "Collecting
  // live data..." forever on such a day even though totalCollected/
  // totalLitres below already default to zero correctly. `recon` only
  // stays null while a request has never yet succeeded, so it's the right
  // "has this page loaded at least once" signal.
  useEffect(() => {
    if (!recon) return;
    const point: LiveTrendPoint = {
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      collected: totalCollected,
      litres: Number(totalLitres),
    };
    setHistory((prev) => [...prev.slice(-19), point]);

    if (!didBoosterFetch.current && isViewingToday) {
      didBoosterFetch.current = true;
      const boosterId = setTimeout(load, 4000);
      return () => clearTimeout(boosterId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sales, recon]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="relative flex flex-wrap items-start justify-between gap-4 overflow-hidden">
        <Hero3D />
        <div className="relative z-10">
          <h1 className="text-xl font-semibold text-ink">
            {t("today.welcome")}, {user?.full_name?.split(" ")[0] ?? "there"}
          </h1>
          <p className="mt-1 text-sm text-ink-soft">{t("today.subtitle")}</p>
        </div>
        <label className="relative z-10 flex items-center gap-2 text-sm">
          <span className="font-medium text-ink-soft">{t("today.date")}</span>
          <input
            type="date"
            value={date}
            max={stationDateIso(stationTimezone)}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </label>
      </div>

      {(pendingCount > 0 || unresolvedCount > 0) && (
        <div className="flex items-start gap-3 rounded-xl border border-caution-100 bg-caution-50 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-caution-600" aria-hidden />
          <div className="text-sm text-caution-600">
            <p className="font-medium">
              {pendingCount + unresolvedCount} item{pendingCount + unresolvedCount === 1 ? "" : "s"} {t("today.needAttention")}
            </p>
            <p className="mt-0.5">
              {pending?.pending_expenses ? `${pending.pending_expenses} expense(s) awaiting approval. ` : ""}
              {pending?.tanker_receipts_awaiting_approval ? `${pending.tanker_receipts_awaiting_approval} delivery(ies) awaiting approval. ` : ""}
              {pending?.reconciliations_requiring_authorization ? `${pending.reconciliations_requiring_authorization} cash discrepancy(ies) need authorization. ` : ""}
              {pending?.low_stock_inventory_items ? `${pending.low_stock_inventory_items} item(s) running low.` : ""}
            </p>
          </div>
        </div>
      )}

      <SectionHeading>{t("today.sectionOverview")}</SectionHeading>
      <ActionQueueCard rows={actionQueueRows} />
      <LiveTrendChart data={history} />
      <KpiStrip
        items={[
          { label: t("today.fuelSoldToday"), value: sales ? formatLitres(totalLitres) : null },
          { label: t("today.salesValue"), value: sales ? `PKR ${formatMoney(totalSalesValue)}` : null },
          { label: t("today.collected"), value: recon ? `PKR ${formatMoney(totalCollected)}` : null },
          { label: t("today.expectedCash"), value: recon ? `PKR ${formatMoney(expectedCash)}` : null },
          { label: t("today.actualCash"), value: recon ? `PKR ${formatMoney(actualCash)}` : null },
          {
            label: t("today.shortageExcess"),
            value: recon ? `PKR ${formatMoney(Math.abs(shortageExcess))}` : null,
            sublabel: recon ? (shortageExcess < 0 ? "Shortage" : shortageExcess > 0 ? "Excess" : "Balanced") : undefined,
          },
          { label: t("today.outstandingCredit"), value: credit ? `PKR ${formatMoney(outstandingCredit)}` : null },
          { label: t("today.transactions"), value: recon ? formatNumber(transactionsCount) : null },
          { label: t("today.avgTransaction"), value: recon ? `PKR ${formatMoney(avgTransaction)}` : null },
        ]}
      />

      <SectionHeading>{t("today.sectionOperations")}</SectionHeading>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <StockLevelBars
          rows={(tanks ?? []).map((tank) => ({
            code: tank.code,
            gradeName: gradeNameById.get(tank.fuel_grade_id) ?? "—",
            stockLitres: Number(tank.book_stock),
            capacityLitres: Number(tank.capacity),
          }))}
        />
        <CashCollectedCard data={paymentBreakdown} total={totalCollected} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Current shift status">
          {!openShifts ? (
            <p className="text-sm text-ink-soft">{t("common.loading")}</p>
          ) : openShifts.length === 0 ? (
            <p className="text-sm text-ink-soft">No shift is currently open at this station.</p>
          ) : (
            <ul className="space-y-2">
              {openShifts.map((s) => (
                <li key={s.id} className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5">
                  <Clock className="h-4 w-4 flex-shrink-0 text-accent" aria-hidden />
                  <div>
                    <p className="text-sm text-ink">{s.label ?? "Shift"}</p>
                    <p className="text-xs text-ink-faint">Opened {new Date(s.opened_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {attendanceToday && (
          <Card title="Attendance today">
            {attendanceToday.length === 0 ? (
              <p className="text-sm text-ink-soft">No attendance recorded yet for today.</p>
            ) : (
              <div className="flex items-center gap-4">
                <AttendanceStat label="Present" count={attendanceToday.filter((a) => a.status === "present").length} tone="text-success-600" />
                <AttendanceStat label="Late" count={attendanceToday.filter((a) => a.status === "late").length} tone="text-warning-600" />
                <AttendanceStat label="Absent" count={attendanceToday.filter((a) => a.status === "absent").length} tone="text-danger-600" />
                <AttendanceStat label="On leave" count={attendanceToday.filter((a) => a.status === "leave").length} tone="text-ink-soft" />
              </div>
            )}
          </Card>
        )}
      </div>

      {activeTenders.length > 0 && (
        <Card title="Recent transactions">
          <ul className="divide-y divide-border">
            {activeTenders
              .slice()
              .sort((a, b) => new Date(b.recorded_at).getTime() - new Date(a.recorded_at).getTime())
              .slice(0, 8)
              .map((tx) => (
                <li key={tx.id} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-ink">{methodById.get(tx.payment_method_id)?.name ?? "Payment"}</span>
                  <span className="flex items-baseline gap-2">
                    <span className="font-medium tabular-nums text-ink">PKR {formatMoney(tx.amount)}</span>
                    <span className="text-xs text-ink-faint">{new Date(tx.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  </span>
                </li>
              ))}
          </ul>
        </Card>
      )}

      <ModuleHealthGrid items={moduleHealthItems} />

      <SectionHeading>{t("today.sectionAnalytics")}</SectionHeading>
      {sales && sales.grades.length > 0 ? (
        <LitresByGradeChart grades={sales.grades} title={t("today.fuelSoldByProduct")} />
      ) : (
        <Card title={t("today.fuelSoldByProduct")}>
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        </Card>
      )}

      <SectionHeading>{t("today.sectionReference")}</SectionHeading>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title={t("today.currentPrices")} description={t("today.currentPricesDescription")}>
          {fuelGrades.length === 0 ? (
            <p className="text-sm text-ink-soft">{t("common.loading")}</p>
          ) : (
            <ul className="space-y-2">
              {fuelGrades.map((grade) => {
                const price = currentPriceByGrade.get(grade.id);
                return (
                  <li key={grade.id} className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                    <span className="text-sm text-ink">{grade.name}</span>
                    {price ? (
                      <span className="text-sm font-semibold text-ink">
                        {/* Not formatMoney(): that rounds to 2dp, but price_per_litre is stored
                            to 4dp (NUMERIC(10,4)) - rounding a per-litre price here would silently
                            hide the precision the backend deliberately keeps. */}
                        PKR {price.price_per_litre} <span className="font-normal text-ink-faint">{t("today.perLitre")}</span>
                      </span>
                    ) : (
                      <span className="text-sm text-ink-faint">—</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title={t("today.lastDelivery")}>
          {!lastReceipt ? (
            <p className="text-sm text-ink-soft">{t("today.noDeliveriesYet")}</p>
          ) : (
            <div className="flex items-start gap-3">
              <Truck className="mt-0.5 h-5 w-5 flex-shrink-0 text-ink-faint" aria-hidden />
              <div>
                <p className="text-sm text-ink">
                  {gradeNameById.get(lastReceipt.fuel_grade_id) ?? "—"} ·{" "}
                  {formatLitres(lastReceipt.accepted_quantity ?? lastReceipt.dispatched_quantity ?? lastReceipt.invoice_quantity ?? null)}
                </p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  {new Date(lastReceipt.created_at).toLocaleString()} · {lastReceipt.status.replace(/_/g, " ")}
                </p>
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card title={t("today.expensesRecordedToday")}>
        <p className="flex items-center gap-2 text-sm text-ink-soft">
          <Receipt className="h-4 w-4" aria-hidden />
          {pending?.pending_expenses
            ? `${pending.pending_expenses} expense(s) awaiting approval across the organization.`
            : t("today.noExpensesPending")}
        </p>
      </Card>
    </div>
  );
}

function AttendanceStat({ label, count, tone }: { label: string; count: number; tone: string }) {
  return (
    <div>
      <p className={`text-xl font-semibold tabular-nums ${tone}`}>{count}</p>
      <p className="text-xs text-ink-faint">{label}</p>
    </div>
  );
}
