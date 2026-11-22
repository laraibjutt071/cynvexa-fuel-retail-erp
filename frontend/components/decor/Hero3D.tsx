/**
 * A genuinely 3D (perspective + rotate3d + translateZ, not flat `rotate()`)
 * decorative rig for hero/welcome moments only - never placed behind KPI
 * numbers, tables or forms, where depth/motion would fight for attention
 * against real financial data. See the `.hero3d-*` rules in globals.css
 * for why this is pure CSS rather than a WebGL/three.js scene: zero
 * bundle cost, no risk of a canvas failing to initialize, and the app's
 * existing global `prefers-reduced-motion` override (globals.css) already
 * collapses every animation here to one still frame for users who ask
 * for it - no separate reduced-motion branch needed.
 *
 * Each ring gets its own rotation axis/speed/direction/depth via inline
 * CSS custom properties so the keyframes in globals.css stay generic.
 * aria-hidden: purely decorative, never carries content.
 */
export function Hero3D({ className = "" }: { className?: string }) {
  return (
    <div className={`hero3d-scene ${className}`} aria-hidden="true">
      <div className="hero3d-rig">
        <div
          className="hero3d-ring"
          style={
            {
              "--ring-size": "220px",
              "--ring-speed": "13s",
              "--ring-axis-x": 1,
              "--ring-axis-y": 0.3,
              "--ring-depth": "10px",
            } as React.CSSProperties
          }
        />
        <div
          className="hero3d-ring hero3d-ring--accent"
          style={
            {
              "--ring-size": "170px",
              "--ring-speed": "9s",
              "--ring-direction": "reverse",
              "--ring-axis-x": 0.2,
              "--ring-axis-y": 1,
              "--ring-depth": "-14px",
            } as React.CSSProperties
          }
        />
        <div
          className="hero3d-ring"
          style={
            {
              "--ring-size": "260px",
              "--ring-speed": "20s",
              "--ring-axis-x": 0.6,
              "--ring-axis-y": 0.8,
              "--ring-depth": "4px",
            } as React.CSSProperties
          }
        />
        <div className="hero3d-core" />
      </div>
    </div>
  );
}
