import Link from "next/link";
import { useLanguage } from "@/lib/i18n/context";

export interface ActionQueueRow {
  module: string;
  count: number;
  href: string;
}

/** A clean "what needs a human right now" table - every row comes
 * straight from PendingApprovalsReport's real counts, never estimated.
 * Mirrors the station's actual pending-approval state, sorted most
 * urgent (highest count) first. */
export function ActionQueueCard({ rows }: { rows: ActionQueueRow[] }) {
  const { t } = useLanguage();
  const sorted = [...rows].filter((r) => r.count > 0).sort((a, b) => b.count - a.count);
  const totalOpen = sorted.reduce((sum, r) => sum + r.count, 0);

  return (
    <section className="card-glow rounded-xl bg-surface p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-ink">{t("today.actionQueue")}</h2>
          <span className="rounded-full border border-success-100 bg-success-50 px-2 py-0.5 text-[11px] font-semibold text-success-600">
            live
          </span>
        </div>
        <span className="text-xs text-ink-faint">
          {totalOpen} {t("today.actionQueueOpen")}
        </span>
      </div>

      {sorted.length === 0 ? (
        <div className="mt-6 rounded-lg border border-dashed border-border py-10 text-center">
          <p className="text-sm text-ink-soft">{t("today.actionQueueEmpty")}</p>
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-faint">
                <th className="py-2 pr-2 font-medium">Module</th>
                <th className="py-2 pr-2 font-medium">Open</th>
                <th className="py-2 pr-2 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <tr key={row.module} className="border-b border-border/60 last:border-0">
                  <td className="py-2.5 pr-2 text-ink">{row.module}</td>
                  <td className="py-2.5 pr-2 font-semibold tabular-nums text-ink">{row.count}</td>
                  <td className="py-2.5 pr-2 text-right">
                    <Link href={row.href} className="text-accent transition-colors hover:text-brand-400 hover:underline">
                      {t("today.review")} →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
