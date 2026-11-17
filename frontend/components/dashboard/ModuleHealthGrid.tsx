import Link from "next/link";
import { useLanguage } from "@/lib/i18n/context";

export interface ModuleHealthItem {
  key: string;
  label: string;
  count: number;
  href: string;
}

function statusTone(count: number): { badge: string; dot: string } {
  if (count === 0) return { badge: "border-success-100 bg-success-50 text-success-600", dot: "bg-success-600" };
  if (count <= 2) return { badge: "border-warning-100 bg-warning-50 text-warning-600", dot: "bg-warning-600" };
  return { badge: "border-danger-100 bg-danger-50 text-danger-600", dot: "bg-danger-600" };
}

/** One status card per operational area, each backed by a real count
 * from PendingApprovalsReport - never a fabricated health score. Zero
 * open items reads as OK; any non-zero count is flagged for attention,
 * more severely as the count grows. */
export function ModuleHealthGrid({ items }: { items: ModuleHealthItem[] }) {
  const { t } = useLanguage();

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-base font-semibold text-ink">{t("today.moduleHealth")}</h2>
        <span className="rounded-full border border-border bg-surface-elevated px-2 py-0.5 text-[11px] font-semibold text-ink-faint">
          partial
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {items.map((item) => {
          const tone = statusTone(item.count);
          const content = (
            <div className="card-glow h-full rounded-xl bg-surface p-4">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
                  <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} aria-hidden />
                  {item.label}
                </span>
                <span className={`rounded-full border px-1.5 py-0.5 text-[10px] font-bold ${tone.badge}`}>
                  {item.count === 0 ? t("today.statusOk") : t("today.statusAttention")}
                </span>
              </div>
              <p className="mt-3 text-xl font-semibold tabular-nums text-ink">{item.count}</p>
              <p className="text-[11px] text-ink-faint">{t("today.actionQueueOpen")}</p>
            </div>
          );
          return item.count > 0 ? (
            <Link key={item.key} href={item.href} className="block">
              {content}
            </Link>
          ) : (
            <div key={item.key}>{content}</div>
          );
        })}
      </div>
    </section>
  );
}
