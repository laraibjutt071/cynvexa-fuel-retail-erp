"use client";

import { AlertTriangle, Fuel } from "lucide-react";
import Link from "next/link";
import { formatLitres } from "@/lib/format";
import { useCallback, useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n/context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Select, TextInput } from "@/components/ui/Field";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { usePermissions } from "@/lib/permissions";
import type { NozzleOverview, Shift, ShiftNozzleReading, ShiftTankReading, Tank } from "@/lib/types";
import type { AuthFetch } from "./page";

export function ReadingsSection({
  orgId,
  stationId,
  shift,
  authFetch,
  onShiftChanged,
  onDirtyChange,
}: {
  orgId: string;
  stationId: string;
  shift: Shift;
  authFetch: AuthFetch;
  onShiftChanged: () => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const { notify } = useToast();
  const { t } = useLanguage();
  const { can } = usePermissions(orgId, stationId);
  const canOpen = can("shift:open");
  const canClose = can("shift:close");
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);
  const [tanks, setTanks] = useState<Tank[] | null>(null);
  const [nozzles, setNozzles] = useState<NozzleOverview[] | null>(null);
  const [tankReadings, setTankReadings] = useState<ShiftTankReading[]>([]);
  const [nozzleReadings, setNozzleReadings] = useState<ShiftNozzleReading[]>([]);
  const [tankDipInputs, setTankDipInputs] = useState<Record<string, string>>({});
  const [nozzleInputs, setNozzleInputs] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [meterEventOpen, setMeterEventOpen] = useState<Record<string, boolean>>({});
  const [meterEventType, setMeterEventType] = useState<Record<string, string>>({});
  const [meterEventPre, setMeterEventPre] = useState<Record<string, string>>({});
  const [meterEventPost, setMeterEventPost] = useState<Record<string, string>>({});
  const [meterEventNotes, setMeterEventNotes] = useState<Record<string, string>>({});
  const [confirmMeterEvent, setConfirmMeterEvent] = useState<{ readingId: string; nozzleId: string } | null>(null);

  useEffect(() => {
    const hasUnsaved =
      Object.values(tankDipInputs).some((v) => v.trim() !== "") ||
      Object.values(nozzleInputs).some((v) => v.trim() !== "");
    onDirtyChange(hasUnsaved);
  }, [tankDipInputs, nozzleInputs, onDirtyChange]);

  const shiftBase = `/organizations/${orgId}/stations/${stationId}/shifts/${shift.id}`;
  const readOnly = shift.status !== "open";

  const load = useCallback(async () => {
    const [tanksResp, nozzlesResp, tankReadingsResp, nozzleReadingsResp] = await Promise.all([
      authFetch(`/organizations/${orgId}/stations/${stationId}/tanks`),
      authFetch(`/organizations/${orgId}/stations/${stationId}/nozzles`),
      authFetch(`${shiftBase}/tank-readings`),
      authFetch(`${shiftBase}/nozzle-readings`),
    ]);
    if (tanksResp.ok) setTanks(await tanksResp.json());
    if (nozzlesResp.ok) setNozzles(await nozzlesResp.json());
    if (tankReadingsResp.ok) setTankReadings(await tankReadingsResp.json());
    if (nozzleReadingsResp.ok) setNozzleReadings(await nozzleReadingsResp.json());
  }, [authFetch, orgId, stationId, shiftBase]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function recordTankDip(tankId: string, kind: "opening" | "closing") {
    const value = tankDipInputs[`${tankId}:${kind}`];
    if (!value) return;
    setBusyKey(`tank:${tankId}:${kind}`);
    try {
      const resp = await authFetch(`${shiftBase}/tank-readings/${kind}`, {
        method: "POST",
        body: JSON.stringify({ tank_id: tankId, dip_reading: value }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not save this reading." }));
        notify("error", body.detail ?? "Could not save this reading.");
        return;
      }
      notify("success", `${kind === "opening" ? "Opening" : "Closing"} dip saved.`);
      setTankDipInputs((prev) => { const next = { ...prev }; delete next[`${tankId}:${kind}`]; return next; });
      await load();
    } finally {
      setBusyKey(null);
    }
  }

  async function recordNozzleOpening(nozzleId: string) {
    const value = nozzleInputs[`${nozzleId}:open`];
    if (!value) return;
    setBusyKey(`nozzle:${nozzleId}:open`);
    try {
      const resp = await authFetch(`${shiftBase}/nozzle-readings`, {
        method: "POST",
        body: JSON.stringify({ nozzle_id: nozzleId, opening_totalizer: value }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not save the opening reading." }));
        notify("error", body.detail ?? "Could not save the opening reading.");
        return;
      }
      notify("success", "Opening reading saved.");
      setNozzleInputs((prev) => { const next = { ...prev }; delete next[`${nozzleId}:open`]; return next; });
      await load();
    } finally {
      setBusyKey(null);
    }
  }

  async function recordNozzleClosing(readingId: string, nozzleId: string) {
    const value = nozzleInputs[`${nozzleId}:close`];
    if (!value) return;
    // A flagged meter event is sensitive and not silently reversible (the
    // original closing/pre/post readings are never overwritten after
    // this - only the existing Reading Corrections workflow can correct
    // them) - require an explicit confirmation step before submitting one,
    // same as closing the whole day's readings already does.
    if (meterEventOpen[nozzleId]) {
      setConfirmMeterEvent({ readingId, nozzleId });
      return;
    }
    await submitNozzleClosing(readingId, nozzleId, value);
  }

  async function submitNozzleClosing(readingId: string, nozzleId: string, value: string) {
    setBusyKey(`nozzle:${nozzleId}:close`);
    try {
      const flagged = meterEventOpen[nozzleId];
      const payload: Record<string, unknown> = { closing_totalizer: value };
      if (flagged) {
        payload.meter_event_type = meterEventType[nozzleId] || "replacement";
        payload.meter_event_pre_reading = meterEventPre[nozzleId];
        payload.meter_event_post_reading = meterEventPost[nozzleId];
        payload.meter_event_notes = meterEventNotes[nozzleId] || undefined;
      }
      const resp = await authFetch(`${shiftBase}/nozzle-readings/${readingId}/close`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not save the closing reading. If the meter was replaced or rolled over, flag a meter event instead of a plain closing reading." }));
        notify("error", body.detail ?? "Could not save the closing reading.");
        return;
      }
      notify(
        "success",
        flagged ? "Meter event recorded - it will need approval before this shift can be approved." : "Closing reading saved - litres sold calculated automatically."
      );
      setNozzleInputs((prev) => { const next = { ...prev }; delete next[`${nozzleId}:close`]; return next; });
      setMeterEventOpen((prev) => ({ ...prev, [nozzleId]: false }));
      await load();
    } finally {
      setBusyKey(null);
    }
  }

  const tankReadingByTank = (tankId: string, type: "opening" | "closing") =>
    tankReadings.find((r) => r.tank_id === tankId && r.reading_type === type);
  const nozzleReadingByNozzle = (nozzleId: string) => nozzleReadings.find((r) => r.nozzle_id === nozzleId);

  // A brand-new station (just onboarded, no tanks/dispensers/nozzles
  // configured yet) has nothing for this section to show readings for -
  // without this, the tank-stock table below silently renders with a
  // header row and zero data rows, which looks like a broken page rather
  // than "set up your station first."
  if (tanks !== null && tanks.length === 0) {
    return (
      <Card title={t("readings.tankStock")}>
        <EmptyState
          icon={Fuel}
          title="No tanks set up yet"
          description="Before readings can be recorded, this station needs at least one fuel grade, tank, dispenser and nozzle configured."
          action={
            <Link href={`/dashboard/org/${orgId}/station/${stationId}/settings`}>
              <Button>Set up tanks &amp; dispensers</Button>
            </Link>
          }
        />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card
        title={t("readings.tankStock")}
        description="Opening stock carries forward automatically from the last approved closing stock - nothing to re-enter, and it is never silently overwritten. Closing dip is what you physically measure at the end of the day."
        action={
          <Link
            href={`/dashboard/org/${orgId}/station/${stationId}/tanks`}
            className="text-xs font-medium text-brand-500 hover:underline"
          >
            Convert a stick reading (dip chart) →
          </Link>
        }
      >
        {!tanks ? (
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-ink-faint">
                <th className="py-2 pr-2">Tank</th>
                <th className="py-2 pr-2">{t("readings.currentBookStock")}</th>
                <th className="py-2 pr-2">{t("readings.openingDip")}</th>
                <th className="py-2 pr-2">{t("readings.closingDip")}</th>
              </tr>
            </thead>
            <tbody>
              {tanks.map((tank) => {
                const opening = tankReadingByTank(tank.id, "opening");
                const closing = tankReadingByTank(tank.id, "closing");
                return (
                  <tr key={tank.id} className="border-b border-border/60">
                    <td className="py-2 pr-2 font-medium text-ink">{tank.code}</td>
                    <td className="py-2 pr-2 text-ink-soft">{tank.book_stock}</td>
                    <td className="py-2 pr-2">
                      {opening ? (
                        <span className="text-ink tabular-nums">{formatLitres(opening.dip_reading)}</span>
                      ) : readOnly ? (
                        <span className="text-ink-faint">{t("readings.notRecorded")}</span>
                      ) : !canOpen ? (
                        <span className="text-ink-faint">Waiting for an authorized user to record this</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            min="0"
                            required
                            aria-label={`Opening dip for tank ${tank.code} (required, litres)`}
                            placeholder="Opening dip (L) *"
                            className="w-32"
                            value={tankDipInputs[`${tank.id}:opening`] ?? ""}
                            onChange={(e) =>
                              setTankDipInputs({ ...tankDipInputs, [`${tank.id}:opening`]: e.target.value })
                            }
                          />
                          <Button
                            size="sm"
                            variant="secondary"
                            busy={busyKey === `tank:${tank.id}:opening`}
                            onClick={() => recordTankDip(tank.id, "opening")}
                          >
                            {t("common.save")}
                          </Button>
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-2">
                      {!opening ? (
                        <span className="text-ink-faint">{t("readings.recordOpeningFirst")}</span>
                      ) : closing ? (
                        <span className="text-ink tabular-nums">{formatLitres(closing.dip_reading)}</span>
                      ) : readOnly ? (
                        <span className="text-ink-faint">{t("readings.notRecorded")}</span>
                      ) : !canClose ? (
                        <span className="text-ink-faint">Waiting for an authorized user to record this</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            min="0"
                            required
                            aria-label={`Closing dip for tank ${tank.code} (required, litres)`}
                            placeholder="Closing dip (L) *"
                            className="w-32"
                            value={tankDipInputs[`${tank.id}:closing`] ?? ""}
                            onChange={(e) =>
                              setTankDipInputs({ ...tankDipInputs, [`${tank.id}:closing`]: e.target.value })
                            }
                          />
                          <Button
                            size="sm"
                            variant="secondary"
                            busy={busyKey === `tank:${tank.id}:closing`}
                            onClick={() => recordTankDip(tank.id, "closing")}
                          >
                            {t("common.save")}
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      <Card title={t("readings.nozzleReadings")} description={t("readings.totalizerHelp")}>
        {!nozzles ? (
          <p className="text-sm text-ink-soft">{t("common.loading")}</p>
        ) : nozzles.length === 0 ? (
          <p className="text-sm text-ink-soft">{t("readings.noNozzles")}</p>
        ) : (
          <div className="space-y-4">
            {nozzles.map((n) => {
              const reading = nozzleReadingByNozzle(n.nozzle_id);
              const suggestedOpening = n.last_closing_totalizer ?? "";
              return (
                <div key={n.nozzle_id} className="card-glow rounded-lg border border-border bg-surface p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-ink">
                        {n.dispenser_code} / {n.nozzle_code} <span className="text-ink-faint">· {n.fuel_grade_name}</span>
                      </p>
                      <p className="text-xs text-ink-faint">
                        Price: {n.current_price_per_litre ?? "not set"} / litre · Previous closing:{" "}
                        {n.last_closing_totalizer ?? "none yet"}
                      </p>
                    </div>
                    {reading?.dispensed_litres && (
                      <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-accent">
                        {formatLitres(reading.dispensed_litres)} {t("readings.litresSoldToday")}
                      </span>
                    )}
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <p className="mb-1 text-xs font-medium text-ink-soft">{t("readings.openingReading")}</p>
                      {reading ? (
                        <p className="text-sm text-ink">{reading.opening_totalizer}</p>
                      ) : readOnly ? (
                        <p className="text-sm text-ink-faint">{t("readings.notRecorded")}</p>
                      ) : !canOpen ? (
                        <p className="text-sm text-ink-faint">Waiting for an authorized user to record this</p>
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            min="0"
                            required
                            aria-label={`Opening totalizer for ${n.dispenser_code}/${n.nozzle_code} (required)`}
                            placeholder="Opening totalizer *"
                            className="w-36"
                            value={nozzleInputs[`${n.nozzle_id}:open`] ?? suggestedOpening}
                            onChange={(e) =>
                              setNozzleInputs({ ...nozzleInputs, [`${n.nozzle_id}:open`]: e.target.value })
                            }
                          />
                          <Button
                            size="sm"
                            variant="secondary"
                            busy={busyKey === `nozzle:${n.nozzle_id}:open`}
                            onClick={() => recordNozzleOpening(n.nozzle_id)}
                          >
                            {t("common.save")}
                          </Button>
                        </div>
                      )}
                    </div>
                    <div>
                      <p className="mb-1 text-xs font-medium text-ink-soft">{t("readings.closingReading")}</p>
                      {!reading ? (
                        <p className="text-sm text-ink-faint">{t("readings.recordOpeningFirst")}</p>
                      ) : reading.closing_totalizer ? (
                        <p className="text-sm text-ink">{reading.closing_totalizer}</p>
                      ) : readOnly ? (
                        <p className="text-sm text-ink-faint">{t("readings.notRecorded")}</p>
                      ) : !canClose ? (
                        <p className="text-sm text-ink-faint">Waiting for an authorized user to record this</p>
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            min="0"
                            required
                            aria-label={`Closing totalizer for ${n.dispenser_code}/${n.nozzle_code} (required)`}
                            placeholder="Closing totalizer *"
                            className="w-36"
                            value={nozzleInputs[`${n.nozzle_id}:close`] ?? ""}
                            onChange={(e) =>
                              setNozzleInputs({ ...nozzleInputs, [`${n.nozzle_id}:close`]: e.target.value })
                            }
                          />
                          <Button
                            size="sm"
                            variant="secondary"
                            busy={busyKey === `nozzle:${n.nozzle_id}:close`}
                            onClick={() => recordNozzleClosing(reading.id, n.nozzle_id)}
                          >
                            {t("common.save")}
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                  {reading && !reading.closing_totalizer && !readOnly && canClose && (
                    <div className="mt-3 border-t border-border pt-3">
                      {Number(nozzleInputs[`${n.nozzle_id}:close`] ?? "1") < Number(reading.opening_totalizer) &&
                        nozzleInputs[`${n.nozzle_id}:close`] &&
                        !meterEventOpen[n.nozzle_id] && (
                          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-caution-600">
                            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
                            This reading is lower than the opening reading. If the meter was reset, replaced, or rolled
                            over, flag a meter event below instead of saving this as-is.
                          </p>
                        )}
                      <label className="flex items-center gap-2 text-xs font-medium text-ink-soft">
                        <input
                          type="checkbox"
                          checked={meterEventOpen[n.nozzle_id] ?? false}
                          onChange={(e) => setMeterEventOpen({ ...meterEventOpen, [n.nozzle_id]: e.target.checked })}
                        />
                        This meter was reset, replaced, or rolled over mid-shift
                      </label>
                      {meterEventOpen[n.nozzle_id] && (
                        <div className="mt-2 grid grid-cols-1 gap-2 rounded-lg border border-caution-100 bg-caution-50/50 p-3 sm:grid-cols-2">
                          <Select
                            aria-label="Meter event type"
                            value={meterEventType[n.nozzle_id] ?? "replacement"}
                            onChange={(e) => setMeterEventType({ ...meterEventType, [n.nozzle_id]: e.target.value })}
                          >
                            <option value="replacement">Replacement</option>
                            <option value="reset">Reset</option>
                            <option value="rollover">Rollover</option>
                          </Select>
                          <div />
                          <TextInput
                            type="number"
                            step="0.001"
                            min="0"
                            required
                            aria-label="Reading just before the event"
                            placeholder="Pre-event reading *"
                            value={meterEventPre[n.nozzle_id] ?? ""}
                            onChange={(e) => setMeterEventPre({ ...meterEventPre, [n.nozzle_id]: e.target.value })}
                          />
                          <TextInput
                            type="number"
                            step="0.001"
                            min="0"
                            required
                            aria-label="Reading just after the event (0 for a rollover/reset)"
                            placeholder="Post-event reading *"
                            value={meterEventPost[n.nozzle_id] ?? ""}
                            onChange={(e) => setMeterEventPost({ ...meterEventPost, [n.nozzle_id]: e.target.value })}
                          />
                          <TextInput
                            aria-label="Notes about this meter event"
                            placeholder="Notes (optional)"
                            className="sm:col-span-2"
                            value={meterEventNotes[n.nozzle_id] ?? ""}
                            onChange={(e) => setMeterEventNotes({ ...meterEventNotes, [n.nozzle_id]: e.target.value })}
                          />
                          <p className="text-xs text-ink-faint sm:col-span-2">
                            Dispensed litres = (pre-event − opening) + (closing − post-event). Both segments must be
                            zero or more. This still needs approval from a Station Manager or Shift Supervisor before
                            the shift can be approved.
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {shift.status === "open" && canClose && (
        <Card title={t("readings.finishedTitle")}>
          <p className="mb-3 text-sm text-ink-soft">{t("readings.finishedHelp")}</p>
          <Button variant="secondary" onClick={() => setCloseConfirmOpen(true)} busy={busyKey === "close-shift"}>
            {t("readings.closeReadings")}
          </Button>
        </Card>
      )}

      <ConfirmDialog
        open={closeConfirmOpen}
        onClose={() => setCloseConfirmOpen(false)}
        onConfirm={async () => {
          setBusyKey("close-shift");
          try {
            const resp = await authFetch(`${shiftBase}/close`, { method: "PATCH" });
            if (!resp.ok) {
              const body = await resp.json().catch(() => ({ detail: "Could not close the shift yet." }));
              notify("error", body.detail ?? "Could not close the shift yet.");
              return;
            }
            notify("success", t("readings.closingSaved"));
            setCloseConfirmOpen(false);
            onShiftChanged();
          } finally {
            setBusyKey(null);
          }
        }}
        title="Close today's readings?"
        description="No more tank dips or nozzle totalizers can be recorded for today after this. Make sure every tank and nozzle above has both an opening and closing reading first."
        confirmLabel="Yes, close readings"
        confirmVariant="primary"
        busy={busyKey === "close-shift"}
      />

      <ConfirmDialog
        open={confirmMeterEvent !== null}
        onClose={() => setConfirmMeterEvent(null)}
        onConfirm={async () => {
          if (!confirmMeterEvent) return;
          const { readingId, nozzleId } = confirmMeterEvent;
          const value = nozzleInputs[`${nozzleId}:close`];
          setConfirmMeterEvent(null);
          await submitNozzleClosing(readingId, nozzleId, value);
        }}
        title="Flag this meter event?"
        description="This records that the nozzle's totalizer was reset, replaced, or rolled over mid-shift - the original closing reading and event values are permanent once saved (a Reading Correction is the only way to fix them afterward). A Station Manager or Shift Supervisor will still need to approve this event before the shift can be approved."
        confirmLabel="Yes, flag this meter event"
        confirmVariant="primary"
        busy={busyKey !== null && busyKey.endsWith(":close")}
      />
    </div>
  );
}
