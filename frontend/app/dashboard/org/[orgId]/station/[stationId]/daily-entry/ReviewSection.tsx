"use client";

import { AlertCircle, CheckCircle2, Circle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n/context";
import type { TranslationKey } from "@/lib/i18n/translations";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import type { Shift, ShiftCashMovement, ShiftNozzleReading, ShiftReconciliation } from "@/lib/types";
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
  authFetch,
  onShiftChanged,
  goToSection,
}: {
  orgId: string;
  stationId: string;
  shift: Shift;
  authFetch: AuthFetch;
  onShiftChanged: () => void;
  goToSection: (section: Section) => void;
}) {
  const { notify } = useToast();
  const { t } = useLanguage();
  const [nozzleReadings, setNozzleReadings] = useState<ShiftNozzleReading[]>([]);
  const [cashMovements, setCashMovements] = useState<ShiftCashMovement[]>([]);
  const [reconciliation, setReconciliation] = useState<ShiftReconciliation | null>(null);
  const [approving, setApproving] = useState(false);

  const shiftBase = `/organizations/${orgId}/stations/${stationId}/shifts/${shift.id}`;

  const load = useCallback(async () => {
    const [nrResp, cmResp, reconResp] = await Promise.all([
      authFetch(`${shiftBase}/nozzle-readings`),
      authFetch(`${shiftBase}/cash-movements`),
      authFetch(`${shiftBase}/reconciliation`),
    ]);
    if (nrResp.ok) setNozzleReadings(await nrResp.json());
    if (cmResp.ok) setCashMovements(await cmResp.json());
    setReconciliation(reconResp.ok ? await reconResp.json() : null);
  }, [authFetch, shiftBase]);

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

      <Card title={t("review.approveEntry")}>
        {shift.status === "approved" ? (
          <p className="flex items-center gap-2 text-sm font-medium text-success-600">
            <CheckCircle2 className="h-4.5 w-4.5" aria-hidden />
            {t("review.alreadyApproved")}
          </p>
        ) : (
          <>
            {!allDone && (
              <p className="mb-3 flex items-center gap-2 text-sm text-caution-600">
                <AlertCircle className="h-4.5 w-4.5 flex-shrink-0" aria-hidden />
                {t("review.finishFirst")}
              </p>
            )}
            <Button onClick={approveToday} disabled={!allDone} busy={approving}>
              {t("review.approveEntry")}
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}
