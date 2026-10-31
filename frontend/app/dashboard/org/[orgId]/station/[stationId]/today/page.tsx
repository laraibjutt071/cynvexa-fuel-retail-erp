"use client";

import {
  AlertTriangle,
  Banknote,
  CheckSquare,
  CreditCard,
  Fuel,
  Receipt,
  ShoppingCart,
  Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import { stationDateIso } from "@/lib/date";
import { Card } from "@/components/Card";
import { FuelStockChart } from "@/components/charts/FuelStockChart";
import { LitresByGradeChart } from "@/components/charts/LitresByGradeChart";
import type { CreditCustomerBalance, DailyFuelSalesDay, PendingApprovalsReport, ShiftReconciliationReportRow, Tank } from "@/lib/types";

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

  const load = useCallback(async () => {
    const stationBase = `/organizations/${orgId}/stations/${stationId}`;
    const [salesResp, reconResp, pendingResp, tanksResp, creditResp] = await Promise.all([
      authFetch(`${stationBase}/reports/daily-fuel-sales?date_from=${date}&date_to=${date}`),
      authFetch(`${stationBase}/reports/shift-reconciliation?date_from=${date}&date_to=${date}`),
      authFetch(`/organizations/${orgId}/reports/pending-approvals`),
      authFetch(`${stationBase}/tanks`),
      authFetch(`/organizations/${orgId}/credit-customers/balances`),
    ]);
    if (salesResp.ok) {
      const days: DailyFuelSalesDay[] = await salesResp.json();
      setSales(days[0] ?? null);
    }
    if (reconResp.ok) setRecon(await reconResp.json());
    if (pendingResp.ok) setPending(await pendingResp.json());
    if (tanksResp.ok) setTanks(await tanksResp.json());
    if (creditResp.ok) setCredit(await creditResp.json());
  }, [authFetch, orgId, stationId, date]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

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

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">
            {t("today.welcome")}, {user?.full_name?.split(" ")[0] ?? "there"}
          </h1>
          <p className="mt-1 text-sm text-ink-soft">{t("today.subtitle")}</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <SummaryCard icon={Fuel} label={t("today.fuelSoldToday")} value={`${totalLitres} L`} />
        <SummaryCard icon={ShoppingCart} label={t("today.salesValue")} value={totalSalesValue} hint={t("today.revenueNotProfit")} />
        <SummaryCard icon={Wallet} label={t("today.collected")} value={totalCollected.toFixed(2)} />
        <SummaryCard icon={Banknote} label={t("today.expectedCash")} value={expectedCash.toFixed(2)} />
        <SummaryCard icon={Banknote} label={t("today.actualCash")} value={actualCash.toFixed(2)} />
        <SummaryCard
          icon={Banknote}
          label={t("today.shortageExcess")}
          value={shortageExcess.toFixed(2)}
          tone={Math.abs(shortageExcess) < 0.01 ? "neutral" : shortageExcess < 0 ? "danger" : "warning"}
        />
        <SummaryCard icon={CreditCard} label={t("today.outstandingCredit")} value={outstandingCredit.toFixed(2)} />
        <SummaryCard icon={CheckSquare} label={t("today.itemsAwaitingApproval")} value={String(pendingCount)} tone={pendingCount > 0 ? "warning" : "neutral"} />
      </div>

      {tanks && tanks.length > 0 && <FuelStockChart tanks={tanks} title={t("today.fuelStockRemaining")} />}
      {sales && sales.grades.length > 0 && <LitresByGradeChart grades={sales.grades} title={t("today.fuelSoldByProduct")} />}

      <Card title={t("today.fuelStockRemaining")} description={t("today.fuelStockDescription")}>
        {!tanks ? (
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        ) : tanks.length === 0 ? (
          <p className="text-sm text-ink-soft">{t("today.noTanks")}</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {tanks.map((tank) => (
              <div key={tank.id} className="card-glow rounded-lg bg-surface p-3">
                <p className="text-lg font-semibold text-ink">{tank.book_stock} L</p>
                <p className="mt-0.5 text-xs text-ink-soft">
                  Tank {tank.code} · {tank.safe_capacity_available} L {t("today.available")}
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>

      {sales && sales.grades.length > 0 && (
        <Card title={t("today.fuelSoldByProduct")}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">Product</th>
                <th className="py-2 pr-2">Litres</th>
                <th className="py-2 pr-2">Value</th>
              </tr>
            </thead>
            <tbody>
              {sales.grades.map((g) => (
                <tr key={g.fuel_grade_id} className="border-b border-border/60">
                  <td className="py-2 pr-2 text-ink">{g.fuel_grade_name}</td>
                  <td className="py-2 pr-2 text-ink-soft">{g.litres_sold}</td>
                  <td className="py-2 pr-2 text-ink-soft">{g.expected_revenue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

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

function SummaryCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = "neutral",
}: {
  icon: typeof Fuel;
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "warning" | "danger";
}) {
  const valueColor = tone === "danger" ? "text-danger-600" : tone === "warning" ? "text-caution-600" : "text-ink";
  return (
    <div className="card-glow animate-fade-slide-up rounded-xl bg-surface p-4">
      <div className="flex items-center gap-2 text-ink-faint">
        <Icon className="h-4 w-4" aria-hidden />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p className={`mt-2 text-xl font-semibold ${valueColor}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}
