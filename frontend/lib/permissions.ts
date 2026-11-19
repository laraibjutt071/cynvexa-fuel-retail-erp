"use client";

import { useCallback, useMemo } from "react";
import { useAuth } from "./auth-context";
import { sessionCoversScope, useActiveSupportSession } from "./support-session";

/**
 * One canonical permission-resolution rule, used everywhere a page or nav
 * item needs to know "can this user do X here" - previously duplicated
 * (and subtly inconsistent: AppShell.tsx filtered by station, the org
 * dashboard page did not) across AppShell.tsx and individual pages.
 *
 * A permission is held for this org/station if the signed-in user has an
 * org-wide role in `orgId` (station_id === null) or a role scoped to
 * exactly `stationId`.
 *
 * A superuser is NOT an unconditional bypass here (Phase 5b closed that
 * on the backend; this hook used to still assume it, which Phase 8's
 * audit flagged as stale - see docs/PHASE_8_MULTI_STATION_SAAS_AUDIT.md
 * §4). A superuser only "can" something when they hold an active,
 * scope-matching support session (app/core/support_sessions.py), and
 * even then only for a `:read` permission code - a session never grants
 * a write, so a write-gated control correctly stays hidden regardless of
 * session state. This mirrors the backend exactly; the backend remains
 * the real security boundary regardless of what this hook decides to
 * show.
 */
export function usePermissions(orgId?: string, stationId?: string | null) {
  const { user, loading } = useAuth();
  const isSuperuser = user?.is_superuser ?? false;
  const supportSession = useActiveSupportSession();

  const permissionCodes = useMemo(() => {
    const set = new Set<string>();
    for (const role of user?.station_roles ?? []) {
      if (orgId && role.organization_id !== orgId) continue;
      if (stationId && role.station_id !== null && role.station_id !== stationId) continue;
      role.permissions.forEach((p) => set.add(p));
    }
    return set;
  }, [user, orgId, stationId]);

  const hasMatchingSession = useMemo(
    () => sessionCoversScope(supportSession, orgId, stationId ?? null),
    [supportSession, orgId, stationId]
  );

  const roleName = useMemo(() => {
    for (const role of user?.station_roles ?? []) {
      if (orgId && role.organization_id !== orgId) continue;
      if (stationId && role.station_id !== null && role.station_id !== stationId) continue;
      return role.role_name;
    }
    if (!isSuperuser) return null;
    return hasMatchingSession ? "Platform Admin (support session)" : "Platform Admin";
  }, [user, orgId, stationId, isSuperuser, hasMatchingSession]);

  const can = useCallback(
    (codes: string | string[]): boolean => {
      // Never assume permission while auth/session state is still
      // resolving - a flash of a button the user can't actually use (or a
      // denial that's about to flip to allowed) is worse than a brief
      // "nothing yet". Callers that need a loading state of their own
      // should check `loading` separately.
      if (loading) return false;
      const list = Array.isArray(codes) ? codes : [codes];
      if (isSuperuser) {
        if (supportSession === undefined) return false; // still resolving - don't flash true
        if (!hasMatchingSession) return false;
        return list.some((c) => c.endsWith(":read"));
      }
      return list.some((c) => permissionCodes.has(c));
    },
    [loading, isSuperuser, supportSession, hasMatchingSession, permissionCodes]
  );

  return { can, loading, isSuperuser, roleName, permissionCodes };
}
