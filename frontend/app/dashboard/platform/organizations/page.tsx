"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Search } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Select, TextInput } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { DataTable, type Column } from "@/components/ui/DataTable";
import type { Organization } from "@/lib/types";

export default function OrganizationsListPage() {
  const { authFetch } = useAuth();
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "active" | "suspended">("");

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    const resp = await authFetch(`/organizations?${params.toString()}`);
    if (resp.ok) setOrgs(await resp.json());
  }, [authFetch, q, status]);

  useEffect(() => {
    const id = setTimeout(load, 250); // debounce search-as-you-type
    return () => clearTimeout(id);
  }, [load]);

  const columns: Column<Organization>[] = [
    {
      key: "name",
      header: "Organization",
      sortable: true,
      sortValue: (o) => o.name,
      render: (o) => (
        <Link href={`/dashboard/platform/organizations/${o.id}`} className="font-medium text-ink hover:text-accent">
          {o.name}
        </Link>
      ),
    },
    { key: "location", header: "Location", render: (o) => [o.city, o.country].filter(Boolean).join(", ") || "—" },
    { key: "status", header: "Status", render: (o) => <Badge tone={o.is_active ? "success" : "danger"}>{o.is_active ? "Active" : "Suspended"}</Badge> },
    {
      key: "created_at",
      header: "Created",
      sortable: true,
      sortValue: (o) => o.created_at,
      render: (o) => new Date(o.created_at).toLocaleDateString(),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (o) => (
        <Link href={`/dashboard/platform/organizations/${o.id}`} className="text-sm font-medium text-accent hover:underline">
          View →
        </Link>
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">Organizations</h1>
          <p className="mt-1 text-sm text-ink-soft">Every petrol pump tenant on the platform.</p>
        </div>
        <Link href="/dashboard/platform/organizations/new">
          <Button>
            <Plus className="h-4 w-4" aria-hidden />
            Create organization
          </Button>
        </Link>
      </div>

      <Card title="All organizations">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" aria-hidden />
            <TextInput
              placeholder="Search by name…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} className="w-40">
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </Select>
        </div>
        <DataTable columns={columns} data={orgs} keyFn={(o) => o.id} emptyMessage="No organizations match this search." />
      </Card>
    </div>
  );
}
