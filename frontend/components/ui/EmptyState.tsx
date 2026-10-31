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
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface-muted/50 px-6 py-10 text-center">
      <Icon className="h-8 w-8 text-ink-faint" aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="max-w-sm text-sm text-ink-soft">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
