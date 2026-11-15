import type { LucideIcon } from "lucide-react";
import { TrendingDown, TrendingUp } from "lucide-react";

type Tone = "neutral" | "success" | "warning" | "danger" | "brand";

const ICON_BG: Record<Tone, string> = {
  neutral: "bg-surface-elevated text-ink-soft",
  success: "bg-success-50 text-success-600",
  warning: "bg-warning-50 text-warning-600",
  danger: "bg-danger-50 text-danger-600",
  brand: "bg-brand-50 text-brand-400",
};

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone?: Tone;
  trend?: { value: string; direction: "up" | "down" };
  subtitle?: string;
}

export function StatCard({ label, value, icon: Icon, tone = "neutral", trend, subtitle }: StatCardProps) {
  return (
    <div className="card-glow flex items-start gap-4 rounded-xl bg-surface p-5">
      <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg ${ICON_BG[tone]}`}>
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-ink-soft">{label}</p>
        <p className="mt-0.5 text-2xl font-semibold text-ink">{value}</p>
        {(trend || subtitle) && (
          <div className="mt-1 flex items-center gap-2">
            {trend && (
              <span
                className={`inline-flex items-center gap-0.5 text-xs font-medium ${
                  trend.direction === "up" ? "text-success-600" : "text-danger-600"
                }`}
              >
                {trend.direction === "up" ? (
                  <TrendingUp className="h-3 w-3" aria-hidden />
                ) : (
                  <TrendingDown className="h-3 w-3" aria-hidden />
                )}
                {trend.value}
              </span>
            )}
            {subtitle && <span className="text-xs text-ink-faint">{subtitle}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export function StatCardGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{children}</div>;
}
