"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { formatMoney } from "@/lib/format";
import type {
  CreditCustomer,
  CreditCustomerAgeingEntry,
  CreditCustomerBalanceDetail,
  CreditCustomerStatement,
} from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function CreditCustomersPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const isSuperuser = user?.is_superuser ?? false;
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

  type Tab = "list" | "ageing";
  const [tab, setTab] = useState<Tab>("list");

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
        <div className="mx-auto max-w-5xl">
          <Link
            href={`/dashboard/org/${orgId}`}
            className="text-xs text-brand-500 hover:underline"
          >
            ← Back to organization
          </Link>
          <h1 className="text-lg font-semibold text-ink">Credit customers</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Manage credit accounts, view balances, statements, and receivables ageing.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <div className="flex gap-2 border-b border-border pb-1" role="tablist">
          {(["list", "ageing"] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`border-b-2 px-3 py-2 text-sm font-medium capitalize ${
                tab === t
                  ? "border-brand-500 text-brand-500"
                  : "border-transparent text-ink-soft hover:text-ink"
              }`}
            >
              {t === "list" ? "Customers & statements" : "Receivables ageing"}
            </button>
          ))}
        </div>

        {tab === "list" && (
          <CustomerListTab
            orgId={orgId}
            authFetch={authFetch}
            canCreate={can("credit_customer:manage")}
            canViewBalance={can("credit_collection:read")}
          />
        )}
        {tab === "ageing" && (
          <AgeingTab orgId={orgId} authFetch={authFetch} />
        )}
      </div>
    </main>
  );
}

function CustomerListTab({
  orgId,
  authFetch,
  canCreate,
  canViewBalance,
}: {
  orgId: string;
  authFetch: AuthFetch;
  canCreate: boolean;
  canViewBalance: boolean;
}) {
  const { notify } = useToast();
  const [customers, setCustomers] = useState<CreditCustomer[] | null>(null);
  const [balances, setBalances] = useState<CreditCustomerBalanceDetail[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statement, setStatement] = useState<CreditCustomerStatement | null>(null);
  const [stmtDates, setStmtDates] = useState({ start: "", end: "" });
  const [loadingStmt, setLoadingStmt] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: "",
    phone: "",
    contact_person: "",
    credit_limit: "",
    payment_terms_days: "",
    address: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const [custResp, balResp] = await Promise.all([
      authFetch(`/organizations/${orgId}/credit-customers`),
      authFetch(`/organizations/${orgId}/credit-customers/balances`),
    ]);
    if (custResp.ok) setCustomers(await custResp.json());
    if (balResp.ok) setBalances(await balResp.json());
  }, [authFetch, orgId]);

  useEffect(() => {
    const today = new Date();
    const monthAgo = new Date(today);
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    setStmtDates({
      start: monthAgo.toISOString().split("T")[0],
      end: today.toISOString().split("T")[0],
    });
    load();
  }, [load]);

  const balanceFor = (custId: string) =>
    balances.find((b) => b.credit_customer_id === custId);

  async function loadStatement(custId: string) {
    if (!stmtDates.start || !stmtDates.end) return;
    setLoadingStmt(true);
    setSelectedId(custId);
    try {
      const resp = await authFetch(
        `/organizations/${orgId}/credit-customers/${custId}/statement?start_date=${stmtDates.start}&end_date=${stmtDates.end}`
      );
      if (resp.ok) {
        setStatement(await resp.json());
      } else {
        setStatement(null);
        notify("error", "Could not load statement.");
      }
    } finally {
      setLoadingStmt(false);
    }
  }

  async function createCustomer(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = { name: createForm.name };
      if (createForm.phone) payload.phone = createForm.phone;
      if (createForm.contact_person) payload.contact_person = createForm.contact_person;
      if (createForm.credit_limit) payload.credit_limit = createForm.credit_limit;
      if (createForm.payment_terms_days)
        payload.payment_terms_days = Number(createForm.payment_terms_days);
      if (createForm.address) payload.address = createForm.address;

      const resp = await authFetch(`/organizations/${orgId}/credit-customers`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not create." }));
        notify("error", body.detail ?? "Could not create customer.");
        return;
      }
      notify("success", "Customer created.");
      setShowCreate(false);
      setCreateForm({ name: "", phone: "", contact_person: "", credit_limit: "", payment_terms_days: "", address: "" });
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card
        title="Credit customers"
        action={
          canCreate ? (
            <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
              {showCreate ? "Cancel" : "Add customer"}
            </Button>
          ) : undefined
        }
      >
        {showCreate && (
          <form onSubmit={createCustomer} className="mb-4 space-y-3 border-b border-border pb-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Field label="Name" required>
                {(id) => (
                  <TextInput
                    id={id}
                    required
                    value={createForm.name}
                    onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  />
                )}
              </Field>
              <Field label="Phone">
                {(id) => (
                  <TextInput
                    id={id}
                    value={createForm.phone}
                    onChange={(e) => setCreateForm({ ...createForm, phone: e.target.value })}
                  />
                )}
              </Field>
              <Field label="Contact person">
                {(id) => (
                  <TextInput
                    id={id}
                    value={createForm.contact_person}
                    onChange={(e) => setCreateForm({ ...createForm, contact_person: e.target.value })}
                  />
                )}
              </Field>
              <Field label="Credit limit (PKR)">
                {(id) => (
                  <TextInput
                    id={id}
                    type="number"
                    step="0.01"
                    min="0"
                    value={createForm.credit_limit}
                    onChange={(e) => setCreateForm({ ...createForm, credit_limit: e.target.value })}
                    placeholder="Leave blank for unlimited"
                  />
                )}
              </Field>
              <Field label="Payment terms (days)">
                {(id) => (
                  <TextInput
                    id={id}
                    type="number"
                    min="1"
                    value={createForm.payment_terms_days}
                    onChange={(e) => setCreateForm({ ...createForm, payment_terms_days: e.target.value })}
                  />
                )}
              </Field>
              <Field label="Address">
                {(id) => (
                  <TextInput
                    id={id}
                    value={createForm.address}
                    onChange={(e) => setCreateForm({ ...createForm, address: e.target.value })}
                  />
                )}
              </Field>
            </div>
            <Button type="submit" busy={submitting} size="sm">
              Create
            </Button>
          </form>
        )}

        {!customers ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : customers.length === 0 ? (
          <p className="text-sm text-ink-soft">No credit customers yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">Name</th>
                <th className="py-2 pr-2">Contact</th>
                <th className="py-2 pr-2">Credit limit</th>
                <th className="py-2 pr-2">Balance</th>
                <th className="py-2 pr-2">Terms</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => {
                const bal = balanceFor(c.id);
                return (
                  <tr
                    key={c.id}
                    className={`border-b border-border/60 ${selectedId === c.id ? "bg-surface-elevated" : ""}`}
                  >
                    <td className="py-2 pr-2 font-medium text-ink">{c.name}</td>
                    <td className="py-2 pr-2 text-ink-soft">
                      {c.contact_person ?? "—"}
                      {c.phone ? ` · ${c.phone}` : ""}
                    </td>
                    <td className="py-2 pr-2 text-ink-soft">
                      {c.credit_limit ? `PKR ${formatMoney(c.credit_limit)}` : "Unlimited"}
                    </td>
                    <td className="py-2 pr-2 text-ink">
                      {bal ? `PKR ${formatMoney(bal.balance)}` : "—"}
                    </td>
                    <td className="py-2 pr-2 text-ink-soft">
                      {c.payment_terms_days ? `${c.payment_terms_days}d` : "—"}
                    </td>
                    <td className="py-2 pr-2 text-right">
                      {canViewBalance && (
                        <button
                          onClick={() => loadStatement(c.id)}
                          className="text-xs font-medium text-accent hover:underline"
                        >
                          Statement
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      {selectedId && (
        <Card title={`Statement — ${statement?.credit_customer_name ?? "..."}`}>
          <div className="mb-3 flex flex-wrap items-end gap-3">
            <label className="text-sm text-ink-soft">
              From
              <input
                type="date"
                value={stmtDates.start}
                onChange={(e) => setStmtDates({ ...stmtDates, start: e.target.value })}
                className="ml-2 rounded-md border border-border px-2 py-1 text-sm"
              />
            </label>
            <label className="text-sm text-ink-soft">
              To
              <input
                type="date"
                value={stmtDates.end}
                onChange={(e) => setStmtDates({ ...stmtDates, end: e.target.value })}
                className="ml-2 rounded-md border border-border px-2 py-1 text-sm"
              />
            </label>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => loadStatement(selectedId)}
              busy={loadingStmt}
            >
              Refresh
            </Button>
          </div>

          {loadingStmt ? (
            <p className="text-sm text-ink-soft">Loading…</p>
          ) : !statement ? (
            <p className="text-sm text-ink-soft">Select a date range and click refresh.</p>
          ) : (
            <>
              <div className="mb-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
                <div>
                  <p className="text-xs text-ink-faint">Opening balance</p>
                  <p className="text-sm font-semibold text-ink">
                    PKR {formatMoney(statement.opening_balance)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Closing balance</p>
                  <p className="text-sm font-semibold text-ink">
                    PKR {formatMoney(statement.closing_balance)}
                  </p>
                </div>
              </div>

              {statement.entries.length === 0 ? (
                <p className="text-sm text-ink-soft">No transactions in this period.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-ink-faint">
                      <th className="py-2 pr-2">Date</th>
                      <th className="py-2 pr-2">Description</th>
                      <th className="py-2 pr-2">Debit</th>
                      <th className="py-2 pr-2">Credit</th>
                      <th className="py-2 pr-2">Running</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statement.entries.map((e, i) => (
                      <tr key={i} className="border-b border-border/60">
                        <td className="py-2 pr-2 text-ink">{e.date}</td>
                        <td className="py-2 pr-2 text-ink-soft">{e.description}</td>
                        <td className="py-2 pr-2 text-ink">
                          {Number(e.debit) > 0 ? e.debit : "—"}
                        </td>
                        <td className="py-2 pr-2 text-ink">
                          {Number(e.credit) > 0 ? e.credit : "—"}
                        </td>
                        <td className="py-2 pr-2 font-medium text-ink">
                          {formatMoney(e.running_balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </Card>
      )}
    </div>
  );
}

function AgeingTab({
  orgId,
  authFetch,
}: {
  orgId: string;
  authFetch: AuthFetch;
}) {
  const [rows, setRows] = useState<CreditCustomerAgeingEntry[] | null>(null);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(
        `/organizations/${orgId}/credit-customers/ageing`
      );
      if (resp.ok) setRows(await resp.json());
    })();
  }, [orgId, authFetch]);

  return (
    <Card
      title="Receivables ageing"
      description="FIFO allocation of payments against oldest outstanding tenders. Buckets: current (0-30d), 30d, 60d, 90d, 90d+."
    >
      {!rows ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-soft">No outstanding credit balances.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-2 pr-2">Customer</th>
              <th className="py-2 pr-2">Current</th>
              <th className="py-2 pr-2">30 days</th>
              <th className="py-2 pr-2">60 days</th>
              <th className="py-2 pr-2">90 days</th>
              <th className="py-2 pr-2">90+ days</th>
              <th className="py-2 pr-2 font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.credit_customer_id} className="border-b border-border/60">
                <td className="py-2 pr-2 font-medium text-ink">
                  {r.credit_customer_name}
                </td>
                <td className="py-2 pr-2 text-ink">{r.current}</td>
                <td className="py-2 pr-2 text-ink">{r.days_30}</td>
                <td className="py-2 pr-2 text-ink">{r.days_60}</td>
                <td className="py-2 pr-2 text-ink">{r.days_90}</td>
                <td className="py-2 pr-2 text-ink">
                  {Number(r.over_90) > 0 ? (
                    <span className="font-medium text-danger-600">{r.over_90}</span>
                  ) : (
                    r.over_90
                  )}
                </td>
                <td className="py-2 pr-2 font-semibold text-ink">{r.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
