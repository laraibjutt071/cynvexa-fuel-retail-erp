"use client";

import { useCallback, useEffect, useState } from "react";
import { Ruler, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { TankDipChartEntry, TankDipChartLookupResult } from "@/lib/types";

type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>;

/**
 * Per-tank calibration ("dip chart" / strapping table) reference tool - a
 * standalone lookup, never wired into shift readings themselves. The
 * operator reads their physical stick measurement here, gets the litre
 * equivalent for THIS tank's geometry, then types that litres value into
 * the daily entry reading exactly as before. Nothing about how shift
 * readings, reconciliation or the stock ledger work changes.
 */
export function TankDipChartPanel({
  orgId,
  stationId,
  tankId,
  authFetch,
  canManage,
}: {
  orgId: string;
  stationId: string;
  tankId: string;
  authFetch: AuthFetch;
  canManage: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<TankDipChartEntry[] | null>(null);
  const [newDip, setNewDip] = useState("");
  const [newVolume, setNewVolume] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [calcDip, setCalcDip] = useState("");
  const [calcResult, setCalcResult] = useState<TankDipChartLookupResult | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);

  const base = `/organizations/${orgId}/stations/${stationId}/tanks/${tankId}/dip-chart`;

  const load = useCallback(async () => {
    const resp = await authFetch(base);
    if (resp.ok) setEntries(await resp.json());
  }, [authFetch, base]);

  useEffect(() => {
    if (open && entries === null) load();
  }, [open, entries, load]);

  async function addEntry(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    setError(null);
    try {
      const resp = await authFetch(base, {
        method: "POST",
        body: JSON.stringify({ dip_mm: newDip, volume_litres: newVolume }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not add this point." }));
        setError(body.detail ?? "Could not add this calibration point.");
        return;
      }
      setNewDip("");
      setNewVolume("");
      await load();
    } finally {
      setAdding(false);
    }
  }

  async function deleteEntry(entryId: string) {
    const resp = await authFetch(`${base}/${entryId}`, { method: "DELETE" });
    if (resp.ok || resp.status === 204) await load();
  }

  async function runLookup(e: React.FormEvent) {
    e.preventDefault();
    setCalculating(true);
    setCalcError(null);
    setCalcResult(null);
    try {
      const resp = await authFetch(`${base}/lookup?dip_mm=${encodeURIComponent(calcDip)}`);
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not convert this reading." }));
        setCalcError(body.detail ?? "Could not convert this reading.");
        return;
      }
      setCalcResult(await resp.json());
    } finally {
      setCalculating(false);
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        <Ruler className="h-3.5 w-3.5" aria-hidden />
        Dip chart (calibration table)
      </Button>
    );
  }

  return (
    <div className="mt-3 w-full space-y-4 border-t border-border pt-3">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-ink">
          <Ruler className="h-3.5 w-3.5" aria-hidden />
          Dip chart (calibration table)
        </p>
        <button onClick={() => setOpen(false)} className="text-xs text-ink-faint hover:text-ink">
          Hide
        </button>
      </div>
      <p className="text-xs text-ink-soft">
        Maps a physical dip-stick reading (mm) to this tank&apos;s litres, per its own calibration certificate -
        a reference lookup only. It never changes how shift readings are recorded; those still take litres directly.
      </p>

      {entries === null ? (
        <p className="text-xs text-ink-soft">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-xs text-ink-soft">No calibration points yet.</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left text-ink-faint">
              <th className="py-1.5 pr-2">Dip (mm)</th>
              <th className="py-1.5 pr-2">Volume (L)</th>
              {canManage && <th className="py-1.5 pr-2"></th>}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b border-border/60">
                <td className="py-1.5 pr-2 text-ink tabular-nums">{entry.dip_mm}</td>
                <td className="py-1.5 pr-2 text-ink tabular-nums">{entry.volume_litres}</td>
                {canManage && (
                  <td className="py-1.5 pr-2 text-right">
                    <button
                      onClick={() => deleteEntry(entry.id)}
                      className="text-ink-faint hover:text-danger-600"
                      aria-label={`Remove calibration point at ${entry.dip_mm}mm`}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canManage && (
        <form onSubmit={addEntry} className="flex flex-wrap items-end gap-2">
          <label className="text-xs text-ink-soft">
            Dip (mm)
            <input
              required
              type="number"
              step="0.1"
              min="0"
              value={newDip}
              onChange={(e) => setNewDip(e.target.value)}
              className="ml-1.5 w-24 rounded-md border border-border px-2 py-1 text-xs"
            />
          </label>
          <label className="text-xs text-ink-soft">
            Volume (L)
            <input
              required
              type="number"
              step="0.001"
              min="0"
              value={newVolume}
              onChange={(e) => setNewVolume(e.target.value)}
              className="ml-1.5 w-28 rounded-md border border-border px-2 py-1 text-xs"
            />
          </label>
          <Button type="submit" size="sm" busy={adding}>
            Add point
          </Button>
        </form>
      )}
      {error && <p className="text-xs text-danger-600">{error}</p>}

      <div className="rounded-lg border border-dashed border-border bg-surface-elevated p-3">
        <p className="mb-2 text-xs font-medium text-ink">Convert a stick reading</p>
        <form onSubmit={runLookup} className="flex flex-wrap items-end gap-2">
          <label className="text-xs text-ink-soft">
            Dip (mm)
            <input
              required
              type="number"
              step="0.1"
              min="0"
              value={calcDip}
              onChange={(e) => setCalcDip(e.target.value)}
              className="ml-1.5 w-24 rounded-md border border-border px-2 py-1 text-xs"
            />
          </label>
          <Button type="submit" size="sm" variant="secondary" busy={calculating}>
            Convert
          </Button>
        </form>
        {calcResult && (
          <p className="mt-2 text-sm font-semibold text-ink">
            {calcResult.volume_litres} L
            {!calcResult.exact_match && <span className="ml-1 text-xs font-normal text-ink-faint">(interpolated)</span>}
          </p>
        )}
        {calcError && <p className="mt-2 text-xs text-danger-600">{calcError}</p>}
      </div>
    </div>
  );
}
