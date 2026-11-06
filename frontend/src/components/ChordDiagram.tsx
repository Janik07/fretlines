import { prettyChord } from "../lib/format";

/** Аккордовая диаграмма: вертикальный гриф, точки — прижатые лады, ○ — открытая, × — не играть. */
export function ChordDiagram({
  name,
  frets,
  size = 96,
}: {
  name: string;
  frets: (number | null)[];
  size?: number;
}) {
  const strings = frets.length;
  const fretted = frets.filter((f): f is number => f !== null && f > 0);
  const low = fretted.length ? Math.min(...fretted) : 1;
  const start = Math.max(...fretted, 0) <= 4 ? 1 : low;
  const rows = 4;
  const width = 64;
  const height = 72;
  const x0 = 10;
  const y0 = 20;
  const gapX = (width - 2 * x0) / (strings - 1);
  const gapY = (height - y0 - 6) / rows;
  // По струнам снизу вверх: на диаграмме слева — толстая (последняя в массиве).
  const columns = [...frets].reverse();

  return (
    <figure className="flex flex-col items-center gap-1.5" style={{ width: size }}>
      <figcaption className="font-display text-[22px] leading-none font-[700]">{prettyChord(name)}</figcaption>
      <svg viewBox={`0 0 ${String(width)} ${String(height)}`} width={size} height={(size * height) / width} aria-label={`Аппликатура ${name}`} role="img">
        {start === 1 ? (
          <rect x={x0 - 1} y={y0 - 2.5} width={width - 2 * x0 + 2} height="2.5" rx="1" fill="var(--text)" />
        ) : (
          <text x="2" y={y0 + gapY * 0.65} fontSize="7" fill="var(--text-dim)" fontFamily="var(--font-mono)">
            {start}
          </text>
        )}
        {Array.from({ length: rows + 1 }, (_, r) => (
          <line key={`f${String(r)}`} x1={x0} x2={width - x0} y1={y0 + r * gapY} y2={y0 + r * gapY} stroke="var(--line-strong)" strokeWidth="0.8" />
        ))}
        {columns.map((_, c) => (
          <line key={`s${String(c)}`} x1={x0 + c * gapX} x2={x0 + c * gapX} y1={y0} y2={y0 + rows * gapY} stroke="var(--text-dim)" strokeWidth={0.5 + (strings - c) * 0.12} />
        ))}
        {columns.map((fret, c) => {
          const x = x0 + c * gapX;
          if (fret === null) {
            return (
              <text key={`m${String(c)}`} x={x} y={y0 - 7} fontSize="7" textAnchor="middle" fill="var(--text-dim)">
                ×
              </text>
            );
          }
          if (fret === 0) {
            return <circle key={`o${String(c)}`} cx={x} cy={y0 - 9.5} r="2.3" fill="none" stroke="var(--text)" strokeWidth="0.8" />;
          }
          const row = fret - start;
          return <circle key={`d${String(c)}`} cx={x} cy={y0 + (row + 0.5) * gapY} r="3.4" fill="var(--accent)" />;
        })}
      </svg>
    </figure>
  );
}
