"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useChartColors, chartAxisTickStyle, chartTooltipStyle } from "@/lib/useChartColors";
import { Card } from "@/components/Card";
import type { InventoryItemWithStock } from "@/lib/types";

/** On-hand quantity per item, colored red when below its own reorder
 * level - items carry different units, so this is read as "how each
 * item sits relative to its own threshold," never compared across
 * items by absolute value. */
export function InventoryLevelsChart({ items, title }: { items: InventoryItemWithStock[]; title: string }) {
  const c = useChartColors();
  const data = items.map((it) => ({
    sku: it.sku,
    onHand: Number(it.on_hand),
    reorderLevel: Number(it.reorder_level),
    belowReorder: it.below_reorder_level,
  }));

  return (
    <Card title={title}>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={c.border} vertical={false} />
            <XAxis dataKey="sku" tick={chartAxisTickStyle(c)} axisLine={{ stroke: c.border }} tickLine={false} />
            <YAxis tick={chartAxisTickStyle(c)} axisLine={false} tickLine={false} width={48} />
            <Tooltip
              contentStyle={chartTooltipStyle(c)}
              formatter={(value, name) => [value, name === "onHand" ? "On hand" : "Reorder level"]}
            />
            <Bar dataKey="onHand" radius={[4, 4, 0, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.belowReorder ? c.danger : c.brand} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-ink-faint">
        <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: c.danger }} /> below reorder level ·{" "}
        <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: c.brand }} /> healthy
      </p>
    </Card>
  );
}
