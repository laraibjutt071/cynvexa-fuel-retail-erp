"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ShiftReconciliationReportRow } from "@/lib/types";
import { Card } from "@/components/Card";
import { axisTickStyle, chartColors, tooltipStyle } from "./theme";

/** Expected vs. actual cash per shift, from the already-fetched
 * shift-reconciliation report rows - the two bars are independently
 * computed figures (see ARCHITECTURE.md's reconciliation rules), never
 * adjusted to force a match. */
export function ReconciliationHistoryChart({ rows, title }: { rows: ShiftReconciliationReportRow[]; title: string }) {
  const data = rows
    .map((r) => ({
      date: new Date(r.opened_at).toLocaleDateString(),
      expected: Number(r.expected_fuel_revenue),
      collected: Number(r.total_tender_amount),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  if (data.length === 0) return null;

  return (
    <Card title={title}>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={chartColors.border} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} />
            <YAxis tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} width={48} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="expected" name="Expected revenue" fill={chartColors.brand} radius={[4, 4, 0, 0]} />
            <Bar dataKey="collected" name="Collected" fill={chartColors.accent} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
