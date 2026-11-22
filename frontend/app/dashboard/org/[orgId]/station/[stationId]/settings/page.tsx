"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { Badge } from "@/components/ui/Badge";
import { DataTable } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { HardwareIntegrationCard } from "@/components/dashboard/HardwareIntegrationCard";
import { Sliders } from "lucide-react";
import type { Station, ShiftTemplate, FuelGrade, Tank, Dispenser, Nozzle } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function StationSettingsPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { authFetch } = useAuth();
  const { can, loading } = usePermissions(orgId, stationId);
  const canViewAnything = can([
    "station:update",
    "fuel_grade:manage",
    "tank:manage",
    "dispenser:manage",
    "nozzle:manage",
  ]);

  if (loading) {
    return <div className="flex flex-1 items-center justify-center"><p className="text-ink-soft">Loading…</p></div>;
  }

  if (!canViewAnything) {
    return (
      <div className="flex-1 px-6 py-10">
        <AccessDenied message="Your role does not include access to station configuration." />
      </div>
    );
  }

  return (
    <div className="flex-1">
      <header className="border-b border-border bg-surface px-6 py-4">
        <div className="mx-auto max-w-5xl">
          <h1 className="text-lg font-semibold text-ink">Station Configuration</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Manage station profile, tanks, fuel grades, dispensers, nozzles, shifts, and settings.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {can("station:update") && <StationProfileCard orgId={orgId} stationId={stationId} authFetch={authFetch} />}
        {can("fuel_grade:manage") && <FuelGradesCard orgId={orgId} authFetch={authFetch} />}
        {can("tank:manage") && <TanksCard orgId={orgId} stationId={stationId} authFetch={authFetch} />}
        {can(["dispenser:manage", "dispenser:read"]) && (
          <DispensersCard orgId={orgId} stationId={stationId} authFetch={authFetch} canManage={can("dispenser:manage")} />
        )}
        {can(["nozzle:manage", "nozzle:read"]) && (
          <NozzlesCard orgId={orgId} stationId={stationId} authFetch={authFetch} canManage={can("nozzle:manage")} />
        )}
        {can("station:update") && <ShiftTemplatesCard orgId={orgId} stationId={stationId} authFetch={authFetch} />}
        {can("station:update") && <StationTolerancesCard orgId={orgId} stationId={stationId} authFetch={authFetch} />}
        {can("station:update") && <HardwareIntegrationCard orgId={orgId} stationId={stationId} authFetch={authFetch} />}
      </div>
    </div>
  );
}

function StationProfileCard({ orgId, stationId, authFetch }: { orgId: string; stationId: string; authFetch: AuthFetch }) {
  const { notify } = useToast();
  const [station, setStation] = useState<Station | null>(null);
  const [form, setForm] = useState({ name: "", address: "", phone: "", email: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}`);
      if (resp.ok) {
        const s = await resp.json();
        setStation(s);
        setForm({ name: s.name ?? "", address: s.address ?? "", phone: s.phone ?? "", email: s.email ?? "" });
      }
    })();
  }, [authFetch, orgId, stationId]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: form.name || undefined,
          address: form.address || undefined,
          phone: form.phone || undefined,
          email: form.email || undefined,
        }),
      });
      if (resp.ok) {
        setStation(await resp.json());
        notify("success", "Station profile updated.");
      } else {
        const body = await resp.json().catch(() => ({ detail: "Update failed." }));
        notify("error", body.detail ?? "Update failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!station) return <Card title="Station Profile"><p className="text-sm text-ink-soft">Loading...</p></Card>;

  return (
    <Card title="Station Profile">
      <form onSubmit={save} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Station Name">
          {(id) => <TextInput id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
        </Field>
        <Field label="Station Code">
          {(id) => <TextInput id={id} value={station.code} disabled />}
        </Field>
        <Field label="Address">
          {(id) => <TextInput id={id} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />}
        </Field>
        <Field label="Phone">
          {(id) => <TextInput id={id} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+92 300 1234567" />}
        </Field>
        <Field label="Email">
          {(id) => <TextInput id={id} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}
        </Field>
        <Field label="Timezone">
          {(id) => <TextInput id={id} value={station.timezone} disabled />}
        </Field>
        <div className="sm:col-span-2">
          <Button type="submit" busy={busy}>Save Profile</Button>
        </div>
      </form>
    </Card>
  );
}

function FuelGradesCard({ orgId, authFetch }: { orgId: string; authFetch: AuthFetch }) {
  const { notify } = useToast();
  const [grades, setGrades] = useState<FuelGrade[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [newGrade, setNewGrade] = useState({ name: "", code: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/fuel-grades`);
    if (resp.ok) setGrades(await resp.json());
    setLoaded(true);
  }, [authFetch, orgId]);

  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/fuel-grades`, {
        method: "POST",
        body: JSON.stringify(newGrade),
      });
      if (resp.ok) {
        notify("success", "Fuel grade created.");
        setNewGrade({ name: "", code: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Failed." }));
        notify("error", body.detail ?? "Failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggle(grade: FuelGrade) {
    const resp = await authFetch(`/organizations/${orgId}/fuel-grades/${grade.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !grade.is_active }),
    });
    if (resp.ok) await load();
  }

  return (
    <Card title="Fuel Grades">
      <DataTable
        columns={[
          { key: "code", header: "Code", render: (g) => <span className="font-mono">{g.code}</span>, sortable: true, sortValue: (g) => g.code },
          { key: "name", header: "Name", render: (g) => g.name, sortable: true, sortValue: (g) => g.name },
          { key: "status", header: "Status", render: (g) => <Badge tone={g.is_active ? "success" : "neutral"}>{g.is_active ? "Active" : "Inactive"}</Badge> },
          {
            key: "actions",
            header: "",
            align: "right",
            render: (g) => (
              <button onClick={() => toggle(g)} className="text-xs font-medium text-accent hover:underline">
                {g.is_active ? "Deactivate" : "Activate"}
              </button>
            ),
          },
        ]}
        data={grades.length === 0 && !loaded ? null : grades}
        keyFn={(g) => g.id}
        emptyMessage="No fuel grades configured yet. Add your first fuel grade below."
      />
      <form onSubmit={create} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-3">
        <Field label="Grade Name">
          {(id) => <TextInput id={id} required value={newGrade.name} onChange={(e) => setNewGrade({ ...newGrade, name: e.target.value })} placeholder="Petrol 92" />}
        </Field>
        <Field label="Grade Code">
          {(id) => <TextInput id={id} required value={newGrade.code} onChange={(e) => setNewGrade({ ...newGrade, code: e.target.value })} placeholder="P92" />}
        </Field>
        <div className="flex items-end">
          <Button type="submit" busy={busy} className="w-full">Add Grade</Button>
        </div>
      </form>
    </Card>
  );
}

function TanksCard({ orgId, stationId, authFetch }: { orgId: string; stationId: string; authFetch: AuthFetch }) {
  const { notify } = useToast();
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [grades, setGrades] = useState<FuelGrade[]>([]);
  const [newTank, setNewTank] = useState({ code: "", name: "", fuel_grade_id: "", capacity: "", safe_fill_limit: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [tanksResp, gradesResp] = await Promise.all([
      authFetch(`/organizations/${orgId}/stations/${stationId}/tanks`),
      authFetch(`/organizations/${orgId}/fuel-grades`),
    ]);
    if (tanksResp.ok) setTanks(await tanksResp.json());
    if (gradesResp.ok) setGrades(await gradesResp.json());
  }, [authFetch, orgId, stationId]);

  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/tanks`, {
        method: "POST",
        body: JSON.stringify(newTank),
      });
      if (resp.ok) {
        notify("success", "Tank created.");
        setNewTank({ code: "", name: "", fuel_grade_id: "", capacity: "", safe_fill_limit: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Failed." }));
        notify("error", body.detail ?? "Failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggle(tank: Tank) {
    const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/tanks/${tank.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !tank.is_active }),
    });
    if (resp.ok) await load();
  }

  const gradeName = (id: string) => grades.find((g) => g.id === id)?.name ?? id;

  return (
    <Card title="Tanks">
      {tanks.length === 0 ? (
        <p className="text-sm text-ink-soft">No tanks configured. Add your first tank below.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-2 pr-2">Code</th>
              <th className="py-2 pr-2">Name</th>
              <th className="py-2 pr-2">Fuel Grade</th>
              <th className="py-2 pr-2">Capacity (L)</th>
              <th className="py-2 pr-2">Safe Fill (L)</th>
              <th className="py-2 pr-2">Status</th>
              <th className="py-2 pr-2"></th>
            </tr>
          </thead>
          <tbody>
            {tanks.map((t) => (
              <tr key={t.id} className="border-b border-border/60">
                <td className="py-2 pr-2 font-mono text-ink">{t.code}</td>
                <td className="py-2 pr-2 text-ink">{t.name}</td>
                <td className="py-2 pr-2 text-ink-soft">{gradeName(t.fuel_grade_id)}</td>
                <td className="py-2 pr-2 text-ink tabular-nums">{Number(t.capacity).toLocaleString()}</td>
                <td className="py-2 pr-2 text-ink tabular-nums">{Number(t.safe_fill_limit).toLocaleString()}</td>
                <td className="py-2 pr-2">
                  <Badge tone={t.is_active ? "success" : "neutral"}>{t.is_active ? "Active" : "Inactive"}</Badge>
                </td>
                <td className="py-2 pr-2 text-right">
                  <button onClick={() => toggle(t)} className="text-xs font-medium text-accent hover:underline">
                    {t.is_active ? "Deactivate" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={create} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-3">
        <Field label="Tank Code">
          {(id) => <TextInput id={id} required value={newTank.code} onChange={(e) => setNewTank({ ...newTank, code: e.target.value })} placeholder="T1" />}
        </Field>
        <Field label="Tank Name">
          {(id) => <TextInput id={id} required value={newTank.name} onChange={(e) => setNewTank({ ...newTank, name: e.target.value })} placeholder="Tank 1" />}
        </Field>
        <Field label="Fuel Grade">
          {(id) => (
            <select id={id} required value={newTank.fuel_grade_id} onChange={(e) => setNewTank({ ...newTank, fuel_grade_id: e.target.value })} className="block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-ink">
              <option value="">Select grade...</option>
              {grades.filter((g) => g.is_active).map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          )}
        </Field>
        <Field label="Capacity (litres)">
          {(id) => <TextInput id={id} type="number" required min="1" step="any" value={newTank.capacity} onChange={(e) => setNewTank({ ...newTank, capacity: e.target.value })} />}
        </Field>
        <Field label="Safe Fill Limit (litres)">
          {(id) => <TextInput id={id} type="number" required min="1" step="any" value={newTank.safe_fill_limit} onChange={(e) => setNewTank({ ...newTank, safe_fill_limit: e.target.value })} />}
        </Field>
        <div className="flex items-end">
          <Button type="submit" busy={busy} className="w-full">Add Tank</Button>
        </div>
      </form>
    </Card>
  );
}

function ShiftTemplatesCard({ orgId, stationId, authFetch }: { orgId: string; stationId: string; authFetch: AuthFetch }) {
  const { notify } = useToast();
  const [templates, setTemplates] = useState<ShiftTemplate[]>([]);
  const [newTmpl, setNewTmpl] = useState({ name: "", start_time: "", end_time: "", grace_period_minutes: "15" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/shift-templates`);
    if (resp.ok) setTemplates(await resp.json());
  }, [authFetch, orgId, stationId]);

  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/shift-templates`, {
        method: "POST",
        body: JSON.stringify({
          name: newTmpl.name,
          start_time: newTmpl.start_time + ":00",
          end_time: newTmpl.end_time + ":00",
          grace_period_minutes: parseInt(newTmpl.grace_period_minutes) || 15,
        }),
      });
      if (resp.ok) {
        notify("success", "Shift template created.");
        setNewTmpl({ name: "", start_time: "", end_time: "", grace_period_minutes: "15" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Failed." }));
        notify("error", body.detail ?? "Failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggle(tmpl: ShiftTemplate) {
    const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/shift-templates/${tmpl.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !tmpl.is_active }),
    });
    if (resp.ok) await load();
  }

  return (
    <Card title="Shift Templates">
      {templates.length === 0 ? (
        <p className="text-sm text-ink-soft">No shift templates defined yet. Define your station shifts below (e.g. Morning, Evening).</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-2 pr-2">Name</th>
              <th className="py-2 pr-2">Start</th>
              <th className="py-2 pr-2">End</th>
              <th className="py-2 pr-2">Grace (min)</th>
              <th className="py-2 pr-2">Status</th>
              <th className="py-2 pr-2"></th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.id} className="border-b border-border/60">
                <td className="py-2 pr-2 text-ink font-medium">{t.name}</td>
                <td className="py-2 pr-2 text-ink tabular-nums">{t.start_time?.slice(0, 5)}</td>
                <td className="py-2 pr-2 text-ink tabular-nums">{t.end_time?.slice(0, 5)}</td>
                <td className="py-2 pr-2 text-ink">{t.grace_period_minutes}</td>
                <td className="py-2 pr-2">
                  <Badge tone={t.is_active ? "success" : "neutral"}>{t.is_active ? "Active" : "Inactive"}</Badge>
                </td>
                <td className="py-2 pr-2 text-right">
                  <button onClick={() => toggle(t)} className="text-xs font-medium text-accent hover:underline">
                    {t.is_active ? "Deactivate" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={create} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-4">
        <Field label="Shift Name">
          {(id) => <TextInput id={id} required value={newTmpl.name} onChange={(e) => setNewTmpl({ ...newTmpl, name: e.target.value })} placeholder="Morning" />}
        </Field>
        <Field label="Start Time">
          {(id) => <TextInput id={id} type="time" required value={newTmpl.start_time} onChange={(e) => setNewTmpl({ ...newTmpl, start_time: e.target.value })} />}
        </Field>
        <Field label="End Time">
          {(id) => <TextInput id={id} type="time" required value={newTmpl.end_time} onChange={(e) => setNewTmpl({ ...newTmpl, end_time: e.target.value })} />}
        </Field>
        <div className="flex items-end gap-2">
          <Field label="Grace (min)">
            {(id) => <TextInput id={id} type="number" min="0" value={newTmpl.grace_period_minutes} onChange={(e) => setNewTmpl({ ...newTmpl, grace_period_minutes: e.target.value })} className="w-20" />}
          </Field>
          <Button type="submit" busy={busy}>Add</Button>
        </div>
      </form>
    </Card>
  );
}

function StationTolerancesCard({ orgId, stationId, authFetch }: { orgId: string; stationId: string; authFetch: AuthFetch }) {
  const { notify } = useToast();
  const [station, setStation] = useState<Record<string, unknown> | null>(null);
  const [form, setForm] = useState({
    receipt_tolerance_percent: "",
    shift_variance_tolerance_percent: "",
    cash_variance_tolerance_amount: "",
    revenue_variance_tolerance_percent: "",
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}`);
      if (resp.ok) {
        const s = await resp.json();
        setStation(s);
        setForm({
          receipt_tolerance_percent: String(s.receipt_tolerance_percent ?? "0.5"),
          shift_variance_tolerance_percent: String(s.shift_variance_tolerance_percent ?? "0.5"),
          cash_variance_tolerance_amount: String(s.cash_variance_tolerance_amount ?? "50"),
          revenue_variance_tolerance_percent: String(s.revenue_variance_tolerance_percent ?? "1.0"),
        });
      }
    })();
  }, [authFetch, orgId, stationId]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}`, {
        method: "PATCH",
        body: JSON.stringify({
          receipt_tolerance_percent: form.receipt_tolerance_percent,
          shift_variance_tolerance_percent: form.shift_variance_tolerance_percent,
          cash_variance_tolerance_amount: form.cash_variance_tolerance_amount,
          revenue_variance_tolerance_percent: form.revenue_variance_tolerance_percent,
        }),
      });
      if (resp.ok) {
        notify("success", "Tolerance settings saved.");
        setStation(await resp.json());
      } else {
        const body = await resp.json().catch(() => ({ detail: "Failed." }));
        notify("error", body.detail ?? "Failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!station) return <Card title="Tolerances & Thresholds"><p className="text-sm text-ink-soft">Loading...</p></Card>;

  return (
    <Card title="Tolerances & Thresholds">
      <p className="mb-4 text-xs text-ink-soft">
        These thresholds control when the system flags variances for review. Adjust carefully — changing them affects future reconciliation.
      </p>
      <form onSubmit={save} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Receipt Tolerance (%)" hint="Acceptable variance between invoice and tank gain">
          {(id) => <TextInput id={id} type="number" step="0.01" min="0" max="100" value={form.receipt_tolerance_percent} onChange={(e) => setForm({ ...form, receipt_tolerance_percent: e.target.value })} />}
        </Field>
        <Field label="Shift Variance Tolerance (%)" hint="Tank dip vs book stock variance limit">
          {(id) => <TextInput id={id} type="number" step="0.01" min="0" max="100" value={form.shift_variance_tolerance_percent} onChange={(e) => setForm({ ...form, shift_variance_tolerance_percent: e.target.value })} />}
        </Field>
        <Field label="Cash Variance Tolerance (amount)" hint="Max acceptable cash discrepancy before requiring auth">
          {(id) => <TextInput id={id} type="number" step="0.01" min="0" value={form.cash_variance_tolerance_amount} onChange={(e) => setForm({ ...form, cash_variance_tolerance_amount: e.target.value })} />}
        </Field>
        <Field label="Revenue Variance Tolerance (%)" hint="Expected revenue vs collected variance limit">
          {(id) => <TextInput id={id} type="number" step="0.01" min="0" max="100" value={form.revenue_variance_tolerance_percent} onChange={(e) => setForm({ ...form, revenue_variance_tolerance_percent: e.target.value })} />}
        </Field>
        <div className="sm:col-span-2">
          <Button type="submit" busy={busy}>Save Tolerances</Button>
        </div>
      </form>
    </Card>
  );
}

function DispensersCard({
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
  const [dispensers, setDispensers] = useState<Dispenser[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [newDispenser, setNewDispenser] = useState({ code: "", name: "" });
  const [busy, setBusy] = useState(false);

  const base = `/organizations/${orgId}/stations/${stationId}/dispensers`;

  const load = useCallback(async () => {
    const resp = await authFetch(base);
    if (resp.ok) setDispensers(await resp.json());
    setLoaded(true);
  }, [authFetch, base]);

  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const resp = await authFetch(base, { method: "POST", body: JSON.stringify(newDispenser) });
      if (resp.ok) {
        notify("success", "Dispenser added.");
        setNewDispenser({ code: "", name: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not add this dispenser." }));
        notify("error", body.detail ?? "Could not add this dispenser.");
      }
    } finally {
      setBusy(false);
    }
  }

  // Deactivation, not deletion - a dispenser with recorded nozzle readings
  // against it can never be safely deleted (the API has no DELETE for
  // this resource at all, by design); is_active is the only state change
  // this screen offers, matching the backend's own safe-deactivation model.
  async function toggle(dispenser: Dispenser) {
    const resp = await authFetch(`${base}/${dispenser.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !dispenser.is_active }),
    });
    if (resp.ok) {
      notify("success", dispenser.is_active ? "Dispenser deactivated." : "Dispenser activated.");
      await load();
    } else {
      const body = await resp.json().catch(() => ({ detail: "Could not update this dispenser." }));
      notify("error", body.detail ?? "Could not update this dispenser.");
    }
  }

  return (
    <Card title="Dispensers">
      {!loaded ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : dispensers.length === 0 ? (
        <EmptyState
          icon={Sliders}
          title="No dispensers configured"
          description="Add your first dispenser below - each one holds the nozzles customers actually pump from."
        />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-2 pr-2">Code</th>
              <th className="py-2 pr-2">Name</th>
              <th className="py-2 pr-2">Status</th>
              {canManage && <th className="py-2 pr-2"></th>}
            </tr>
          </thead>
          <tbody>
            {dispensers.map((d) => (
              <tr key={d.id} className="border-b border-border/60">
                <td className="py-2 pr-2 font-mono text-ink">{d.code}</td>
                <td className="py-2 pr-2 text-ink">{d.name}</td>
                <td className="py-2 pr-2">
                  <Badge tone={d.is_active ? "success" : "neutral"}>{d.is_active ? "Active" : "Inactive"}</Badge>
                </td>
                {canManage && (
                  <td className="py-2 pr-2 text-right">
                    <button onClick={() => toggle(d)} className="text-xs font-medium text-accent hover:underline">
                      {d.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage && (
        <form onSubmit={create} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-3">
          <Field label="Dispenser Code">
            {(id) => <TextInput id={id} required value={newDispenser.code} onChange={(e) => setNewDispenser({ ...newDispenser, code: e.target.value })} placeholder="D1" />}
          </Field>
          <Field label="Dispenser Name">
            {(id) => <TextInput id={id} required value={newDispenser.name} onChange={(e) => setNewDispenser({ ...newDispenser, name: e.target.value })} placeholder="Dispenser 1" />}
          </Field>
          <div className="flex items-end">
            <Button type="submit" busy={busy} className="w-full">Add Dispenser</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function NozzlesCard({
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
  const [dispensers, setDispensers] = useState<Dispenser[]>([]);
  const [nozzlesByDispenser, setNozzlesByDispenser] = useState<Record<string, Nozzle[]>>({});
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [newNozzle, setNewNozzle] = useState({ dispenser_id: "", tank_id: "", code: "" });
  const [busy, setBusy] = useState(false);

  const stationBase = `/organizations/${orgId}/stations/${stationId}`;

  const load = useCallback(async () => {
    const [dispensersResp, tanksResp] = await Promise.all([
      authFetch(`${stationBase}/dispensers`),
      authFetch(`${stationBase}/tanks`),
    ]);
    const dispenserList: Dispenser[] = dispensersResp.ok ? await dispensersResp.json() : [];
    setDispensers(dispenserList);
    if (tanksResp.ok) setTanks(await tanksResp.json());

    const nozzleResults = await Promise.all(
      dispenserList.map((d) => authFetch(`${stationBase}/dispensers/${d.id}/nozzles`))
    );
    const byDispenser: Record<string, Nozzle[]> = {};
    for (let i = 0; i < dispenserList.length; i++) {
      byDispenser[dispenserList[i].id] = nozzleResults[i].ok ? await nozzleResults[i].json() : [];
    }
    setNozzlesByDispenser(byDispenser);
    setLoaded(true);
  }, [authFetch, stationBase]);

  useEffect(() => { load(); }, [load]);

  const tankCode = (id: string) => tanks.find((t) => t.id === id)?.code ?? id.slice(0, 8);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!newNozzle.dispenser_id || !newNozzle.tank_id) {
      notify("error", "Select a dispenser and a tank first.");
      return;
    }
    setBusy(true);
    try {
      const resp = await authFetch(`${stationBase}/dispensers/${newNozzle.dispenser_id}/nozzles`, {
        method: "POST",
        body: JSON.stringify({ tank_id: newNozzle.tank_id, code: newNozzle.code }),
      });
      if (resp.ok) {
        notify("success", "Nozzle added.");
        setNewNozzle({ dispenser_id: "", tank_id: "", code: "" });
        await load();
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not add this nozzle." }));
        notify("error", body.detail ?? "Could not add this nozzle.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function toggle(dispenserId: string, nozzle: Nozzle) {
    const resp = await authFetch(`${stationBase}/dispensers/${dispenserId}/nozzles/${nozzle.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !nozzle.is_active }),
    });
    if (resp.ok) {
      notify("success", nozzle.is_active ? "Nozzle deactivated." : "Nozzle activated.");
      await load();
    } else {
      const body = await resp.json().catch(() => ({ detail: "Could not update this nozzle." }));
      notify("error", body.detail ?? "Could not update this nozzle.");
    }
  }

  const activeDispensers = dispensers.filter((d) => d.is_active);
  const allNozzles = dispensers.flatMap((d) => (nozzlesByDispenser[d.id] ?? []).map((n) => ({ ...n, dispenserCode: d.code })));

  return (
    <Card title="Nozzles" description="Each nozzle belongs to one dispenser and draws from one tank.">
      {!loaded ? (
        <p className="text-sm text-ink-soft">Loading…</p>
      ) : dispensers.length === 0 ? (
        <EmptyState icon={Sliders} title="Add a dispenser first" description="Nozzles belong to a dispenser - configure at least one dispenser above before adding nozzles." />
      ) : allNozzles.length === 0 ? (
        <EmptyState icon={Sliders} title="No nozzles configured" description="Add your first nozzle below - this is what a cashier's reading is actually recorded against." />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-2 pr-2">Code</th>
              <th className="py-2 pr-2">Dispenser</th>
              <th className="py-2 pr-2">Tank</th>
              <th className="py-2 pr-2">Status</th>
              {canManage && <th className="py-2 pr-2"></th>}
            </tr>
          </thead>
          <tbody>
            {allNozzles.map((n) => (
              <tr key={n.id} className="border-b border-border/60">
                <td className="py-2 pr-2 font-mono text-ink">{n.code}</td>
                <td className="py-2 pr-2 text-ink-soft">{n.dispenserCode}</td>
                <td className="py-2 pr-2 text-ink-soft">{tankCode(n.tank_id)}</td>
                <td className="py-2 pr-2">
                  <Badge tone={n.is_active ? "success" : "neutral"}>{n.is_active ? "Active" : "Inactive"}</Badge>
                </td>
                {canManage && (
                  <td className="py-2 pr-2 text-right">
                    <button onClick={() => toggle(n.dispenser_id, n)} className="text-xs font-medium text-accent hover:underline">
                      {n.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage && activeDispensers.length > 0 && (
        <form onSubmit={create} className="mt-4 grid grid-cols-1 gap-3 border-t border-border pt-4 sm:grid-cols-4">
          <Field label="Dispenser">
            {(id) => (
              <select id={id} required value={newNozzle.dispenser_id} onChange={(e) => setNewNozzle({ ...newNozzle, dispenser_id: e.target.value })} className="block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-ink">
                <option value="">Select...</option>
                {activeDispensers.map((d) => <option key={d.id} value={d.id}>{d.code}</option>)}
              </select>
            )}
          </Field>
          <Field label="Tank">
            {(id) => (
              <select id={id} required value={newNozzle.tank_id} onChange={(e) => setNewNozzle({ ...newNozzle, tank_id: e.target.value })} className="block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-ink">
                <option value="">Select...</option>
                {tanks.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.code}</option>)}
              </select>
            )}
          </Field>
          <Field label="Nozzle Code">
            {(id) => <TextInput id={id} required value={newNozzle.code} onChange={(e) => setNewNozzle({ ...newNozzle, code: e.target.value })} placeholder="N1" />}
          </Field>
          <div className="flex items-end">
            <Button type="submit" busy={busy} className="w-full">Add Nozzle</Button>
          </div>
        </form>
      )}
    </Card>
  );
}
