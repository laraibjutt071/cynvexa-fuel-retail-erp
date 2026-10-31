/**
 * `Date.prototype.toISOString()` always converts to UTC, so
 * `new Date().toISOString().slice(0, 10)` silently returns the *UTC*
 * calendar date, not the viewer's own local one - wrong by a day for
 * anyone west or east of UTC near midnight (e.g. a station in Pakistan,
 * UTC+5, where "today" in UTC can already be local tomorrow in the
 * evening, or still local yesterday just after midnight). Station
 * operators read and pick dates in their own local time, not UTC, so
 * every "today"/date-picker default in this app must go through this
 * helper instead of toISOString() directly.
 */
export function localDateIso(date: Date = new Date()): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 10);
}

export function localDateDaysAgoIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return localDateIso(d);
}

/**
 * "Today" for a STATION's business day must be the station's own
 * configured timezone (Station.timezone, matched by the backend's own
 * business_date filter in app/api/shifts.py::list_shifts) - not the
 * viewer's browser timezone. An owner checking in from a different city
 * should still see the station's business day, and a shift created at
 * the station right now must land on the date this returns, not drift a
 * day either way depending on where the browser happens to be.
 */
export function stationDateIso(timezone: string, date: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  } catch {
    // An invalid/unrecognized timezone string falls back to UTC, the
    // same fallback app/api/shifts.py uses server-side for the same
    // reason - never crash the page over a bad config value.
    return date.toISOString().slice(0, 10);
  }
}
