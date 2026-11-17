import { useLanguage } from "@/lib/i18n/context";

export interface KpiItem {
  label: string;
  value: string | null;
}

/** Minimal label-over-big-number tiles, deliberately plainer than
 * StatCard (no icon/color chip) - used for the "financial snapshot"
 * strip. `value: null` renders an em dash, same convention as the
 * rest of the app for "not loaded yet," never a fabricated zero. */
export function KpiStrip({ items }: { items: KpiItem[] }) {
  const { t } = useLanguage();
  return (
    <section className="card-glow rounded-xl bg-surface p-6">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-semibold text-ink">{t("today.financialSnapshot")}</h2>
        <span className="rounded-full border border-border bg-surface-elevated px-2 py-0.5 text-[11px] font-semibold text-ink-faint">
          partial
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {items.map((item) => (
          <div key={item.label}>
            <p className="text-xs text-ink-faint">{item.label}</p>
            <p className="mt-1.5 text-xl font-semibold tabular-nums text-ink">
              {item.value === null ? <span className="text-ink-faint">—</span> : item.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
