/** A single tank's fill-level gauge - current book stock against physical
 * capacity, color-coded by level. Real-world fuel-retail dashboards lead
 * with this view (tank levels at a glance) rather than a plain number
 * table. Book stock only, never a live sensor reading - see Tank's own
 * docs in ARCHITECTURE.md on why physical dips are a separate fact. */
export function TankGauge({
  code,
  gradeName,
  stockLitres,
  capacityLitres,
  daysRemaining,
  daysRemainingLabel,
}: {
  code: string;
  gradeName: string;
  stockLitres: number;
  capacityLitres: number;
  daysRemaining?: number | null;
  daysRemainingLabel?: string;
}) {
  const percent = capacityLitres > 0 ? Math.min(100, Math.max(0, (stockLitres / capacityLitres) * 100)) : 0;
  const tone = percent < 20 ? "danger" : percent < 40 ? "warning" : "success";
  const barColor = tone === "danger" ? "bg-danger-600" : tone === "warning" ? "bg-warning-600" : "bg-success-600";
  const textColor = tone === "danger" ? "text-danger-600" : tone === "warning" ? "text-warning-600" : "text-success-600";

  return (
    <div className="card-glow rounded-xl bg-surface p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-ink">
            Tank {code} <span className="text-ink-faint">· {gradeName}</span>
          </p>
        </div>
        <span className={`text-sm font-bold ${textColor}`}>{percent.toFixed(0)}%</span>
      </div>
      <div className="mt-3 h-3 w-full overflow-hidden rounded-full bg-surface-elevated">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-ink-soft">
        <span>{stockLitres.toLocaleString()} L</span>
        <span>{capacityLitres.toLocaleString()} L capacity</span>
      </div>
      {daysRemaining != null && daysRemainingLabel && (
        <p className="mt-2 text-xs text-ink-faint">
          ~{daysRemaining.toFixed(1)} {daysRemainingLabel}
        </p>
      )}
    </div>
  );
}
