"use client";

import { useEffect, useState } from "react";

interface ParticleSpec {
  id: number;
  left: number;
  top: number;
  size: number;
  duration: number;
  delay: number;
  color: string;
}

const PARTICLE_COLORS = [
  "var(--color-accent)",
  "var(--color-brand-400)",
  "#ffffff",
];

/** Floating background particles, purely decorative. Positions are
 * randomized only after mount (an empty list renders identically on the
 * server and the client, so there is no hydration mismatch) - see
 * docs/UX_UPGRADE_PLAN.md on why this pattern is required for any
 * randomized visual in a server-rendered component. */
export function Particles({ count = 18, className = "" }: { count?: number; className?: string }) {
  const [particles, setParticles] = useState<ParticleSpec[]>([]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setParticles(
      Array.from({ length: count }, (_, id) => ({
        id,
        left: Math.random() * 100,
        top: Math.random() * 100,
        size: 2 + Math.random() * 3,
        duration: 4 + Math.random() * 5,
        delay: Math.random() * -8,
        color: PARTICLE_COLORS[id % PARTICLE_COLORS.length],
      }))
    );
  }, [count]);

  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} aria-hidden="true">
      {particles.map((p) => (
        <span
          key={p.id}
          className="particle"
          style={{
            left: `${p.left}%`,
            top: `${p.top}%`,
            width: `${p.size}px`,
            height: `${p.size}px`,
            background: p.color,
            boxShadow: `0 0 ${p.size * 2}px ${p.color}`,
            animationDuration: `${p.duration}s`,
            animationDelay: `${p.delay}s`,
          }}
        />
      ))}
    </div>
  );
}
