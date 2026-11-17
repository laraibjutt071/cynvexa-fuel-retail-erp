"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Field";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { ConfirmDialog } from "@/components/ui/Dialog";
import type { Organization, OrgUser, Plan, RoleAssignment, Station, Subscription, SubscriptionStatus } from "@/lib/types";

const STATUS_TONE: Record<SubscriptionStatus, BadgeTone> = {
  trial: "warning",
  active: "success",
  past_due: "caution",
  canceled: "neutral",
  expired: "danger",
};

export default function OrganizationDetailPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { authFetch } = useAuth();
  const { notify } = useToast();
  const router = useRouter();

  const [org, setOrg] = useState<Organization | null>(null);
  const [stations, setStations] = useState<Station[] | null>(null);
  const [users, setUsers] = useState<OrgUser[] | null>(null);
  const [ownerRoles, setOwnerRoles] = useState<Map<string, RoleAssignment[]>>(new Map());
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [confirmSuspend, setConfirmSuspend] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [orgResp, stationsResp, usersResp, plansResp, subResp] = await Promise.all([
      authFetch(`/organizations/${orgId}`),
      authFetch(`/organizations/${orgId}/stations`),
      authFetch(`/organizations/${orgId}/users`),
      authFetch("/platform/plans"),
      authFetch(`/platform/organizations/${orgId}/subscription`),
    ]);
    if (orgResp.ok) setOrg(await orgResp.json());
    if (stationsResp.ok) setStations(await stationsResp.json());
    if (plansResp.ok) setPlans(await plansResp.json());
    setSubscription(subResp.ok ? await subResp.json() : null);

    if (usersResp.ok) {
      const list: OrgUser[] = await usersResp.json();
      setUsers(list);
      const roleEntries = await Promise.all(
        list.map(async (u) => {
          const r = await authFetch(`/organizations/${orgId}/users/${u.id}/roles`);
          return [u.id, r.ok ? ((await r.json()) as RoleAssignment[]) : []] as const;
        })
      );
      setOwnerRoles(new Map(roleEntries));
    }
  }, [authFetch, orgId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function toggleSuspend() {
    if (!org || busy) return;
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !org.is_active }),
      });
      if (!resp.ok) {
        notify("error", "Could not update this organization's status.");
        return;
      }
      notify("success", org.is_active ? "Organization suspended." : "Organization reactivated.");
      setConfirmSuspend(false);
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (!org) {
    return <div className="mx-auto max-w-5xl px-4 py-10 text-sm text-ink-soft sm:px-6">Loading…</div>;
  }

  const ownerRows = (users ?? []).filter((u) => (ownerRoles.get(u.id) ?? []).some((r) => r.station_id === null));

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/dashboard/platform/organizations" className="text-xs text-accent hover:underline">
            ← All organizations
          </Link>
          <div className="mt-1 flex items-center gap-2">
            <h1 className="text-xl font-semibold text-ink">{org.name}</h1>
            <Badge tone={org.is_active ? "success" : "danger"}>{org.is_active ? "Active" : "Suspended"}</Badge>
          </div>
        </div>
        <Button variant={org.is_active ? "danger" : "primary"} onClick={() => setConfirmSuspend(true)}>
          {org.is_active ? "Suspend organization" : "Reactivate organization"}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Business information">
          <dl className="space-y-2.5 text-sm">
            <Row label="Legal name" value={org.legal_name ?? "—"} />
            <Row label="Phone" value={org.phone ?? "—"} />
            <Row label="Address" value={org.address ?? "—"} />
            <Row label="City / Province" value={[org.city, org.province].filter(Boolean).join(", ") || "—"} />
            <Row label="Country" value={org.country ?? "—"} />
            <Row label="Created" value={new Date(org.created_at).toLocaleString()} />
          </dl>
        </Card>

        <Card title="Owner(s)">
          {!users ? (
            <p className="text-sm text-ink-soft">Loading…</p>
          ) : ownerRows.length === 0 ? (
            <p className="text-sm text-ink-soft">No org-wide Owner found.</p>
          ) : (
            <ul className="divide-y divide-border">
              {ownerRows.map((u) => (
                <li key={u.id} className="py-2.5">
                  <p className="text-sm font-medium text-ink">{u.full_name}</p>
                  <p className="text-xs text-ink-faint">{u.email}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Stations" description="Every station this organization operates.">
        {!stations ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : stations.length === 0 ? (
          <p className="text-sm text-ink-soft">No stations yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {stations.map((s) => (
              <li key={s.id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-ink">
                  {s.name} <span className="text-ink-faint">{s.code}</span>
                </span>
                <Badge tone={s.is_active ? "success" : "neutral"}>{s.is_active ? "active" : "inactive"}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="All users" description={`${users?.length ?? 0} account(s) with a role in this organization.`}>
        {!users ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : (
          <ul className="divide-y divide-border">
            {users.map((u) => (
              <li key={u.id} className="flex items-center justify-between py-2.5 text-sm">
                <div>
                  <p className="text-ink">{u.full_name}</p>
                  <p className="text-xs text-ink-faint">{u.email}</p>
                </div>
                <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "active" : "deactivated"}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <SubscriptionCard orgId={orgId} subscription={subscription} plans={plans} onChanged={load} />

      <ConfirmDialog
        open={confirmSuspend}
        onClose={() => setConfirmSuspend(false)}
        onConfirm={toggleSuspend}
        busy={busy}
        title={org.is_active ? "Suspend this organization?" : "Reactivate this organization?"}
        description={
          org.is_active
            ? "Every user in this organization will immediately lose API access until it's reactivated. This does not delete any data."
            : "This organization's users will immediately regain normal access."
        }
        confirmLabel={org.is_active ? "Suspend" : "Reactivate"}
        confirmVariant={org.is_active ? "danger" : "primary"}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="text-right text-ink">{value}</dd>
    </div>
  );
}

function SubscriptionCard({
  orgId,
  subscription,
  plans,
  onChanged,
}: {
  orgId: string;
  subscription: Subscription | null;
  plans: Plan[];
  onChanged: () => void;
}) {
  const { authFetch } = useAuth();
  const { notify } = useToast();
  const [planId, setPlanId] = useState(plans[0]?.id ?? "");
  const [status, setStatus] = useState<SubscriptionStatus>(subscription?.status ?? "trial");
  const [submitting, setSubmitting] = useState(false);

  async function assignSubscription() {
    if (submitting || !planId) return;
    setSubmitting(true);
    try {
      const now = new Date();
      const periodEnd = new Date(now);
      periodEnd.setDate(periodEnd.getDate() + 30);
      const resp = await authFetch(`/platform/organizations/${orgId}/subscription`, {
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
        notify("error", "Could not assign a subscription.");
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

  return (
    <Card title="Subscription">
      {subscription ? (
        <div className="space-y-3">
          <p className="text-sm text-ink">
            {subscription.plan.name} · <Badge tone={STATUS_TONE[subscription.status]}>{subscription.status}</Badge>
            {" · "}period ends {new Date(subscription.current_period_end).toLocaleDateString()}
          </p>
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
        </div>
      ) : (
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
      )}
    </Card>
  );
}
