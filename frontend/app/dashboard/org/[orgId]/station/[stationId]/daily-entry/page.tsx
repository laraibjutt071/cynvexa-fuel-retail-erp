"use client";

import {
  Banknote,
  ClipboardList,
  Gauge,
  Receipt,
  Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import type { TranslationKey } from "@/lib/i18n/translations";
import { useToast } from "@/components/ui/Toast";
import { stationDateIso } from "@/lib/date";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import type { Shift } from "@/lib/types";
import { ReadingsSection } from "./ReadingsSection";
import { SalesSection } from "./SalesSection";
import { ExpensesSection } from "./ExpensesSection";
import { CashSection } from "./CashSection";
import { ReviewSection } from "./ReviewSection";

export type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

type Section = "readings" | "sales" | "expenses" | "cash" | "review";

const SECTIONS: { id: Section; labelKey: TranslationKey; helpKey: TranslationKey; icon: typeof Gauge }[] = [
  { id: "readings", labelKey: "dailyEntry.section.readings", helpKey: "dailyEntry.help.readings", icon: Gauge },
  { id: "sales", labelKey: "dailyEntry.section.sales", helpKey: "dailyEntry.help.sales", icon: Wallet },
  { id: "expenses", labelKey: "dailyEntry.section.expenses", helpKey: "dailyEntry.help.expenses", icon: Receipt },
  { id: "cash", labelKey: "dailyEntry.section.cash", helpKey: "dailyEntry.help.cash", icon: Banknote },
  { id: "review", labelKey: "dailyEntry.section.review", helpKey: "dailyEntry.help.review", icon: ClipboardList },
];

export default function DailyEntryPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { authFetch } = useAuth();
  const { t } = useLanguage();
  const { notify } = useToast();
  const searchParams = useSearchParams();

  // The station's own configured timezone, not the viewer's browser -
  // "today" must mean the station's business day (see lib/date.ts's own
  // docstring on stationDateIso for why). Defaults to UTC only until the
  // station's real timezone has loaded.
  const [stationTimezone, setStationTimezone] = useState("UTC");
  const [businessDate, setBusinessDate] = useState(() => stationDateIso("UTC"));
  const [shift, setShift] = useState<Shift | null | "loading">("loading");
  const [starting, setStarting] = useState(false);
  const requestedSection = searchParams.get("section") as Section | null;
  const [section, setSection] = useState<Section>(requestedSection ?? "readings");

  const shiftsBase = `/organizations/${orgId}/stations/${stationId}/shifts`;

  useEffect(() => {
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}`);
      if (!resp.ok) return;
      const station: { timezone: string } = await resp.json();
      setStationTimezone(station.timezone);
      setBusinessDate((current) => {
        const stationToday = stationDateIso(station.timezone);
        // Only snap to the station's "today" if the date was still at its
        // UTC-default guess - an explicit pick by the user (via the date
        // input below) is never overwritten once the real timezone loads.
        return current === stationDateIso("UTC") ? stationToday : current;
      });
    })();
  }, [authFetch, orgId, stationId]);

  const loadShift = useCallback(async () => {
    setShift("loading");
    const resp = await authFetch(`${shiftsBase}?business_date=${businessDate}`);
    if (!resp.ok) {
      setShift(null);
      return;
    }
    const rows: Shift[] = await resp.json();
    // One-shift-per-business-day is this workspace's own simplifying
    // convention (the backend supports many shifts a day) - see
    // docs/ASSUMPTIONS.md. If more than one exists for this date (created
    // outside this workspace), the most recently opened one is what
    // "today's entry" means here.
    setShift(rows.length > 0 ? rows[0] : null);
  }, [authFetch, shiftsBase, businessDate]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadShift();
  }, [loadShift]);

  async function startTodaysEntry() {
    setStarting(true);
    try {
      const resp = await authFetch(shiftsBase, {
        method: "POST",
        body: JSON.stringify({ label: `Daily entry — ${businessDate}` }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not start today's entry." }));
        notify("error", body.detail ?? "Could not start today's entry.");
        return;
      }
      notify("success", t("dailyEntry.started"));
      await loadShift();
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">{t("dailyEntry.title")}</h1>
          <p className="mt-1 text-sm text-ink-soft">{t("dailyEntry.subtitle")}</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="font-medium text-ink-soft">{t("dailyEntry.businessDate")}</span>
          <input
            type="date"
            value={businessDate}
            max={stationDateIso(stationTimezone)}
            onChange={(e) => setBusinessDate(e.target.value)}
            className="rounded-lg border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </label>
      </div>

      {shift === "loading" ? (
        <Card title={t("common.loading")}>
          <p className="text-sm text-ink-soft">Checking for an entry on this date…</p>
        </Card>
      ) : shift === null ? (
        <Card title={t("dailyEntry.noEntryYet")}>
          <EmptyState
            icon={ClipboardList}
            title="Nothing recorded for this business date"
            description={
              businessDate === stationDateIso(stationTimezone)
                ? "Start today's entry to begin recording pump readings, sales, expenses and cash closing. Yesterday's closing stock carries forward automatically - nothing to re-enter."
                : t("dailyEntry.pastDateCorrection")
            }
            action={
              businessDate === stationDateIso(stationTimezone) ? (
                <Button onClick={startTodaysEntry} busy={starting}>
                  {t("dailyEntry.startToday")}
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <>
          <Card title={shift.label ?? "Today's entry"}>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <StatusBadge status={shift.status} />
              <span className="text-ink-soft">
                Opened {new Date(shift.opened_at).toLocaleString()}
                {shift.closed_at && ` · Closed ${new Date(shift.closed_at).toLocaleString()}`}
                {shift.approved_at && ` · Approved ${new Date(shift.approved_at).toLocaleString()}`}
              </span>
            </div>
          </Card>

          <DailyEntryProgress sections={SECTIONS} current={section} t={t} />

          <div className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-surface p-1" role="tablist">
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              return (
                <button
                  key={s.id}
                  role="tab"
                  aria-selected={section === s.id}
                  onClick={() => setSection(s.id)}
                  className={`flex flex-shrink-0 items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors ${
                    section === s.id ? "bg-brand-500 text-white" : "text-ink-soft hover:bg-surface-elevated"
                  }`}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {t(s.labelKey)}
                </button>
              );
            })}
          </div>

          <p className="flex items-start gap-2 rounded-lg bg-brand-50 px-3 py-2.5 text-sm text-ink-soft">
            {t(SECTIONS.find((s) => s.id === section)!.helpKey)}
          </p>

          <div>
            {section === "readings" && (
              <ReadingsSection orgId={orgId} stationId={stationId} shift={shift} authFetch={authFetch} onShiftChanged={loadShift} />
            )}
            {section === "sales" && (
              <SalesSection orgId={orgId} stationId={stationId} shift={shift} authFetch={authFetch} />
            )}
            {section === "expenses" && (
              <ExpensesSection orgId={orgId} stationId={stationId} businessDate={businessDate} authFetch={authFetch} />
            )}
            {section === "cash" && (
              <CashSection orgId={orgId} stationId={stationId} shift={shift} authFetch={authFetch} onShiftChanged={loadShift} />
            )}
            {section === "review" && (
              <ReviewSection
                orgId={orgId}
                stationId={stationId}
                shift={shift}
                authFetch={authFetch}
                onShiftChanged={loadShift}
                goToSection={(s) => setSection(s)}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

function DailyEntryProgress({
  sections,
  current,
  t,
}: {
  sections: { id: Section; labelKey: TranslationKey }[];
  current: Section;
  t: (key: TranslationKey) => string;
}) {
  const currentIndex = sections.findIndex((s) => s.id === current);
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-ink-faint">
        {t("dailyEntry.step")} {currentIndex + 1} {t("dailyEntry.of")} {sections.length} ·{" "}
        {t(sections[currentIndex].labelKey)}
      </p>
      <div className="flex gap-1.5">
        {sections.map((s, i) => (
          <div
            key={s.id}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${
              i <= currentIndex ? "bg-brand-500" : "bg-surface-elevated"
            }`}
          />
        ))}
      </div>
    </div>
  );
}
