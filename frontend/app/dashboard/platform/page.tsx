"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { Organization, Plan, Subscription, SubscriptionStatus } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

const STATUS_TONE: Record<SubscriptionStatus, BadgeTone> = {
  trial: "warning",
  active: "success",
  past_due: "caution",
  canceled: "neutral",
  expired: "danger",
};

/** Platform-admin only - manages the Plan catalog and every organization's
 * subscription. Deliberately NOT wrapped in the org-scoped AppShell (this
 * page has no orgId in its own route), so it has its own minimal header. */
export default function PlatformAdminPage() {
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();
  const { notify } = useToast();

  useEffect(() => {
    if (!loading && (!user || !user.is_superuser)) router.replace("/dashboard");
  }, [loading, user, router]);

  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [subscriptions, setSubscriptions] = useState<Subscription[] | null>(null);
  const [newPlan, setNewPlan] = useState({ code: "", name: "", price_monthly: "", price_annual: "", max_stations: "", max_users: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const [plansResp, orgsResp, subsResp] = await Promise.all([
      authFetch("/platform/plans"),
      authFetch("/organizations"),
      authFetch("/platform/subscriptions"),
    ]);
    if (plansResp.ok) setPlans(await plansResp.json());
    if (orgsResp.ok) setOrgs(await orgsResp.json());
    if (subsResp.ok) setSubscriptions(await subsResp.json());
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

  if (loading || !user?.is_superuser) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-ink-soft">Loading…</p>
      </main>
    );
  }

  const subByOrg = new Map((subscriptions ?? []).map((s) => [s.organization_id, s]));

  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border bg-sidebar px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <Link href="/dashboard" className="text-xs text-brand-500 hover:underline">
              ← Back to organizations
            </Link>
            <h1 className="text-lg font-semibold text-ink">Platform Admin</h1>
            <p className="mt-1 text-sm text-ink-soft">Plans and subscriptions across every organization on CYNVEXA.</p>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
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
                    <td className="py-2 pr-2 text-ink-soft">{p.price_monthly}</td>
                    <td className="py-2 pr-2 text-ink-soft">{p.price_annual}</td>
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

        <Card title="Organizations & subscriptions">
          {!orgs ? (
            <p className="text-sm text-ink-soft">Loading…</p>
          ) : (
            <div className="space-y-3">
              {orgs.map((org) => (
                <OrgSubscriptionRow
                  key={org.id}
                  org={org}
                  subscription={subByOrg.get(org.id) ?? null}
                  plans={plans ?? []}
                  authFetch={authFetch}
                  onChanged={load}
                />
              ))}
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}

function OrgSubscriptionRow({
  org,
  subscription,
  plans,
  authFetch,
  onChanged,
}: {
  org: Organization;
  subscription: Subscription | null;
  plans: Plan[];
  authFetch: AuthFetch;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const [expanded, setExpanded] = useState(false);
  const [planId, setPlanId] = useState(plans[0]?.id ?? "");
  const [status, setStatus] = useState<SubscriptionStatus>(subscription?.status ?? "trial");
  const [submitting, setSubmitting] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState("bank_transfer");
  const [payReference, setPayReference] = useState("");

  async function assignSubscription() {
    if (submitting || !planId) return;
    setSubmitting(true);
    try {
      const now = new Date();
      const periodEnd = new Date(now);
      periodEnd.setDate(periodEnd.getDate() + 30);
      const resp = await authFetch(`/platform/organizations/${org.id}/subscription`, {
        method: "POST",
        body: JSON.stringify({
          plan_id: planId,
          billing_cycle: "monthly",
          status: "trial",
          trial_ends_at: periodEnd.toISOString(),
          current_period_start: now.toISOString(),
          current_period_end: periodEnd.toISOString(),
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not assign a subscription." }));
        notify("error", body.detail ?? "Could not assign a subscription.");
        return;
      }
      notify("success", "Subscription assigned.");
      await onChanged();
    } finally {
      setSubmitting(false);
    }
  }

  async function updateStatus() {
    if (!subscription || submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`/platform/subscriptions/${subscription.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      if (!resp.ok) {
        notify("error", "Could not update subscription status.");
        return;
      }
      notify("success", "Subscription status updated.");
      await onChanged();
    } finally {
      setSubmitting(false);
    }
  }

  async function recordPayment() {
    if (!subscription || submitting || !payAmount) return;
    setSubmitting(true);
    try {
      const now = new Date();
      const periodEnd = new Date(now);
      periodEnd.setDate(periodEnd.getDate() + 30);
      const resp = await authFetch(`/platform/subscriptions/${subscription.id}/payments`, {
        method: "POST",
        body: JSON.stringify({
          amount: payAmount,
          method: payMethod,
          reference: payReference || undefined,
          period_start: now.toISOString(),
          period_end: periodEnd.toISOString(),
        }),
      });
      if (!resp.ok) {
        notify("error", "Could not record this payment.");
        return;
      }
      notify("success", "Payment recorded and verified.");
      setPayAmount("");
      setPayReference("");
      await onChanged();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card-glow rounded-lg bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-ink">
            {org.name} <span className="text-ink-faint">· {org.is_active ? "active account" : "suspended"}</span>
          </p>
          {subscription ? (
            <p className="mt-0.5 text-xs text-ink-soft">
              {subscription.plan.name} · <Badge tone={STATUS_TONE[subscription.status]}>{subscription.status}</Badge>
              {" · "}period ends {new Date(subscription.current_period_end).toLocaleDateString()}
            </p>
          ) : (
            <p className="mt-0.5 text-xs text-ink-faint">No subscription yet.</p>
          )}
        </div>
        <button onClick={() => setExpanded(!expanded)} className="text-xs font-medium text-accent hover:underline">
          {expanded ? "Close" : "Manage"}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-border pt-3">
          {!subscription ? (
            <div className="flex flex-wrap items-end gap-2">
              <Select value={planId} onChange={(e) => setPlanId(e.target.value)} className="w-40">
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
              <Button size="sm" busy={submitting} onClick={assignSubscription}>
                Start trial subscription
              </Button>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-2">
                <Select value={status} onChange={(e) => setStatus(e.target.value as SubscriptionStatus)} className="w-40">
                  <option value="trial">trial</option>
                  <option value="active">active</option>
                  <option value="past_due">past_due</option>
                  <option value="canceled">canceled</option>
                  <option value="expired">expired</option>
                </Select>
                <Button size="sm" variant="secondary" busy={submitting} onClick={updateStatus}>
                  Update status
                </Button>
              </div>

              <div className="flex flex-wrap items-end gap-2">
                <TextInput type="number" step="0.01" placeholder="Amount" className="w-28" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} />
                <Select value={payMethod} onChange={(e) => setPayMethod(e.target.value)} className="w-36">
                  <option value="bank_transfer">Bank transfer</option>
                  <option value="jazzcash">JazzCash</option>
                  <option value="easypaisa">Easypaisa</option>
                  <option value="card">Card</option>
                  <option value="cash">Cash</option>
                </Select>
                <TextInput placeholder="Reference (optional)" className="w-40" value={payReference} onChange={(e) => setPayReference(e.target.value)} />
                <Button size="sm" busy={submitting} onClick={recordPayment}>
                  Record verified payment
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
