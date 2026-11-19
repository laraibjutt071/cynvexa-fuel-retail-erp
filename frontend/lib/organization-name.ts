"use client";

import { useEffect, useState } from "react";
import { useAuth } from "./auth-context";

/**
 * The organization's display name, for showing "clear organization
 * context" in the shell (Phase 8c §3). Reuses GET /organizations (no
 * permission gate beyond being signed in - it already returns every
 * organization the caller holds any role in, see app/api/organizations.py)
 * rather than GET /organizations/{id}, which requires organization:read -
 * a permission not every seed role holds (e.g. Station Manager), so a
 * station-scoped user would otherwise 403 just trying to see their own
 * organization's name in the header.
 */
export function useOrganizationName(orgId: string | undefined): string | null {
  const { authFetch } = useAuth();
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    (async () => {
      const resp = await authFetch("/organizations");
      if (cancelled || !resp.ok) return;
      const orgs: { id: string; name: string }[] = await resp.json();
      const match = orgs.find((o) => o.id === orgId);
      if (match) setName(match.name);
    })();
    return () => {
      cancelled = true;
    };
  }, [authFetch, orgId]);

  return name;
}
