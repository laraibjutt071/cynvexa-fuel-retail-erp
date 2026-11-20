"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Dialog } from "@/components/ui/Dialog";
import { ApiError } from "@/lib/api";
import type { Station } from "@/lib/types";

export default function StationsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { authFetch } = useAuth();
  const { can } = usePermissions(orgId);
  const router = useRouter();
  const { notify } = useToast();

  const [stations, setStations] = useState<Station[] | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", address: "", phone: "", email: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/stations`);
    if (resp.ok) setStations(await resp.json());
  }, [authFetch, orgId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function createStation(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await authFetch(`/organizations/${orgId}/stations`, {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          code: form.code,
          address: form.address || undefined,
          phone: form.phone || undefined,
          email: form.email || undefined,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not create this station." }));
        throw new ApiError(resp.status, body.detail ?? "Could not create this station.");
      }
      notify("success", `${form.name} has been added.`);
      setForm({ name: "", code: "", address: "", phone: "", email: "" });
      setCreateOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  const columns: Column<Station>[] = [
    {
      key: "name",
      header: "Station",
      sortable: true,
      sortValue: (s) => s.name,
      render: (s) => (
        <button
          onClick={() => router.push(`/dashboard/org/${orgId}/station/${s.id}/settings`)}
          className="font-medium text-ink hover:text-accent"
        >
          {s.name} <span className="font-normal text-ink-faint">{s.code}</span>
        </button>
      ),
    },
    { key: "address", header: "Address", render: (s) => s.address ?? "—" },
    { key: "phone", header: "Phone", render: (s) => s.phone ?? "—" },
    { key: "status", header: "Status", render: (s) => <Badge tone={s.is_active ? "success" : "neutral"}>{s.is_active ? "Active" : "Inactive"}</Badge> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (s) => (
        <button
          onClick={() => router.push(`/dashboard/org/${orgId}/station/${s.id}/today`)}
          className="text-sm font-medium text-accent hover:underline"
        >
          Open →
        </button>
      ),
    },
  ];

  return (
    <div className="flex-1">
      <PageHeader title="Stations" breadcrumbs={[{ label: "Users & Settings", href: `/dashboard/org/${orgId}/settings` }, { label: "Stations" }]} />
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-soft">Every station this organization operates.</p>
          {can("station:create") && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" aria-hidden />
              Add station
            </Button>
          )}
        </div>

        <Card title="All stations">
          <DataTable columns={columns} data={stations} keyFn={(s) => s.id} emptyMessage="No stations yet." />
        </Card>
      </div>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title="Add station">
        <form onSubmit={createStation} className="space-y-4">
          <Field label="Station name" required>
            {(id) => <TextInput id={id} required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
          </Field>
          <Field label="Station code" required hint="A short unique code, e.g. ST-2">
            {(id) => <TextInput id={id} required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />}
          </Field>
          <Field label="Address">
            {(id) => <TextInput id={id} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />}
          </Field>
          <Field label="Phone">
            {(id) => <TextInput id={id} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />}
          </Field>
          <Field label="Email">
            {(id) => <TextInput id={id} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
          </Field>
          {error && <p className="text-sm text-danger-600">{error}</p>}
          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <Button type="button" variant="secondary" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" busy={submitting}>
              Add station
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
