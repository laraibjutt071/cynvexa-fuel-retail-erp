"use client";

import { Banknote } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n/context";
import type { TranslationKey } from "@/lib/i18n/translations";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import type { CashMovementType, Shift, ShiftCashMovement, ShiftReconciliation } from "@/lib/types";
import type { AuthFetch } from "./page";

const MOVEMENT_LABEL_KEY: Record<CashMovementType, TranslationKey> = {
  opening_cash: "movement.opening_cash",
  expense: "movement.expense",
  deposit: "movement.deposit",
  safe_transfer_in: "movement.safe_transfer_in",
  safe_transfer_out: "movement.safe_transfer_out",
  refund: "movement.refund",
  other_increase: "movement.other_increase",
  other_decrease: "movement.other_decrease",
};
const DECREASING: CashMovementType[] = ["expense", "deposit", "safe_transfer_out", "refund", "other_decrease"];

export function CashSection({
  orgId,
  stationId,
  shift,
  authFetch,
  onShiftChanged,
}: {
  orgId: string;
  stationId: string;
  shift: Shift;
  authFetch: AuthFetch;
  onShiftChanged: () => void;
}) {
  const { notify } = useToast();
  const { t } = useLanguage();
  const [movements, setMovements] = useState<ShiftCashMovement[] | null>(null);
  const [reconciliation, setReconciliation] = useState<ShiftReconciliation | null | "none">("none");
  const [form, setForm] = useState<{ movement_type: CashMovementType; amount: string; reason: string }>({
    movement_type: "opening_cash",
    amount: "",
    reason: "",
  });
  const [actualCash, setActualCash] = useState("");
  const [explanation, setExplanation] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const shiftBase = `/organizations/${orgId}/stations/${stationId}/shifts/${shift.id}`;

  const load = useCallback(async () => {
    const [movementsResp, reconResp] = await Promise.all([
      authFetch(`${shiftBase}/cash-movements`),
      authFetch(`${shiftBase}/reconciliation`),
    ]);
    if (movementsResp.ok) setMovements(await movementsResp.json());
    setReconciliation(reconResp.ok ? await reconResp.json() : null);
  }, [authFetch, shiftBase]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function submitMovement(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`${shiftBase}/cash-movements`, { method: "POST", body: JSON.stringify(form) });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not record this movement." }));
        notify("error", body.detail ?? "Could not record this movement.");
        return;
      }
      notify("success", t("cash.movementRecorded"));
      setForm({ movement_type: "opening_cash", amount: "", reason: "" });
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  async function approveMovement(id: string) {
    const resp = await authFetch(`${shiftBase}/cash-movements/${id}/approve`, { method: "PATCH" });
    if (!resp.ok) {
      notify("error", "Could not approve this movement.");
      return;
    }
    notify("success", t("cash.movementApproved"));
    await load();
  }

  async function submitReconciliation(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`${shiftBase}/reconciliation`, {
        method: "POST",
        body: JSON.stringify({ actual_physical_cash: actualCash, explanation: explanation || undefined }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not close the cash for today." }));
        notify("error", body.detail ?? "Could not close the cash for today.");
        return;
      }
      notify("success", t("cash.closingRecorded"));
      await load();
      onShiftChanged();
    } finally {
      setSubmitting(false);
    }
  }

  async function authorize() {
    const resp = await authFetch(`${shiftBase}/reconciliation/authorize`, { method: "PATCH", body: JSON.stringify({}) });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ detail: "Could not authorize this discrepancy." }));
      notify("error", body.detail ?? "Could not authorize this discrepancy.");
      return;
    }
    notify("success", t("cash.discrepancyAuthorizedToast"));
    await load();
  }

  const pendingApprovals = (movements ?? []).filter(
    (m) => DECREASING.includes(m.movement_type) && !m.approved_by_user_id && !m.reversed_at
  );

  return (
    <div className="space-y-6">
      {shift.status === "open" && (
        <Card title={t("cash.movements")} description={t("cash.movementsDescription")}>
          <form onSubmit={submitMovement} className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <Select
              value={form.movement_type}
              onChange={(e) => setForm({ ...form, movement_type: e.target.value as CashMovementType })}
            >
              {Object.entries(MOVEMENT_LABEL_KEY).map(([value, labelKey]) => (
                <option key={value} value={value}>
                  {t(labelKey)}
                </option>
              ))}
            </Select>
            <TextInput
              required
              type="number"
              step="0.01"
              placeholder={t("cash.amount")}
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <TextInput
              required
              placeholder="Reason / note"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
            <Button type="submit" busy={submitting}>
              {t("common.record")}
            </Button>
          </form>

          {!movements ? (
            <p className="mt-4 text-sm text-ink-soft">{t("common.loading")}</p>
          ) : movements.length === 0 ? (
            <div className="mt-4">
              <EmptyState icon={Banknote} title={t("cash.noMovementsYet")} description={t("cash.recordOpeningFloat")} />
            </div>
          ) : (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-ink-faint">
                  <th className="py-2 pr-2">{t("cash.type")}</th>
                  <th className="py-2 pr-2">{t("cash.amount")}</th>
                  <th className="py-2 pr-2">{t("cash.reason")}</th>
                  <th className="py-2 pr-2">{t("expenses.status")}</th>
                  <th className="py-2 pr-2"></th>
                </tr>
              </thead>
              <tbody>
                {movements.map((m) => (
                  <tr key={m.id} className={`border-b border-border/60 ${m.reversed_at ? "opacity-50" : ""}`}>
                    <td className="py-2 pr-2 text-ink">{t(MOVEMENT_LABEL_KEY[m.movement_type])}</td>
                    <td className="py-2 pr-2 text-ink">{m.amount}</td>
                    <td className="py-2 pr-2 text-ink-soft">{m.reason}</td>
                    <td className="py-2 pr-2">
                      {m.reversed_at ? (
                        <Badge tone="neutral">{t("movement.reversed")}</Badge>
                      ) : DECREASING.includes(m.movement_type) ? (
                        m.approved_by_user_id ? (
                          <Badge tone="success">{t("movement.approved")}</Badge>
                        ) : (
                          <Badge tone="warning">{t("movement.needsApproval")}</Badge>
                        )
                      ) : (
                        <Badge tone="success">{t("movement.recorded")}</Badge>
                      )}
                    </td>
                    <td className="py-2 pr-2 text-right">
                      {DECREASING.includes(m.movement_type) && !m.approved_by_user_id && !m.reversed_at && (
                        <button onClick={() => approveMovement(m.id)} className="text-xs font-medium text-accent hover:underline">
                          {t("common.approve")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {pendingApprovals.length > 0 && (
            <p className="mt-3 text-xs font-medium text-caution-600">
              {pendingApprovals.length} {t("cash.needApproval")}
            </p>
          )}
        </Card>
      )}

      <Card title={t("cash.closing")} description={t("cash.closingDescription")}>
        {shift.status === "open" ? (
          <p className="text-sm text-ink-soft">{t("cash.closeReadingsFirst")}</p>
        ) : reconciliation === "none" ? (
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        ) : reconciliation === null ? (
          <form onSubmit={submitReconciliation} className="space-y-3">
            <Field label={t("cash.actualPhysicalCash")} required hint={t("cash.actualCashHint")}>
              {(id) => (
                <TextInput
                  id={id}
                  required
                  type="number"
                  step="0.01"
                  value={actualCash}
                  onChange={(e) => setActualCash(e.target.value)}
                />
              )}
            </Field>
            <Field label={t("cash.explanationLabel")} hint={t("cash.explanationHint")}>
              {(id) => (
                <textarea
                  id={id}
                  rows={2}
                  value={explanation}
                  onChange={(e) => setExplanation(e.target.value)}
                  className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              )}
            </Field>
            <Button type="submit" busy={submitting}>
              {t("cash.closeCashButton")}
            </Button>
          </form>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SummaryTile label={t("cash.expectedRevenue")} value={reconciliation.expected_fuel_revenue} />
            <SummaryTile label={t("cash.collectedAllMethods")} value={reconciliation.total_tender_amount} />
            <SummaryTile label={t("cash.expectedCash")} value={reconciliation.expected_physical_cash} />
            <SummaryTile label={t("cash.actualCashCounted")} value={reconciliation.actual_physical_cash} />
            <SummaryTile
              label={t("cash.shortageExcess")}
              value={reconciliation.cash_shortage_excess}
              tone={reconciliation.cash_within_tolerance ? "success" : "danger"}
            />
            <SummaryTile
              label={t("cash.revenueVsCollections")}
              value={`${reconciliation.revenue_variance} (${reconciliation.revenue_variance_percent}%)`}
              tone={reconciliation.revenue_within_tolerance ? "success" : "danger"}
            />
            {reconciliation.requires_authorization && (
              <div className="col-span-2 sm:col-span-4">
                {reconciliation.authorized_at ? (
                  <Badge tone="success">{t("cash.discrepancyAuthorized")}</Badge>
                ) : (
                  <div className="flex flex-wrap items-center gap-3 rounded-lg border border-caution-100 bg-caution-50 p-3">
                    <p className="text-sm text-caution-600">{t("cash.needsAuthorization")}</p>
                    <Button size="sm" onClick={authorize}>
                      {t("cash.authorize")}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Card>
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
