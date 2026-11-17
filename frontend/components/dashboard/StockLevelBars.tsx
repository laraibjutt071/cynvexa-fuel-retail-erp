import { useLanguage } from "@/lib/i18n/context";

export interface StockLevelRow {
  code: string;
  gradeName: string;
  stockLitres: number;
  capacityLitres: number;
}

function tierColor(pct: number): { bar: string; text: string } {
  if (pct >= 60) return { bar: "bg-success-600", text: "text-success-600" };
  if (pct >= 30) return { bar: "bg-warning-600", text: "text-warning-600" };
  if (pct >= 15) return { bar: "bg-caution-600", text: "text-caution-600" };
  return { bar: "bg-danger-600", text: "text-danger-600" };
}

/** Horizontal fill-level bars, one per tank - the same "proportional
 * bar + amount + percent" layout used for aging/breakdown panels
 * elsewhere, applied here to book stock vs. tank capacity. */
export function StockLevelBars({ rows }: { rows: StockLevelRow[] }) {
  const { t } = useLanguage();
  const totalStock = rows.reduce((sum, r) => sum + r.stockLitres, 0);
  const totalCapacity = rows.reduce((sum, r) => sum + r.capacityLitres, 0);

  return (
    <section className="card-glow rounded-xl bg-surface p-6">
      <h2 className="text-base font-semibold text-ink">{t("today.stockLevels")}</h2>

      {rows.length === 0 ? (
        <p className="mt-4 text-sm text-ink-soft">{t("today.noTanks")}</p>
      ) : (
        <>
          <div className="mt-4 space-y-3.5">
            {rows.map((row) => {
              const pct = row.capacityLitres > 0 ? (row.stockLitres / row.capacityLitres) * 100 : 0;
              const { bar, text } = tierColor(pct);
              return (
                <div key={row.code}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-medium text-ink">
                      {row.code} · {row.gradeName}
                    </span>
                    <span className={`font-semibold tabular-nums ${text}`}>{pct.toFixed(0)}%</span>
                  </div>
                  <div className="h-2.5 w-full overflow-hidden rounded-full bg-surface-muted">
                    <div
                      className={`h-full rounded-full ${bar}`}
                      style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-ink-faint">
                    {row.stockLitres.toLocaleString()} L / {row.capacityLitres.toLocaleString()} L
                  </p>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex items-center gap-4 border-t border-border pt-3 text-xs text-ink-faint">
            <span>
              Total stock: <span className="font-semibold text-ink">{totalStock.toLocaleString()} L</span>
            </span>
            <span>
              Total capacity: <span className="font-semibold text-ink">{totalCapacity.toLocaleString()} L</span>
            </span>
          </div>
        </>
      )}
    </section>
  );
}
