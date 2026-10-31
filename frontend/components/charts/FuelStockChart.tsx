"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Tank } from "@/lib/types";
import { Card } from "@/components/Card";
import { axisTickStyle, chartColors, tooltipStyle } from "./theme";

/** Real book stock per tank, read directly from the already-fetched tanks
 * list - no separate fetch, no fabricated figures. */
export function FuelStockChart({ tanks, title }: { tanks: Tank[]; title: string }) {
  const data = tanks.map((tank) => ({
    tank: tank.code,
    stock: Number(tank.book_stock),
  }));

  return (
    <Card title={title}>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={chartColors.border} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="tank" tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} />
            <YAxis tick={axisTickStyle} axisLine={{ stroke: chartColors.border }} tickLine={false} width={48} />
            <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${Number(value).toFixed(0)} L`, "Book stock"]} />
            <Bar dataKey="stock" fill={chartColors.brand} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
