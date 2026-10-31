"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Expense } from "@/lib/types";
import { Card } from "@/components/Card";
import { chartSeriesColors, tooltipStyle } from "./theme";

/** Groups the already-fetched expense list by category client-side - no
 * separate aggregation endpoint exists for this yet (see
 * docs/UX_UPGRADE_PLAN.md Stage 4), so this reads only real records
 * already on screen, never a fabricated total. */
export function ExpenseBreakdownChart({ expenses, title }: { expenses: Expense[]; title: string }) {
  const byCategory = new Map<string, number>();
  for (const expense of expenses) {
    if (expense.status === "rejected" || expense.reversed_at) continue;
    byCategory.set(expense.category, (byCategory.get(expense.category) ?? 0) + Number(expense.amount));
  }
  const data = Array.from(byCategory, ([category, amount]) => ({ category, amount }));
  if (data.length === 0) return null;

  return (
    <Card title={title}>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="amount" nameKey="category" cx="50%" cy="50%" outerRadius={75}>
              {data.map((entry, i) => (
                <Cell key={entry.category} fill={chartSeriesColors[i % chartSeriesColors.length]} />
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
