"use client";

import { useEffect, useState } from "react";
import { useAuth } from "./auth-context";
import { useActiveSupportSession } from "./support-session";
import type { Station } from "./types";

export interface AccessibleStationsResult {
  loading: boolean;
  /** True only for a real org-wide grant (a UserStationRole with
   * station_id null) or, for a superuser, an org-wide support session -
   * never true just because every individual station happens to be
   * listed below. Drives whether "All Stations" is offered at all (Phase
   * 8c §3: "only for authorized organization-wide users"). */
  hasOrgWideAccess: boolean;
  /** Every station this signed-in user may actually switch to - derived
   * from their own server-issued role grants (Me.station_roles) or, for a
   * superuser, their active support session's own scope. Never the
   * organization's full station list filtered after the fact: a
   * station-scoped viewer never even sees an unauthorized station's name
   * here. The backend re-validates every one of these on the page it
   * leads to regardless - this is a navigation convenience, not the
   * security boundary. */
  stations: Station[];
}

/** Which stations the signed-in user may switch the dashboard to, for the
 * persistent station switcher (Phase 8c §3). */
export function useAccessibleStations(orgId: string | undefined): AccessibleStationsResult {
  const { user, authFetch } = useAuth();
  const supportSession = useActiveSupportSession();
  const [allStations, setAllStations] = useState<Station[] | null>(null);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    (async () => {
      const resp = await authFetch(`/organizations/${orgId}/stations`);
      if (!cancelled && resp.ok) setAllStations(await resp.json());
    })();
    return () => {
      cancelled = true;
    };
  }, [authFetch, orgId]);

  const isSuperuser = user?.is_superuser ?? false;

  if (!orgId) return { loading: true, hasOrgWideAccess: false, stations: [] };

  let hasOrgWideAccess = false;
  let allowedStationIds: Set<string> | null = null; // null = every station in the org

  if (isSuperuser) {
    if (supportSession === undefined) {
      return { loading: true, hasOrgWideAccess: false, stations: [] };
    }
    if (supportSession?.status === "active" && supportSession.organization_id === orgId) {
      if (supportSession.station_id === null) {
        hasOrgWideAccess = true;
      } else {
        allowedStationIds = new Set([supportSession.station_id]);
      }
    } else {
      allowedStationIds = new Set(); // no active session for this org - no access at all
    }
  } else {
    const myRoles = (user?.station_roles ?? []).filter((r) => r.organization_id === orgId);
    if (myRoles.some((r) => r.station_id === null)) {
      hasOrgWideAccess = true;
    } else {
      allowedStationIds = new Set(myRoles.map((r) => r.station_id).filter((id): id is string => id !== null));
    }
  }

  const stations = (allStations ?? []).filter(
    (s) => allowedStationIds === null || allowedStationIds.has(s.id)
  );

  return { loading: allStations === null, hasOrgWideAccess, stations };
}
