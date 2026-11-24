"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { TankDipChartPanel } from "@/components/dashboard/TankDipChartPanel";
import { formatLitres } from "@/lib/format";
import type { FuelGrade, Tank } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

export default function TankManagementPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { user, loading, authFetch } = useAuth();
  const router = useRouter();
  const { notify } = useToast();

  const [tanks, setTanks] = useState<Tank[] | null>(null);
  const [fuelGrades, setFuelGrades] = useState<FuelGrade[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ location: "", calibration_reference: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const { can } = usePermissions(orgId, stationId);
  const canManage = can("tank:manage");

  const loadData = useCallback(async () => {
    const [tanksResp, gradesResp] = await Promise.all([
      authFetch(`/organizations/${orgId}/stations/${stationId}/tanks`),
      authFetch(`/organizations/${orgId}/fuel-grades`),
    ]);
    if (tanksResp.ok) setTanks(await tanksResp.json());
    if (gradesResp.ok) setFuelGrades(await gradesResp.json());
  }, [authFetch, orgId, stationId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  function startEdit(tank: Tank) {
    setEditing(tank.id);
    setEditForm({
      location: tank.location ?? "",
      calibration_reference: tank.calibration_reference ?? "",
    });
  }

  async function saveTank(tankId: string) {
    setBusy(true);
    try {
      const resp = await authFetch(
        `/organizations/${orgId}/stations/${stationId}/tanks/${tankId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            location: editForm.location || null,
            calibration_reference: editForm.calibration_reference || null,
          }),
        }
      );
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not update." }));
        notify("error", body.detail ?? "Could not update tank.");
        return;
      }
      notify("success", "Tank updated.");
      setEditing(null);
      await loadData();
    } finally {
      setBusy(false);
    }
  }

  const gradeName = (gradeId: string) =>
    fuelGrades.find((g) => g.id === gradeId)?.name ?? gradeId;

  if (loading || !user) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-ink-soft">Loading…</p>
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
          <h1 className="text-lg font-semibold text-ink">Tank configuration</h1>
          <p className="mt-1 text-sm text-ink-soft">
            View and manage tank details: location, calibration reference, capacity, and current book stock.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <Card title="Tanks">
          {!tanks ? (
            <p className="text-sm text-ink-soft">Loading…</p>
          ) : tanks.length === 0 ? (
            <p className="text-sm text-ink-soft">No tanks configured.</p>
          ) : (
            <div className="space-y-4">
              {tanks.map((tank) => (
                <div
                  key={tank.id}
                  className="rounded-lg border border-border bg-surface p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-ink">
                        {tank.code} — {tank.name}
                      </p>
                      <p className="text-xs text-ink-faint">
                        Grade: {gradeName(tank.fuel_grade_id)} · Capacity:{" "}
                        {formatLitres(tank.capacity)} · Safe fill: {formatLitres(tank.safe_fill_limit)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-ink">
                        Book stock: {formatLitres(tank.book_stock)}
                      </p>
                      <p className="text-xs text-ink-faint">
                        Available: {formatLitres(tank.safe_capacity_available)}
                      </p>
                    </div>
                  </div>

                  <div className="mt-2 grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-ink-faint">Location: </span>
                      <span className="text-ink">{tank.location ?? "—"}</span>
                    </div>
                    <div>
                      <span className="text-ink-faint">Calibration ref: </span>
                      <span className="text-ink">
                        {tank.calibration_reference ?? "—"}
                      </span>
                    </div>
                  </div>

                  {canManage && editing !== tank.id && (
                    <Button
                      size="sm"
                      variant="secondary"
                      className="mt-3"
                      onClick={() => startEdit(tank)}
                    >
                      Edit details
                    </Button>
                  )}

                  <TankDipChartPanel
                    orgId={orgId}
                    stationId={stationId}
                    tankId={tank.id}
                    authFetch={authFetch}
                    canManage={canManage}
                  />

                  {editing === tank.id && (
                    <div className="mt-3 space-y-3 border-t border-border pt-3">
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <Field label="Location">
                          {(id) => (
                            <TextInput
                              id={id}
                              value={editForm.location}
                              onChange={(e) =>
                                setEditForm({
                                  ...editForm,
                                  location: e.target.value,
                                })
                              }
                              placeholder="e.g. North yard, underground pit 2"
                            />
                          )}
                        </Field>
                        <Field label="Calibration reference">
                          {(id) => (
                            <TextInput
                              id={id}
                              value={editForm.calibration_reference}
                              onChange={(e) =>
                                setEditForm({
                                  ...editForm,
                                  calibration_reference: e.target.value,
                                })
                              }
                              placeholder="e.g. Cal cert #12345, expires 2027-03"
                            />
                          )}
                        </Field>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => saveTank(tank.id)}
                          busy={busy}
                        >
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setEditing(null)}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
