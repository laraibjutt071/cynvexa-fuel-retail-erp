"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useChartColors, chartSeriesColors, chartTooltipStyle } from "@/lib/useChartColors";

export interface DonutSlice {
  label: string;
  value: number;
}

/** A center-labeled donut with a colored-dot legend listing each
 * slice's amount and share of the total - same shape as the reference
 * "cases by status" panel, applied here to revenue by fuel grade. */
export function RevenueDonut({ data, centerLabel, title }: { data: DonutSlice[]; centerLabel: string; title: string }) {
  const c = useChartColors();
  const colors = chartSeriesColors(c);
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <section className="card-glow rounded-xl bg-surface p-6">
      <h2 className="text-base font-semibold text-ink">{title}</h2>

      {data.length === 0 || total === 0 ? (
        <p className="mt-4 text-sm text-ink-soft">No revenue in this range yet.</p>
      ) : (
        <div className="mt-4 flex flex-col items-center gap-6 sm:flex-row">
          <div className="relative h-44 w-44 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="label" innerRadius="68%" outerRadius="100%" paddingAngle={2} isAnimationActive={false}>
                  {data.map((_, i) => (
                    <Cell key={i} fill={colors[i % colors.length]} stroke="none" />
                  ))}
                </Pie>
                <Tooltip contentStyle={chartTooltipStyle(c)} formatter={(v) => Number(v).toFixed(2)} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-lg font-bold text-ink">{total.toFixed(0)}</span>
              <span className="text-[11px] text-ink-faint">{centerLabel}</span>
            </div>
          </div>
          <ul className="w-full flex-1 space-y-2">
            {data.map((d, i) => (
              <li key={d.label} className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-ink">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: colors[i % colors.length] }} />
                  {d.label}
                </span>
                <span className="flex items-baseline gap-2">
                  <span className="font-semibold tabular-nums text-ink">{d.value.toFixed(2)}</span>
                  <span className="text-xs tabular-nums text-ink-faint">{((d.value / total) * 100).toFixed(1)}%</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
