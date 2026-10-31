"use client";

import { AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLanguage } from "@/lib/i18n/context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import type { NozzleOverview, Shift, ShiftNozzleReading, ShiftTankReading, Tank } from "@/lib/types";
import type { AuthFetch } from "./page";

export function ReadingsSection({
  orgId,
  stationId,
  shift,
  authFetch,
  onShiftChanged,
}: {
  orgId: string;
  stationId: string;
  shift: Shift;
  authFetch: AuthFetch;
  onShiftChanged: () => void;
}) {
  const { notify } = useToast();
  const { t } = useLanguage();
  const [tanks, setTanks] = useState<Tank[] | null>(null);
  const [nozzles, setNozzles] = useState<NozzleOverview[] | null>(null);
  const [tankReadings, setTankReadings] = useState<ShiftTankReading[]>([]);
  const [nozzleReadings, setNozzleReadings] = useState<ShiftNozzleReading[]>([]);
  const [tankDipInputs, setTankDipInputs] = useState<Record<string, string>>({});
  const [nozzleInputs, setNozzleInputs] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);

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
      await load();
    } finally {
      setBusyKey(null);
    }
  }

  async function recordNozzleClosing(readingId: string, nozzleId: string) {
    const value = nozzleInputs[`${nozzleId}:close`];
    if (!value) return;
    setBusyKey(`nozzle:${nozzleId}:close`);
    try {
      const resp = await authFetch(`${shiftBase}/nozzle-readings/${readingId}/close`, {
        method: "PATCH",
        body: JSON.stringify({ closing_totalizer: value }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not save the closing reading. If the meter was replaced or rolled over, this needs a meter-event correction instead of a plain closing reading." }));
        notify("error", body.detail ?? "Could not save the closing reading.");
        return;
      }
      notify("success", "Closing reading saved - litres sold calculated automatically.");
      await load();
    } finally {
      setBusyKey(null);
    }
  }

  const tankReadingByTank = (tankId: string, type: "opening" | "closing") =>
    tankReadings.find((r) => r.tank_id === tankId && r.reading_type === type);
  const nozzleReadingByNozzle = (nozzleId: string) => nozzleReadings.find((r) => r.nozzle_id === nozzleId);

  return (
    <div className="space-y-6">
      <Card
        title={t("readings.tankStock")}
        description="Opening stock carries forward automatically from the last approved closing stock - nothing to re-enter, and it is never silently overwritten. Closing dip is what you physically measure at the end of the day."
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
                        <span className="text-ink">{opening.dip_reading}</span>
                      ) : readOnly ? (
                        <span className="text-ink-faint">{t("readings.notRecorded")}</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            placeholder="Opening dip"
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
                        <span className="text-ink">{closing.dip_reading}</span>
                      ) : readOnly ? (
                        <span className="text-ink-faint">{t("readings.notRecorded")}</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            placeholder="Closing dip"
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
                        {reading.dispensed_litres} L {t("readings.litresSoldToday")}
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
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            placeholder="Opening totalizer"
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
                      ) : (
                        <div className="flex items-center gap-2">
                          <TextInput
                            type="number"
                            step="0.001"
                            placeholder="Closing totalizer"
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
                  {reading && !reading.closing_totalizer && Number(nozzleInputs[`${n.nozzle_id}:close`] ?? "1") < Number(reading.opening_totalizer) && nozzleInputs[`${n.nozzle_id}:close`] && (
                    <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-caution-600">
                      <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                      This reading is lower than the opening reading. If the meter was reset or replaced, use the
                      meter-event correction (ask a manager) instead of saving this as-is.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {shift.status === "open" && (
        <Card title={t("readings.finishedTitle")}>
          <p className="mb-3 text-sm text-ink-soft">{t("readings.finishedHelp")}</p>
          <Button
            variant="secondary"
            onClick={async () => {
              setBusyKey("close-shift");
              const resp = await authFetch(`${shiftBase}/close`, { method: "PATCH" });
              if (!resp.ok) {
                const body = await resp.json().catch(() => ({ detail: "Could not close the shift yet." }));
                notify("error", body.detail ?? "Could not close the shift yet.");
              } else {
                notify("success", t("readings.closingSaved"));
                onShiftChanged();
              }
              setBusyKey(null);
            }}
            busy={busyKey === "close-shift"}
          >
            {t("readings.closeReadings")}
          </Button>
        </Card>
      )}
    </div>
  );
}
