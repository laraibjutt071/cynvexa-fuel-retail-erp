"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { ConfirmDialog } from "@/components/ui/Dialog";
import type { OrgUser, Role, RoleAssignment, Station } from "@/lib/types";

export default function EmployeeProfilePage() {
  const { orgId, userId } = useParams<{ orgId: string; userId: string }>();
  const { authFetch } = useAuth();
  const { can } = usePermissions(orgId);
  const { notify } = useToast();

  const [user, setUser] = useState<OrgUser | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [assignments, setAssignments] = useState<RoleAssignment[] | null>(null);
  const [form, setForm] = useState({ full_name: "", employee_code: "", job_title: "", phone: "" });
  const [editing, setEditing] = useState(false);
  const [confirmToggle, setConfirmToggle] = useState(false);
  const [busy, setBusy] = useState(false);
  const [assignForm, setAssignForm] = useState({ role_id: "", station_id: "" });

  const load = useCallback(async () => {
    const [userResp, rolesResp, stationsResp, assignResp] = await Promise.all([
      authFetch(`/organizations/${orgId}/users/${userId}`),
      authFetch("/roles"),
      authFetch(`/organizations/${orgId}/stations`),
      authFetch(`/organizations/${orgId}/users/${userId}/roles`),
    ]);
    if (userResp.ok) {
      const u: OrgUser = await userResp.json();
      setUser(u);
      setForm({ full_name: u.full_name, employee_code: u.employee_code ?? "", job_title: u.job_title ?? "", phone: u.phone ?? "" });
    }
    if (rolesResp.ok) setRoles(await rolesResp.json());
    if (stationsResp.ok) setStations(await stationsResp.json());
    setAssignments(assignResp.ok ? await assignResp.json() : []);
  }, [authFetch, orgId, userId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const canUpdate = can("user:update");
  const canAssign = can("user:assign_role");

  async function saveProfile() {
    if (busy) return;
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify(form),
      });
      if (!resp.ok) {
        notify("error", "Could not save changes.");
        return;
      }
      notify("success", "Profile updated.");
      setEditing(false);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive() {
    if (!user || busy) return;
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !user.is_active }),
      });
      if (!resp.ok) {
        notify("error", "Could not update employment status.");
        return;
      }
      notify("success", user.is_active ? "Employee deactivated." : "Employee reactivated.");
      setConfirmToggle(false);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function assignRole(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !assignForm.role_id) return;
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/users/${userId}/roles`, {
        method: "POST",
        body: JSON.stringify({ role_id: assignForm.role_id, station_id: assignForm.station_id || null }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not assign this role." }));
        notify("error", body.detail ?? "Could not assign this role.");
        return;
      }
      notify("success", "Role assigned.");
      setAssignForm({ role_id: "", station_id: "" });
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function revokeRole(assignmentId: string) {
    const resp = await authFetch(`/organizations/${orgId}/users/${userId}/roles/${assignmentId}`, { method: "DELETE" });
    if (!resp.ok) {
      notify("error", "Could not revoke this role.");
      return;
    }
    notify("success", "Role revoked.");
    await load();
  }

  const roleName = (id: string) => roles.find((r) => r.id === id)?.name ?? "—";
  const stationName = (id: string | null) => (id ? stations.find((s) => s.id === id)?.name ?? "—" : "Org-wide");

  if (!user) {
    return <div className="px-6 py-10 text-sm text-ink-soft">Loading…</div>;
  }

  return (
    <div className="flex-1">
      <PageHeader
        title={user.full_name}
        breadcrumbs={[
          { label: "Staff", href: `/dashboard/org/${orgId}/staff` },
          { label: user.full_name },
        ]}
        action={
          canUpdate && (
            <Button variant={user.is_active ? "danger" : "primary"} onClick={() => setConfirmToggle(true)}>
              {user.is_active ? "Deactivate" : "Reactivate"}
            </Button>
          )
        }
      />

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <div className="flex items-center gap-2">
          <Badge tone={user.is_active ? "success" : "neutral"}>{user.is_active ? "Active" : "Inactive"}</Badge>
          {user.job_title && <span className="text-sm text-ink-soft">{user.job_title}</span>}
        </div>

        <Card
          title="Profile"
          action={
            canUpdate && !editing ? (
              <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                Edit
              </Button>
            ) : undefined
          }
        >
          {editing ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Full name" required>
                  {(id) => <TextInput id={id} required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />}
                </Field>
                <Field label="Phone">
                  {(id) => <TextInput id={id} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />}
                </Field>
                <Field label="Employee code">
                  {(id) => <TextInput id={id} value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value })} />}
                </Field>
                <Field label="Job designation">
                  {(id) => <TextInput id={id} value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} />}
                </Field>
              </div>
              <div className="flex gap-2">
                <Button size="sm" busy={busy} onClick={saveProfile}>
                  Save changes
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
              <Row label="Email" value={user.email} />
              <Row label="Phone" value={user.phone ?? "—"} />
              <Row label="Employee code" value={user.employee_code ?? "—"} />
              <Row label="Job designation" value={user.job_title ?? "—"} />
              <Row label="Account created" value={new Date(user.created_at).toLocaleDateString()} />
            </dl>
          )}
        </Card>

        <Card title="Roles & station access">
          {!assignments ? (
            <p className="text-sm text-ink-soft">Loading…</p>
          ) : assignments.length === 0 ? (
            <p className="text-sm text-ink-soft">No roles assigned yet - this employee cannot access anything until one is granted.</p>
          ) : (
            <ul className="space-y-2">
              {assignments.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
                  <div>
                    <span className="text-sm text-ink">
                      {roleName(a.role_id)} <span className="text-ink-faint">· {stationName(a.station_id)}</span>
                    </span>
                    <p className="text-xs text-ink-faint">Joined {new Date(a.created_at).toLocaleDateString()}</p>
                  </div>
                  {canAssign && (
                    <button onClick={() => revokeRole(a.id)} className="text-xs font-medium text-danger-600 hover:underline">
                      Revoke
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
                  Role
                </option>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
              <Select value={assignForm.station_id} onChange={(e) => setAssignForm({ ...assignForm, station_id: e.target.value })}>
                <option value="">Org-wide</option>
                {stations.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
              <Button type="submit" busy={busy}>
                Assign
              </Button>
            </form>
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={confirmToggle}
        onClose={() => setConfirmToggle(false)}
        onConfirm={toggleActive}
        busy={busy}
        title={user.is_active ? "Deactivate this employee?" : "Reactivate this employee?"}
        description={
          user.is_active
            ? "They will immediately lose access to every station and API in this organization. This does not delete any of their records."
            : "They will immediately regain their previous role and station access."
        }
        confirmLabel={user.is_active ? "Deactivate" : "Reactivate"}
        confirmVariant={user.is_active ? "danger" : "primary"}
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
