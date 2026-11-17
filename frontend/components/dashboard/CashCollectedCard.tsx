import { useLanguage } from "@/lib/i18n/context";
import type { PaymentMethodSlice } from "@/components/charts/PaymentMethodBreakdownChart";

export function CashCollectedCard({ data, total }: { data: PaymentMethodSlice[]; total: number }) {
  const { t } = useLanguage();

  return (
    <section className="card-glow rounded-xl bg-surface p-6">
      <h2 className="text-base font-semibold text-ink">{t("today.cashCollected")}</h2>

      {data.length === 0 ? (
        <div className="mt-6 rounded-lg border border-dashed border-border py-10 text-center">
          <p className="text-sm text-ink-soft">{t("today.noCashCollected")}</p>
        </div>
      ) : (
        <div className="mt-4 space-y-2.5">
          {data.map((slice) => {
            const pct = total > 0 ? (slice.amount / total) * 100 : 0;
            return (
              <div key={slice.label} className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
                <span className="text-sm text-ink">{slice.label}</span>
                <span className="flex items-baseline gap-2">
                  <span className="text-sm font-semibold tabular-nums text-ink">{slice.amount.toFixed(2)}</span>
                  <span className="text-xs tabular-nums text-ink-faint">{pct.toFixed(1)}%</span>
                </span>
              </div>
            );
          })}
          <div className="flex items-center justify-between pt-1 text-sm">
            <span className="font-medium text-ink-soft">Total</span>
            <span className="font-semibold tabular-nums text-ink">{total.toFixed(2)}</span>
          </div>
        </div>
      )}
    </section>
  );
}
