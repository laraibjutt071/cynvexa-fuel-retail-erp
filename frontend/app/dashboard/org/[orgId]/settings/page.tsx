"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { OrgUser, Role, RoleAssignment, Session, Station, Subscription, SubscriptionPayment, SubscriptionStatus } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function SettingsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { user, authFetch } = useAuth();
  const { language, setLanguage, t } = useLanguage();

  const isSuperuser = user?.is_superuser ?? false;
  const permissions = useMemo(() => {
    const perms = new Set<string>();
    for (const role of user?.station_roles ?? []) {
      if (role.organization_id === orgId) role.permissions.forEach((p) => perms.add(p));
    }
    return perms;
  }, [user, orgId]);
  const can = useCallback((code: string) => isSuperuser || permissions.has(code), [isSuperuser, permissions]);

  return (
    <main className="flex-1">
      <header className="border-b border-border bg-surface px-6 py-4">
        <div className="mx-auto max-w-5xl">
          <h1 className="text-lg font-semibold text-ink">{t("settings.title")}</h1>
          <p className="mt-1 text-sm text-ink-soft">{t("settings.subtitle")}</p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <AccountCard authFetch={authFetch} language={language} setLanguage={setLanguage} t={t} />
        {can("subscription:read") && <BillingCard orgId={orgId} authFetch={authFetch} />}
        {can("user:read") && (
          <OrgUsersCard
            orgId={orgId}
            authFetch={authFetch}
            canCreate={can("user:create")}
            canAssign={can("user:assign_role")}
            t={t}
          />
        )}
      </div>
    </main>
  );
}

function AccountCard({
  authFetch,
  language,
  setLanguage,
  t,
}: {
  authFetch: AuthFetch;
  language: "en" | "ur";
  setLanguage: (lang: "en" | "ur") => void;
  t: (key: Parameters<ReturnType<typeof useLanguage>["t"]>[0]) => string;
}) {
  const { notify } = useToast();
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadSessions = useCallback(async () => {
    const resp = await authFetch("/auth/sessions");
    if (resp.ok) setSessions(await resp.json());
  }, [authFetch]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSessions();
  }, [loadSessions]);

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch("/auth/password", {
        method: "PATCH",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not change your password." }));
        notify("error", body.detail ?? "Could not change your password.");
        return;
      }
      notify("success", t("settings.passwordChanged"));
      setCurrentPassword("");
      setNewPassword("");
      await loadSessions();
    } finally {
      setSubmitting(false);
    }
  }

  async function signOutEverywhere() {
    const resp = await authFetch("/auth/logout-all", { method: "POST" });
    if (resp.ok) {
      notify("success", t("settings.signedOutEverywhere"));
      await loadSessions();
    }
  }

  return (
    <Card title={t("settings.yourAccount")}>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium text-ink">{t("settings.language")}</p>
          <div className="flex gap-2">
            <Button variant={language === "en" ? "primary" : "secondary"} size="sm" onClick={() => setLanguage("en")}>
              English
            </Button>
            <Button variant={language === "ur" ? "primary" : "secondary"} size="sm" onClick={() => setLanguage("ur")}>
              Roman Urdu
            </Button>
          </div>
          <p className="mt-1 text-xs text-ink-faint">{t("settings.languageHelp")}</p>

          <p className="mt-5 mb-2 text-sm font-medium text-ink">{t("settings.activeSessions")}</p>
          <p className="text-sm text-ink-soft">{sessions ? sessions.length : "…"}</p>
          <Button variant="secondary" size="sm" className="mt-2" onClick={signOutEverywhere}>
            {t("settings.signOutEverywhere")}
          </Button>
        </div>

        <form onSubmit={changePassword} className="space-y-3">
          <p className="text-sm font-medium text-ink">{t("settings.changePassword")}</p>
          <Field label={t("settings.currentPassword")} required>
            {(id) => (
              <TextInput
                id={id}
                type="password"
                required
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            )}
          </Field>
          <Field label={t("settings.newPassword")} required>
            {(id) => (
              <TextInput
                id={id}
                type="password"
                required
                minLength={10}
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" busy={submitting} size="sm">
            {t("settings.changePassword")}
          </Button>
        </form>
      </div>
    </Card>
  );
}

function OrgUsersCard({
  orgId,
  authFetch,
  canCreate,
  canAssign,
  t,
}: {
  orgId: string;
  authFetch: AuthFetch;
  canCreate: boolean;
  canAssign: boolean;
  t: (key: Parameters<ReturnType<typeof useLanguage>["t"]>[0]) => string;
}) {
  const { notify } = useToast();
  const [users, setUsers] = useState<OrgUser[] | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<RoleAssignment[] | null>(null);
  const [newUser, setNewUser] = useState({ email: "", full_name: "", password: "" });
  const [assignForm, setAssignForm] = useState({ role_id: "", station_id: "" });
  const [submitting, setSubmitting] = useState(false);

  const loadUsers = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/users`);
    if (resp.ok) setUsers(await resp.json());
  }, [authFetch, orgId]);

  useEffect(() => {
    (async () => {
      await loadUsers();
      const [rolesResp, stationsResp] = await Promise.all([
        authFetch("/roles"),
        authFetch(`/organizations/${orgId}/stations`),
      ]);
      if (rolesResp.ok) setRoles(await rolesResp.json());
      if (stationsResp.ok) setStations(await stationsResp.json());
    })();
  }, [authFetch, orgId, loadUsers]);

  const loadAssignments = useCallback(async (userId: string) => {
    const resp = await authFetch(`/organizations/${orgId}/users/${userId}/roles`);
    setAssignments(resp.ok ? await resp.json() : []);
  }, [authFetch, orgId]);

  useEffect(() => {
    if (selectedUserId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadAssignments(selectedUserId);
    }
  }, [selectedUserId, loadAssignments]);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/users`, {
        method: "POST",
        body: JSON.stringify(newUser),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not create this user." }));
        notify("error", body.detail ?? "Could not create this user.");
        return;
      }
      notify("success", t("settings.userCreated"));
      setNewUser({ email: "", full_name: "", password: "" });
      await loadUsers();
    } finally {
      setSubmitting(false);
    }
  }

  async function assignRole(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedUserId || submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/users/${selectedUserId}/roles`, {
        method: "POST",
        body: JSON.stringify({
          role_id: assignForm.role_id,
          station_id: assignForm.station_id || null,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not assign this role." }));
        notify("error", body.detail ?? "Could not assign this role.");
        return;
      }
      notify("success", t("settings.roleAssigned"));
      setAssignForm({ role_id: "", station_id: "" });
      await loadAssignments(selectedUserId);
    } finally {
      setSubmitting(false);
    }
  }

  async function revokeRole(assignmentId: string) {
    if (!selectedUserId) return;
    const resp = await authFetch(`/organizations/${orgId}/users/${selectedUserId}/roles/${assignmentId}`, {
      method: "DELETE",
    });
    if (!resp.ok) {
      notify("error", "Could not revoke this role.");
      return;
    }
    notify("success", t("settings.roleRevoked"));
    await loadAssignments(selectedUserId);
  }

  const roleName = (roleId: string) => roles.find((r) => r.id === roleId)?.name ?? roleId;
  const stationName = (stationId: string | null) =>
    stationId ? stations.find((s) => s.id === stationId)?.name ?? stationId : t("settings.orgWide");

  return (
    <div className="space-y-6">
      <Card title={t("settings.orgUsers")}>
        {!users ? (
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">{t("settings.fullName")}</th>
                <th className="py-2 pr-2">{t("settings.email")}</th>
                <th className="py-2 pr-2">{t("expenses.status")}</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={`border-b border-border/60 ${selectedUserId === u.id ? "bg-surface-elevated" : ""}`}>
                  <td className="py-2 pr-2 text-ink">{u.full_name}</td>
                  <td className="py-2 pr-2 text-ink-soft">{u.email}</td>
                  <td className="py-2 pr-2 text-ink-soft">{u.is_active ? t("common.yes") : t("common.no")}</td>
                  <td className="py-2 pr-2 text-right">
                    <button onClick={() => setSelectedUserId(u.id)} className="text-xs font-medium text-accent hover:underline">
                      {t("settings.roles")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {canCreate && (
        <Card title={t("settings.addUser")}>
          <form onSubmit={createUser} className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <Field label={t("settings.fullName")} required>
              {(id) => (
                <TextInput id={id} required value={newUser.full_name} onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })} />
              )}
            </Field>
            <Field label={t("settings.email")} required>
              {(id) => (
                <TextInput id={id} type="email" required value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} />
              )}
            </Field>
            <Field label={t("settings.temporaryPassword")} required hint="At least 10 characters.">
              {(id) => (
                <TextInput
                  id={id}
                  type="password"
                  required
                  minLength={10}
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                />
              )}
            </Field>
            <div className="flex items-end">
              <Button type="submit" busy={submitting} className="w-full">
                {t("settings.createUser")}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {selectedUserId ? (
        <Card title={`${t("settings.roles")} — ${users?.find((u) => u.id === selectedUserId)?.full_name ?? ""}`}>
          {!assignments ? (
            <p className="text-sm text-ink-soft">{t("common.loading")}</p>
          ) : assignments.length === 0 ? (
            <p className="text-sm text-ink-soft">{t("settings.noRolesYet")}</p>
          ) : (
            <ul className="space-y-2">
              {assignments.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
                  <span className="text-sm text-ink">
                    {roleName(a.role_id)} <span className="text-ink-faint">· {stationName(a.station_id)}</span>
                  </span>
                  {canAssign && (
                    <button onClick={() => revokeRole(a.id)} className="text-xs font-medium text-danger-600 hover:underline">
                      {t("settings.revoke")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {canAssign && (
            <form onSubmit={assignRole} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-3">
              <Select required value={assignForm.role_id} onChange={(e) => setAssignForm({ ...assignForm, role_id: e.target.value })}>
                <option value="" disabled>
                  {t("settings.role")}
                </option>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
              <Select value={assignForm.station_id} onChange={(e) => setAssignForm({ ...assignForm, station_id: e.target.value })}>
                <option value="">{t("settings.allStations")}</option>
                {stations.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
              <Button type="submit" busy={submitting}>
                {t("settings.assign")}
              </Button>
            </form>
          )}
        </Card>
      ) : (
        <p className="text-sm text-ink-soft">{t("settings.selectUser")}</p>
      )}
    </div>
  );
}

const SUB_STATUS_TONE: Record<SubscriptionStatus, BadgeTone> = {
  trial: "warning",
  active: "success",
  past_due: "caution",
  canceled: "neutral",
  expired: "danger",
};

function BillingCard({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const [subscription, setSubscription] = useState<Subscription | "none" | null>(null);
  const [payments, setPayments] = useState<SubscriptionPayment[]>([]);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/subscription`);
      if (!resp.ok) {
        setSubscription("none");
        return;
      }
      setSubscription(await resp.json());
      const payResp = await authFetch(`/organizations/${orgId}/subscription/payments`);
      if (payResp.ok) setPayments(await payResp.json());
    })();
  }, [authFetch, orgId]);

  return (
    <Card title="Billing & subscription">
      {subscription === null ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : subscription === "none" ? (
        <p className="text-sm text-ink-soft">No subscription set up yet - contact CYNVEXA to get started.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-ink-faint">Plan</p>
              <p className="text-sm font-semibold text-ink">{subscription.plan.name}</p>
            </div>
            <div>
              <p className="text-xs text-ink-faint">Status</p>
              <Badge tone={SUB_STATUS_TONE[subscription.status]}>{subscription.status.replace(/_/g, " ")}</Badge>
            </div>
            <div>
              <p className="text-xs text-ink-faint">Billing cycle</p>
              <p className="text-sm text-ink">{subscription.billing_cycle}</p>
            </div>
            <div>
              <p className="text-xs text-ink-faint">Current period ends</p>
              <p className="text-sm text-ink">{new Date(subscription.current_period_end).toLocaleDateString()}</p>
            </div>
          </div>

          {payments.length > 0 && (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-ink-faint">
                  <th className="py-2 pr-2">Date</th>
                  <th className="py-2 pr-2">Amount</th>
                  <th className="py-2 pr-2">Method</th>
                  <th className="py-2 pr-2">Reference</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id} className="border-b border-border/60">
                    <td className="py-2 pr-2 text-ink">{new Date(p.created_at).toLocaleDateString()}</td>
                    <td className="py-2 pr-2 text-ink">{p.amount}</td>
                    <td className="py-2 pr-2 text-ink-soft">{p.method.replace(/_/g, " ")}</td>
                    <td className="py-2 pr-2 text-ink-soft">{p.reference ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </Card>
  );
}
