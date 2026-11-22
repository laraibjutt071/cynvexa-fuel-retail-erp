"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import type { Plan } from "@/lib/types";
import { formatMoney } from "@/lib/format";

export default function PlansPage() {
  const { authFetch } = useAuth();
  const { notify } = useToast();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [newPlan, setNewPlan] = useState({ code: "", name: "", price_monthly: "", price_annual: "", max_stations: "", max_users: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const resp = await authFetch("/platform/plans");
    if (resp.ok) setPlans(await resp.json());
  }, [authFetch]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function createPlan(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch("/platform/plans", {
        method: "POST",
        body: JSON.stringify({
          code: newPlan.code,
          name: newPlan.name,
          price_monthly: newPlan.price_monthly,
          price_annual: newPlan.price_annual,
          max_stations: newPlan.max_stations ? Number(newPlan.max_stations) : null,
          max_users: newPlan.max_users ? Number(newPlan.max_users) : null,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not create this plan." }));
        notify("error", body.detail ?? "Could not create this plan.");
        return;
      }
      notify("success", "Plan created.");
      setNewPlan({ code: "", name: "", price_monthly: "", price_annual: "", max_stations: "", max_users: "" });
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div>
        <h1 className="text-xl font-semibold text-ink">Plans</h1>
        <p className="mt-1 text-sm text-ink-soft">The subscription plan catalog offered to every organization.</p>
      </div>

      <Card title="Plans">
        {!plans ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">Code</th>
                <th className="py-2 pr-2">Name</th>
                <th className="py-2 pr-2">Monthly</th>
                <th className="py-2 pr-2">Annual</th>
                <th className="py-2 pr-2">Stations</th>
                <th className="py-2 pr-2">Users</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.id} className="border-b border-border/60">
                  <td className="py-2 pr-2 text-ink">{p.code}</td>
                  <td className="py-2 pr-2 text-ink">{p.name}</td>
                  <td className="py-2 pr-2 text-ink-soft">PKR {formatMoney(p.price_monthly)}</td>
                  <td className="py-2 pr-2 text-ink-soft">PKR {formatMoney(p.price_annual)}</td>
                  <td className="py-2 pr-2 text-ink-soft">{p.max_stations ?? "Unlimited"}</td>
                  <td className="py-2 pr-2 text-ink-soft">{p.max_users ?? "Unlimited"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <form onSubmit={createPlan} className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 sm:grid-cols-6">
          <Field label="Code" required>
            {(id) => <TextInput id={id} required placeholder="e.g. starter" value={newPlan.code} onChange={(e) => setNewPlan({ ...newPlan, code: e.target.value })} />}
          </Field>
          <Field label="Name" required>
            {(id) => <TextInput id={id} required value={newPlan.name} onChange={(e) => setNewPlan({ ...newPlan, name: e.target.value })} />}
          </Field>
          <Field label="Monthly price" required>
            {(id) => <TextInput id={id} required type="number" step="0.01" value={newPlan.price_monthly} onChange={(e) => setNewPlan({ ...newPlan, price_monthly: e.target.value })} />}
          </Field>
          <Field label="Annual price" required>
            {(id) => <TextInput id={id} required type="number" step="0.01" value={newPlan.price_annual} onChange={(e) => setNewPlan({ ...newPlan, price_annual: e.target.value })} />}
          </Field>
          <Field label="Max stations" hint="Blank = unlimited">
            {(id) => <TextInput id={id} type="number" value={newPlan.max_stations} onChange={(e) => setNewPlan({ ...newPlan, max_stations: e.target.value })} />}
          </Field>
          <Field label="Max users" hint="Blank = unlimited">
            {(id) => <TextInput id={id} type="number" value={newPlan.max_users} onChange={(e) => setNewPlan({ ...newPlan, max_users: e.target.value })} />}
          </Field>
          <div className="col-span-2 sm:col-span-6">
            <Button type="submit" busy={submitting}>
              Create plan
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
