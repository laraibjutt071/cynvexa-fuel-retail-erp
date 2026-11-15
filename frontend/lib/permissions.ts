"use client";

import { useCallback, useMemo } from "react";
import { useAuth } from "./auth-context";

/**
 * One canonical permission-resolution rule, used everywhere a page or nav
 * item needs to know "can this user do X here" - previously duplicated
 * (and subtly inconsistent: AppShell.tsx filtered by station, the org
 * dashboard page did not) across AppShell.tsx and individual pages.
 *
 * A permission is held for this org/station if the signed-in user has an
 * org-wide role in `orgId` (station_id === null) or a role scoped to
 * exactly `stationId`. A superuser bypasses every check, matching the
 * backend's own `require_permission` (app/api/deps.py) - the frontend
 * must never be stricter or looser than that boundary, only mirror it for
 * UX. The backend remains the real security boundary regardless of what
 * this hook decides to show.
 */
export function usePermissions(orgId?: string, stationId?: string | null) {
  const { user, loading } = useAuth();
  const isSuperuser = user?.is_superuser ?? false;

  const permissionCodes = useMemo(() => {
    const set = new Set<string>();
    for (const role of user?.station_roles ?? []) {
      if (orgId && role.organization_id !== orgId) continue;
      if (stationId && role.station_id !== null && role.station_id !== stationId) continue;
      role.permissions.forEach((p) => set.add(p));
    }
    return set;
  }, [user, orgId, stationId]);

  const roleName = useMemo(() => {
    for (const role of user?.station_roles ?? []) {
      if (orgId && role.organization_id !== orgId) continue;
      if (stationId && role.station_id !== null && role.station_id !== stationId) continue;
      return role.role_name;
    }
    return isSuperuser ? "Platform Admin" : null;
  }, [user, orgId, stationId, isSuperuser]);

  const can = useCallback(
    (codes: string | string[]): boolean => {
      // Never assume permission while auth/session state is still
      // resolving - a flash of a button the user can't actually use (or a
      // denial that's about to flip to allowed) is worse than a brief
      // "nothing yet". Callers that need a loading state of their own
      // should check `loading` separately.
      if (loading) return false;
      if (isSuperuser) return true;
      const list = Array.isArray(codes) ? codes : [codes];
      return list.some((c) => permissionCodes.has(c));
    },
    [loading, isSuperuser, permissionCodes]
  );

  return { can, loading, isSuperuser, roleName, permissionCodes };
}
