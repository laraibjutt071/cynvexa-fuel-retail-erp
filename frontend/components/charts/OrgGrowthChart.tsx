"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors, chartAxisTickStyle, chartTooltipStyle } from "@/lib/useChartColors";
import { Card } from "@/components/Card";

export interface OrgGrowthPoint {
  month: string;
  cumulative: number;
}

/** Cumulative organizations onboarded, by month - computed client-side from
 * the real /platform/organizations list's own created_at values (never a
 * fabricated trend). A single series, so no legend is needed - the title
 * and axis already name what's plotted. */
export function OrgGrowthChart({ data }: { data: OrgGrowthPoint[] }) {
  const c = useChartColors();

  return (
    <Card title="Organizations onboarded over time" description="Cumulative count of fuel retail organizations on the platform.">
      {data.length < 2 ? (
        <p className="py-10 text-center text-sm text-ink-soft">Not enough history yet to chart a trend.</p>
      ) : (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="orgGrowthFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={c.brand} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={c.brand} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="month" tick={chartAxisTickStyle(c)} axisLine={{ stroke: c.border }} tickLine={false} />
              <YAxis
                allowDecimals={false}
                tick={chartAxisTickStyle(c)}
                axisLine={false}
                tickLine={false}
                width={32}
              />
              <Tooltip contentStyle={chartTooltipStyle(c)} formatter={(value) => [value, "Organizations"]} />
              <Area
                type="monotone"
                dataKey="cumulative"
                stroke={c.brand}
                strokeWidth={2}
                fill="url(#orgGrowthFill)"
                dot={{ r: 3, fill: c.brand, strokeWidth: 0 }}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
