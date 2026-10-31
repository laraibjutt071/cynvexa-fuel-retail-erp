/**
 * recharts needs literal color values (SVG fill/stroke), not Tailwind
 * classes - these mirror the tokens in app/globals.css by hand. If the
 * palette there changes, update these too.
 */
export const chartColors = {
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

export const chartSeriesColors = [
  chartColors.brand,
  chartColors.accent,
  chartColors.success,
  chartColors.warning,
  chartColors.caution,
  chartColors.danger,
];

export const tooltipStyle = {
  backgroundColor: chartColors.surfaceElevated,
  border: `1px solid ${chartColors.border}`,
  borderRadius: 8,
  color: chartColors.ink,
  fontSize: 12,
};

export const axisTickStyle = { fill: chartColors.inkFaint, fontSize: 11 };
