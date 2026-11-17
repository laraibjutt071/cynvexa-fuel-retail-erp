"use client";

import { useEffect, useState } from "react";
import { useTheme } from "@/lib/theme-context";

export interface ChartColors {
  brand: string;
  accent: string;
  success: string;
  warning: string;
  caution: string;
  danger: string;
  ink: string;
  inkSoft: string;
  inkFaint: string;
  border: string;
  surface: string;
  surfaceElevated: string;
}

// Dark-theme values, used only as the initial render before the client
// effect below reads the real CSS custom properties - matches the
// long-standing dark default so there's no flash of wrong colors.
const FALLBACK: ChartColors = {
  brand: "#2563eb",
  accent: "#38bdf8",
  success: "#22c55e",
  warning: "#f59e0b",
  caution: "#fb923c",
  danger: "#ef4444",
  ink: "#f8fafc",
  inkSoft: "#94a3b8",
  inkFaint: "#64748b",
  border: "#22304a",
  surface: "#111c30",
  surfaceElevated: "#17243a",
};

function readFromDom(): ChartColors {
  const style = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    brand: v("--color-brand-500", FALLBACK.brand),
    accent: v("--color-accent", FALLBACK.accent),
    success: v("--color-success-600", FALLBACK.success),
    warning: v("--color-warning-600", FALLBACK.warning),
    caution: v("--color-caution-600", FALLBACK.caution),
    danger: v("--color-danger-600", FALLBACK.danger),
    ink: v("--color-ink", FALLBACK.ink),
    inkSoft: v("--color-ink-soft", FALLBACK.inkSoft),
    inkFaint: v("--color-ink-faint", FALLBACK.inkFaint),
    border: v("--color-border", FALLBACK.border),
    surface: v("--color-surface", FALLBACK.surface),
    surfaceElevated: v("--color-surface-elevated", FALLBACK.surfaceElevated),
  };
}

/** recharts needs literal SVG color values, not Tailwind classes or CSS
 * vars, so this reads the actual computed --color-* custom properties
 * (app/globals.css) and re-reads them whenever the theme toggles, so
 * every chart built on this hook renders correctly in both themes
 * without hardcoding two palettes by hand. */
export function useChartColors(): ChartColors {
  const { theme } = useTheme();
  const [colors, setColors] = useState<ChartColors>(FALLBACK);

  useEffect(() => {
    setColors(readFromDom());
  }, [theme]);

  return colors;
}

export function chartSeriesColors(c: ChartColors): string[] {
  return [c.brand, c.accent, c.success, c.warning, c.caution, c.danger];
}

export function chartTooltipStyle(c: ChartColors) {
  return {
    backgroundColor: c.surfaceElevated,
    border: `1px solid ${c.border}`,
    borderRadius: 8,
    color: c.ink,
    fontSize: 12,
  };
}

export function chartAxisTickStyle(c: ChartColors) {
  return { fill: c.inkFaint, fontSize: 11 };
}
