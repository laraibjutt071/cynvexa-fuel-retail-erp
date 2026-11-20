"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Gauge, Search } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { formatLitres } from "@/lib/format";
import { DateRangeFilter, defaultDateRange } from "@/components/DateRangeFilter";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Dialog, ConfirmDialog } from "@/components/ui/Dialog";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { EmptyState } from "@/components/ui/EmptyState";
import type { MeterEventRow } from "@/lib/types";

const EVENT_LABELS: Record<string, string> = {
  rollover: "Meter rollover",
  reset: "Meter reset",
  replacement: "Meter replacement",
};

const EVENT_TONE: Record<string, BadgeTone> = {
  rollover: "brand",
  reset: "warning",
  replacement: "caution",
};

type ApprovedFilter = "" | "true" | "false";

export default function MeterEventsPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { authFetch } = useAuth();
  const { notify } = useToast();
  const { can, loading: permLoading } = usePermissions(orgId, stationId);
  const canApprove = can("shift:approve");

  const [{ dateFrom, dateTo }, setRange] = useState(defaultDateRange());
  const [eventType, setEventType] = useState("");
  const [approved, setApproved] = useState<ApprovedFilter>("");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<MeterEventRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<MeterEventRow | null>(null);
  const [approveTarget, setApproveTarget] = useState<MeterEventRow | null>(null);
  const [approving, setApproving] = useState(false);

  const base = `/organizations/${orgId}/stations/${stationId}/meter-events`;

  const load = useCallback(async () => {
    let cancelled = false;
    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
    if (eventType) params.set("event_type", eventType);
    if (approved) params.set("approved", approved);
    setError(null);
    const resp = await authFetch(`${base}?${params.toString()}`);
    if (cancelled) return;
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ detail: "Could not load meter events for this range." }));
      setError(body.detail ?? "Could not load meter events for this range.");
      return;
    }
    setRows(await resp.json());
    return () => {
      cancelled = true;
    };
  }, [authFetch, base, dateFrom, dateTo, eventType, approved]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRows(null);
    load();
  }, [load]);

  const filteredRows = useMemo(() => {
    if (!rows) return rows;
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.nozzle_code.toLowerCase().includes(q) ||
        r.dispenser_code.toLowerCase().includes(q) ||
        r.tank_code.toLowerCase().includes(q) ||
        r.fuel_grade_name.toLowerCase().includes(q) ||
        (r.shift_label ?? "").toLowerCase().includes(q)
    );
  }, [rows, search]);

  async function approveEvent() {
    if (!approveTarget) return;
    setApproving(true);
    try {
      const resp = await authFetch(
        `/organizations/${orgId}/stations/${stationId}/shifts/${approveTarget.shift_id}/nozzle-readings/${approveTarget.nozzle_reading_id}/approve-meter-event`,
        { method: "PATCH", body: JSON.stringify({}) }
      );
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not approve this meter event." }));
        notify("error", body.detail ?? "Could not approve this meter event.");
        return;
      }
      notify("success", "Meter event approved.");
      setApproveTarget(null);
      setDetail(null);
      await load();
    } finally {
      setApproving(false);
    }
  }

  const columns: Column<MeterEventRow>[] = [
    {
      key: "date",
      header: "Shift date",
      sortable: true,
      sortValue: (r) => r.shift_opened_at,
      render: (r) => new Date(r.shift_opened_at).toLocaleDateString(),
    },
    { key: "nozzle", header: "Dispenser / Nozzle", render: (r) => `${r.dispenser_code} / ${r.nozzle_code}` },
    { key: "tank", header: "Tank", render: (r) => `${r.tank_code} (${r.fuel_grade_name})` },
    {
      key: "type",
      header: "Event type",
      render: (r) => <Badge tone={EVENT_TONE[r.event_type] ?? "neutral"}>{EVENT_LABELS[r.event_type] ?? r.event_type}</Badge>,
    },
    {
      key: "segments",
      header: "Pre → Post reading",
      align: "right",
      render: (r) => `${formatLitres(r.meter_event_pre_reading)} → ${formatLitres(r.meter_event_post_reading)}`,
    },
    {
      key: "dispensed",
      header: "Dispensed (both segments)",
      align: "right",
      render: (r) => (r.dispensed_litres ? formatLitres(r.dispensed_litres) : "—"),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => (r.approved_at ? <Badge tone="success">Approved</Badge> : <Badge tone="warning">Pending approval</Badge>),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (r) => (
        <div className="flex justify-end gap-3">
          <button onClick={() => setDetail(r)} className="text-sm font-medium text-accent hover:underline">
            Details
          </button>
          {!r.approved_at && canApprove && (
            <button
              onClick={() => setApproveTarget(r)}
              className="text-sm font-medium text-success-600 hover:underline"
            >
              Approve
            </button>
          )}
        </div>
      ),
    },
  ];

  if (permLoading) {
    return <main className="flex-1 px-6 py-10 text-sm text-ink-soft">Loading…</main>;
  }

  if (!can("shift:read")) {
    return (
      <main className="flex-1">
        <PageHeader title="Meter Events" breadcrumbs={[{ label: "Dashboard" }, { label: "Meter Events" }]} />
        <div className="mx-auto max-w-3xl px-6 py-10">
          <AccessDenied message="Your role does not include visibility into this station's meter events." />
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1">
      <PageHeader
        title="Meter Events"
        description="Every flagged meter rollover, reset and replacement for this station, across every shift."
        breadcrumbs={[{ label: "Dashboard" }, { label: "Meter Events" }]}
        action={<DateRangeFilter dateFrom={dateFrom} dateTo={dateTo} onChange={setRange} />}
      />

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card title="Filters">
          <div className="flex flex-wrap items-end gap-3">
            <div className="relative min-w-[200px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" aria-hidden />
              <TextInput
                placeholder="Search by nozzle, dispenser, tank or shift…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <Field label="Event type">
              {(id) => (
                <Select id={id} value={eventType} onChange={(e) => setEventType(e.target.value)} className="w-44">
                  <option value="">All types</option>
                  <option value="rollover">Meter rollover</option>
                  <option value="reset">Meter reset</option>
                  <option value="replacement">Meter replacement</option>
                </Select>
              )}
            </Field>
            <Field label="Status">
              {(id) => (
                <Select id={id} value={approved} onChange={(e) => setApproved(e.target.value as ApprovedFilter)} className="w-40">
                  <option value="">All statuses</option>
                  <option value="false">Pending approval</option>
                  <option value="true">Approved</option>
                </Select>
              )}
            </Field>
          </div>
        </Card>

        <Card title="Event history">
          {error ? (
            <p className="text-sm text-danger-600">{error}</p>
          ) : filteredRows && filteredRows.length === 0 && !search && !eventType && !approved ? (
            <EmptyState
              icon={Gauge}
              title="No meter events in this range"
              description="A meter rollover, reset or replacement is flagged when a nozzle's closing totalizer is lower than its opening reading - it will show up here as soon as one is recorded."
            />
          ) : (
            <DataTable
              columns={columns}
              data={filteredRows}
              keyFn={(r) => r.nozzle_reading_id}
              emptyMessage="No meter events match these filters."
            />
          )}
        </Card>
      </div>

      <Dialog open={detail !== null} onClose={() => setDetail(null)} title="Meter event details" size="lg">
        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <DetailRow label="Station / Dispenser / Nozzle" value={`${detail.dispenser_code} / ${detail.nozzle_code}`} />
              <DetailRow label="Tank / Fuel grade" value={`${detail.tank_code} / ${detail.fuel_grade_name}`} />
              <DetailRow label="Shift" value={detail.shift_label ?? detail.shift_id.slice(0, 8)} />
              <DetailRow label="Shift opened" value={new Date(detail.shift_opened_at).toLocaleString()} />
              <DetailRow label="Event type" value={EVENT_LABELS[detail.event_type] ?? detail.event_type} />
              <DetailRow label="Opening totalizer" value={formatLitres(detail.opening_totalizer)} />
              <DetailRow label="Pre-event reading" value={formatLitres(detail.meter_event_pre_reading)} />
              <DetailRow label="Post-event reading" value={formatLitres(detail.meter_event_post_reading)} />
              <DetailRow label="Closing totalizer" value={formatLitres(detail.closing_totalizer)} />
              <DetailRow label="Dispensed (both segments)" value={detail.dispensed_litres ? formatLitres(detail.dispensed_litres) : "—"} />
              <DetailRow label="Recorded at" value={detail.recorded_at ? new Date(detail.recorded_at).toLocaleString() : "—"} />
              <DetailRow
                label="Approval"
                value={detail.approved_at ? `Approved ${new Date(detail.approved_at).toLocaleString()}` : "Pending approval"}
              />
            </div>
            {detail.notes && (
              <div>
                <p className="text-xs font-medium text-ink-soft">Notes</p>
                <p className="mt-1 rounded-lg border border-border bg-surface-muted p-3 text-sm text-ink">{detail.notes}</p>
              </div>
            )}
            <p className="rounded-lg border border-border bg-surface-muted p-3 text-xs text-ink-soft">
              Need to correct a pre- or post-event reading? Original readings are never overwritten here - use{" "}
              <a
                href={`/dashboard/org/${orgId}/station/${stationId}/reading-corrections`}
                className="font-medium text-accent hover:underline"
              >
                Reading Corrections
              </a>{" "}
              for this shift instead, which preserves the original value and applies the same correction-window / amendment
              rules as every other reading.
            </p>
            {!detail.approved_at && canApprove && (
              <div className="flex justify-end border-t border-border pt-4">
                <Button onClick={() => setApproveTarget(detail)}>Approve this event</Button>
              </div>
            )}
          </div>
        )}
      </Dialog>

      <ConfirmDialog
        open={approveTarget !== null}
        onClose={() => setApproveTarget(null)}
        onConfirm={approveEvent}
        busy={approving}
        title="Approve this meter event?"
        description={
          approveTarget
            ? `This confirms the ${EVENT_LABELS[approveTarget.event_type] ?? approveTarget.event_type} on ${approveTarget.dispenser_code}/${approveTarget.nozzle_code} is genuine. Once approved, the shift this event belongs to can proceed to final approval. This cannot be undone from here - a correction would need the Reading Corrections workflow instead.`
            : ""
        }
        confirmLabel="Yes, approve"
        confirmVariant="primary"
      />
    </main>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-ink-faint">{label}</p>
      <p className="text-ink">{value}</p>
    </div>
  );
}
