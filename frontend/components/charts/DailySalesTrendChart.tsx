"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors, chartAxisTickStyle, chartTooltipStyle } from "@/lib/useChartColors";
import { formatMoney } from "@/lib/format";
import type { OrgDailySalesDay } from "@/lib/types";

/** Daily expected-revenue trend across every authorized station, from the
 * live GET .../reports/daily-sales endpoint - never computed here. Every
 * day in the requested range is a real data point, including zero days
 * (the backend zero-fills gaps rather than omitting them), so a flat
 * stretch reads as "no approved sales," not a rendering gap. */
export function DailySalesTrendChart({ days }: { days: OrgDailySalesDay[] }) {
  const c = useChartColors();
  const hasData = days.some((d) => Number(d.expected_revenue) > 0);

  const data = days.map((d) => ({
    date: d.sales_date,
    label: new Date(`${d.sales_date}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    revenue: Number(d.expected_revenue),
    litres: Number(d.litres_sold),
  }));

  if (!hasData) {
    return <p className="py-6 text-center text-sm text-ink-soft">No approved sales in this range yet.</p>;
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="dailySalesFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={c.brand} stopOpacity={0.35} />
              <stop offset="100%" stopColor={c.brand} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            tick={chartAxisTickStyle(c)}
            axisLine={{ stroke: c.border }}
            tickLine={false}
            interval={data.length > 14 ? Math.ceil(data.length / 10) : 0}
          />
          <YAxis
            tick={chartAxisTickStyle(c)}
            axisLine={{ stroke: c.border }}
            tickLine={false}
            width={64}
            tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v))}
          />
          <Tooltip
            contentStyle={chartTooltipStyle(c)}
            formatter={(value, name) =>
              name === "revenue"
                ? [`PKR ${formatMoney(Number(value))}`, "Expected revenue"]
                : [`${Number(value).toFixed(0)} L`, "Litres sold"]
            }
            labelFormatter={(label) => label}
          />
          <Area type="monotone" dataKey="revenue" stroke={c.brand} strokeWidth={2} fill="url(#dailySalesFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
