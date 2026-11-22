import type { LucideIcon } from "lucide-react";

/** Shown instead of a blank table/list - always explains what the empty
 * state means and, where there's an action, what to do about it. Never
 * just "No data." */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-surface-muted/50 px-6 py-10 text-center">
      {/* Circular icon badge, same treatment as AccessDenied.tsx - a bare
       * icon floating on its own read as an afterthought next to that
       * screen's framed one. */}
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-elevated text-ink-faint">
        <Icon className="h-6 w-6" aria-hidden />
      </span>
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="max-w-sm text-sm text-ink-soft">{description}</p>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
