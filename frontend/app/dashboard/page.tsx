"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";
import type { Organization, Station } from "@/lib/types";

const DASHBOARD_PERMISSIONS = [
  "report:read",
  "audit:read",
  "supplier_ledger:read",
  "credit_collection:read",
  "expense:read",
  "inventory_item:read",
];

function hasDashboardAccess(permissions: string[]): boolean {
  return DASHBOARD_PERMISSIONS.some((p) => permissions.includes(p));
}

interface OrgCardData {
  organization: Organization | null;
  roleName: string;
  stationId: string | null;
  permissions: string[];
  stations: Station[];
}

export default function DashboardPage() {
  const { user, loading, logout, authFetch } = useAuth();
  const router = useRouter();
  const [orgCards, setOrgCards] = useState<Record<string, OrgCardData>>({});
  const [newOrgName, setNewOrgName] = useState("");
  const [orgError, setOrgError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const loadData = useCallback(async () => {
    if (!user) return;
    const cards: Record<string, OrgCardData> = {};
    for (const role of user.station_roles) {
      cards[role.organization_id] = {
        organization: null,
        roleName: role.role_name,
        stationId: role.station_id,
        permissions: role.permissions,
        stations: [],
      };
    }

    await Promise.all(
      Object.entries(cards).map(async ([orgId, card]) => {
        try {
          const orgResp = await authFetch(`/organizations/${orgId}`);
          if (orgResp.ok) card.organization = await orgResp.json();
        } catch {
          // Leave organization as null; the card still renders the role info.
        }
        if (card.permissions.includes("station:read")) {
          try {
            const stationsResp = await authFetch(`/organizations/${orgId}/stations`);
            if (stationsResp.ok) card.stations = await stationsResp.json();
          } catch {
            // Non-fatal: station list simply stays empty.
          }
        }
      })
    );

    setOrgCards(cards);
  }, [user, authFetch]);

  useEffect(() => {
    // Intentional client-side refetch when the signed-in user changes -
    // there is no server component here to pass this authenticated data
    // down as initial props, since the access token lives only in memory.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
  }, [loadData]);

  const [redirectChecked, setRedirectChecked] = useState(false);
  useEffect(() => {
    // An ordinary single-station petrol pump owner should never have to
    // pick from a list of one - skip straight to their station's
    // dashboard. A superuser, or anyone with more than one org/station,
    // still sees the picker below (there's a real choice to make).
    if (redirectChecked || user?.is_superuser || Object.keys(orgCards).length === 0) return;
    const entries = Object.entries(orgCards);
    if (entries.length === 1) {
      const [orgId, card] = entries[0];
      if (hasDashboardAccess(card.permissions) && card.stations.length === 1) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setRedirectChecked(true);
        router.replace(`/dashboard/org/${orgId}/station/${card.stations[0].id}/today`);
        return;
      }
    }
    setRedirectChecked(true);
  }, [orgCards, user, router, redirectChecked]);

  async function handleCreateOrganization(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOrgError(null);
    try {
      const resp = await authFetch("/organizations", {
        method: "POST",
        body: JSON.stringify({ name: newOrgName }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Failed to create organization." }));
        throw new ApiError(resp.status, body.detail ?? "Failed to create organization.");
      }
      setNewOrgName("");
      await loadData();
    } catch (err) {
      setOrgError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  if (loading || !user) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-ink-soft">Loading…</p>
      </main>
    );
  }

  return (
    <main className="flex-1">
      <header className="border-b border-border bg-surface px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-ink">CYNVEXA Fuel Retail ERP</h1>
            <p className="text-sm text-ink-soft">
              {user.full_name} &middot; {user.email}
              {user.is_superuser && " · Platform Admin"}
            </p>
          </div>
          <button
            onClick={() => logout().then(() => router.replace("/login"))}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-elevated"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        {user.is_superuser && (
          <section className="rounded-xl border border-border bg-surface p-6">
            <h2 className="text-sm font-semibold text-ink">Create organization</h2>
            <p className="mt-1 text-sm text-ink-soft">
              Platform-admin action: onboards a new fuel retail organization.
            </p>
            <form onSubmit={handleCreateOrganization} className="mt-4 flex gap-2">
              <input
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
                placeholder="Organization name"
                required
                className="flex-1 rounded-md border border-border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                type="submit"
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
              >
                Create
              </button>
            </form>
            {orgError && <p className="mt-2 text-sm text-danger-600">{orgError}</p>}
          </section>
        )}

        {Object.keys(orgCards).length === 0 && !user.is_superuser && (
          <p className="text-sm text-ink-soft">
            You do not have a role in any organization yet. Ask an administrator to assign one.
          </p>
        )}

        {Object.entries(orgCards).map(([orgId, card]) => (
          <section key={orgId} className="rounded-xl border border-border bg-surface p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-ink">
                {card.organization?.name ?? "Organization"}
              </h2>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-500">
                  {card.roleName}
                  {card.stationId ? " · station-scoped" : " · org-wide"}
                </span>
                {hasDashboardAccess(card.permissions) && (
                  <Link
                    href={`/dashboard/org/${orgId}`}
                    className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-ink hover:bg-surface-elevated"
                  >
                    Org dashboard →
                  </Link>
                )}
              </div>
            </div>

            {card.permissions.includes("station:read") ? (
              <div className="mt-4">
                <h3 className="text-sm font-medium text-ink">Stations</h3>
                {card.stations.length === 0 ? (
                  <p className="mt-1 text-sm text-ink-soft">No stations configured yet.</p>
                ) : (
                  <ul className="mt-2 divide-y divide-border">
                    {card.stations.map((s) => (
                      <li key={s.id} className="flex items-center justify-between py-2 text-sm">
                        <span className="text-ink">
                          {s.name} <span className="text-ink-soft">{s.code}</span>
                        </span>
                        {hasDashboardAccess(card.permissions) && (
                          <Link
                            href={`/dashboard/org/${orgId}/station/${s.id}`}
                            className="text-xs font-medium text-brand-500 hover:underline"
                          >
                            Station dashboard →
                          </Link>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="mt-4 text-sm text-ink-soft">
                This role does not include station visibility.
              </p>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
