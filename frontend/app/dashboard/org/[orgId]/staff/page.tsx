"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Plus, Search, UserPlus } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api";
import type { OrgUser, Role, Station } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function StaffPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { authFetch } = useAuth();
  const { can } = usePermissions(orgId);
  const router = useRouter();

  const [users, setUsers] = useState<OrgUser[] | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "active" | "inactive">("");
  const [stationFilter, setStationFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    if (stationFilter) params.set("station_id", stationFilter);
    const resp = await authFetch(`/organizations/${orgId}/users?${params.toString()}`);
    if (resp.ok) setUsers(await resp.json());
  }, [authFetch, orgId, q, status, stationFilter]);

  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
  }, [load]);

  useEffect(() => {
    (async () => {
      const [rolesResp, stationsResp] = await Promise.all([
        authFetch("/roles"),
        authFetch(`/organizations/${orgId}/stations`),
      ]);
      if (rolesResp.ok) setRoles(await rolesResp.json());
      if (stationsResp.ok) setStations(await stationsResp.json());
    })();
  }, [authFetch, orgId]);

  const stationName = (id: string | null) => (id ? stations.find((s) => s.id === id)?.name ?? "—" : "Org-wide");

  const columns: Column<OrgUser>[] = [
    {
      key: "full_name",
      header: "Employee",
      sortable: true,
      sortValue: (u) => u.full_name,
      render: (u) => (
        <button onClick={() => router.push(`/dashboard/org/${orgId}/staff/${u.id}`)} className="font-medium text-ink hover:text-accent">
          {u.full_name}
        </button>
      ),
    },
    { key: "employee_code", header: "Code", render: (u) => u.employee_code ?? "—" },
    { key: "job_title", header: "Designation", render: (u) => u.job_title ?? "—" },
    { key: "email", header: "Email", render: (u) => u.email },
    { key: "status", header: "Status", render: (u) => <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</Badge> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (u) => (
        <button onClick={() => router.push(`/dashboard/org/${orgId}/staff/${u.id}`)} className="text-sm font-medium text-accent hover:underline">
          View →
        </button>
      ),
    },
  ];

  return (
    <main className="flex-1">
      <PageHeader
        title="Staff"
        breadcrumbs={[{ label: "Users & Settings", href: `/dashboard/org/${orgId}/settings` }, { label: "Staff" }]}
      />
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-soft">Everyone with access to this organization.</p>
          {can("user:create") && (
            <Button onClick={() => setCreateOpen(true)}>
              <UserPlus className="h-4 w-4" aria-hidden />
              Add employee
            </Button>
          )}
        </div>

        <Card title="All employees">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" aria-hidden />
              <TextInput placeholder="Search by name, email, or code…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
            </div>
            <Select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} className="w-40">
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
            <Select value={stationFilter} onChange={(e) => setStationFilter(e.target.value)} className="w-48">
              <option value="">All stations</option>
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          {users && users.length === 0 && !q && !status && !stationFilter ? (
            <EmptyState icon={UserPlus} title="No staff yet" description="Add your first employee to get started." />
          ) : (
            <DataTable columns={columns} data={users} keyFn={(u) => u.id} emptyMessage="No employees match this search." />
          )}
        </Card>
      </div>

      <AddEmployeeDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        orgId={orgId}
        authFetch={authFetch}
        roles={roles}
        stations={stations}
        onCreated={load}
      />
    </main>
  );
}

function AddEmployeeDialog({
  open,
  onClose,
  orgId,
  authFetch,
  roles,
  stations,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  orgId: string;
  authFetch: AuthFetch;
  roles: Role[];
  stations: Station[];
  onCreated: () => void;
}) {
  const { notify } = useToast();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    employee_code: "",
    job_title: "",
    phone: "",
    role_id: "",
    station_id: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setForm({ full_name: "", email: "", password: "", employee_code: "", job_title: "", phone: "", role_id: "", station_id: "" });
      setError(null);
    }
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const createResp = await authFetch(`/organizations/${orgId}/users`, {
        method: "POST",
        body: JSON.stringify({
          full_name: form.full_name,
          email: form.email,
          password: form.password,
          employee_code: form.employee_code || undefined,
          job_title: form.job_title || undefined,
          phone: form.phone || undefined,
        }),
      });
      if (!createResp.ok) {
        const body = await createResp.json().catch(() => ({ detail: "Could not create this employee." }));
        throw new ApiError(createResp.status, body.detail ?? "Could not create this employee.");
      }
      const user = await createResp.json();

      if (form.role_id) {
        const roleResp = await authFetch(`/organizations/${orgId}/users/${user.id}/roles`, {
          method: "POST",
          body: JSON.stringify({ role_id: form.role_id, station_id: form.station_id || null }),
        });
        if (!roleResp.ok) {
          const body = await roleResp.json().catch(() => ({ detail: "Employee created, but the role could not be assigned." }));
          notify("error", body.detail ?? "Employee created, but the role could not be assigned.");
          onClose();
          onCreated();
          return;
        }
      }

      notify("success", `${form.full_name} has been added.`);
      onClose();
      await onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Add employee" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Full name" required>
            {(id) => <TextInput id={id} required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />}
          </Field>
          <Field label="Email" required>
            {(id) => <TextInput id={id} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
          </Field>
          <Field label="Temporary password" required hint="At least 10 characters">
            {(id) => <TextInput id={id} type="password" required minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}
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
          <Field label="Role" hint="Can be assigned later from their profile">
            {(id) => (
              <Select id={id} value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
                <option value="">No role yet</option>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Station" hint="Leave blank for organization-wide">
            {(id) => (
              <Select id={id} value={form.station_id} onChange={(e) => setForm({ ...form, station_id: e.target.value })} disabled={!form.role_id}>
                <option value="">Org-wide</option>
                {stations.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        {error && <p className="text-sm text-danger-600">{error}</p>}
        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={submitting}>
            <Plus className="h-4 w-4" aria-hidden />
            Add employee
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
