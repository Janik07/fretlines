import { useMemo } from "react";

const WIDTH = 1200;
const HEIGHT = 160;

/** Синтетическая волна, пока настоящей ещё нет: сумма синусов под огибающей. */
function synthetic(count: number, phase: number): number[] {
  return Array.from({ length: count }, (_, i) => {
    const t = i / count;
    const envelope = Math.sin(Math.PI * t) ** 1.2;
    const signal =
      Math.abs(Math.sin(2 * Math.PI * t * 5.3 + phase)) * 0.5 +
      Math.abs(Math.sin(2 * Math.PI * t * 13.1 + phase * 1.9)) * 0.3 +
      Math.abs(Math.sin(2 * Math.PI * t * 31.7 + phase * 0.7)) * 0.2;
    return 0.06 + envelope * signal * 0.94;
  });
}

function resample(peaks: number[], count: number): number[] {
  if (!peaks.length) return synthetic(count, 0.4);
  return Array.from({ length: count }, (_, i) => {
    const start = Math.floor((i / count) * peaks.length);
    const end = Math.max(start + 1, Math.floor(((i + 1) / count) * peaks.length));
    let top = 0;
    for (let j = start; j < end; j++) top = Math.max(top, peaks[j] ?? 0);
    return top;
  });
}

/**
 * Волна песни зеркальными штрихами. progress (0…1) — сколько уже «пройдено»: эта часть светлее.
 * sweeping — по волне бежит свет (экран обработки, SPEC §2.5).
 */
export function Waveform({
  peaks,
  progress = 1,
  sweeping = false,
  bars = 220,
  className = "",
}: {
  peaks: number[];
  progress?: number;
  sweeping?: boolean;
  bars?: number;
  className?: string;
}) {
  const values = useMemo(() => resample(peaks, bars), [peaks, bars]);
  const step = WIDTH / bars;
  const mid = HEIGHT / 2;
  const done = Math.round(progress * bars);
  return (
    <div className={`relative overflow-hidden ${className}`}>
      <svg viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`} preserveAspectRatio="none" className="block h-full w-full" aria-hidden="true">
        {values.map((value, i) => {
          const h = Math.max(1.5, value * (HEIGHT - 8));
          return (
            <rect
              key={i}
              x={i * step + step * 0.22}
              y={mid - h / 2}
              width={step * 0.56}
              height={h}
              rx={step * 0.28}
              fill="var(--accent)"
              opacity={i < done ? 0.92 : 0.22}
            />
          );
        })}
      </svg>
      {sweeping && (
        <div
          aria-hidden="true"
          className="light-sweep pointer-events-none absolute inset-y-0 left-0 w-full"
          style={{
            background:
              "linear-gradient(90deg, transparent 0%, transparent 35%, color-mix(in srgb, var(--accent) 35%, transparent) 50%, transparent 65%, transparent 100%)",
            mixBlendMode: "overlay",
          }}
        />
      )}
    </div>
  );
}

/** Тонкая «дышащая» линия-волна для героя главной (SPEC §2.4). */
export function BreathingLine({ className = "" }: { className?: string }) {
  const path = useMemo(() => {
    const points = 320;
    const parts: string[] = [];
    for (let i = 0; i <= points; i++) {
      const t = i / points;
      const envelope = Math.sin(Math.PI * t) ** 1.4 * (0.55 + 0.45 * Math.sin(t * 9) ** 2);
      const signal =
        Math.sin(2 * Math.PI * t * 5.3) * 0.5 +
        Math.sin(2 * Math.PI * t * 13.1) * 0.3 +
        Math.sin(2 * Math.PI * t * 31.7) * 0.2;
      const y = 70 + signal * envelope * 64;
      parts.push(`${i === 0 ? "M" : "L"}${(t * 1200).toFixed(1)} ${y.toFixed(1)}`);
    }
    return parts.join(" ");
  }, []);
  return (
    <svg viewBox="0 0 1200 140" preserveAspectRatio="none" aria-hidden="true" className={className}>
      <defs>
        <linearGradient id="line-fade" x1="0" x2="1">
          <stop offset="0" stopColor="white" stopOpacity="0" />
          <stop offset="0.2" stopColor="white" stopOpacity="1" />
          <stop offset="0.8" stopColor="white" stopOpacity="1" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </linearGradient>
        <mask id="line-mask">
          <rect width="1200" height="140" fill="url(#line-fade)" />
        </mask>
      </defs>
      <g mask="url(#line-mask)" className="wave-breathe">
        <path d={path} fill="none" strokeWidth="1" vectorEffect="non-scaling-stroke" className="stroke-accent opacity-70" />
      </g>
    </svg>
  );
}
