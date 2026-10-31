"use client";

import { localDateDaysAgoIso } from "@/lib/date";

export function defaultDateRange(): { dateFrom: string; dateTo: string } {
  return { dateFrom: localDateDaysAgoIso(30), dateTo: localDateDaysAgoIso(0) };
}

export function DateRangeFilter({
  dateFrom,
  dateTo,
  onChange,
}: {
  dateFrom: string;
  dateTo: string;
  onChange: (next: { dateFrom: string; dateTo: string }) => void;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <label className="flex items-center gap-1.5 text-ink-soft">
        From
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onChange({ dateFrom: e.target.value, dateTo })}
          className="rounded-md border border-border bg-surface-muted px-2 py-1 text-sm text-ink"
        />
      </label>
      <label className="flex items-center gap-1.5 text-ink-soft">
        To
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onChange({ dateFrom, dateTo: e.target.value })}
          className="rounded-md border border-border bg-surface-muted px-2 py-1 text-sm text-ink"
        />
      </label>
    </div>
  );
}
