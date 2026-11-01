"use client";

import {
  AlertTriangle,
  BarChart3,
  Banknote,
  CheckSquare,
  ClipboardList,
  CreditCard,
  Fuel,
  Gauge,
  Languages,
  LayoutDashboard,
  LogOut,
  Menu,
  Receipt,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Truck,
  Wallet,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useParams, useRouter } from "next/navigation";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import type { TranslationKey } from "@/lib/i18n/translations";

interface NavItem {
  labelKey: TranslationKey;
  href: string;
  icon: typeof LayoutDashboard;
  /** At least one of these permissions must be held (org-wide or at the
   * current station) for the item to show - real backend permission
   * codes, never a frontend-only guess at who "should" see something. */
  anyPermission: string[];
  /** True if the item needs a station in context (disabled/hidden with
   * no station selected rather than linking to a broken page). */
  needsStation?: boolean;
}

function buildNav(orgId: string, stationId: string | null): NavItem[] {
  const station = stationId ?? "";
  return [
    {
      labelKey: "nav.dashboard",
      href: `/dashboard/org/${orgId}/station/${station}/today`,
      icon: LayoutDashboard,
      anyPermission: ["report:read", "shift:read"],
      needsStation: true,
    },
    {
      labelKey: "nav.dailyEntry",
      href: `/dashboard/org/${orgId}/station/${station}/daily-entry`,
      icon: ClipboardList,
      anyPermission: ["shift:open", "shift:close", "shift_reconcile:record"],
      needsStation: true,
    },
    {
      labelKey: "nav.fuelStock",
      href: `/dashboard/org/${orgId}/station/${station}?tab=variance`,
      icon: Fuel,
      anyPermission: ["report:read"],
      needsStation: true,
    },
    {
      labelKey: "nav.pumpReadings",
      href: `/dashboard/org/${orgId}/station/${station}/daily-entry?section=readings`,
      icon: Gauge,
      anyPermission: ["shift:open", "shift:close"],
      needsStation: true,
    },
    {
      labelKey: "nav.salesCollections",
      href: `/dashboard/org/${orgId}/station/${station}/daily-entry?section=sales`,
      icon: Wallet,
      anyPermission: ["shift_reconcile:record"],
      needsStation: true,
    },
    {
      labelKey: "nav.expenses",
      href: `/dashboard/org/${orgId}?tab=expenses`,
      icon: Receipt,
      anyPermission: ["expense:read"],
    },
    {
      labelKey: "nav.cashBank",
      href: `/dashboard/org/${orgId}/station/${station}/daily-entry?section=cash`,
      icon: Banknote,
      anyPermission: ["shift_reconcile:record", "shift_reconcile:approve"],
      needsStation: true,
    },
    {
      labelKey: "nav.creditSales",
      href: `/dashboard/org/${orgId}?tab=credit`,
      icon: CreditCard,
      anyPermission: ["credit_collection:read"],
    },
    {
      labelKey: "nav.purchases",
      href: `/dashboard/org/${orgId}/station/${station}/purchases`,
      icon: Truck,
      anyPermission: ["fuel_receipt:read"],
      needsStation: true,
    },
    {
      labelKey: "nav.reconciliation",
      href: `/dashboard/org/${orgId}/station/${station}?tab=reconciliation`,
      icon: ShoppingCart,
      anyPermission: ["report:read"],
      needsStation: true,
    },
    {
      labelKey: "nav.reports",
      href: `/dashboard/org/${orgId}/station/${station}?tab=sales`,
      icon: BarChart3,
      anyPermission: ["report:read"],
      needsStation: true,
    },
    {
      labelKey: "nav.approvals",
      href: `/dashboard/org/${orgId}?tab=overview`,
      icon: CheckSquare,
      anyPermission: ["report:read"],
    },
    {
      labelKey: "nav.alerts",
      href: `/dashboard/org/${orgId}?tab=overview`,
      icon: AlertTriangle,
      anyPermission: ["report:read"],
    },
    {
      labelKey: "nav.auditHistory",
      href: `/dashboard/org/${orgId}?tab=audit`,
      icon: Settings,
      anyPermission: ["audit:read"],
    },
  ];
}

export function AppShell({ children }: { children: ReactNode }) {
  const { orgId, stationId } = useParams<{ orgId: string; stationId?: string }>();
  const { user, logout } = useAuth();
  const { language, setLanguage, t } = useLanguage();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isSuperuser = user?.is_superuser ?? false;
  const permissions = useMemo(() => {
    const perms = new Set<string>();
    for (const role of user?.station_roles ?? []) {
      if (role.organization_id === orgId && (!stationId || role.station_id === null || role.station_id === stationId)) {
        role.permissions.forEach((p) => perms.add(p));
      }
    }
    return perms;
  }, [user, orgId, stationId]);
  const can = useCallback(
    (codes: string[]) => isSuperuser || codes.some((c) => permissions.has(c)),
    [isSuperuser, permissions]
  );

  const nav = buildNav(orgId, stationId ?? null).filter(
    (item) => can(item.anyPermission) && (!item.needsStation || stationId)
  );

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/login");
  }, [logout, router]);

  const sidebarContent = (
    <>
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-white">
          <Fuel className="h-4.5 w-4.5" aria-hidden />
        </div>
        <span className="text-base font-semibold text-ink">CYNVEXA</span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
        {nav.map((item) => {
          const active = pathname === item.href.split("?")[0];
          const Icon = item.icon;
          return (
            <Link
              key={item.labelKey}
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active ? "bg-brand-50 text-accent" : "text-ink-soft hover:bg-surface-elevated hover:text-ink"
              }`}
            >
              <Icon className="h-4.5 w-4.5 flex-shrink-0" aria-hidden />
              {t(item.labelKey)}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border px-3 py-3">
        <button
          onClick={() => setLanguage(language === "en" ? "ur" : "en")}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-ink-soft hover:bg-surface-elevated hover:text-ink"
          aria-label="Switch language"
        >
          <Languages className="h-4.5 w-4.5" aria-hidden />
          {t("common.language")}
          <span className="ml-auto rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-accent">
            {language === "en" ? "EN" : "UR"}
          </span>
        </button>
        {isSuperuser && (
          <Link
            href="/dashboard/platform"
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-ink-soft hover:bg-surface-elevated hover:text-ink"
          >
            <ShieldCheck className="h-4.5 w-4.5" aria-hidden />
            Platform Admin
          </Link>
        )}
        {can(["user:read"]) && (
          <Link
            href={`/dashboard/org/${orgId}/settings`}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-ink-soft hover:bg-surface-elevated hover:text-ink"
          >
            <Settings className="h-4.5 w-4.5" aria-hidden />
            {t("nav.usersSettings")}
          </Link>
        )}
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-ink-soft hover:bg-surface-elevated hover:text-ink"
        >
          <LogOut className="h-4.5 w-4.5" aria-hidden />
          {t("nav.signOut")}
        </button>
      </div>
    </>
  );

  return (
    <div className="flex min-h-screen bg-background">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 flex-shrink-0 flex-col border-r border-border bg-sidebar lg:flex">
        {sidebarContent}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 animate-slide-in-left flex-col bg-sidebar shadow-xl">
            <button
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-4 rounded-md p-1.5 text-ink-soft hover:bg-surface-elevated"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            {sidebarContent}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-sidebar px-4 py-3 lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="rounded-md p-2 text-ink-soft hover:bg-surface-elevated"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-sm font-semibold text-ink">CYNVEXA</span>
          <span className="w-9" />
        </header>
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
