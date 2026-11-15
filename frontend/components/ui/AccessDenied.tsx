import { ShieldAlert } from "lucide-react";

/**
 * Shown when a signed-in user reaches a page they don't hold the
 * permission for - distinct from EmptyState (which means "nothing here
 * yet") and from the auth redirect in individual pages (which means "not
 * signed in at all"). This is a real, named reason the page is blank,
 * never a silent redirect that leaves the user guessing why.
 */
export function AccessDenied({
  message = "Your role does not include access to this page.",
}: {
  message?: string;
}) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-surface-muted/50 px-6 py-12 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-warning-50 text-warning-600">
        <ShieldAlert className="h-6 w-6" aria-hidden />
      </span>
      <p className="text-base font-semibold text-ink">Access restricted</p>
      <p className="text-sm text-ink-soft">{message}</p>
      <p className="text-xs text-ink-faint">
        If you believe this is wrong, ask your organization owner to review your role.
      </p>
    </div>
  );
}
