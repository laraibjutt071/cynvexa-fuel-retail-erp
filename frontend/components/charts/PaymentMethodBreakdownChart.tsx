"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card } from "@/components/Card";
import { chartSeriesColors, tooltipStyle } from "./theme";

export interface PaymentMethodSlice {
  label: string;
  amount: number;
}

/** Today's collections grouped by payment-method category - from real,
 * already-fetched tender records, never estimated. */
export function PaymentMethodBreakdownChart({ data, title }: { data: PaymentMethodSlice[]; title: string }) {
  const nonZero = data.filter((d) => d.amount > 0);
  if (nonZero.length === 0) return null;

  return (
    <Card title={title}>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={nonZero} dataKey="amount" nameKey="label" cx="50%" cy="50%" outerRadius={75}>
              {nonZero.map((entry, i) => (
                <Cell key={entry.label} fill={chartSeriesColors[i % chartSeriesColors.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={tooltipStyle} formatter={(value) => Number(value).toFixed(2)} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
