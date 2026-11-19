"use client";

import { useEffect, useState } from "react";
import { useAuth } from "./auth-context";
import type { SupportSession } from "./types";

/**
 * The signed-in superuser's current active support session (Phase 5b),
 * or `null` if there isn't one / the signed-in user isn't a superuser at
 * all. `undefined` means "not yet known" - callers gating access on this
 * must treat that as "not yet known", not as "no session", or a
 * permission could flash on then off once the real answer arrives.
 *
 * Never fetched for an ordinary (non-superuser) user - this is Phase 5b's
 * own boundary, not a general-purpose permissions fetch.
 */
export function useActiveSupportSession(): SupportSession | null | undefined {
  const { user, authFetch } = useAuth();
  const isSuperuser = user?.is_superuser ?? false;
  const [session, setSession] = useState<SupportSession | null | undefined>(undefined);

  useEffect(() => {
    if (!isSuperuser) {
      setSession(null);
      return;
    }
    let cancelled = false;
    (async () => {
      const resp = await authFetch("/platform/support-sessions/active");
      const body = resp.ok ? ((await resp.json()) as SupportSession | null) : null;
      if (!cancelled) setSession(body);
    })();
    return () => {
      cancelled = true;
    };
  }, [isSuperuser, authFetch]);

  return isSuperuser ? session : null;
}

/** Mirrors app/core/support_sessions.py::support_session_grants' scope
 * check exactly: a session grants a (organization_id, station_id) target
 * only if the organization matches and, when the session itself is
 * station-scoped, the target station is exactly that one - never a
 * different station, and never an org-wide (station_id null) target. */
export function sessionCoversScope(
  session: SupportSession | null | undefined,
  orgId: string | undefined,
  stationId: string | null | undefined
): boolean {
  if (!session || session.status !== "active") return false;
  if (!orgId || session.organization_id !== orgId) return false;
  if (session.station_id !== null && session.station_id !== stationId) return false;
  return true;
}
