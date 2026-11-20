"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Banknote, FileText, Package, Receipt, Search, Wallet } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { formatMoney } from "@/lib/format";
import { DateRangeFilter, defaultDateRange } from "@/components/DateRangeFilter";
import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Dialog, ConfirmDialog, ReasonDialog } from "@/components/ui/Dialog";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tabs, TabPanel } from "@/components/ui/Tabs";
import { StatCard, StatCardGrid } from "@/components/ui/StatCard";
import type {
  Supplier,
  SupplierBalance,
  SupplierInvoice,
  SupplierPayment,
  SupplierLedgerStatement,
} from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function SuppliersPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { authFetch } = useAuth();
  const { can, loading: permLoading } = usePermissions(orgId);

  const [pageTab, setPageTab] = useState<"directory" | "balances">("directory");

  if (permLoading) {
    return <div className="flex-1 px-6 py-10 text-sm text-ink-soft">Loading…</div>;
  }

  if (!can("supplier:read")) {
    return (
      <div className="flex-1">
        <PageHeader title="Suppliers" breadcrumbs={[{ label: "Dashboard" }, { label: "Suppliers" }]} />
        <div className="mx-auto max-w-3xl px-6 py-10">
          <AccessDenied message="Your role does not include supplier visibility." />
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1">
      <PageHeader
        title="Suppliers"
        description="Supplier directory, invoices, payments and accounts-payable balances."
        breadcrumbs={[{ label: "Dashboard" }, { label: "Suppliers" }]}
      />
      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Tabs
          tabs={[
            { id: "directory", label: "Directory" },
            { id: "balances", label: "Balances" },
          ]}
          active={pageTab}
          onChange={(id) => setPageTab(id as "directory" | "balances")}
        />
        <TabPanel id="directory" active={pageTab}>
          <DirectoryTab
            orgId={orgId}
            authFetch={authFetch}
            canManage={can("supplier:manage")}
            canRecord={can("supplier_ledger:record")}
            canApprove={can("supplier_ledger:approve")}
            canReadLedger={can("supplier_ledger:read")}
          />
        </TabPanel>
        <TabPanel id="balances" active={pageTab}>
          <BalancesTab orgId={orgId} authFetch={authFetch} canReadLedger={can("supplier_ledger:read")} />
        </TabPanel>
      </div>
    </div>
  );
}

function DirectoryTab({
  orgId,
  authFetch,
  canManage,
  canRecord,
  canApprove,
  canReadLedger,
}: {
  orgId: string;
  authFetch: AuthFetch;
  canManage: boolean;
  canRecord: boolean;
  canApprove: boolean;
  canReadLedger: boolean;
}) {
  const { notify } = useToast();
  const [suppliers, setSuppliers] = useState<Supplier[] | null>(null);
  const [balances, setBalances] = useState<SupplierBalance[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");
  const [selected, setSelected] = useState<Supplier | null>(null);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    const [supResp, balResp] = await Promise.all([
      authFetch(`/organizations/${orgId}/suppliers`),
      canReadLedger ? authFetch(`/organizations/${orgId}/suppliers/balances`) : Promise.resolve(null),
    ]);
    if (supResp.ok) setSuppliers(await supResp.json());
    if (balResp && balResp.ok) setBalances(await balResp.json());
  }, [authFetch, orgId, canReadLedger]);

  useEffect(() => {
    load();
  }, [load]);

  const balanceFor = useCallback(
    (supplierId: string) => balances.find((b) => b.supplier_id === supplierId)?.balance ?? null,
    [balances]
  );

  const filtered = useMemo(() => {
    if (!suppliers) return suppliers;
    const q = search.trim().toLowerCase();
    return suppliers.filter((s) => {
      if (statusFilter === "active" && !s.is_active) return false;
      if (statusFilter === "inactive" && s.is_active) return false;
      if (!q) return true;
      return (
        s.name.toLowerCase().includes(q) ||
        (s.contact_phone ?? "").toLowerCase().includes(q) ||
        (s.contact_email ?? "").toLowerCase().includes(q)
      );
    });
  }, [suppliers, search, statusFilter]);

  const columns: Column<Supplier>[] = [
    { key: "name", header: "Supplier", render: (s) => <span className="font-medium text-ink">{s.name}</span> },
    {
      key: "contact",
      header: "Contact",
      render: (s) => (
        <span className="text-ink-soft">
          {s.contact_phone ?? "—"}
          {s.contact_email ? ` · ${s.contact_email}` : ""}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (s) => <Badge tone={s.is_active ? "success" : "neutral"}>{s.is_active ? "Active" : "Inactive"}</Badge>,
    },
    {
      key: "balance",
      header: "Outstanding balance",
      align: "right",
      render: (s) => {
        if (!canReadLedger) return <span className="text-ink-faint">—</span>;
        const bal = balanceFor(s.id);
        if (bal === null) return <span className="text-ink-faint">—</span>;
        const owing = Number(bal) > 0;
        return (
          <span className={`font-medium ${owing ? "text-danger-600" : "text-ink"}`}>PKR {formatMoney(bal)}</span>
        );
      },
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (s) => (
        <div className="flex justify-end gap-3">
          <button className="text-xs font-medium text-accent hover:underline" onClick={() => setSelected(s)}>
            View
          </button>
          {canManage && (
            <button className="text-xs font-medium text-accent hover:underline" onClick={() => setEditing(s)}>
              Edit
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <Card
        title="Supplier directory"
        action={canManage ? <Button size="sm" onClick={() => setShowCreate(true)}>Add supplier</Button> : undefined}
      >
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative max-w-xs flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <TextInput
              className="pl-9"
              placeholder="Search name, phone, email…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select
            className="w-auto"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as "" | "active" | "inactive")}
            aria-label="Status filter"
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </Select>
        </div>

        {suppliers !== null && suppliers.length === 0 ? (
          <EmptyState
            icon={Package}
            title="No suppliers yet"
            description={canManage ? "Add your first supplier to start recording invoices and payments." : "No suppliers have been added for this organization yet."}
            action={canManage ? <Button size="sm" onClick={() => setShowCreate(true)}>Add supplier</Button> : undefined}
          />
        ) : (
          <DataTable columns={columns} data={filtered} keyFn={(s) => s.id} emptyMessage="No suppliers match your filters." />
        )}
      </Card>

      {selected && (
        <SupplierWorkspace
          key={selected.id}
          orgId={orgId}
          authFetch={authFetch}
          supplier={selected}
          canRecord={canRecord}
          canApprove={canApprove}
          canReadLedger={canReadLedger}
          onBalanceChanged={load}
        />
      )}

      <CreateSupplierDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        orgId={orgId}
        authFetch={authFetch}
        onCreated={async () => {
          setShowCreate(false);
          notify("success", "Supplier created.");
          await load();
        }}
      />
      <EditSupplierDialog
        supplier={editing}
        onClose={() => setEditing(null)}
        orgId={orgId}
        authFetch={authFetch}
        onSaved={async () => {
          setEditing(null);
          notify("success", "Supplier updated.");
          await load();
        }}
      />
    </div>
  );
}

function CreateSupplierDialog({
  open,
  onClose,
  orgId,
  authFetch,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  orgId: string;
  authFetch: AuthFetch;
  onCreated: () => void;
}) {
  const { notify } = useToast();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setName("");
      setPhone("");
      setEmail("");
    }
  }, [open]);

  async function submit() {
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = { name };
      if (phone) payload.contact_phone = phone;
      if (email) payload.contact_email = email;
      const resp = await authFetch(`/organizations/${orgId}/suppliers`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not create supplier." }));
        notify("error", body.detail ?? "Could not create supplier.");
        return;
      }
      onCreated();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add supplier"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} busy={submitting} disabled={!name.trim()}>
            Create
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Name" required>
          {(id) => <TextInput id={id} required value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Phone">
          {(id) => <TextInput id={id} value={phone} onChange={(e) => setPhone(e.target.value)} />}
        </Field>
        <Field label="Email">
          {(id) => <TextInput id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
      </div>
    </Dialog>
  );
}

function EditSupplierDialog({
  supplier,
  onClose,
  orgId,
  authFetch,
  onSaved,
}: {
  supplier: Supplier | null;
  onClose: () => void;
  orgId: string;
  authFetch: AuthFetch;
  onSaved: () => void;
}) {
  const { notify } = useToast();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (supplier) {
      setName(supplier.name);
      setPhone(supplier.contact_phone ?? "");
      setEmail(supplier.contact_email ?? "");
      setIsActive(supplier.is_active);
    }
  }, [supplier]);

  async function submit() {
    if (!supplier) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/suppliers/${supplier.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name,
          contact_phone: phone || null,
          contact_email: email || null,
          is_active: isActive,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not save changes." }));
        notify("error", body.detail ?? "Could not save changes.");
        return;
      }
      onSaved();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={supplier !== null}
      onClose={onClose}
      title={`Edit ${supplier?.name ?? "supplier"}`}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} busy={submitting} disabled={!name.trim()}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Name" required>
          {(id) => <TextInput id={id} required value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Phone">
          {(id) => <TextInput id={id} value={phone} onChange={(e) => setPhone(e.target.value)} />}
        </Field>
        <Field label="Email">
          {(id) => <TextInput id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          Active
        </label>
      </div>
    </Dialog>
  );
}

function SupplierWorkspace({
  orgId,
  authFetch,
  supplier,
  canRecord,
  canApprove,
  canReadLedger,
  onBalanceChanged,
}: {
  orgId: string;
  authFetch: AuthFetch;
  supplier: Supplier;
  canRecord: boolean;
  canApprove: boolean;
  canReadLedger: boolean;
  onBalanceChanged: () => void;
}) {
  const [tab, setTab] = useState<"invoices" | "payments" | "statement">("invoices");
  const [balance, setBalance] = useState<string | null>(null);

  const loadBalance = useCallback(async () => {
    if (!canReadLedger) return;
    const resp = await authFetch(`/organizations/${orgId}/suppliers/${supplier.id}/balance`);
    if (resp.ok) setBalance((await resp.json()).balance);
  }, [authFetch, orgId, supplier.id, canReadLedger]);

  useEffect(() => {
    loadBalance();
  }, [loadBalance]);

  const refreshAll = useCallback(async () => {
    await loadBalance();
    onBalanceChanged();
  }, [loadBalance, onBalanceChanged]);

  return (
    <Card title={`${supplier.name} — invoices, payments & statement`}>
      {canReadLedger && (
        <StatCardGrid>
          <StatCard
            label="Outstanding balance"
            value={balance === null ? "—" : `PKR ${formatMoney(balance)}`}
            icon={Wallet}
            tone={balance !== null && Number(balance) > 0 ? "danger" : "success"}
            subtitle="Total invoiced minus approved, non-reversed payments"
          />
        </StatCardGrid>
      )}
      <div className="mt-4">
        <Tabs
          tabs={[
            { id: "invoices", label: "Invoices" },
            { id: "payments", label: "Payments" },
            { id: "statement", label: "Statement" },
          ]}
          active={tab}
          onChange={(id) => setTab(id as typeof tab)}
        />
        <TabPanel id="invoices" active={tab}>
          <InvoicesPanel orgId={orgId} authFetch={authFetch} supplier={supplier} canRecord={canRecord} onChanged={refreshAll} />
        </TabPanel>
        <TabPanel id="payments" active={tab}>
          <PaymentsPanel
            orgId={orgId}
            authFetch={authFetch}
            supplier={supplier}
            canRecord={canRecord}
            canApprove={canApprove}
            onChanged={refreshAll}
          />
        </TabPanel>
        <TabPanel id="statement" active={tab}>
          <StatementPanel orgId={orgId} authFetch={authFetch} supplier={supplier} />
        </TabPanel>
      </div>
    </Card>
  );
}

function InvoicesPanel({
  orgId,
  authFetch,
  supplier,
  canRecord,
  onChanged,
}: {
  orgId: string;
  authFetch: AuthFetch;
  supplier: Supplier;
  canRecord: boolean;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const [invoices, setInvoices] = useState<SupplierInvoice[] | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [amount, setAmount] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const base = `/organizations/${orgId}/suppliers/${supplier.id}/invoices`;

  const load = useCallback(async () => {
    const resp = await authFetch(base);
    if (resp.ok) setInvoices(await resp.json());
  }, [authFetch, base]);

  useEffect(() => {
    setInvoices(null);
    load();
  }, [load]);

  async function submit() {
    setSubmitting(true);
    try {
      const resp = await authFetch(base, {
        method: "POST",
        body: JSON.stringify({
          amount,
          invoice_date: invoiceDate,
          reference: reference || undefined,
          description: description || undefined,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not record invoice." }));
        notify("error", body.detail ?? "Could not record invoice.");
        return;
      }
      notify("success", "Invoice recorded.");
      setShowCreate(false);
      setAmount("");
      setReference("");
      setDescription("");
      await load();
      onChanged();
    } finally {
      setSubmitting(false);
    }
  }

  const total = useMemo(
    () => (invoices ?? []).reduce((sum, inv) => sum + Number(inv.amount), 0),
    [invoices]
  );

  const columns: Column<SupplierInvoice>[] = [
    { key: "date", header: "Invoice date", sortable: true, sortValue: (r) => r.invoice_date, render: (r) => r.invoice_date },
    { key: "reference", header: "Reference", render: (r) => r.reference ?? "—" },
    { key: "description", header: "Description", render: (r) => <span className="text-ink-soft">{r.description ?? "—"}</span> },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      sortable: true,
      sortValue: (r) => Number(r.amount),
      render: (r) => <span className="font-medium text-ink">PKR {formatMoney(r.amount)}</span>,
    },
  ];

  return (
    <div className="space-y-4 pt-2">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-soft">
          Total invoiced: <span className="font-medium text-ink">PKR {formatMoney(total)}</span>
        </p>
        {canRecord && (
          <Button size="sm" onClick={() => setShowCreate(true)}>
            Record invoice
          </Button>
        )}
      </div>

      {invoices !== null && invoices.length === 0 ? (
        <EmptyState icon={FileText} title="No invoices yet" description="No invoices have been recorded for this supplier." />
      ) : (
        <DataTable columns={columns} data={invoices} keyFn={(r) => r.id} emptyMessage="No invoices recorded." />
      )}

      <Dialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Record supplier invoice"
        description="This records money owed to the supplier. The amount cannot be changed from here afterward."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setShowCreate(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button size="sm" onClick={submit} busy={submitting} disabled={!amount || Number(amount) <= 0 || !invoiceDate}>
              Record invoice
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Amount (PKR)" required>
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="0.01"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            )}
          </Field>
          <Field label="Invoice date" required>
            {(id) => (
              <TextInput id={id} type="date" required value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
            )}
          </Field>
          <Field label="Reference" hint="Supplier's own invoice number, if any">
            {(id) => <TextInput id={id} value={reference} onChange={(e) => setReference(e.target.value)} />}
          </Field>
          <Field label="Description">
            {(id) => <TextInput id={id} value={description} onChange={(e) => setDescription(e.target.value)} />}
          </Field>
        </div>
      </Dialog>
    </div>
  );
}

type PaymentStatus = "pending" | "approved" | "reversed";

function paymentStatus(p: SupplierPayment): PaymentStatus {
  if (p.reversed_at) return "reversed";
  if (p.approved_by_user_id) return "approved";
  return "pending";
}

function PaymentsPanel({
  orgId,
  authFetch,
  supplier,
  canRecord,
  canApprove,
  onChanged,
}: {
  orgId: string;
  authFetch: AuthFetch;
  supplier: Supplier;
  canRecord: boolean;
  canApprove: boolean;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const [payments, setPayments] = useState<SupplierPayment[] | null>(null);
  const [statusFilter, setStatusFilter] = useState<"" | PaymentStatus>("");
  const [showCreate, setShowCreate] = useState(false);
  const [amount, setAmount] = useState("");
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reverseTarget, setReverseTarget] = useState<SupplierPayment | null>(null);
  const [approveTarget, setApproveTarget] = useState<SupplierPayment | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const base = `/organizations/${orgId}/suppliers/${supplier.id}/payments`;

  const load = useCallback(async () => {
    const resp = await authFetch(base);
    if (resp.ok) setPayments(await resp.json());
  }, [authFetch, base]);

  useEffect(() => {
    setPayments(null);
    load();
  }, [load]);

  async function submit() {
    setSubmitting(true);
    try {
      const resp = await authFetch(base, {
        method: "POST",
        body: JSON.stringify({ amount, payment_date: paymentDate, reference: reference || undefined }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not record payment." }));
        notify("error", body.detail ?? "Could not record payment.");
        return;
      }
      notify("success", "Payment recorded — awaiting approval before it counts against the balance.");
      setShowCreate(false);
      setAmount("");
      setReference("");
      await load();
      onChanged();
    } finally {
      setSubmitting(false);
    }
  }

  async function approve() {
    if (!approveTarget) return;
    setBusyId(approveTarget.id);
    try {
      const resp = await authFetch(`${base}/${approveTarget.id}/approve`, { method: "PATCH" });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not approve this payment." }));
        notify("error", body.detail ?? "Could not approve this payment.");
        return;
      }
      notify("success", "Payment approved.");
      setApproveTarget(null);
      await load();
      onChanged();
    } finally {
      setBusyId(null);
    }
  }

  async function reverse(reason: string) {
    if (!reverseTarget) return;
    setBusyId(reverseTarget.id);
    try {
      const resp = await authFetch(`${base}/${reverseTarget.id}/reverse`, {
        method: "PATCH",
        body: JSON.stringify({ reason }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not reverse this payment." }));
        notify("error", body.detail ?? "Could not reverse this payment.");
        return;
      }
      notify("success", "Payment reversed.");
      setReverseTarget(null);
      await load();
      onChanged();
    } finally {
      setBusyId(null);
    }
  }

  const filtered = useMemo(() => {
    if (!payments) return payments;
    if (!statusFilter) return payments;
    return payments.filter((p) => paymentStatus(p) === statusFilter);
  }, [payments, statusFilter]);

  const totalApproved = useMemo(
    () => (payments ?? []).filter((p) => paymentStatus(p) === "approved").reduce((sum, p) => sum + Number(p.amount), 0),
    [payments]
  );

  const columns: Column<SupplierPayment>[] = [
    { key: "date", header: "Payment date", sortable: true, sortValue: (r) => r.payment_date, render: (r) => r.payment_date },
    { key: "reference", header: "Reference", render: (r) => r.reference ?? "—" },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      sortable: true,
      sortValue: (r) => Number(r.amount),
      render: (r) => <span className="font-medium text-ink">PKR {formatMoney(r.amount)}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (r) => {
        const status = paymentStatus(r);
        return (
          <Badge tone={status === "approved" ? "success" : status === "reversed" ? "neutral" : "warning"}>
            {status}
          </Badge>
        );
      },
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (r) => {
        const status = paymentStatus(r);
        if (status !== "pending" && status !== "approved") return null;
        return (
          <div className="flex justify-end gap-3">
            {status === "pending" && canApprove && (
              <button
                className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
                disabled={busyId === r.id}
                onClick={() => setApproveTarget(r)}
              >
                Approve
              </button>
            )}
            {canApprove && (
              <button
                className="text-xs font-medium text-danger-600 hover:underline disabled:opacity-50"
                disabled={busyId === r.id}
                onClick={() => setReverseTarget(r)}
              >
                Reverse
              </button>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <p className="text-sm text-ink-soft">
            Total approved: <span className="font-medium text-ink">PKR {formatMoney(totalApproved)}</span>
          </p>
          <Select
            className="w-auto"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as "" | PaymentStatus)}
            aria-label="Payment status filter"
          >
            <option value="">All statuses</option>
            <option value="pending">Pending approval</option>
            <option value="approved">Approved</option>
            <option value="reversed">Reversed</option>
          </Select>
        </div>
        {canRecord && (
          <Button size="sm" onClick={() => setShowCreate(true)}>
            Record payment
          </Button>
        )}
      </div>

      {payments !== null && payments.length === 0 ? (
        <EmptyState icon={Banknote} title="No payments yet" description="No payments have been recorded for this supplier." />
      ) : (
        <DataTable columns={columns} data={filtered} keyFn={(r) => r.id} emptyMessage="No payments match this filter." />
      )}

      <Dialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Record supplier payment"
        description="A payment is never applied to the balance automatically — it needs a Station Manager or Accountant's approval first."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setShowCreate(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button size="sm" onClick={submit} busy={submitting} disabled={!amount || Number(amount) <= 0 || !paymentDate}>
              Record payment
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Amount (PKR)" required>
            {(id) => (
              <TextInput id={id} type="number" step="0.01" min="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} />
            )}
          </Field>
          <Field label="Payment date" required>
            {(id) => (
              <TextInput id={id} type="date" required value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} />
            )}
          </Field>
          <Field label="Reference" hint="Cheque number, bank transfer ID, etc.">
            {(id) => <TextInput id={id} value={reference} onChange={(e) => setReference(e.target.value)} />}
          </Field>
        </div>
      </Dialog>

      <ConfirmDialog
        open={approveTarget !== null}
        onClose={() => setApproveTarget(null)}
        onConfirm={approve}
        title="Approve this payment?"
        description={`This confirms PKR ${approveTarget ? formatMoney(approveTarget.amount) : ""} was genuinely paid to ${supplier.name}. Once approved, it counts against the supplier's outstanding balance.`}
        confirmLabel="Yes, approve"
        confirmVariant="primary"
        busy={busyId === approveTarget?.id}
      />

      <ReasonDialog
        open={reverseTarget !== null}
        onClose={() => setReverseTarget(null)}
        onSubmit={reverse}
        title="Reverse this payment?"
        description="The payment record stays for audit purposes but no longer counts against the supplier's balance. This cannot be undone."
        label="Reason for reversal"
        confirmLabel="Reverse payment"
        busy={busyId === reverseTarget?.id}
      />
    </div>
  );
}

function StatementPanel({
  orgId,
  authFetch,
  supplier,
}: {
  orgId: string;
  authFetch: AuthFetch;
  supplier: Supplier;
}) {
  const { notify } = useToast();
  const [{ dateFrom, dateTo }, setRange] = useState(defaultDateRange());
  const [statement, setStatement] = useState<SupplierLedgerStatement | null>(null);
  const [loadingStmt, setLoadingStmt] = useState(false);

  const load = useCallback(async () => {
    setLoadingStmt(true);
    try {
      const resp = await authFetch(
        `/organizations/${orgId}/suppliers/${supplier.id}/statement?date_from=${dateFrom}&date_to=${dateTo}`
      );
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not load statement." }));
        notify("error", body.detail ?? "Could not load statement.");
        setStatement(null);
        return;
      }
      setStatement(await resp.json());
    } finally {
      setLoadingStmt(false);
    }
  }, [authFetch, orgId, supplier.id, dateFrom, dateTo, notify]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, supplier.id]);

  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-wrap items-center gap-3">
        <DateRangeFilter dateFrom={dateFrom} dateTo={dateTo} onChange={setRange} />
        <Button size="sm" variant="secondary" onClick={load} busy={loadingStmt}>
          Refresh
        </Button>
      </div>

      {loadingStmt ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : !statement ? (
        <p className="text-sm text-ink-soft">Select a date range and refresh.</p>
      ) : (
        <>
          <StatCardGrid>
            <StatCard label="Opening balance" value={`PKR ${formatMoney(statement.opening_balance)}`} icon={Wallet} />
            <StatCard
              label="Closing balance"
              value={`PKR ${formatMoney(statement.closing_balance)}`}
              icon={Wallet}
              tone={Number(statement.closing_balance) > 0 ? "danger" : "success"}
            />
          </StatCardGrid>
          {statement.entries.length === 0 ? (
            <EmptyState icon={Receipt} title="No activity in this period" description="No invoices or approved payments fall in the selected date range." />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface-muted/50 text-left text-ink-soft">
                    <th className="px-4 py-3 font-medium">Date</th>
                    <th className="px-4 py-3 font-medium">Type</th>
                    <th className="px-4 py-3 font-medium">Reference</th>
                    <th className="px-4 py-3 font-medium">Description</th>
                    <th className="px-4 py-3 text-right font-medium">Amount</th>
                    <th className="px-4 py-3 text-right font-medium">Running balance</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.entries.map((e, i) => (
                    <tr key={i} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 text-ink">{e.entry_date}</td>
                      <td className="px-4 py-3">
                        <Badge tone={e.entry_type === "invoice" ? "caution" : "success"}>{e.entry_type}</Badge>
                      </td>
                      <td className="px-4 py-3 text-ink-soft">{e.reference ?? "—"}</td>
                      <td className="px-4 py-3 text-ink-soft">{e.description ?? "—"}</td>
                      <td className="px-4 py-3 text-right text-ink">PKR {formatMoney(e.amount)}</td>
                      <td className="px-4 py-3 text-right font-medium text-ink">PKR {formatMoney(e.running_balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function BalancesTab({
  orgId,
  authFetch,
  canReadLedger,
}: {
  orgId: string;
  authFetch: AuthFetch;
  canReadLedger: boolean;
}) {
  const [balances, setBalances] = useState<SupplierBalance[] | null>(null);

  useEffect(() => {
    if (!canReadLedger) return;
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/suppliers/balances`);
      if (resp.ok) setBalances(await resp.json());
    })();
  }, [authFetch, orgId, canReadLedger]);

  if (!canReadLedger) {
    return <AccessDenied message="Your role does not include supplier ledger visibility." />;
  }

  const totalPayable = (balances ?? []).reduce((sum, b) => sum + Number(b.balance), 0);
  const owingCount = (balances ?? []).filter((b) => Number(b.balance) > 0).length;

  const columns: Column<SupplierBalance>[] = [
    { key: "name", header: "Supplier", render: (b) => <span className="font-medium text-ink">{b.supplier_name}</span> },
    {
      key: "balance",
      header: "Outstanding balance",
      align: "right",
      sortable: true,
      sortValue: (b) => Number(b.balance),
      render: (b) => (
        <span className={`font-medium ${Number(b.balance) > 0 ? "text-danger-600" : "text-ink"}`}>
          PKR {formatMoney(b.balance)}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <StatCardGrid>
        <StatCard label="Total accounts payable" value={`PKR ${formatMoney(totalPayable)}`} icon={Wallet} tone={totalPayable > 0 ? "danger" : "success"} />
        <StatCard label="Suppliers with a balance" value={owingCount} icon={Package} />
      </StatCardGrid>
      <Card
        title="Supplier-wise balances"
        description="Each supplier's total invoiced amount minus approved, non-reversed payments — the same figure used throughout this page."
        action={<ExportButton path={`/organizations/${orgId}/suppliers/balances/export`} filename="supplier-balances.csv" />}
      >
        <DataTable columns={columns} data={balances} keyFn={(b) => b.supplier_id} emptyMessage="No suppliers to summarize yet." />
      </Card>
    </div>
  );
}
