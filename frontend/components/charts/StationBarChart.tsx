"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors, chartAxisTickStyle, chartTooltipStyle } from "@/lib/useChartColors";
import { Card } from "@/components/Card";

export interface StationBarDatum {
  label: string;
  value: number;
}

/** One bar per station for a single metric (litres sold, expected revenue,
 * approved expenses, ...) - used by the Phase 8c station-comparison view.
 * Kept to one metric per chart rather than a grouped multi-series bar so
 * each one stays readable with a small station count on a phone-width
 * screen; the underlying figures all come from the same Phase 8b
 * station-performance endpoint, this never computes its own. */
export function StationBarChart({
  data,
  title,
  valueLabel,
  formatValue,
}: {
  data: StationBarDatum[];
  title: string;
  valueLabel: string;
  formatValue?: (value: number) => string;
}) {
  const c = useChartColors();
  const hasData = data.some((d) => d.value > 0);

  return (
    <Card title={title}>
      {!hasData ? (
        <p className="py-6 text-center text-sm text-ink-soft">No data in this range yet.</p>
      ) : (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="label"
                tick={chartAxisTickStyle(c)}
                axisLine={{ stroke: c.border }}
                tickLine={false}
                interval={0}
                angle={data.length > 4 ? -20 : 0}
                textAnchor={data.length > 4 ? "end" : "middle"}
                height={data.length > 4 ? 48 : 24}
              />
              <YAxis tick={chartAxisTickStyle(c)} axisLine={{ stroke: c.border }} tickLine={false} width={56} />
              <Tooltip
                contentStyle={chartTooltipStyle(c)}
                formatter={(value) => [formatValue ? formatValue(Number(value)) : Number(value).toFixed(2), valueLabel]}
              />
              <Bar dataKey="value" fill={c.brand} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
