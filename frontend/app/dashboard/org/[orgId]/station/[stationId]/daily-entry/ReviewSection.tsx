"use client";

import { AlertCircle, CheckCircle2, Circle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n/context";
import type { TranslationKey } from "@/lib/i18n/translations";
import { useToast } from "@/components/ui/Toast";
import { usePermissions } from "@/lib/permissions";
import { formatMoney } from "@/lib/format";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { AccessDenied } from "@/components/ui/AccessDenied";
import type { Shift, ShiftCashMovement, ShiftNozzleReading, ShiftReconciliation, ShiftTender, Expense } from "@/lib/types";
import type { AuthFetch } from "./page";

type Section = "readings" | "sales" | "expenses" | "cash" | "review";

interface CheckItem {
  labelKey: TranslationKey;
  done: boolean;
  blocking: boolean;
  goTo?: Section;
}

export function ReviewSection({
  orgId,
  stationId,
  shift,
  businessDate,
  authFetch,
  onShiftChanged,
  goToSection,
}: {
  orgId: string;
  stationId: string;
  shift: Shift;
  businessDate: string;
  authFetch: AuthFetch;
  onShiftChanged: () => void;
  goToSection: (section: Section) => void;
}) {
  const { notify } = useToast();
  const { t } = useLanguage();
  const { can } = usePermissions(orgId, stationId);
  const canApprove = can("shift:approve");
  const [nozzleReadings, setNozzleReadings] = useState<ShiftNozzleReading[]>([]);
  const [cashMovements, setCashMovements] = useState<ShiftCashMovement[]>([]);
  const [reconciliation, setReconciliation] = useState<ShiftReconciliation | null>(null);
  const [tenders, setTenders] = useState<ShiftTender[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [approving, setApproving] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const shiftBase = `/organizations/${orgId}/stations/${stationId}/shifts/${shift.id}`;

  const load = useCallback(async () => {
    const [nrResp, cmResp, reconResp, tendersResp, expensesResp] = await Promise.all([
      authFetch(`${shiftBase}/nozzle-readings`),
      authFetch(`${shiftBase}/cash-movements`),
      authFetch(`${shiftBase}/reconciliation`),
      authFetch(`${shiftBase}/tenders`),
      authFetch(`/organizations/${orgId}/expenses?station_id=${stationId}&limit=100`),
    ]);
    if (nrResp.ok) setNozzleReadings(await nrResp.json());
    if (cmResp.ok) setCashMovements(await cmResp.json());
    setReconciliation(reconResp.ok ? await reconResp.json() : null);
    if (tendersResp.ok) setTenders(await tendersResp.json());
    if (expensesResp.ok) {
      const all: Expense[] = await expensesResp.json();
      setExpenses(all.filter((e) => e.expense_date === businessDate));
    }
  }, [authFetch, shiftBase, orgId, stationId, businessDate]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const unclosedNozzles = nozzleReadings.filter((r) => !r.closing_totalizer);
  const unapprovedMeterEvents = nozzleReadings.filter((r) => r.meter_event_type && !r.meter_event_approved_by_user_id);
  const unapprovedMovements = cashMovements.filter(
    (m) => ["expense", "deposit", "safe_transfer_out", "refund", "other_decrease"].includes(m.movement_type) && !m.approved_by_user_id && !m.reversed_at
  );

  const checks: CheckItem[] = [
    { labelKey: "review.check.readingsClosed", done: shift.status !== "open" && unclosedNozzles.length === 0, blocking: true, goTo: "readings" },
    { labelKey: "review.check.meterEvents", done: unapprovedMeterEvents.length === 0, blocking: true, goTo: "readings" },
    { labelKey: "review.check.cashMovements", done: unapprovedMovements.length === 0, blocking: true, goTo: "cash" },
    { labelKey: "review.check.cashClosing", done: reconciliation !== null, blocking: true, goTo: "cash" },
    {
      labelKey: "review.check.discrepancy",
      done: !reconciliation || !reconciliation.requires_authorization || !!reconciliation.authorized_at,
      blocking: true,
      goTo: "cash",
    },
  ];
  const allDone = checks.every((c) => c.done);

  const activeTenders = tenders.filter((tn) => !tn.reversed_at);
  const salesTotal = activeTenders.reduce((sum, tn) => sum + Number(tn.amount), 0);
  const activeExpenses = expenses.filter((e) => e.status !== "rejected" && !e.reversed_at);
  const expensesTotal = activeExpenses.reduce((sum, e) => sum + Number(e.amount), 0);

  async function approveToday() {
    setApproving(true);
    try {
      const resp = await authFetch(`${shiftBase}/approve`, { method: "PATCH" });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not approve today's entry yet." }));
        notify("error", body.detail ?? "Could not approve today's entry yet.");
        return;
      }
      notify("success", t("review.approvedToast"));
      setConfirmOpen(false);
      await load();
      onShiftChanged();
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card title={t("review.completeTitle")} description={t("review.completeDescription")}>
        <ul className="space-y-2">
          {checks.map((c) => (
            <li key={c.labelKey} className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
              <div className="flex items-center gap-2.5">
                {c.done ? (
                  <CheckCircle2 className="h-4.5 w-4.5 flex-shrink-0 text-success-600" aria-hidden />
                ) : (
                  <Circle className="h-4.5 w-4.5 flex-shrink-0 text-ink-faint" aria-hidden />
                )}
                <span className={`text-sm ${c.done ? "text-ink" : "text-ink-soft"}`}>{t(c.labelKey)}</span>
              </div>
              {!c.done && c.goTo && (
                <button onClick={() => goToSection(c.goTo!)} className="text-xs font-medium text-accent hover:underline">
                  {t("review.goFix")}
                </button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Summary — what you're about to approve" description="Real figures from today's entry, not estimates. Review these before approving.">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <SummaryTile label="Sales collected" value={formatMoney(salesTotal)} />
          <SummaryTile label="Expenses recorded" value={formatMoney(expensesTotal)} />
          {reconciliation && (
            <>
              <SummaryTile label="Expected revenue" value={formatMoney(reconciliation.expected_fuel_revenue)} />
              <SummaryTile label="Actual cash counted" value={formatMoney(reconciliation.actual_physical_cash)} />
              <SummaryTile
                label="Cash shortage/excess"
                value={formatMoney(reconciliation.cash_shortage_excess)}
                tone={reconciliation.cash_within_tolerance ? "success" : "danger"}
              />
              <SummaryTile
                label="Revenue vs collections"
                value={`${formatMoney(reconciliation.revenue_variance)} (${reconciliation.revenue_variance_percent}%)`}
                tone={reconciliation.revenue_within_tolerance ? "success" : "danger"}
              />
            </>
          )}
        </div>
        {!reconciliation && (
          <p className="mt-3 text-sm text-ink-soft">Cash hasn&apos;t been closed yet - reconciliation figures will appear here once it is.</p>
        )}
      </Card>

      <Card title={t("review.approveEntry")}>
        {shift.status === "approved" ? (
          <p className="flex items-center gap-2 text-sm font-medium text-success-600">
            <CheckCircle2 className="h-4.5 w-4.5" aria-hidden />
            {t("review.alreadyApproved")}
          </p>
        ) : !canApprove ? (
          <AccessDenied message="Only a Station Manager or Shift Supervisor can approve today's entry. Ask one of them to review and approve it." />
        ) : (
          <>
            {!allDone && (
              <p className="mb-3 flex items-center gap-2 text-sm text-caution-600">
                <AlertCircle className="h-4.5 w-4.5 flex-shrink-0" aria-hidden />
                {t("review.finishFirst")}
              </p>
            )}
            <Button onClick={() => setConfirmOpen(true)} disabled={!allDone} busy={approving}>
              {t("review.approveEntry")}
            </Button>
          </>
        )}
      </Card>

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={approveToday}
        title="Approve today's entry?"
        description="This locks today's shift - readings, sales, expenses and cash closing can no longer be edited after this. Make sure the summary above looks correct first."
        confirmLabel="Yes, approve today's entry"
        confirmVariant="primary"
        busy={approving}
      />
    </div>
  );
}

function SummaryTile({ label, value, tone }: { label: string; value: string; tone?: "success" | "danger" }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <p className={`text-lg font-semibold ${tone === "danger" ? "text-danger-600" : tone === "success" ? "text-success-600" : "text-ink"}`}>
        {value}
      </p>
      <p className="mt-0.5 text-xs text-ink-soft">{label}</p>
    </div>
  );
}
