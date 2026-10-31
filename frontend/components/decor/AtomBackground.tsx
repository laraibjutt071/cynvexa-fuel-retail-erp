/** A glowing nucleus, five orbiting electrons at varied tilts/speeds, and
 * expanding radiation rings - pure CSS (see globals.css's .atom-decor
 * rules), no randomness, so it renders identically on the server and
 * client and never causes a hydration mismatch. Purely decorative:
 * aria-hidden, no interactive content. */
export function AtomBackground({ className = "" }: { className?: string }) {
  return (
    <div className={`atom-decor ${className}`} aria-hidden="true">
      <div className="orbit orbit-1" />
      <div className="orbit orbit-2" />
      <div className="orbit orbit-3" />
      <div className="orbit orbit-4" />
      <div className="orbit orbit-5" />
      <div className="radiate" />
      <div className="radiate r2" />
      <div className="radiate r3" />
      <div className="nucleus" />
    </div>
  );
}
