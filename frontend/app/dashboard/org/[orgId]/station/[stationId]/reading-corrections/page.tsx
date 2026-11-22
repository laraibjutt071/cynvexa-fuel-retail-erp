"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ReasonDialog } from "@/components/ui/Dialog";
import { History } from "lucide-react";
import type { NozzleOverview, ReadingCorrection, Shift, ShiftNozzleReading, ShiftTankReading, Tank } from "@/lib/types";
import { formatLitres } from "@/lib/format";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

const CORRECTION_WINDOW_HOURS = 24;

export default function ReadingCorrectionsPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();
  const { can, loading: permissionsLoading } = usePermissions(orgId, stationId);
  const canRequest = can("reading:correct");
  const canApprove = can("reading:correct_approve");
  const canView = canRequest || canApprove;

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

  if (!canView) {
    return (
      <div className="flex-1 px-6 py-10">
        <AccessDenied message="Your role does not include access to reading corrections at this station." />
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
            ← Back to station
          </Link>
          <h1 className="text-lg font-semibold text-ink">Reading corrections</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Request and manage corrections for shift readings. A reading can be corrected directly within{" "}
            {CORRECTION_WINDOW_HOURS} hours of its original submission; after that, the original is permanently
            locked and only a separate amendment record can be created.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <ShiftPicker orgId={orgId} stationId={stationId} authFetch={authFetch} canRequest={canRequest} canApprove={canApprove} />
      </div>
    </div>
  );
}

function ShiftPicker({
  orgId,
  stationId,
  authFetch,
  canRequest,
  canApprove,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  canRequest: boolean;
  canApprove: boolean;
}) {
  const [shifts, setShifts] = useState<Shift[] | null>(null);
  const [selectedShiftId, setSelectedShiftId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/shifts`);
      if (resp.ok) setShifts(await resp.json());
    })();
  }, [orgId, stationId, authFetch]);

  return (
    <>
      <Card title="Select a shift">
        {!shifts ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : shifts.length === 0 ? (
          <EmptyState icon={History} title="No shifts found" description="Open and close at least one shift before requesting a reading correction." />
        ) : (
          <div className="space-y-2">
            {shifts.slice(0, 10).map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedShiftId(s.id)}
                className={`block w-full rounded-lg border p-3 text-left text-sm ${
                  selectedShiftId === s.id ? "border-brand-500 bg-brand-50" : "border-border hover:bg-surface-elevated"
                }`}
              >
                <span className="font-medium text-ink">{s.label ?? "Shift"} </span>
                <span className="text-ink-soft">
                  · {new Date(s.opened_at).toLocaleString()} · <span className="capitalize">{s.status}</span>
                </span>
              </button>
            ))}
          </div>
        )}
      </Card>

      {selectedShiftId && (
        <CorrectionsList
          orgId={orgId}
          stationId={stationId}
          shiftId={selectedShiftId}
          authFetch={authFetch}
          canRequest={canRequest}
          canApprove={canApprove}
        />
      )}
    </>
  );
}

interface EligibleReading {
  key: string;
  label: string;
  reading_type: "tank_dip" | "nozzle_opening" | "nozzle_closing" | "meter_event_pre" | "meter_event_post";
  tank_reading_id?: string;
  nozzle_reading_id?: string;
  original_value: string;
  submitted_at: string;
}

function buildEligibleReadings(
  tankReadings: ShiftTankReading[],
  nozzleReadings: ShiftNozzleReading[],
  tankCode: (id: string) => string,
  nozzleCode: (id: string) => string
): EligibleReading[] {
  const items: EligibleReading[] = [];
  for (const r of tankReadings) {
    items.push({
      key: `tank:${r.id}`,
      label: `Tank ${tankCode(r.tank_id)} — ${r.reading_type} dip (${formatLitres(r.dip_reading)})`,
      reading_type: "tank_dip",
      tank_reading_id: r.id,
      original_value: r.dip_reading,
      submitted_at: r.recorded_at,
    });
  }
  for (const r of nozzleReadings) {
    items.push({
      key: `nozzle-open:${r.id}`,
      label: `Nozzle ${nozzleCode(r.nozzle_id)} — opening totalizer (${r.opening_totalizer})`,
      reading_type: "nozzle_opening",
      nozzle_reading_id: r.id,
      original_value: r.opening_totalizer,
      submitted_at: r.opening_recorded_at,
    });
    if (r.closing_totalizer !== null && r.closing_recorded_at) {
      items.push({
        key: `nozzle-close:${r.id}`,
        label: `Nozzle ${nozzleCode(r.nozzle_id)} — closing totalizer (${r.closing_totalizer})`,
        reading_type: "nozzle_closing",
        nozzle_reading_id: r.id,
        original_value: r.closing_totalizer,
        submitted_at: r.closing_recorded_at,
      });
    }
    if (r.meter_event_pre_reading !== null && r.closing_recorded_at) {
      items.push({
        key: `nozzle-meterpre:${r.id}`,
        label: `Nozzle ${nozzleCode(r.nozzle_id)} — meter event pre-reading (${r.meter_event_pre_reading})`,
        reading_type: "meter_event_pre",
        nozzle_reading_id: r.id,
        original_value: r.meter_event_pre_reading,
        submitted_at: r.closing_recorded_at,
      });
    }
    if (r.meter_event_post_reading !== null && r.closing_recorded_at) {
      items.push({
        key: `nozzle-meterpost:${r.id}`,
        label: `Nozzle ${nozzleCode(r.nozzle_id)} — meter event post-reading (${r.meter_event_post_reading})`,
        reading_type: "meter_event_post",
        nozzle_reading_id: r.id,
        original_value: r.meter_event_post_reading,
        submitted_at: r.closing_recorded_at,
      });
    }
  }
  return items;
}

function correctionDeadline(submittedAt: string): { deadline: Date; withinWindow: boolean; hoursLeft: number } {
  const submitted = new Date(submittedAt);
  const deadline = new Date(submitted.getTime() + CORRECTION_WINDOW_HOURS * 60 * 60 * 1000);
  const now = new Date();
  const hoursLeft = (deadline.getTime() - now.getTime()) / (60 * 60 * 1000);
  return { deadline, withinWindow: hoursLeft > 0, hoursLeft };
}

function RequestCorrectionForm({
  orgId,
  stationId,
  shiftId,
  authFetch,
  existingCorrections,
  onSubmitted,
}: {
  orgId: string;
  stationId: string;
  shiftId: string;
  authFetch: AuthFetch;
  existingCorrections: ReadingCorrection[];
  onSubmitted: () => Promise<void>;
}) {
  const { notify } = useToast();
  const stationBase = `/organizations/${orgId}/stations/${stationId}`;
  const [tankReadings, setTankReadings] = useState<ShiftTankReading[]>([]);
  const [nozzleReadings, setNozzleReadings] = useState<ShiftNozzleReading[]>([]);
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [nozzleOverview, setNozzleOverview] = useState<NozzleOverview[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selectedKey, setSelectedKey] = useState("");
  const [correctedValue, setCorrectedValue] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const [tanksResp, nozzlesResp, tankReadingsResp, nozzleReadingsResp] = await Promise.all([
        authFetch(`${stationBase}/tanks`),
        authFetch(`${stationBase}/nozzles`),
        authFetch(`${stationBase}/shifts/${shiftId}/tank-readings`),
        authFetch(`${stationBase}/shifts/${shiftId}/nozzle-readings`),
      ]);
      if (tanksResp.ok) setTanks(await tanksResp.json());
      if (nozzlesResp.ok) setNozzleOverview(await nozzlesResp.json());
      if (tankReadingsResp.ok) setTankReadings(await tankReadingsResp.json());
      if (nozzleReadingsResp.ok) setNozzleReadings(await nozzleReadingsResp.json());
      setLoaded(true);
    })();
  }, [authFetch, stationBase, shiftId]);

  const tankCode = useCallback((id: string) => tanks.find((t) => t.id === id)?.code ?? id.slice(0, 8), [tanks]);
  const nozzleCode = useCallback(
    (id: string) => nozzleOverview.find((n) => n.nozzle_id === id)?.nozzle_code ?? id.slice(0, 8),
    [nozzleOverview]
  );

  const eligible = useMemo(
    () => buildEligibleReadings(tankReadings, nozzleReadings, tankCode, nozzleCode),
    [tankReadings, nozzleReadings, tankCode, nozzleCode]
  );
  const selected = eligible.find((e) => e.key === selectedKey) ?? null;
  const deadline = selected ? correctionDeadline(selected.submitted_at) : null;

  // Duplicate-submission guard: a pending request already exists for this
  // exact reading - block a second one from being filed on top of it
  // rather than letting the approver see two competing requests.
  const duplicatePending = selected
    ? existingCorrections.some(
        (c) =>
          c.status === "pending" &&
          c.reading_type === selected.reading_type &&
          (selected.tank_reading_id ? c.tank_reading_id === selected.tank_reading_id : c.nozzle_reading_id === selected.nozzle_reading_id)
      )
    : false;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || submitting) return;
    if (!correctedValue.trim() || !reason.trim()) {
      setError("Enter both a corrected value and a reason.");
      return;
    }
    if (correctedValue.trim() === selected.original_value) {
      setError("The corrected value is the same as the original value.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await authFetch(`${stationBase}/shifts/${shiftId}/reading-corrections`, {
        method: "POST",
        body: JSON.stringify({
          reading_type: selected.reading_type,
          tank_reading_id: selected.tank_reading_id ?? null,
          nozzle_reading_id: selected.nozzle_reading_id ?? null,
          corrected_value: correctedValue.trim(),
          reason: reason.trim(),
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not submit this correction request." }));
        setError(body.detail ?? "Could not submit this correction request.");
        return;
      }
      notify("success", "Correction request submitted.");
      setSelectedKey("");
      setCorrectedValue("");
      setReason("");
      await onSubmitted();
    } finally {
      setSubmitting(false);
    }
  }

  if (!loaded) {
    return (
      <Card title="Request a correction">
        <p className="text-sm text-ink-soft">Loading readings…</p>
      </Card>
    );
  }

  return (
    <Card
      title="Request a correction"
      description="Pick the reading that was entered wrong. The deadline below is calculated from when it was originally submitted — not from now."
    >
      {eligible.length === 0 ? (
        <EmptyState icon={History} title="No readings on this shift yet" description="Readings must be recorded before a correction can be requested." />
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Reading">
            {(id) => (
              <Select id={id} required value={selectedKey} onChange={(e) => { setSelectedKey(e.target.value); setError(null); }}>
                <option value="" disabled>Select a reading…</option>
                {eligible.map((r) => (
                  <option key={r.key} value={r.key}>{r.label}</option>
                ))}
              </Select>
            )}
          </Field>

          {selected && deadline && (
            <div
              className={`rounded-lg border px-3 py-2.5 text-sm ${
                deadline.withinWindow ? "border-border bg-surface-muted text-ink-soft" : "border-warning-100 bg-warning-50 text-warning-600"
              }`}
            >
              <p>
                <strong className="text-ink">Original value:</strong> {selected.original_value} · submitted{" "}
                {new Date(selected.submitted_at).toLocaleString()}
              </p>
              {deadline.withinWindow ? (
                <p className="mt-1">
                  Correction deadline: <strong>{deadline.deadline.toLocaleString()}</strong> ({Math.max(0, Math.round(deadline.hoursLeft))}h left).
                  Approving this request before then updates the reading directly.
                </p>
              ) : (
                <p className="mt-1">
                  This reading&apos;s 24-hour window closed on <strong>{deadline.deadline.toLocaleString()}</strong>. The original value is
                  permanently locked — this request will create a separate, auditable amendment record instead of changing it.
                </p>
              )}
            </div>
          )}

          {duplicatePending && (
            <p className="text-sm text-danger-600">
              A correction request for this exact reading is already pending approval. Wait for it to be decided before submitting another.
            </p>
          )}

          <Field label="Corrected value">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.001"
                required
                disabled={!selected}
                value={correctedValue}
                onChange={(e) => { setCorrectedValue(e.target.value); setError(null); }}
                placeholder={selected ? `Not ${selected.original_value}` : "Select a reading first"}
              />
            )}
          </Field>

          <Field label="Reason" hint="Required - this is recorded permanently on the audit trail.">
            {(id) => (
              <textarea
                id={id}
                required
                disabled={!selected}
                value={reason}
                onChange={(e) => { setReason(e.target.value); setError(null); }}
                rows={3}
                placeholder="e.g. Transposed two digits while writing down the totalizer"
                className="block w-full rounded-lg border border-border bg-surface-muted px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:opacity-50"
              />
            )}
          </Field>

          {error && <p className="text-sm text-danger-600">{error}</p>}

          <Button type="submit" busy={submitting} disabled={!selected || duplicatePending}>
            Submit correction request
          </Button>
        </form>
      )}
    </Card>
  );
}

function CorrectionsList({
  orgId,
  stationId,
  shiftId,
  authFetch,
  canRequest,
  canApprove,
}: {
  orgId: string;
  stationId: string;
  shiftId: string;
  authFetch: AuthFetch;
  canRequest: boolean;
  canApprove: boolean;
}) {
  const { notify } = useToast();
  const [corrections, setCorrections] = useState<ReadingCorrection[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);
  const [rejectError, setRejectError] = useState<string | null>(null);

  const base = `/organizations/${orgId}/stations/${stationId}/shifts/${shiftId}/reading-corrections`;

  const load = useCallback(async () => {
    const resp = await authFetch(base);
    if (resp.ok) setCorrections(await resp.json());
  }, [authFetch, base]);

  useEffect(() => {
    load();
  }, [load]);

  async function approve(correctionId: string) {
    if (busy) return; // guard against double-click re-firing the approval
    setBusy(correctionId);
    try {
      const resp = await authFetch(`${base}/${correctionId}/approve`, { method: "POST" });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not approve." }));
        notify("error", body.detail ?? "Could not approve.");
        return;
      }
      notify("success", "Correction approved.");
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function submitRejection(reason: string) {
    if (!rejectTarget) return;
    setBusy(rejectTarget);
    setRejectError(null);
    try {
      const resp = await authFetch(`${base}/${rejectTarget}/reject`, {
        method: "POST",
        body: JSON.stringify({ rejection_reason: reason }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not reject." }));
        setRejectError(body.detail ?? "Could not reject.");
        return;
      }
      notify("success", "Correction rejected.");
      setRejectTarget(null);
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {canRequest && corrections && (
        <RequestCorrectionForm
          orgId={orgId}
          stationId={stationId}
          shiftId={shiftId}
          authFetch={authFetch}
          existingCorrections={corrections}
          onSubmitted={load}
        />
      )}

      <Card
        title="Corrections for this shift"
        description="Corrections requested within the 24-hour window are applied in-place when approved. Post-lock corrections create amendment records and never change the original reading."
      >
        {!corrections ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : corrections.length === 0 ? (
          <p className="text-sm text-ink-soft">No correction requests for this shift.</p>
        ) : (
          <div className="space-y-3">
            {corrections.map((c) => (
              <div key={c.id} className="rounded-lg border border-border bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-ink">{c.reading_type.replace(/_/g, " ")}</p>
                    <p className="text-xs text-ink-faint">
                      Original: {c.original_value} → Corrected: {c.corrected_value}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {c.is_post_lock && <Badge tone="caution">Post-lock amendment</Badge>}
                    <StatusBadge status={c.status} />
                  </div>
                </div>

                <p className="mt-2 text-sm text-ink-soft">
                  <strong>Reason:</strong> {c.reason}
                </p>
                <p className="mt-1 text-xs text-ink-faint">
                  Submitted: {new Date(c.original_submitted_at).toLocaleString()} · Requested:{" "}
                  {new Date(c.requested_at).toLocaleString()}
                </p>
                {c.rejection_reason && (
                  <p className="mt-1 text-xs text-red-600">Rejection reason: {c.rejection_reason}</p>
                )}

                {c.status === "pending" && canApprove && (
                  <div className="mt-3 flex gap-2">
                    <Button size="sm" onClick={() => approve(c.id)} busy={busy === c.id}>
                      Approve
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => { setRejectTarget(c.id); setRejectError(null); }} disabled={busy === c.id}>
                      Reject
                    </Button>
                  </div>
                )}
                {c.status === "pending" && !canApprove && (
                  <p className="mt-3 text-xs text-ink-faint">Waiting for an authorized approver to decide this request.</p>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <ReasonDialog
        open={rejectTarget !== null}
        onClose={() => setRejectTarget(null)}
        onSubmit={submitRejection}
        title="Reject correction request"
        description="The original reading stays as-is. The reason is recorded in the audit trail."
        label="Reason for rejecting this request"
        confirmLabel="Reject request"
        busy={busy === rejectTarget}
        error={rejectError}
      />
    </>
  );
}
