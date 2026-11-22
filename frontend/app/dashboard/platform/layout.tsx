"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { Building2, CreditCard, LayoutDashboard, LogOut, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggleRow } from "@/components/ui/ThemeToggle";

/** The platform admin's own navigation shell - deliberately separate from
 * the tenant AppShell (components/AppShell.tsx), which has no concept of
 * "every organization" and is scoped to one orgId/stationId in its route.
 * Every page under here must only ever be reachable by a real superuser -
 * enforced again per-page via each page's own data fetch (every endpoint
 * they call is require_superuser-gated server-side), this layout's guard
 * is the UX-only first line, not the security boundary. */
export default function PlatformLayout({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && (!user || !user.is_superuser)) router.replace("/dashboard");
  }, [loading, user, router]);

  if (loading || !user?.is_superuser) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-ink-soft">Loading…</p>
      </main>
    );
  }

  const nav = [
    { href: "/dashboard/platform", label: "Overview", icon: LayoutDashboard },
    { href: "/dashboard/platform/organizations", label: "Organizations", icon: Building2 },
    { href: "/dashboard/platform/plans", label: "Plans", icon: CreditCard },
  ];

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden w-64 flex-shrink-0 flex-col border-r border-border bg-sidebar lg:flex">
        <div className="px-5 py-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 text-white shadow-lg shadow-brand-500/20">
              <ShieldCheck className="h-4.5 w-4.5" aria-hidden />
            </div>
            <div className="min-w-0">
              <span className="block text-sm font-bold text-ink">PetroNiq</span>
              <span className="block truncate text-xs text-ink-faint">Platform Admin</span>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {nav.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  active ? "bg-brand-50 text-accent" : "text-ink-soft hover:bg-surface-elevated hover:text-ink"
                }`}
              >
                <Icon className="h-4.5 w-4.5 flex-shrink-0" aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border px-3 py-2">
          <Link
            href="/dashboard"
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-ink-soft hover:bg-surface-elevated hover:text-ink"
          >
            ← Back to my organizations
          </Link>
          <ThemeToggleRow />
        </div>
        <div className="border-t border-border px-3 py-3">
          <div className="flex items-center gap-3 px-3">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-400">
              {(user.full_name ?? "A").charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">{user.full_name}</p>
              <p className="truncate text-xs text-ink-faint">{user.email}</p>
            </div>
            <button
              onClick={() => logout().then(() => router.replace("/login"))}
              className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-elevated hover:text-ink"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      </aside>

      <header className="flex items-center justify-between border-b border-border bg-sidebar px-4 py-3 lg:hidden">
        <span className="text-sm font-semibold text-ink">PetroNiq Platform Admin</span>
      </header>

      <div className="flex min-w-0 flex-1 flex-col">
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
