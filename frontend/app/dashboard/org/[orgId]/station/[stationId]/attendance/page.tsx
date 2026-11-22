"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { DataTable } from "@/components/ui/DataTable";
import { HardwareIntegrationCard } from "@/components/dashboard/HardwareIntegrationCard";
import type { AttendanceRecord, OrgUser } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

const STATUSES = ["present", "absent", "late", "half_day", "leave"] as const;

export default function AttendancePage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();
  const { can, loading: permissionsLoading } = usePermissions(orgId, stationId);
  const canRead = can(["attendance:read", "attendance:record"]);
  const canRecord = can("attendance:record");
  const canConfigureHardware = can("station:update");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user || permissionsLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-ink-soft">Loading...</p>
      </div>
    );
  }

  if (!canRead) {
    return (
      <div className="flex-1 px-6 py-10">
        <AccessDenied message="Your role does not include access to attendance records at this station." />
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
          <h1 className="text-lg font-semibold text-ink">Attendance</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Record who was present, absent, late, or on leave each day - entered manually, or automatically once a
            biometric device is connected below. Payroll rules are configured separately and are not part of this
            screen yet.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {canConfigureHardware && (
          <HardwareIntegrationCard
            orgId={orgId}
            stationId={stationId}
            authFetch={authFetch}
            allowedTypes={["biometric_attendance"]}
            title="Biometric Attendance Device"
            description="Connect a fingerprint or face-scan device so check-in/check-out are recorded automatically instead of typed in."
            idlePrompt='Attendance here is currently entered manually below. Click "Start Hardware Connection" to connect a biometric device, step by step.'
          />
        )}
        <AttendanceSection orgId={orgId} stationId={stationId} authFetch={authFetch} canRecord={canRecord} />
      </div>
    </div>
  );
}

function AttendanceSection({
  orgId,
  stationId,
  authFetch,
  canRecord,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  canRecord: boolean;
}) {
  const { notify } = useToast();
  const [records, setRecords] = useState<AttendanceRecord[] | null>(null);
  const [users, setUsers] = useState<OrgUser[]>([]);
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().split("T")[0];
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().split("T")[0]);

  const [formUserId, setFormUserId] = useState("");
  const [formDate, setFormDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [formStatus, setFormStatus] = useState<string>("present");
  const [formCheckIn, setFormCheckIn] = useState("");
  const [formCheckOut, setFormCheckOut] = useState("");
  const [formNotes, setFormNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const base = `/organizations/${orgId}/stations/${stationId}/attendance`;

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/users`);
      if (resp.ok) setUsers(await resp.json());
    })();
  }, [orgId, authFetch]);

  const load = useCallback(async () => {
    const qs = `?date_from=${dateFrom}&date_to=${dateTo}`;
    const resp = await authFetch(`${base}${qs}`);
    if (resp.ok) setRecords(await resp.json());
  }, [authFetch, base, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate() {
    if (!formUserId) {
      notify("error", "Please select an employee.");
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        user_id: formUserId,
        attendance_date: formDate,
        status: formStatus,
      };
      if (formCheckIn) body.check_in_time = formCheckIn;
      if (formCheckOut) body.check_out_time = formCheckOut;
      if (formNotes) body.notes = formNotes;

      const resp = await authFetch(base, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Could not save." }));
        notify("error", err.detail ?? "Could not save.");
        return;
      }
      notify("success", "Attendance recorded.");
      setFormNotes("");
      setFormCheckIn("");
      setFormCheckOut("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      present: "bg-green-100 text-green-700",
      absent: "bg-red-100 text-red-700",
      late: "bg-yellow-100 text-yellow-800",
      half_day: "bg-orange-100 text-orange-700",
      leave: "bg-blue-100 text-blue-700",
    };
    return (
      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] ?? "bg-surface-elevated text-ink"}`}>
        {status.replace(/_/g, " ")}
      </span>
    );
  };

  const userNameById = new Map(users.map((u) => [u.id, u.full_name]));

  return (
    <>
      {canRecord && (
      <Card title="Record attendance">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">Employee</span>
            <select
              value={formUserId}
              onChange={(e) => setFormUserId(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm"
            >
              <option value="">Select...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">Date</span>
            <input type="date" value={formDate} onChange={(e) => setFormDate(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">Status</span>
            <select value={formStatus} onChange={(e) => setFormStatus(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm">
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">Check-in time</span>
            <input type="time" value={formCheckIn} onChange={(e) => setFormCheckIn(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">Check-out time</span>
            <input type="time" value={formCheckOut} onChange={(e) => setFormCheckOut(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">Notes</span>
            <input type="text" value={formNotes} onChange={(e) => setFormNotes(e.target.value)}
              placeholder="Optional"
              className="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </label>
        </div>
        <div className="mt-4">
          <Button onClick={handleCreate} busy={busy}>Save attendance</Button>
        </div>
      </Card>
      )}

      <Card title="Attendance records">
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">From</span>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-lg border border-border px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-soft">To</span>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
              className="rounded-lg border border-border px-3 py-2 text-sm" />
          </label>
          <Button size="sm" variant="secondary" onClick={load}>Refresh</Button>
        </div>

        <DataTable
          columns={[
            { key: "date", header: "Date", render: (r) => r.attendance_date, sortable: true, sortValue: (r) => r.attendance_date },
            { key: "employee", header: "Employee", render: (r) => userNameById.get(r.user_id) ?? r.user_id.slice(0, 8) },
            { key: "status", header: "Status", render: (r) => statusBadge(r.status) },
            { key: "check_in", header: "Check-in", render: (r) => <span className="text-ink-soft">{r.check_in_time ?? "—"}</span> },
            { key: "check_out", header: "Check-out", render: (r) => <span className="text-ink-soft">{r.check_out_time ?? "—"}</span> },
            { key: "notes", header: "Notes", render: (r) => <span className="text-ink-soft">{r.notes ?? ""}</span> },
          ]}
          data={records}
          keyFn={(r) => r.id}
          emptyMessage="No attendance records for this period."
        />
      </Card>
    </>
  );
}
