"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatMoney, formatNumber } from "@/lib/format";
import { Zap } from "lucide-react";
import type {
  EVCharger,
  EVChargerPort,
  EVTariff,
  EVChargingSession,
  EVChargerType,
  EVPricingBasis,
  PaymentMethod,
} from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

const PORT_STATUS_TONE: Record<string, BadgeTone> = {
  available: "success",
  occupied: "warning",
  charging: "warning",
  out_of_service: "neutral",
  faulted: "danger",
  offline: "danger",
};

const SESSION_STATUS_TONE: Record<string, BadgeTone> = {
  initiated: "brand",
  charging: "warning",
  completed: "success",
  interrupted: "danger",
  failed: "danger",
  cancelled: "neutral",
  refunded: "caution",
};

function kwh(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${formatNumber(value)} kWh`;
}

export default function EVChargingPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();
  const { can, loading: permissionsLoading } = usePermissions(orgId, stationId);

  const canRead = can(["ev_charger:read", "ev_session:read"]);
  const canManageChargers = can("ev_charger:manage");
  const canRecordSessions = can("ev_session:record");
  const canApproveSessions = can("ev_session:approve");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user || permissionsLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-ink-soft">Loading…</p>
      </div>
    );
  }

  if (!canRead) {
    return (
      <div className="flex-1 px-6 py-10">
        <AccessDenied message="Your role does not include access to EV charging at this station." />
      </div>
    );
  }

  return (
    <div className="flex-1">
      <header className="border-b border-border bg-surface px-6 py-4">
        <div className="mx-auto max-w-5xl">
          <Link
            href={`/dashboard/org/${orgId}/station/${stationId}`}
            className="text-xs text-brand-500 hover:underline"
          >
            &larr; Back to station
          </Link>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <Zap className="h-5 w-5 text-accent" /> EV Charging
          </h1>
          <p className="mt-1 text-sm text-ink-soft">
            Chargers, ports, tariffs and charging sessions - tracked entirely separately from fuel tank stock.
            Energy (kWh) is never added to fuel litres.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <ChargersCard orgId={orgId} stationId={stationId} authFetch={authFetch} canManage={canManageChargers} />
        <TariffsCard orgId={orgId} stationId={stationId} authFetch={authFetch} canManage={canManageChargers} />
        <SessionsCard
          orgId={orgId}
          stationId={stationId}
          authFetch={authFetch}
          canRecord={canRecordSessions}
          canApprove={canApproveSessions}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chargers + ports
// ---------------------------------------------------------------------------

function ChargersCard({
  orgId,
  stationId,
  authFetch,
  canManage,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  canManage: boolean;
}) {
  const { notify } = useToast();
  const base = `/organizations/${orgId}/stations/${stationId}/ev-chargers`;

  const [chargers, setChargers] = useState<EVCharger[]>([]);
  const [portsByCharger, setPortsByCharger] = useState<Record<string, EVChargerPort[]>>({});
  const [loaded, setLoaded] = useState(false);
  const [newCharger, setNewCharger] = useState({
    code: "",
    label: "",
    charger_type: "dc" as EVChargerType,
    manufacturer: "",
    model: "",
    rated_power_kw: "",
  });
  const [newPort, setNewPort] = useState({ charger_id: "", port_code: "", connector_standard: "", rated_power_kw: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const resp = await authFetch(base);
    const list: EVCharger[] = resp.ok ? await resp.json() : [];
    setChargers(list);
    const portResults = await Promise.all(list.map((c) => authFetch(`${base}/${c.id}/ports`)));
    const byCharger: Record<string, EVChargerPort[]> = {};
    for (let i = 0; i < list.length; i++) {
      byCharger[list[i].id] = portResults[i].ok ? await portResults[i].json() : [];
    }
    setPortsByCharger(byCharger);
    setLoaded(true);
  }, [authFetch, base]);

  useEffect(() => { load(); }, [load]);

  async function createCharger(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(base, {
        method: "POST",
        body: JSON.stringify({
          code: newCharger.code,
          label: newCharger.label,
          charger_type: newCharger.charger_type,
          manufacturer: newCharger.manufacturer || undefined,
          model: newCharger.model || undefined,
          rated_power_kw: newCharger.rated_power_kw || undefined,
        }),
      });
      if (resp.ok) {
        notify("success", "Charger added.");
        setNewCharger({ code: "", label: "", charger_type: "dc", manufacturer: "", model: "", rated_power_kw: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not add this charger." }));
        notify("error", body.detail ?? "Could not add this charger.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggleCharger(charger: EVCharger) {
    const resp = await authFetch(`${base}/${charger.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !charger.is_active }),
    });
    if (resp.ok) {
      notify("success", charger.is_active ? "Charger deactivated." : "Charger activated.");
      await load();
    } else {
      const body = await resp.json().catch(() => ({ detail: "Could not update this charger." }));
      notify("error", body.detail ?? "Could not update this charger.");
    }
  }

  async function createPort(e: React.FormEvent) {
    e.preventDefault();
    if (!newPort.charger_id) {
      notify("error", "Select a charger first.");
      return;
    }
    setBusy(true);
    try {
      const resp = await authFetch(`${base}/${newPort.charger_id}/ports`, {
        method: "POST",
        body: JSON.stringify({
          port_code: newPort.port_code,
          connector_standard: newPort.connector_standard,
          rated_power_kw: newPort.rated_power_kw || undefined,
        }),
      });
      if (resp.ok) {
        notify("success", "Port added.");
        setNewPort({ charger_id: "", port_code: "", connector_standard: "", rated_power_kw: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not add this port." }));
        notify("error", body.detail ?? "Could not add this port.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function togglePort(charger: EVCharger, port: EVChargerPort) {
    const resp = await authFetch(`${base}/${charger.id}/ports/${port.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !port.is_active }),
    });
    if (resp.ok) {
      await load();
    } else {
      const body = await resp.json().catch(() => ({ detail: "Could not update this port." }));
      notify("error", body.detail ?? "Could not update this port.");
    }
  }

  const activeChargers = chargers.filter((c) => c.is_active);
  const allPorts = chargers.flatMap((c) => (portsByCharger[c.id] ?? []).map((p) => ({ ...p, chargerLabel: c.label })));

  return (
    <Card title="Chargers & Ports" description="Each port belongs to one charger and is where a vehicle actually plugs in.">
      {!loaded ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : chargers.length === 0 ? (
        <EmptyState icon={Zap} title="No EV chargers configured" description="Add your station's first charger below." />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-2 pr-2">Code</th>
              <th className="py-2 pr-2">Label</th>
              <th className="py-2 pr-2">Type</th>
              <th className="py-2 pr-2">Brand / Model</th>
              <th className="py-2 pr-2">Rated kW</th>
              <th className="py-2 pr-2">Status</th>
              {canManage && <th className="py-2 pr-2"></th>}
            </tr>
          </thead>
          <tbody>
            {chargers.map((c) => (
              <tr key={c.id} className="border-b border-border/60">
                <td className="py-2 pr-2 font-mono text-ink">{c.code}</td>
                <td className="py-2 pr-2 text-ink">{c.label}</td>
                <td className="py-2 pr-2 text-ink-soft uppercase">{c.charger_type}</td>
                <td className="py-2 pr-2 text-ink-soft">{c.manufacturer ?? "—"} {c.model ?? ""}</td>
                <td className="py-2 pr-2 text-ink tabular-nums">{c.rated_power_kw ?? "—"}</td>
                <td className="py-2 pr-2">
                  <Badge tone={c.is_active ? "success" : "neutral"}>{c.is_active ? "Active" : "Inactive"}</Badge>
                </td>
                {canManage && (
                  <td className="py-2 pr-2 text-right">
                    <button onClick={() => toggleCharger(c)} className="text-xs font-medium text-accent hover:underline">
                      {c.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canManage && (
        <form onSubmit={createCharger} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-3">
          <Field label="Charger Code">
            {(id) => <TextInput id={id} required value={newCharger.code} onChange={(e) => setNewCharger({ ...newCharger, code: e.target.value })} placeholder="EVC-1" />}
          </Field>
          <Field label="Label">
            {(id) => <TextInput id={id} required value={newCharger.label} onChange={(e) => setNewCharger({ ...newCharger, label: e.target.value })} placeholder="Fast Charger 1" />}
          </Field>
          <Field label="Type">
            {(id) => (
              <Select id={id} value={newCharger.charger_type} onChange={(e) => setNewCharger({ ...newCharger, charger_type: e.target.value as EVChargerType })}>
                <option value="dc">DC (fast)</option>
                <option value="ac">AC</option>
              </Select>
            )}
          </Field>
          <Field label="Manufacturer">
            {(id) => <TextInput id={id} value={newCharger.manufacturer} onChange={(e) => setNewCharger({ ...newCharger, manufacturer: e.target.value })} placeholder="ABB" />}
          </Field>
          <Field label="Model">
            {(id) => <TextInput id={id} value={newCharger.model} onChange={(e) => setNewCharger({ ...newCharger, model: e.target.value })} placeholder="Terra 184" />}
          </Field>
          <Field label="Rated Power (kW)">
            {(id) => <TextInput id={id} type="number" min="1" step="any" value={newCharger.rated_power_kw} onChange={(e) => setNewCharger({ ...newCharger, rated_power_kw: e.target.value })} />}
          </Field>
          <div className="sm:col-span-3">
            <Button type="submit" busy={busy}>Add Charger</Button>
          </div>
        </form>
      )}

      {/* Ports */}
      <div className="mt-6 border-t border-border pt-4">
        <h3 className="mb-3 text-sm font-semibold text-ink">Ports</h3>
        {allPorts.length === 0 ? (
          <p className="text-sm text-ink-soft">No ports configured yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">Port</th>
                <th className="py-2 pr-2">Charger</th>
                <th className="py-2 pr-2">Connector</th>
                <th className="py-2 pr-2">Rated kW</th>
                <th className="py-2 pr-2">Status</th>
                {canManage && <th className="py-2 pr-2"></th>}
              </tr>
            </thead>
            <tbody>
              {allPorts.map((p) => (
                <tr key={p.id} className="border-b border-border/60">
                  <td className="py-2 pr-2 font-mono text-ink">{p.port_code}</td>
                  <td className="py-2 pr-2 text-ink-soft">{p.chargerLabel}</td>
                  <td className="py-2 pr-2 text-ink-soft">{p.connector_standard}</td>
                  <td className="py-2 pr-2 text-ink tabular-nums">{p.rated_power_kw ?? "—"}</td>
                  <td className="py-2 pr-2">
                    <Badge tone={PORT_STATUS_TONE[p.status] ?? "neutral"}>{p.status.replace(/_/g, " ")}</Badge>
                  </td>
                  {canManage && (
                    <td className="py-2 pr-2 text-right">
                      <button
                        onClick={() => togglePort(chargers.find((c) => c.id === p.charger_id)!, p)}
                        className="text-xs font-medium text-accent hover:underline"
                      >
                        {p.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {canManage && activeChargers.length > 0 && (
          <form onSubmit={createPort} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-4">
            <Field label="Charger">
              {(id) => (
                <Select id={id} required value={newPort.charger_id} onChange={(e) => setNewPort({ ...newPort, charger_id: e.target.value })}>
                  <option value="">Select...</option>
                  {activeChargers.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Port Code">
              {(id) => <TextInput id={id} required value={newPort.port_code} onChange={(e) => setNewPort({ ...newPort, port_code: e.target.value })} placeholder="P1" />}
            </Field>
            <Field label="Connector Standard">
              {(id) => <TextInput id={id} required value={newPort.connector_standard} onChange={(e) => setNewPort({ ...newPort, connector_standard: e.target.value })} placeholder="CCS2" />}
            </Field>
            <div className="flex items-end">
              <Button type="submit" busy={busy} className="w-full">Add Port</Button>
            </div>
          </form>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Tariffs
// ---------------------------------------------------------------------------

function TariffsCard({
  orgId,
  stationId,
  authFetch,
  canManage,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  canManage: boolean;
}) {
  const { notify } = useToast();
  const base = `/organizations/${orgId}/stations/${stationId}/ev-tariffs`;

  const [tariffs, setTariffs] = useState<EVTariff[]>([]);
  const [chargers, setChargers] = useState<EVCharger[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [form, setForm] = useState({ charger_id: "", pricing_basis: "per_kwh" as EVPricingBasis, rate: "", effective_from: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [tariffResp, chargerResp] = await Promise.all([
      authFetch(base),
      authFetch(`/organizations/${orgId}/stations/${stationId}/ev-chargers`),
    ]);
    if (tariffResp.ok) setTariffs(await tariffResp.json());
    if (chargerResp.ok) setChargers(await chargerResp.json());
    setLoaded(true);
  }, [authFetch, base, orgId, stationId]);

  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(base, {
        method: "POST",
        body: JSON.stringify({
          charger_id: form.charger_id || undefined,
          pricing_basis: form.pricing_basis,
          rate: form.rate,
          effective_from: form.effective_from ? new Date(form.effective_from).toISOString() : new Date().toISOString(),
        }),
      });
      if (resp.ok) {
        notify("success", "Tariff saved - effective immediately, previous tariffs are kept for history.");
        setForm({ charger_id: "", pricing_basis: "per_kwh", rate: "", effective_from: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not save this tariff." }));
        notify("error", body.detail ?? "Could not save this tariff.");
      }
    } finally {
      setBusy(false);
    }
  }

  const chargerLabel = (id: string | null) => (id ? chargers.find((c) => c.id === id)?.label ?? id.slice(0, 8) : "Station default");

  return (
    <Card title="Tariffs" description="Versioned by effective date - a new tariff never overwrites an old one.">
      {!loaded ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : tariffs.length === 0 ? (
        <EmptyState icon={Zap} title="No tariff set yet" description="Set a station-wide or per-charger rate below before opening any session." />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-2 pr-2">Applies To</th>
              <th className="py-2 pr-2">Basis</th>
              <th className="py-2 pr-2">Rate</th>
              <th className="py-2 pr-2">Effective From</th>
              <th className="py-2 pr-2">Effective To</th>
            </tr>
          </thead>
          <tbody>
            {tariffs.map((t) => (
              <tr key={t.id} className="border-b border-border/60">
                <td className="py-2 pr-2 text-ink">{chargerLabel(t.charger_id)}</td>
                <td className="py-2 pr-2 text-ink-soft">{t.pricing_basis.replace(/_/g, " ")}</td>
                <td className="py-2 pr-2 text-ink tabular-nums">PKR {formatMoney(t.rate)}</td>
                <td className="py-2 pr-2 text-ink-soft">{new Date(t.effective_from).toLocaleString()}</td>
                <td className="py-2 pr-2 text-ink-soft">{t.effective_to ? new Date(t.effective_to).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canManage && (
        <form onSubmit={create} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-4">
          <Field label="Charger" hint="Leave blank for a station-wide default">
            {(id) => (
              <Select id={id} value={form.charger_id} onChange={(e) => setForm({ ...form, charger_id: e.target.value })}>
                <option value="">Station default</option>
                {chargers.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Pricing Basis">
            {(id) => (
              <Select id={id} value={form.pricing_basis} onChange={(e) => setForm({ ...form, pricing_basis: e.target.value as EVPricingBasis })}>
                <option value="per_kwh">Per kWh</option>
                <option value="time_based">Time-based</option>
                <option value="session_fee">Flat session fee</option>
              </Select>
            )}
          </Field>
          <Field label="Rate (PKR)" required>
            {(id) => <TextInput id={id} required type="number" min="0.0001" step="any" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} placeholder="85.0000" />}
          </Field>
          <Field label="Effective From" hint="Defaults to now if left blank">
            {(id) => <TextInput id={id} type="datetime-local" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />}
          </Field>
          <div className="sm:col-span-4">
            <Button type="submit" busy={busy}>Save Tariff</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

function SessionsCard({
  orgId,
  stationId,
  authFetch,
  canRecord,
  canApprove,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  canRecord: boolean;
  canApprove: boolean;
}) {
  const { notify } = useToast();
  const base = `/organizations/${orgId}/stations/${stationId}/ev-charging-sessions`;

  const [sessions, setSessions] = useState<EVChargingSession[]>([]);
  const [ports, setPorts] = useState<(EVChargerPort & { chargerLabel: string })[]>([]);
  const [tariffs, setTariffs] = useState<EVTariff[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);

  const [openForm, setOpenForm] = useState({ port_id: "", tariff_id: "", start_meter_kwh: "", vehicle_reference: "" });
  const [closeForms, setCloseForms] = useState<Record<string, { end_meter_kwh: string; payment_method_id: string }>>({});
  const [reverseReason, setReverseReason] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [sessResp, chargerResp, tariffResp, pmResp] = await Promise.all([
      authFetch(base),
      authFetch(`/organizations/${orgId}/stations/${stationId}/ev-chargers`),
      authFetch(`/organizations/${orgId}/stations/${stationId}/ev-tariffs`),
      authFetch(`/organizations/${orgId}/payment-methods`),
    ]);
    if (sessResp.ok) {
      const list: EVChargingSession[] = await sessResp.json();
      list.sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());
      setSessions(list);
    }
    if (chargerResp.ok) {
      const chargers: EVCharger[] = await chargerResp.json();
      const portResults = await Promise.all(
        chargers.map((c) => authFetch(`/organizations/${orgId}/stations/${stationId}/ev-chargers/${c.id}/ports`))
      );
      const allPorts: (EVChargerPort & { chargerLabel: string })[] = [];
      for (let i = 0; i < chargers.length; i++) {
        if (portResults[i].ok) {
          const ps: EVChargerPort[] = await portResults[i].json();
          allPorts.push(...ps.map((p) => ({ ...p, chargerLabel: chargers[i].label })));
        }
      }
      setPorts(allPorts);
    }
    if (tariffResp.ok) setTariffs(await tariffResp.json());
    if (pmResp.ok) setPaymentMethods(await pmResp.json());
    setLoaded(true);
  }, [authFetch, base, orgId, stationId]);

  useEffect(() => { load(); }, [load]);

  async function openSession(e: React.FormEvent) {
    e.preventDefault();
    if (!openForm.port_id || !openForm.tariff_id) {
      notify("error", "Select a port and a tariff.");
      return;
    }
    setBusy(true);
    try {
      const resp = await authFetch(base, {
        method: "POST",
        body: JSON.stringify({
          port_id: openForm.port_id,
          tariff_id: openForm.tariff_id,
          start_meter_kwh: openForm.start_meter_kwh,
          vehicle_reference: openForm.vehicle_reference || undefined,
        }),
      });
      if (resp.ok) {
        notify("success", "Charging session started.");
        setOpenForm({ port_id: "", tariff_id: "", start_meter_kwh: "", vehicle_reference: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not start this session." }));
        notify("error", body.detail ?? "Could not start this session.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function closeSession(session: EVChargingSession) {
    const form = closeForms[session.id];
    if (!form?.end_meter_kwh) {
      notify("error", "Enter the ending meter reading.");
      return;
    }
    setBusy(true);
    try {
      const resp = await authFetch(`${base}/${session.id}/close`, {
        method: "PATCH",
        body: JSON.stringify({
          end_meter_kwh: form.end_meter_kwh,
          payment_method_id: form.payment_method_id || undefined,
        }),
      });
      if (resp.ok) {
        notify("success", "Session closed and reconciled.");
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not close this session." }));
        notify("error", body.detail ?? "Could not close this session.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function failSession(session: EVChargingSession) {
    const reason = window.prompt("Reason for marking this session as interrupted/failed?");
    if (!reason) return;
    const resp = await authFetch(`${base}/${session.id}/fail`, {
      method: "PATCH",
      body: JSON.stringify({ status: "interrupted", fault_reason: reason }),
    });
    if (resp.ok) {
      notify("success", "Session marked interrupted.");
      await load();
    } else {
      const body = await resp.json().catch(() => ({ detail: "Could not update this session." }));
      notify("error", body.detail ?? "Could not update this session.");
    }
  }

  async function reverseSession(session: EVChargingSession) {
    const reason = reverseReason[session.id];
    if (!reason) {
      notify("error", "Enter a reason before reversing.");
      return;
    }
    const resp = await authFetch(`${base}/${session.id}/reverse`, {
      method: "PATCH",
      body: JSON.stringify({ reason }),
    });
    if (resp.ok) {
      notify("success", "Session reversed.");
      setReverseReason((prev) => ({ ...prev, [session.id]: "" }));
      await load();
    } else {
      const body = await resp.json().catch(() => ({ detail: "Could not reverse this session." }));
      notify("error", body.detail ?? "Could not reverse this session.");
    }
  }

  const portLabel = (id: string) => {
    const p = ports.find((p) => p.id === id);
    return p ? `${p.chargerLabel} / ${p.port_code}` : id.slice(0, 8);
  };

  const availablePorts = ports.filter((p) => p.is_active && p.status !== "out_of_service" && p.status !== "faulted" && p.status !== "offline");
  const openSessions = sessions.filter((s) => s.status === "initiated" || s.status === "charging");
  const closedSessions = sessions.filter((s) => s.status !== "initiated" && s.status !== "charging");

  return (
    <Card title="Charging Sessions" description="Manual entry - start/end meter readings, same principle as fuel nozzle totalizers.">
      {canRecord && (
        <form onSubmit={openSession} className="mb-6 grid grid-cols-1 gap-3 rounded-lg border border-border p-4 sm:grid-cols-4">
          <Field label="Port" required>
            {(id) => (
              <Select id={id} required value={openForm.port_id} onChange={(e) => setOpenForm({ ...openForm, port_id: e.target.value })}>
                <option value="">Select...</option>
                {availablePorts.map((p) => <option key={p.id} value={p.id}>{p.chargerLabel} / {p.port_code}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Tariff" required>
            {(id) => (
              <Select id={id} required value={openForm.tariff_id} onChange={(e) => setOpenForm({ ...openForm, tariff_id: e.target.value })}>
                <option value="">Select...</option>
                {tariffs.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.pricing_basis.replace(/_/g, " ")} — PKR {formatMoney(t.rate)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Start Meter (kWh)" required>
            {(id) => <TextInput id={id} required type="number" min="0" step="any" value={openForm.start_meter_kwh} onChange={(e) => setOpenForm({ ...openForm, start_meter_kwh: e.target.value })} />}
          </Field>
          <Field label="Vehicle Reference">
            {(id) => <TextInput id={id} value={openForm.vehicle_reference} onChange={(e) => setOpenForm({ ...openForm, vehicle_reference: e.target.value })} placeholder="Optional" />}
          </Field>
          <div className="sm:col-span-4">
            <Button type="submit" busy={busy}>Start Session</Button>
          </div>
        </form>
      )}

      {!loaded ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : sessions.length === 0 ? (
        <EmptyState icon={Zap} title="No charging sessions yet" description="Start one above once a charger and tariff are configured." />
      ) : (
        <div className="space-y-6">
          {openSessions.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-semibold text-ink">In Progress</h3>
              <div className="space-y-3">
                {openSessions.map((s) => (
                  <div key={s.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-ink">
                        {portLabel(s.port_id)} — started {new Date(s.start_time).toLocaleString()}
                        {s.vehicle_reference && <span className="text-ink-soft"> · {s.vehicle_reference}</span>}
                      </div>
                      <Badge tone={SESSION_STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
                    </div>
                    <div className="mt-2 text-xs text-ink-soft">Start meter: {kwh(s.start_meter_kwh)}</div>
                    {canRecord && (
                      <div className="mt-3 flex flex-wrap items-end gap-2">
                        <Field label="End Meter (kWh)">
                          {(id) => (
                            <TextInput
                              id={id}
                              type="number"
                              min="0"
                              step="any"
                              value={closeForms[s.id]?.end_meter_kwh ?? ""}
                              onChange={(e) => setCloseForms((prev) => ({ ...prev, [s.id]: { ...prev[s.id], end_meter_kwh: e.target.value, payment_method_id: prev[s.id]?.payment_method_id ?? "" } }))}
                              className="w-40"
                            />
                          )}
                        </Field>
                        <Field label="Payment Method">
                          {(id) => (
                            <Select
                              id={id}
                              value={closeForms[s.id]?.payment_method_id ?? ""}
                              onChange={(e) => setCloseForms((prev) => ({ ...prev, [s.id]: { ...prev[s.id], end_meter_kwh: prev[s.id]?.end_meter_kwh ?? "", payment_method_id: e.target.value } }))}
                              className="w-40"
                            >
                              <option value="">Unset</option>
                              {paymentMethods.map((pm) => <option key={pm.id} value={pm.id}>{pm.name}</option>)}
                            </Select>
                          )}
                        </Field>
                        <Button type="button" size="sm" busy={busy} onClick={() => closeSession(s)}>Close Session</Button>
                        <Button type="button" size="sm" variant="secondary" onClick={() => failSession(s)}>Mark Interrupted</Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 className="mb-2 text-sm font-semibold text-ink">History</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-ink-faint">
                  <th className="py-2 pr-2">Port</th>
                  <th className="py-2 pr-2">Ended</th>
                  <th className="py-2 pr-2">Delivered</th>
                  <th className="py-2 pr-2">Amount</th>
                  <th className="py-2 pr-2">Status</th>
                  {canApprove && <th className="py-2 pr-2"></th>}
                </tr>
              </thead>
              <tbody>
                {closedSessions.map((s) => (
                  <tr key={s.id} className="border-b border-border/60">
                    <td className="py-2 pr-2 text-ink">{portLabel(s.port_id)}</td>
                    <td className="py-2 pr-2 text-ink-soft">{s.end_time ? new Date(s.end_time).toLocaleString() : "—"}</td>
                    <td className="py-2 pr-2 text-ink tabular-nums">{kwh(s.delivered_kwh)}</td>
                    <td className="py-2 pr-2 text-ink tabular-nums">{s.gross_amount ? `PKR ${formatMoney(s.gross_amount)}` : "—"}</td>
                    <td className="py-2 pr-2">
                      <Badge tone={SESSION_STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
                      {s.reversed_at && <span className="ml-1 text-xs text-ink-faint">(reversed)</span>}
                    </td>
                    {canApprove && (
                      <td className="py-2 pr-2 text-right">
                        {s.status === "completed" && !s.reversed_at && (
                          <div className="flex items-center justify-end gap-2">
                            <TextInput
                              value={reverseReason[s.id] ?? ""}
                              onChange={(e) => setReverseReason((prev) => ({ ...prev, [s.id]: e.target.value }))}
                              placeholder="Reversal reason"
                              className="w-40"
                            />
                            <button onClick={() => reverseSession(s)} className="text-xs font-medium text-danger-600 hover:underline">
                              Reverse
                            </button>
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}
