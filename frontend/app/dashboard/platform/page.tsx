"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Building2, CheckCircle2, Fuel, ShieldAlert, Sparkles, Users } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/Card";
import { StatCard, StatCardGrid } from "@/components/ui/StatCard";
import { Badge } from "@/components/ui/Badge";
import { OrgGrowthChart, type OrgGrowthPoint } from "@/components/charts/OrgGrowthChart";
import { OrgStatusSplitBar } from "@/components/charts/OrgStatusSplitBar";
import { StationBarChart } from "@/components/charts/StationBarChart";
import type { AuditLogEntry, PlatformOrganizationRow, PlatformStats } from "@/lib/types";

function buildGrowthSeries(orgs: PlatformOrganizationRow[]): OrgGrowthPoint[] {
  // Real history, not a fabricated trend: bucket each organization's own
  // created_at by month, sort chronologically, then run a cumulative sum -
  // "organizations onboarded by this point in time," exactly reproducible
  // from the same rows /platform/organizations itself returns.
  const byMonth = new Map<string, number>();
  for (const org of orgs) {
    const d = new Date(org.created_at);
    const key = `${d.toLocaleString("en-US", { month: "short" })} ${d.getFullYear()}`;
    byMonth.set(key, (byMonth.get(key) ?? 0) + 1);
  }
  const sorted = [...orgs].map((o) => new Date(o.created_at)).sort((a, b) => a.getTime() - b.getTime());
  const orderedMonths: string[] = [];
  const seen = new Set<string>();
  for (const d of sorted) {
    const key = `${d.toLocaleString("en-US", { month: "short" })} ${d.getFullYear()}`;
    if (!seen.has(key)) {
      seen.add(key);
      orderedMonths.push(key);
    }
  }
  let cumulative = 0;
  return orderedMonths.map((month) => {
    cumulative += byMonth.get(month) ?? 0;
    return { month, cumulative };
  });
}

/** Platform Admin overview - every number and chart here is computed from
 * GET /platform/stats and GET /platform/organizations, both real
 * COUNT(*)/row data against the actual tables (see
 * backend/app/api/platform.py), never a fabricated figure or trend. */
export default function PlatformOverviewPage() {
  const { authFetch } = useAuth();
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [orgs, setOrgs] = useState<PlatformOrganizationRow[] | null>(null);
  const [activity, setActivity] = useState<AuditLogEntry[] | null>(null);

  const load = useCallback(async () => {
    const [statsResp, orgsResp, activityResp] = await Promise.all([
      authFetch("/platform/stats"),
      authFetch("/platform/organizations"),
      authFetch("/platform/audit-log?limit=10"),
    ]);
    if (statsResp.ok) setStats(await statsResp.json());
    if (orgsResp.ok) setOrgs(await orgsResp.json());
    if (activityResp.ok) setActivity(await activityResp.json());
  }, [authFetch]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const growthSeries = orgs ? buildGrowthSeries(orgs) : [];
  const topByStations = orgs
    ? [...orgs]
        .sort((a, b) => b.station_count - a.station_count)
        .slice(0, 8)
        .map((o) => ({ label: o.name, value: o.station_count }))
    : [];
  const totalStations = orgs ? orgs.reduce((sum, o) => sum + o.station_count, 0) : 0;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-brand-500/10 via-surface to-surface p-6">
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-500/20 bg-brand-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-brand-400">
              <Sparkles className="h-3 w-3" aria-hidden />
              Platform Admin
            </span>
            <h1 className="mt-2 text-2xl font-bold text-ink">Platform overview</h1>
            <p className="mt-1 text-sm text-ink-soft">Every petrol pump organization on PetroNiq, at a glance.</p>
          </div>
          {stats && (
            <span className="text-xs text-ink-faint">
              Updated {new Date(stats.generated_at).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {stats && (
        <StatCardGrid>
          <StatCard icon={Building2} label="Total organizations" value={stats.total_organizations} tone="brand" />
          <StatCard icon={CheckCircle2} label="Active" value={stats.active_organizations} tone="success" />
          <StatCard
            icon={ShieldAlert}
            label="Suspended"
            value={stats.suspended_organizations}
            tone={stats.suspended_organizations > 0 ? "warning" : "neutral"}
          />
          <StatCard icon={Users} label="Tenant owners" value={stats.total_owners} tone="brand" subtitle={`${stats.total_users} total users`} />
        </StatCardGrid>
      )}

      {orgs && (
        <StatCardGrid>
          <StatCard icon={Fuel} label="Stations, platform-wide" value={totalStations} tone="brand" />
          <StatCard
            icon={Building2}
            label="Avg. stations per org"
            value={orgs.length > 0 ? (totalStations / orgs.length).toFixed(1) : "0"}
            tone="neutral"
          />
          <StatCard
            icon={Users}
            label="Employees, platform-wide"
            value={orgs.reduce((sum, o) => sum + o.employee_count, 0)}
            tone="neutral"
          />
          <StatCard
            icon={Activity}
            label="Orgs active in last 7 days"
            value={
              orgs.filter(
                (o) => o.last_activity_at && Date.now() - new Date(o.last_activity_at).getTime() < 7 * 24 * 60 * 60 * 1000
              ).length
            }
            tone="success"
          />
        </StatCardGrid>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <OrgGrowthChart data={growthSeries} />
        {stats && <OrgStatusSplitBar active={stats.active_organizations} suspended={stats.suspended_organizations} />}
      </div>

      {topByStations.length > 0 && (
        <StationBarChart title="Organizations by station count" valueLabel="Stations" data={topByStations} formatValue={(v) => String(v)} />
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
                <li key={a.id} className="flex items-start gap-2.5 py-2.5">
                  <Activity className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-ink-faint" aria-hidden />
                  <div className="min-w-0">
                    <p className="text-sm text-ink">{a.action.replace(/_/g, " ")}</p>
                    <p className="text-xs text-ink-faint">{new Date(a.created_at).toLocaleString()}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
