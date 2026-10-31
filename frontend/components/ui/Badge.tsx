export type BadgeTone = "neutral" | "success" | "warning" | "caution" | "danger" | "brand";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-surface-elevated text-ink-soft",
  success: "bg-success-100 text-success-600",
  warning: "bg-warning-100 text-warning-600",
  caution: "bg-caution-100 text-caution-600",
  danger: "bg-danger-100 text-danger-600",
  brand: "bg-brand-50 text-accent",
};

/** A small status pill - used for record status, approval state, and
 * reconciliation outcomes throughout the app. Color conveys meaning
 * consistently: green = good/approved, amber = pending, orange = needs a
 * look, red = a real problem, blue = primary/active - never decorative. */
export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, BadgeTone> = {
  pending: "warning",
  awaiting_approval: "warning",
  pending_unload: "warning",
  open: "brand",
  closed: "warning",
  approved: "success",
  rejected: "danger",
  reversed: "neutral",
};

/** Maps this app's own backend status strings to a consistent badge tone,
 * so "approved" always reads as green everywhere it appears. */
export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return <Badge tone={tone}>{status.replace(/_/g, " ")}</Badge>;
}
