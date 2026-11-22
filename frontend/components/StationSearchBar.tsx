"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { useAccessibleStations } from "@/lib/station-scope";

/**
 * Quick station search, shown top-center above the page content on every
 * authenticated screen. Filters the same authorized station list the
 * sidebar's StationSwitcher already uses (never the organization's full
 * list) and navigates to the chosen station's own dashboard route -
 * same security posture as StationSwitcher: this is a navigation
 * convenience, the backend re-validates access on the page it leads to.
 */
export function StationSearchBar({ orgId }: { orgId: string }) {
  const router = useRouter();
  const { loading, stations } = useAccessibleStations(orgId);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return stations;
    return stations.filter(
      (s) => s.name.toLowerCase().includes(q) || s.code.toLowerCase().includes(q)
    );
  }, [stations, query]);

  function goToStation(stationId: string) {
    setQuery("");
    setOpen(false);
    router.push(`/dashboard/org/${orgId}/station/${stationId}/today`);
  }

  if (loading || stations.length === 0) return null;

  return (
    <div ref={containerRef} className="relative w-full max-w-md">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" aria-hidden />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            // Delay so a click on a dropdown option registers before it closes.
            setTimeout(() => setOpen(false), 150);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && matches.length > 0) {
              goToStation(matches[0].id);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          placeholder="Search stations…"
          aria-label="Search stations"
          className="w-full rounded-full border border-border bg-surface-muted py-2 pl-9 pr-4 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
        />
      </div>

      {open && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-64 overflow-auto rounded-lg border border-border bg-surface shadow-lg">
          {matches.length === 0 ? (
            <p className="px-4 py-3 text-sm text-ink-faint">No stations match &quot;{query}&quot;.</p>
          ) : (
            matches.map((s) => (
              <button
                key={s.id}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => goToStation(s.id)}
                className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-ink hover:bg-surface-elevated"
              >
                <span className="font-medium">{s.name}</span>
                <span className="font-mono text-xs text-ink-faint">{s.code}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
