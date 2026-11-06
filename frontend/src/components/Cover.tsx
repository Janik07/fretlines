import { useMemo } from "react";

import { coverShape } from "../lib/cover";

/** Обложка разбора: абстрактная чёрно-белая волна, своя у каждой песни. */
export function Cover({ seed, peaks, className = "" }: { seed: string; peaks: number[]; className?: string }) {
  const shape = useMemo(() => coverShape(seed, peaks), [seed, peaks]);
  const gradient = `cover-${seed.slice(0, 8)}`;
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" aria-hidden="true" className={className}>
      <defs>
        <radialGradient id={gradient} cx="70%" cy="20%" r="85%">
          <stop offset="0" stopColor="var(--surface-3)" />
          <stop offset="1" stopColor="var(--surface)" />
        </radialGradient>
      </defs>
      <rect width="100" height="100" fill={`url(#${gradient})`} />
      <g transform={`rotate(${shape.tilt.toFixed(2)} 50 50)`}>
        {shape.style === "rings" &&
          shape.rings.map((ring) => (
            <circle
              key={ring.r}
              cx="50"
              cy={shape.horizon}
              r={ring.r}
              fill="none"
              stroke="var(--accent)"
              strokeOpacity={ring.opacity}
              strokeWidth="0.6"
            />
          ))}
        {shape.style === "lines" &&
          shape.bars.map((bar, i) => (
            <line
              key={bar.x}
              x1="-10"
              x2="110"
              y1={20 + i * 1.4 + bar.height * 6}
              y2={20 + i * 1.4 - bar.height * 6}
              stroke="var(--accent)"
              strokeOpacity={0.12 + bar.height * 0.6}
              strokeWidth="0.35"
            />
          ))}
        {shape.bars.map((bar) => (
          <line
            key={`b${String(bar.x)}`}
            x1={bar.x}
            x2={bar.x}
            y1={shape.horizon - bar.height * 22}
            y2={shape.horizon + bar.height * 22}
            stroke="var(--accent)"
            strokeWidth={shape.style === "bars" ? 1.1 : 0.5}
            strokeLinecap="round"
            strokeOpacity={shape.style === "bars" ? 0.85 : 0.55}
          />
        ))}
      </g>
    </svg>
  );
}
