"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Building2, CheckCircle2, ShieldAlert, Users } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/Card";
import { StatCard, StatCardGrid } from "@/components/ui/StatCard";
import { Badge } from "@/components/ui/Badge";
import type { AuditLogEntry, PlatformStats } from "@/lib/types";

/** Platform Admin overview - every number here comes from GET
 * /platform/stats, which is itself a real COUNT(*) against the actual
 * tables (see backend/app/api/platform.py::platform_stats), never a
 * fabricated figure. */
export default function PlatformOverviewPage() {
  const { authFetch } = useAuth();
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [activity, setActivity] = useState<AuditLogEntry[] | null>(null);

  const load = useCallback(async () => {
    const [statsResp, activityResp] = await Promise.all([
      authFetch("/platform/stats"),
      authFetch("/platform/audit-log?limit=10"),
    ]);
    if (statsResp.ok) setStats(await statsResp.json());
    if (activityResp.ok) setActivity(await activityResp.json());
  }, [authFetch]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div>
        <h1 className="text-xl font-semibold text-ink">Platform overview</h1>
        <p className="mt-1 text-sm text-ink-soft">Every petrol pump organization on CYNVEXA, at a glance.</p>
      </div>

      {stats && (
        <StatCardGrid>
          <StatCard icon={Building2} label="Total organizations" value={stats.total_organizations} tone="brand" />
          <StatCard icon={CheckCircle2} label="Active" value={stats.active_organizations} tone="success" />
          <StatCard icon={ShieldAlert} label="Suspended" value={stats.suspended_organizations} tone={stats.suspended_organizations > 0 ? "warning" : "neutral"} />
          <StatCard icon={Users} label="Tenant owners" value={stats.total_owners} tone="brand" subtitle={`${stats.total_users} total users`} />
        </StatCardGrid>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Recently created organizations">
          {!stats ? (
            <p className="text-sm text-ink-soft">Loading…</p>
          ) : stats.recent_organizations.length === 0 ? (
            <p className="text-sm text-ink-soft">No organizations yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {stats.recent_organizations.map((o) => (
                <li key={o.id} className="flex items-center justify-between py-2.5">
                  <Link href={`/dashboard/platform/organizations/${o.id}`} className="text-sm font-medium text-ink hover:text-accent">
                    {o.name}
                  </Link>
                  <div className="flex items-center gap-2">
                    <Badge tone={o.is_active ? "success" : "danger"}>{o.is_active ? "active" : "suspended"}</Badge>
                    <span className="text-xs text-ink-faint">{new Date(o.created_at).toLocaleDateString()}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent platform activity">
          {!activity ? (
            <p className="text-sm text-ink-soft">Loading…</p>
          ) : activity.length === 0 ? (
            <p className="text-sm text-ink-soft">No activity recorded yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {activity.map((a) => (
                <li key={a.id} className="py-2.5">
                  <p className="text-sm text-ink">{a.action.replace(/_/g, " ")}</p>
                  <p className="text-xs text-ink-faint">{new Date(a.created_at).toLocaleString()}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
