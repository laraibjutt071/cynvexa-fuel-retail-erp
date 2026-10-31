"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/Card";
import { ExportButton } from "@/components/ExportButton";
import type {
  AuditLogEntry,
  CreditCustomerBalance,
  Expense,
  PendingApprovalsReport,
  SupplierBalance,
} from "@/lib/types";

type Tab = "overview" | "suppliers" | "credit" | "expenses" | "audit";

const TABS: { id: Tab; label: string; permission: string }[] = [
  { id: "overview", label: "Pending & exceptions", permission: "report:read" },
  { id: "suppliers", label: "Supplier balances", permission: "supplier_ledger:read" },
  { id: "credit", label: "Credit customers", permission: "credit_collection:read" },
  { id: "expenses", label: "Expenses", permission: "expense:read" },
  { id: "audit", label: "Audit history", permission: "audit:read" },
];

export default function OrgDashboardPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const isSuperuser = user?.is_superuser ?? false;

  // Union across every role this user holds in this org - a user can hold
  // more than one station-scoped role within the same org (e.g.
  // Accountant at one station, Station Manager at another), and this
  // page's own visibility must not be narrower than their real access.
  // A superuser bypasses every server-side permission check (see
  // app/api/deps.py::require_permission), so `can()` - not this raw set -
  // is what every visibility decision on this page must go through.
  const permissions = useMemo(() => {
    const perms = new Set<string>();
    for (const role of user?.station_roles ?? []) {
      if (role.organization_id === orgId) role.permissions.forEach((p) => perms.add(p));
    }
    return perms;
  }, [user, orgId]);
  const can = useCallback(
    (code: string) => isSuperuser || permissions.has(code),
    [isSuperuser, permissions]
  );

  const availableTabs = TABS.filter((t) => can(t.permission));
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") as Tab | null;
  const [activeTab, setActiveTab] = useState<Tab | null>(null);

  useEffect(() => {
    // Picks the tab a deep link asked for (?tab=expenses, used by the
    // sidebar), falling back to the first tab the user can see, once
    // permissions are known - not synchronizing with an external system.
    if (!activeTab && availableTabs.length > 0) {
      const wanted = requestedTab && availableTabs.some((t) => t.id === requestedTab) ? requestedTab : availableTabs[0].id;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveTab(wanted);
    }
  }, [activeTab, availableTabs, requestedTab]);

  if (loading || !user) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-ink-soft">Loading…</p>
      </main>
    );
  }

  return (
    <main className="flex-1">
      <header className="border-b border-border bg-surface px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <Link href="/dashboard" className="text-xs text-brand-500 hover:underline">
              ← Back to organizations
            </Link>
            <h1 className="text-lg font-semibold text-ink">Organization dashboard</h1>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {availableTabs.length === 0 ? (
          <p className="text-sm text-ink-soft">
            Your role does not include dashboard visibility for this organization.
          </p>
        ) : (
          <>
            <div className="flex gap-2 border-b border-border" role="tablist">
              {availableTabs.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={activeTab === t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`border-b-2 px-3 py-2 text-sm font-medium ${
                    activeTab === t.id
                      ? "border-brand-500 text-brand-500"
                      : "border-transparent text-ink-soft hover:text-ink"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {activeTab === "overview" && <OverviewTab orgId={orgId} authFetch={authFetch} />}
            {activeTab === "suppliers" && <SuppliersTab orgId={orgId} authFetch={authFetch} />}
            {activeTab === "credit" && <CreditTab orgId={orgId} authFetch={authFetch} />}
            {activeTab === "expenses" && (
              <ExpensesTab orgId={orgId} authFetch={authFetch} canApprove={can("expense:approve")} />
            )}
            {activeTab === "audit" && <AuditTab orgId={orgId} authFetch={authFetch} />}
          </>
        )}
      </div>
    </main>
  );
}

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

function OverviewTab({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const [report, setReport] = useState<PendingApprovalsReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/reports/pending-approvals`);
      if (!resp.ok) {
        setError("Could not load pending approvals.");
        return;
      }
      setReport(await resp.json());
    })();
  }, [orgId, authFetch]);

  const rows: [string, number][] = report
    ? [
        ["Tanker receipts awaiting approval", report.tanker_receipts_awaiting_approval],
        ["Shifts closed, awaiting approval", report.shifts_awaiting_approval],
        ["Unapproved meter events", report.unapproved_meter_events],
        ["Reconciliations requiring authorization", report.reconciliations_requiring_authorization],
        ["Unapproved cash outflows", report.unapproved_decreasing_cash_movements],
        ["Pending expenses", report.pending_expenses],
        ["Unapproved supplier payments", report.unapproved_supplier_payments],
        ["Low-stock inventory items", report.low_stock_inventory_items],
      ]
    : [];

  return (
    <Card title="Pending approvals & exception alerts" description="Counts across every station you can see.">
      {error && <p className="text-sm text-danger-600">{error}</p>}
      {!report && !error && <p className="text-sm text-ink-soft">Loading…</p>}
      {report && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className={`rounded-lg border p-3 ${
                value > 0 ? "border-warning-100 bg-warning-50" : "border-border bg-surface-elevated"
              }`}
            >
              <p className="text-2xl font-semibold text-ink">{value}</p>
              <p className="mt-1 text-xs text-ink-soft">{label}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function SuppliersTab({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const [rows, setRows] = useState<SupplierBalance[] | null>(null);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/suppliers/balances`);
      if (resp.ok) setRows(await resp.json());
    })();
  }, [orgId, authFetch]);

  return (
    <Card
      title="Supplier balances"
      description="Invoiced minus approved payments, per supplier."
      action={<ExportButton path={`/organizations/${orgId}/suppliers/balances/export`} filename="supplier-balances.csv" />}
    >
      <Table
        columns={["Supplier", "Balance owed"]}
        rows={rows?.map((r) => [r.supplier_name, r.balance]) ?? null}
      />
    </Card>
  );
}

function CreditTab({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const [rows, setRows] = useState<CreditCustomerBalance[] | null>(null);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/credit-customers/balances`);
      if (resp.ok) setRows(await resp.json());
    })();
  }, [orgId, authFetch]);

  return (
    <Card
      title="Credit customer balances"
      description="Credit sales minus recorded collections, per customer."
      action={
        <ExportButton
          path={`/organizations/${orgId}/credit-customers/balances/export`}
          filename="credit-customer-balances.csv"
        />
      }
    >
      <Table
        columns={["Customer", "Balance receivable"]}
        rows={rows?.map((r) => [r.credit_customer_name, r.balance]) ?? null}
      />
    </Card>
  );
}

function ExpensesTab({
  orgId,
  authFetch,
  canApprove,
}: {
  orgId: string;
  authFetch: AuthFetch;
  canApprove: boolean;
}) {
  const [rows, setRows] = useState<Expense[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/expenses?limit=100`);
    if (resp.ok) setRows(await resp.json());
  }, [orgId, authFetch]);

  useEffect(() => {
    // Intentional client-side fetch on mount - no server component passes
    // this authenticated data down, since the access token lives only in
    // memory (see AuthProvider).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function approve(id: string) {
    setActionError(null);
    const resp = await authFetch(`/organizations/${orgId}/expenses/${id}/approve`, { method: "PATCH" });
    if (!resp.ok) {
      setActionError("Could not approve this expense.");
      return;
    }
    await load();
  }

  async function reject(id: string) {
    const reason = window.prompt("Reason for rejecting this expense:");
    if (!reason) return;
    setActionError(null);
    const resp = await authFetch(`/organizations/${orgId}/expenses/${id}/reject`, {
      method: "PATCH",
      body: JSON.stringify({ rejection_reason: reason }),
    });
    if (!resp.ok) {
      setActionError("Could not reject this expense.");
      return;
    }
    await load();
  }

  return (
    <Card title="Expenses" description="General (non-shift) business expenses and their approval status.">
      {actionError && <p className="mb-2 text-sm text-danger-600">{actionError}</p>}
      {!rows ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-soft">No expenses recorded yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-soft">
              <th className="py-2 pr-2">Date</th>
              <th className="py-2 pr-2">Category</th>
              <th className="py-2 pr-2">Description</th>
              <th className="py-2 pr-2">Amount</th>
              <th className="py-2 pr-2">Status</th>
              {canApprove && <th className="py-2 pr-2">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-b border-border">
                <td className="py-2 pr-2 text-ink">{e.expense_date}</td>
                <td className="py-2 pr-2 text-ink">{e.category}</td>
                <td className="py-2 pr-2 text-ink">{e.description}</td>
                <td className="py-2 pr-2 text-ink">{e.amount}</td>
                <td className="py-2 pr-2">
                  <StatusBadge status={e.status} />
                </td>
                {canApprove && (
                  <td className="py-2 pr-2">
                    {e.status === "pending" && (
                      <div className="flex gap-2">
                        <button onClick={() => approve(e.id)} className="text-xs font-medium text-brand-500 hover:underline">
                          Approve
                        </button>
                        <button onClick={() => reject(e.id)} className="text-xs font-medium text-danger-600 hover:underline">
                          Reject
                        </button>
                      </div>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function AuditTab({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const [rows, setRows] = useState<AuditLogEntry[] | null>(null);
  const [action, setAction] = useState("");

  const load = useCallback(async () => {
    const qs = action ? `?action=${encodeURIComponent(action)}` : "";
    const resp = await authFetch(`/organizations/${orgId}/audit-log${qs}`);
    if (resp.ok) setRows(await resp.json());
  }, [orgId, authFetch, action]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  return (
    <Card
      title="Audit history"
      description="Every recorded change, most recent first."
      action={<ExportButton path={`/organizations/${orgId}/audit-log/export`} filename="audit-log.csv" />}
    >
      <div className="mb-3 flex items-center gap-2">
        <input
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="Filter by action (e.g. expense.create)"
          className="rounded-md border border-border px-2 py-1 text-sm"
        />
        <button onClick={load} className="rounded-md border border-border px-3 py-1 text-xs font-medium text-ink hover:bg-surface-elevated">
          Apply
        </button>
      </div>
      {!rows ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-soft">No matching audit events.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-soft">
              <th className="py-2 pr-2">When</th>
              <th className="py-2 pr-2">Action</th>
              <th className="py-2 pr-2">Entity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border">
                <td className="py-2 pr-2 text-ink">{new Date(r.created_at).toLocaleString()}</td>
                <td className="py-2 pr-2 text-ink">{r.action}</td>
                <td className="py-2 pr-2 text-ink-soft">
                  {r.entity_type} · {r.entity_id.slice(0, 8)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-warning-50 text-warning-600",
    approved: "bg-success-50 text-success-600",
    rejected: "bg-danger-50 text-danger-600",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] ?? "bg-surface-elevated text-ink"}`}>
      {status}
    </span>
  );
}

function Table({ columns, rows }: { columns: string[]; rows: (string | number)[][] | null }) {
  if (!rows) return <p className="text-sm text-ink-soft">Loading…</p>;
  if (rows.length === 0) return <p className="text-sm text-ink-soft">No records yet.</p>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-left text-ink-soft">
          {columns.map((c) => (
            <th key={c} className="py-2 pr-2">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className="border-b border-border">
            {row.map((cell, j) => (
              <td key={j} className={`py-2 pr-2 ${j === 0 ? "text-ink" : "text-ink"}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
