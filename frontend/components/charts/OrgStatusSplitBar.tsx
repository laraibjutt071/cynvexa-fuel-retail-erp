"use client";

import { useChartColors } from "@/lib/useChartColors";
import { Card } from "@/components/Card";

/** The one tall segmented bar exempted from the "no direct labels" rule
 * (see the dataviz skill's marks-and-anatomy reference: "Figures") - two
 * segments, both always direct-labeled and legend-kept since there are
 * only ever two categories (active/suspended) and the split itself, not
 * precise values, is the point. Status colors (success/danger), never
 * reused for an unrelated series. */
export function OrgStatusSplitBar({ active, suspended }: { active: number; suspended: number }) {
  const c = useChartColors();
  const total = active + suspended;
  const activePct = total > 0 ? (active / total) * 100 : 0;
  const suspendedPct = total > 0 ? (suspended / total) * 100 : 0;

  return (
    <Card title="Organization status" description="Active vs. suspended, across the whole platform.">
      {total === 0 ? (
        <p className="py-10 text-center text-sm text-ink-soft">No organizations yet.</p>
      ) : (
        <div className="space-y-4 py-2">
          <div className="flex h-8 w-full gap-0.5 overflow-hidden rounded-full border border-border bg-surface-muted">
            {active > 0 && (
              <div
                className="flex items-center justify-center rounded-full text-xs font-semibold text-white transition-all"
                style={{ width: `${activePct}%`, backgroundColor: c.success, minWidth: active > 0 ? "2.5rem" : 0 }}
              >
                {active}
              </div>
            )}
            {suspended > 0 && (
              <div
                className="flex items-center justify-center rounded-full text-xs font-semibold text-white transition-all"
                style={{ width: `${suspendedPct}%`, backgroundColor: c.danger, minWidth: suspended > 0 ? "2.5rem" : 0 }}
              >
                {suspended}
              </div>
            )}
          </div>
          <div className="flex items-center gap-5 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c.success }} />
              <span className="text-ink-soft">Active</span>
              <span className="font-semibold text-ink">{active}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c.danger }} />
              <span className="text-ink-soft">Suspended</span>
              <span className="font-semibold text-ink">{suspended}</span>
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}
