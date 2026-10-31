"use client";

import { useCallback, useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n/context";
import type { TranslationKey } from "@/lib/i18n/translations";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Select, TextInput } from "@/components/ui/Field";
import { EmptyState } from "@/components/ui/EmptyState";
import { Wallet } from "lucide-react";
import type { CreditCustomer, PaymentMethod, Shift, ShiftTender } from "@/lib/types";
import type { AuthFetch } from "./page";

const CATEGORY_LABEL_KEY: Record<string, TranslationKey> = {
  cash: "category.cash",
  card: "category.card",
  digital: "category.digital",
  credit: "category.credit",
};

export function SalesSection({
  orgId,
  stationId,
  shift,
  authFetch,
}: {
  orgId: string;
  stationId: string;
  shift: Shift;
  authFetch: AuthFetch;
}) {
  const { notify } = useToast();
  const { t } = useLanguage();
  const [methods, setMethods] = useState<PaymentMethod[] | null>(null);
  const [customers, setCustomers] = useState<CreditCustomer[]>([]);
  const [tenders, setTenders] = useState<ShiftTender[] | null>(null);
  const [form, setForm] = useState({ payment_method_id: "", amount: "", credit_customer_id: "", reference: "" });
  const [submitting, setSubmitting] = useState(false);

  const shiftBase = `/organizations/${orgId}/stations/${stationId}/shifts/${shift.id}`;
  const readOnly = shift.status !== "open" && shift.status !== "closed";

  const load = useCallback(async () => {
    const [methodsResp, customersResp, tendersResp] = await Promise.all([
      authFetch(`/organizations/${orgId}/payment-methods`),
      authFetch(`/organizations/${orgId}/credit-customers`),
      authFetch(`${shiftBase}/tenders`),
    ]);
    if (methodsResp.ok) setMethods(await methodsResp.json());
    if (customersResp.ok) setCustomers(await customersResp.json());
    if (tendersResp.ok) setTenders(await tendersResp.json());
  }, [authFetch, orgId, shiftBase]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const selectedMethod = methods?.find((m) => m.id === form.payment_method_id);
  const isCredit = selectedMethod?.category === "credit";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const payload: Record<string, string> = {
        payment_method_id: form.payment_method_id,
        amount: form.amount,
      };
      if (isCredit) payload.credit_customer_id = form.credit_customer_id;
      if (form.reference) payload.reference = form.reference;
      const resp = await authFetch(`${shiftBase}/tenders`, { method: "POST", body: JSON.stringify(payload) });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not record this collection." }));
        notify("error", body.detail ?? "Could not record this collection.");
        return;
      }
      notify("success", t("sales.recorded"));
      setForm({ payment_method_id: "", amount: "", credit_customer_id: "", reference: "" });
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  async function reverseTender(id: string) {
    const reason = window.prompt("Reason for reversing this entry (it stays visible, just excluded from totals):");
    if (!reason) return;
    const resp = await authFetch(`${shiftBase}/tenders/${id}/reverse`, {
      method: "PATCH",
      body: JSON.stringify({ reason }),
    });
    if (!resp.ok) {
      notify("error", "Could not reverse this entry.");
      return;
    }
    notify("success", t("sales.entryReversed"));
    await load();
  }

  const total = (tenders ?? []).filter((tender) => !tender.reversed_at).reduce((sum, tender) => sum + Number(tender.amount), 0);

  return (
    <div className="space-y-6">
      {!readOnly && (
        <Card title={t("sales.recordTitle")} description={t("sales.recordDescription")}>
          <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <Select
              required
              value={form.payment_method_id}
              onChange={(e) => setForm({ ...form, payment_method_id: e.target.value, credit_customer_id: "" })}
            >
              <option value="" disabled>
                {t("sales.paymentMethod")}
              </option>
              {(methods ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({t(CATEGORY_LABEL_KEY[m.category])})
                </option>
              ))}
            </Select>
            <TextInput
              required
              type="number"
              step="0.01"
              placeholder={t("sales.amount")}
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            {isCredit && (
              <Select
                required
                value={form.credit_customer_id}
                onChange={(e) => setForm({ ...form, credit_customer_id: e.target.value })}
              >
                <option value="" disabled>
                  {t("sales.customer")}
                </option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            )}
            <Button type="submit" busy={submitting}>
              {t("common.record")}
            </Button>
          </form>
        </Card>
      )}

      <Card title={t("sales.todaysCollections")} description={`${t("sales.totalSoFar")}: ${total.toFixed(2)}`}>
        {!tenders ? (
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        ) : tenders.length === 0 ? (
          <EmptyState icon={Wallet} title={t("sales.noCollectionsYet")} description={t("sales.noCollectionsDescription")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">{t("sales.method")}</th>
                <th className="py-2 pr-2">{t("sales.amount")}</th>
                <th className="py-2 pr-2">{t("sales.reference")}</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {tenders.map((tender) => {
                const method = methods?.find((m) => m.id === tender.payment_method_id);
                return (
                  <tr key={tender.id} className={`border-b border-border/60 ${tender.reversed_at ? "opacity-50" : ""}`}>
                    <td className="py-2 pr-2 text-ink">{method?.name ?? "—"}</td>
                    <td className="py-2 pr-2 text-ink">{tender.amount}</td>
                    <td className="py-2 pr-2 text-ink-soft">{tender.reference ?? "—"}</td>
                    <td className="py-2 pr-2 text-right">
                      {!tender.reversed_at && (
                        <button onClick={() => reverseTender(tender.id)} className="text-xs font-medium text-danger-600 hover:underline">
                          {t("common.reverse")}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
