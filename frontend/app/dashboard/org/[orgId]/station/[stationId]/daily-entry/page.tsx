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
import { ProgressSteps } from "@/components/ui/ProgressSteps";
import { ConfirmDialog } from "@/components/ui/Dialog";
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

/**
 * Real completion, not "the tab was opened" - see Phase 5 Step 3 and
 * docs/PHASE_5_DAILY_ENTRY_AUDIT.md. Readings count as done only once the
 * shift has actually been closed (the backend already refuses to close a
 * shift with any reading missing); Cash counts as done only once a
 * reconciliation record genuinely exists; Review counts as done only once
 * the shift is approved. Sales and Expenses have no defined "finished"
 * state of their own in this business process (entries can be added at
 * any point before cash closing) - they only read as complete once the
 * whole day is approved, matching ReviewSection's own checklist, which
 * never requires a minimum number of sales/expense entries either.
 */
function dailyEntryCompletedSteps(shift: Shift | null | "loading", reconciliationExists: boolean): Set<number> {
  const done = new Set<number>();
  if (shift === "loading" || shift === null) return done;
  if (shift.status !== "open") done.add(0); // readings
  if (reconciliationExists) done.add(3); // cash
  if (shift.status === "approved") {
    done.add(1); // sales
    done.add(2); // expenses
    done.add(4); // review
  }
  return done;
}

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
  // Whether a reconciliation record exists for this shift - the real
  // signal that the Cash step is actually finished, not just opened.
  // Fetched once here (not just inside CashSection) so the progress
  // indicator can reflect genuine completion, per Phase 5 Step 3.
  const [reconciliationExists, setReconciliationExists] = useState(false);
  const requestedSection = searchParams.get("section") as Section | null;
  const [section, setSection] = useState<Section>(requestedSection ?? "readings");
  // Whether the currently-open section has typed-but-unsaved input - each
  // section reports this up via onDirtyChange so we can warn before it's
  // silently lost (switching tabs unmounts the inactive section; see
  // docs/PHASE_5_DAILY_ENTRY_AUDIT.md). Not a real autosave - nothing is
  // persisted here, this only stops the user from losing it by accident.
  const [isDirty, setIsDirty] = useState(false);
  const [pendingSection, setPendingSection] = useState<Section | null>(null);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (!isDirty) return;
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  function requestSectionChange(next: Section) {
    if (isDirty && next !== section) {
      setPendingSection(next);
      return;
    }
    setSection(next);
  }

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
    const current = rows.length > 0 ? rows[0] : null;
    setShift(current);
    if (current) {
      const reconResp = await authFetch(`${shiftsBase}/${current.id}/reconciliation`);
      setReconciliationExists(reconResp.ok);
    } else {
      setReconciliationExists(false);
    }
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

          <ProgressSteps
            steps={SECTIONS.map((s) => ({ label: t(s.labelKey) }))}
            currentStep={SECTIONS.findIndex((s) => s.id === section)}
            completedSteps={dailyEntryCompletedSteps(shift, reconciliationExists)}
          />

          <div className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-surface p-1" role="tablist">
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              return (
                <button
                  key={s.id}
                  role="tab"
                  aria-selected={section === s.id}
                  onClick={() => requestSectionChange(s.id)}
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
              <ReadingsSection orgId={orgId} stationId={stationId} shift={shift} authFetch={authFetch} onShiftChanged={loadShift} onDirtyChange={setIsDirty} />
            )}
            {section === "sales" && (
              <SalesSection orgId={orgId} stationId={stationId} shift={shift} authFetch={authFetch} onDirtyChange={setIsDirty} />
            )}
            {section === "expenses" && (
              <ExpensesSection orgId={orgId} stationId={stationId} businessDate={businessDate} authFetch={authFetch} onDirtyChange={setIsDirty} />
            )}
            {section === "cash" && (
              <CashSection orgId={orgId} stationId={stationId} shift={shift} authFetch={authFetch} onShiftChanged={loadShift} onDirtyChange={setIsDirty} />
            )}
            {section === "review" && (
              <ReviewSection
                orgId={orgId}
                stationId={stationId}
                shift={shift}
                businessDate={businessDate}
                authFetch={authFetch}
                onShiftChanged={loadShift}
                goToSection={(s) => requestSectionChange(s)}
              />
            )}
          </div>
        </>
      )}

      <ConfirmDialog
        open={pendingSection !== null}
        onClose={() => setPendingSection(null)}
        onConfirm={() => {
          setIsDirty(false);
          setSection(pendingSection!);
          setPendingSection(null);
        }}
        title="Leave without saving?"
        description="You've typed a value in this step that hasn't been saved yet. Switching tabs will lose it. Save it first, or continue and lose it."
        confirmLabel="Continue without saving"
        confirmVariant="danger"
      />
    </div>
  );
}
