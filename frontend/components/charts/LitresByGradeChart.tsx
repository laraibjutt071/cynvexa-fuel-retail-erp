"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailyFuelSalesGradeRow } from "@/lib/types";
import { Card } from "@/components/Card";
import { axisTickStyle, chartColors, tooltipStyle } from "./theme";

/** Litres sold per fuel grade for a single day - from the real
 * daily-fuel-sales report response already fetched by the page. */
export function LitresByGradeChart({ grades, title }: { grades: DailyFuelSalesGradeRow[]; title: string }) {
  const data = grades.map((g) => ({
    grade: g.fuel_grade_name,
    litres: Number(g.litres_sold),
  }));

  return (
    <Card title={title}>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={chartColors.border} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="grade" tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} />
            <YAxis tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} width={48} />
            <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${Number(value).toFixed(2)} L`, "Litres sold"]} />
            <Bar dataKey="litres" fill={chartColors.accent} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
