"use client";

import { Receipt } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n/context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/Badge";
import { ExpenseBreakdownChart } from "@/components/charts/ExpenseBreakdownChart";
import type { Expense } from "@/lib/types";
import type { AuthFetch } from "./page";

export function ExpensesSection({
  orgId,
  stationId,
  businessDate,
  authFetch,
}: {
  orgId: string;
  stationId: string;
  businessDate: string;
  authFetch: AuthFetch;
}) {
  const { notify } = useToast();
  const { t } = useLanguage();
  const [expenses, setExpenses] = useState<Expense[] | null>(null);
  const [form, setForm] = useState({ category: "", description: "", amount: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/expenses?station_id=${stationId}&limit=100`);
    if (resp.ok) {
      const all: Expense[] = await resp.json();
      setExpenses(all.filter((e) => e.expense_date === businessDate));
    }
  }, [authFetch, orgId, stationId, businessDate]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/expenses`, {
        method: "POST",
        body: JSON.stringify({
          station_id: stationId,
          category: form.category,
          description: form.description,
          amount: form.amount,
          expense_date: businessDate,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not record this expense." }));
        notify("error", body.detail ?? "Could not record this expense.");
        return;
      }
      notify("success", t("expenses.recorded"));
      setForm({ category: "", description: "", amount: "" });
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  const total = (expenses ?? [])
    .filter((e) => e.status !== "rejected" && !e.reversed_at)
    .reduce((sum, e) => sum + Number(e.amount), 0);

  return (
    <div className="space-y-6">
      <Card title={t("expenses.recordTitle")} description={t("expenses.recordDescription")}>
        <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <Field label={t("expenses.category")} required>
            {(id) => (
              <TextInput
                id={id}
                required
                placeholder="e.g. Electricity"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              />
            )}
          </Field>
          <Field label={t("expenses.description")} required>
            {(id) => (
              <TextInput
                id={id}
                required
                placeholder="What was this for?"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            )}
          </Field>
          <Field label={t("expenses.amount")} required>
            {(id) => (
              <TextInput
                id={id}
                required
                type="number"
                step="0.01"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            )}
          </Field>
          <div className="flex items-end">
            <Button type="submit" busy={submitting} className="w-full">
              {t("expenses.recordButton")}
            </Button>
          </div>
        </form>
      </Card>

      {expenses && expenses.length > 0 && <ExpenseBreakdownChart expenses={expenses} title={t("expenses.breakdown")} />}

      <Card title={t("expenses.todaysExpenses")} description={`${t("expenses.totalExcluding")}: ${total.toFixed(2)}`}>
        {!expenses ? (
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        ) : expenses.length === 0 ? (
          <EmptyState icon={Receipt} title={t("expenses.noneRecorded")} description={t("expenses.addAsCostsComeUp")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">{t("expenses.category")}</th>
                <th className="py-2 pr-2">{t("expenses.description")}</th>
                <th className="py-2 pr-2">{t("expenses.amount")}</th>
                <th className="py-2 pr-2">{t("expenses.status")}</th>
              </tr>
            </thead>
            <tbody>
              {expenses.map((e) => (
                <tr key={e.id} className="border-b border-border/60">
                  <td className="py-2 pr-2 text-ink">{e.category}</td>
                  <td className="py-2 pr-2 text-ink-soft">{e.description}</td>
                  <td className="py-2 pr-2 text-ink">{e.amount}</td>
                  <td className="py-2 pr-2">
                    <StatusBadge status={e.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
