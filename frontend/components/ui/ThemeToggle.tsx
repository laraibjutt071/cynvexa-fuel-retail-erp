"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme-context";

/** Full-width row button matching the sidebar's other utility buttons
 * (language switch, sign out) - used in AppShell only. Not present on
 * the login page by design. */
export function ThemeToggleRow() {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === "light";

  return (
    <button
      onClick={toggleTheme}
      className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium text-ink-soft hover:bg-surface-elevated hover:text-ink"
      aria-label={isLight ? "Switch to dark theme" : "Switch to light theme"}
    >
      {isLight ? <Sun className="h-4.5 w-4.5" aria-hidden /> : <Moon className="h-4.5 w-4.5" aria-hidden />}
      {isLight ? "Light mode" : "Dark mode"}
      <span className="ml-auto rounded-full bg-brand-50 px-1.5 py-0.5 text-xs font-semibold text-accent">
        {isLight ? "ON" : "OFF"}
      </span>
    </button>
  );
}

/** Compact icon-only variant for tight spaces (mobile header). */
export function ThemeToggleIcon() {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === "light";

  return (
    <button
      onClick={toggleTheme}
      className="rounded-md p-2 text-ink-soft hover:bg-surface-elevated hover:text-ink"
      aria-label={isLight ? "Switch to dark theme" : "Switch to light theme"}
    >
      {isLight ? <Sun className="h-5 w-5" aria-hidden /> : <Moon className="h-5 w-5" aria-hidden />}
    </button>
  );
}
