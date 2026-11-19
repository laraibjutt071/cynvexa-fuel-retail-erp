"use client";

import { Building2, ChevronsUpDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAccessibleStations } from "@/lib/station-scope";
import { useOrganizationName } from "@/lib/organization-name";

const ALL_STATIONS_VALUE = "__all__";

/**
 * Persistent station selector (Phase 8c §3): "All Stations" (only when
 * the signed-in user genuinely holds an org-wide grant or, for a
 * superuser, an org-wide support session) plus every individual station
 * they're actually authorized for - never the organization's full station
 * list. Switching never mixes data from two stations: it's a full
 * navigation to that station's (or the organization's) own dashboard
 * route, not a client-side data swap.
 */
export function StationSwitcher({
  orgId,
  currentStationId,
}: {
  orgId: string;
  currentStationId?: string | null;
}) {
  const router = useRouter();
  const orgName = useOrganizationName(orgId);
  const { loading, hasOrgWideAccess, stations } = useAccessibleStations(orgId);

  if (loading) {
    return (
      <div className="px-3 py-2 text-xs text-ink-faint">Loading stations…</div>
    );
  }

  if (!hasOrgWideAccess && stations.length === 0) {
    return null; // nothing this user can switch to - no switcher to show
  }

  const value = currentStationId ?? (hasOrgWideAccess ? ALL_STATIONS_VALUE : stations[0]?.id ?? "");
  const currentLabel =
    value === ALL_STATIONS_VALUE
      ? "All Stations"
      : stations.find((s) => s.id === value)?.name ?? "Select a station";

  function handleChange(next: string) {
    if (next === value) return;
    if (next === ALL_STATIONS_VALUE) {
      router.push(`/dashboard/org/${orgId}/overview`);
    } else {
      router.push(`/dashboard/org/${orgId}/station/${next}/today`);
    }
  }

  return (
    <div className="border-b border-border px-3 py-3">
      {orgName && (
        <p className="truncate px-1 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          {orgName}
        </p>
      )}
      <div className="relative mt-1">
        <Building2
          className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint"
          aria-hidden
        />
        <select
          aria-label="Switch station"
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          className="w-full appearance-none truncate rounded-lg border border-border bg-surface-muted py-2 pl-8 pr-7 text-sm font-medium text-ink focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
        >
          {hasOrgWideAccess && <option value={ALL_STATIONS_VALUE}>All Stations</option>}
          {stations.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <ChevronsUpDown
          className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint"
          aria-hidden
        />
      </div>
      <p className="mt-1 truncate px-1 text-[11px] text-ink-faint">Viewing: {currentLabel}</p>
    </div>
  );
}
