"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailyFuelSalesDay } from "@/lib/types";
import { Card } from "@/components/Card";
import { axisTickStyle, chartColors, tooltipStyle } from "./theme";

/** Total litres sold per day across the selected date range - summed from
 * the real per-grade figures already returned by the daily-fuel-sales
 * report, not a separate fetch. */
export function SalesOverTimeChart({ days, title }: { days: DailyFuelSalesDay[]; title: string }) {
  const data = days
    .map((d) => ({
      date: d.sale_date,
      litres: d.grades.reduce((sum, g) => sum + Number(g.litres_sold), 0),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  return (
    <Card title={title}>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={chartColors.border} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} />
            <YAxis tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} width={48} />
            <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${Number(value).toFixed(2)} L`, "Litres sold"]} />
            <Bar dataKey="litres" fill={chartColors.brand} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
