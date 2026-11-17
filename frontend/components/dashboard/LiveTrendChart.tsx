"use client";

import { Line, LineChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors, chartAxisTickStyle, chartTooltipStyle } from "@/lib/useChartColors";

export interface LiveTrendPoint {
  time: string;
  collected: number;
  litres: number;
}

/** Appends one real point every time the dashboard's own data actually
 * refreshes (see the polling effect in today/page.tsx) - never a
 * simulated/randomized tick. Needs at least 2 points to draw a line, so
 * it shows an honest "collecting live data" state until then rather
 * than a misleading flat or empty chart. */
export function LiveTrendChart({ data }: { data: LiveTrendPoint[] }) {
  const c = useChartColors();
  const series = chartSeriesColorsFor(c);

  return (
    <section className="card-glow rounded-xl bg-surface p-6">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-semibold text-ink">Live activity</h2>
        <span className="flex items-center gap-1 rounded-full border border-success-100 bg-success-50 px-2 py-0.5 text-[11px] font-semibold text-success-600">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success-600" />
          LIVE
        </span>
        <span className="text-xs text-ink-faint">updates automatically as today's figures change</span>
      </div>

      {data.length < 2 ? (
        <div className="mt-4 flex h-48 items-center justify-center rounded-lg border border-dashed border-border">
          <p className="text-sm text-ink-soft">Collecting live data…</p>
        </div>
      ) : (
        <div className="mt-4 h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={c.border} vertical={false} />
              <XAxis dataKey="time" tick={chartAxisTickStyle(c)} axisLine={{ stroke: c.border }} tickLine={false} />
              <YAxis
                yAxisId="collected"
                tick={chartAxisTickStyle(c)}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <YAxis
                yAxisId="litres"
                orientation="right"
                tick={chartAxisTickStyle(c)}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <Tooltip contentStyle={chartTooltipStyle(c)} />
              <Legend wrapperStyle={{ fontSize: 12, color: c.inkSoft }} />
              <Line
                yAxisId="collected"
                type="monotone"
                dataKey="collected"
                name="Cash collected"
                stroke={series[0]}
                strokeWidth={2}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
              <Line
                yAxisId="litres"
                type="monotone"
                dataKey="litres"
                name="Litres sold"
                stroke={series[1]}
                strokeWidth={2}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

function chartSeriesColorsFor(c: ReturnType<typeof useChartColors>) {
  return [c.brand, c.accent];
}
