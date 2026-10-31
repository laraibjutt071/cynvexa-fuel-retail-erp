"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TankVarianceReportRow } from "@/lib/types";
import { Card } from "@/components/Card";
import { axisTickStyle, chartColors, tooltipStyle } from "./theme";

/** Closing variance percent per shift date, from the already-fetched
 * tank-variance report rows - a neutral trend, never labeled as theft or
 * fraud (see docs/ASSUMPTIONS.md on variance framing). */
export function VarianceTrendChart({ rows, title }: { rows: TankVarianceReportRow[]; title: string }) {
  const data = rows
    .filter((r) => r.closing_variance_percent !== null)
    .map((r) => ({
      date: r.shift_date,
      tank: r.tank_code,
      variance: Number(r.closing_variance_percent),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  if (data.length === 0) return null;

  return (
    <Card title={title} description="A neutral trend of book-vs-physical variance - not a judgment about its cause.">
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={chartColors.border} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} />
            <YAxis tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} width={48} unit="%" />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value, _name, item) => [`${Number(value).toFixed(2)}%`, `Tank ${item.payload.tank}`]}
            />
            <Line type="monotone" dataKey="variance" stroke={chartColors.accent} strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
