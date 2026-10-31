"use client";

import { Truck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/Badge";
import type { Supplier, Tank, TankerReceipt } from "@/lib/types";

export default function PurchasesPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { authFetch } = useAuth();
  const { notify } = useToast();

  const [receipts, setReceipts] = useState<TankerReceipt[] | null>(null);
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [form, setForm] = useState({
    tank_id: "",
    supplier_id: "",
    tanker_registration: "",
    invoice_quantity: "",
    pre_receipt_tank_reading: "",
  });
  const [unloadReading, setUnloadReading] = useState<Record<string, string>>({});
  const [acceptedQty, setAcceptedQty] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const stationBase = `/organizations/${orgId}/stations/${stationId}`;

  const load = useCallback(async () => {
    const [receiptsResp, tanksResp, suppliersResp] = await Promise.all([
      authFetch(`${stationBase}/tanker-receipts`),
      authFetch(`${stationBase}/tanks`),
      authFetch(`/organizations/${orgId}/suppliers`),
    ]);
    if (receiptsResp.ok) setReceipts(await receiptsResp.json());
    if (tanksResp.ok) setTanks(await tanksResp.json());
    if (suppliersResp.ok) setSuppliers(await suppliersResp.json());
  }, [authFetch, orgId, stationBase]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const tankByid = useMemo(() => new Map(tanks.map((t) => [t.id, t])), [tanks]);
  const supplierById = useMemo(() => new Map(suppliers.map((s) => [s.id, s])), [suppliers]);

  async function submitDelivery(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await authFetch(`${stationBase}/tanker-receipts`, { method: "POST", body: JSON.stringify(form) });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not record this delivery." }));
        notify("error", body.detail ?? "Could not record this delivery.");
        return;
      }
      notify("success", "Delivery recorded - record the post-unload tank reading next.");
      setForm({ tank_id: "", supplier_id: "", tanker_registration: "", invoice_quantity: "", pre_receipt_tank_reading: "" });
      await load();
    } finally {
      setSubmitting(false);
    }
  }

  async function recordUnload(id: string) {
    const reading = unloadReading[id];
    if (!reading) return;
    const resp = await authFetch(`${stationBase}/tanker-receipts/${id}/record-unload`, {
      method: "PATCH",
      body: JSON.stringify({ post_receipt_tank_reading: reading }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ detail: "Could not record the unload reading." }));
      notify("error", body.detail ?? "Could not record the unload reading.");
      return;
    }
    notify("success", "Unload reading recorded - ready for approval.");
    await load();
  }

  async function approve(receipt: TankerReceipt) {
    const accepted = acceptedQty[receipt.id] || receipt.invoice_quantity || receipt.tank_gain_quantity;
    if (!accepted) return;
    const resp = await authFetch(`${stationBase}/tanker-receipts/${receipt.id}/approve`, {
      method: "PATCH",
      body: JSON.stringify({ accepted_quantity: accepted, payable_quantity_basis: "invoice_quantity" }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ detail: "Could not approve this delivery." }));
      notify("error", body.detail ?? "Could not approve this delivery.");
      return;
    }
    notify("success", "Delivery approved and added to stock.");
    await load();
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div>
        <h1 className="text-xl font-semibold text-ink">Purchases &amp; Deliveries</h1>
        <p className="mt-1 text-sm text-ink-soft">Record a tanker delivery, confirm what was actually unloaded, then approve it to add it to stock.</p>
      </div>

      <Card title="Record a new delivery">
        <form onSubmit={submitDelivery} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select required value={form.tank_id} onChange={(e) => setForm({ ...form, tank_id: e.target.value })}>
            <option value="" disabled>
              Tank
            </option>
            {tanks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.code}
              </option>
            ))}
          </Select>
          <Select required value={form.supplier_id} onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}>
            <option value="" disabled>
              Supplier
            </option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
          <Field label="Tanker registration" required>
            {(id) => (
              <TextInput id={id} required value={form.tanker_registration} onChange={(e) => setForm({ ...form, tanker_registration: e.target.value })} />
            )}
          </Field>
          <Field label="Invoiced quantity (litres)" required>
            {(id) => (
              <TextInput id={id} required type="number" step="0.001" value={form.invoice_quantity} onChange={(e) => setForm({ ...form, invoice_quantity: e.target.value })} />
            )}
          </Field>
          <Field label="Tank dip before unloading" required hint="Physical reading right now, before this delivery is unloaded.">
            {(id) => (
              <TextInput id={id} required type="number" step="0.001" value={form.pre_receipt_tank_reading} onChange={(e) => setForm({ ...form, pre_receipt_tank_reading: e.target.value })} />
            )}
          </Field>
          <div className="flex items-end">
            <Button type="submit" busy={submitting} className="w-full">
              Record delivery
            </Button>
          </div>
        </form>
      </Card>

      <Card title="Deliveries">
        {!receipts ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : receipts.length === 0 ? (
          <EmptyState icon={Truck} title="No deliveries recorded yet" description="Use the form above when a tanker arrives." />
        ) : (
          <div className="space-y-3">
            {receipts.map((r) => (
              <div key={r.id} className="rounded-lg border border-border p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-ink">
                      {r.tanker_registration} <span className="text-ink-faint">· {tankByid.get(r.tank_id)?.code ?? r.tank_id}</span>
                    </p>
                    <p className="text-xs text-ink-faint">
                      {supplierById.get(r.supplier_id)?.name ?? "Supplier"} · Invoiced {r.invoice_quantity ?? "—"} L
                    </p>
                  </div>
                  <StatusBadge status={r.status} />
                </div>

                {r.status === "pending_unload" && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <TextInput
                      type="number"
                      step="0.001"
                      placeholder="Tank dip after unloading"
                      className="w-56"
                      value={unloadReading[r.id] ?? ""}
                      onChange={(e) => setUnloadReading({ ...unloadReading, [r.id]: e.target.value })}
                    />
                    <Button size="sm" variant="secondary" onClick={() => recordUnload(r.id)}>
                      Record unload reading
                    </Button>
                  </div>
                )}

                {r.status === "awaiting_approval" && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <p className="text-xs text-ink-soft">
                      Tank gained {r.tank_gain_quantity ?? "—"} L. Confirm the accepted quantity to approve.
                    </p>
                    <TextInput
                      type="number"
                      step="0.001"
                      placeholder="Accepted quantity"
                      className="w-40"
                      value={acceptedQty[r.id] ?? r.invoice_quantity ?? ""}
                      onChange={(e) => setAcceptedQty({ ...acceptedQty, [r.id]: e.target.value })}
                    />
                    <Button size="sm" onClick={() => approve(r)}>
                      Approve &amp; add to stock
                    </Button>
                  </div>
                )}

                {r.status === "approved" && (
                  <p className="mt-2 text-xs text-ink-soft">
                    Accepted {r.accepted_quantity} L · Payable basis: {r.payable_quantity_basis}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
