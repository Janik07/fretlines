import { prettyChord } from "../lib/format";

/** Аккордовая диаграмма: вертикальный гриф, точки с номерами пальцев, ○ — открытая, × — не играть. */
export function ChordDiagram({
  name,
  frets,
  fingers,
  barre,
  size = 96,
  note,
  onClick,
}: {
  name: string;
  frets: (number | null)[];
  /** Палец на каждой струне: 1–4; у старых разборов пальцев нет. */
  fingers?: (number | null)[];
  /** Лад баррэ — рисуется перемычкой под указательным пальцем. */
  barre?: number | null;
  size?: number;
  /** Подпись под диаграммой, например «вариант 2 из 5». */
  note?: string;
  /** Нажатие — взять аккорд по-другому. */
  onClick?: () => void;
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
  const hands = fingers?.length === strings ? [...fingers].reverse() : null;
  // Баррэ: от самой толстой струны под указательным пальцем до самой тонкой.
  const barred = barre && hands ? columns.map((fret, c) => (fret === barre && hands[c] === 1 ? c : -1)).filter((c) => c >= 0) : [];
  const barreFrom = barred.length >= 2 ? Math.min(...barred) : -1;
  const barreTo = barred.length >= 2 ? Math.max(...barred) : -1;

  const diagram = (
    <>
      <figcaption className="font-display text-[22px] leading-none font-[700]">{prettyChord(name)}</figcaption>
      <svg viewBox={`0 0 ${String(width)} ${String(height)}`} width={size} height={(size * height) / width} aria-label={`Аппликатура ${name}`} role="img">
        {start === 1 ? (
          <rect x={x0 - 1} y={y0 - 2.5} width={width - 2 * x0 + 2} height="2.5" rx="1" fill="var(--text)" />
        ) : (
          <text x="0" y={y0 + gapY * 0.65} fontSize="6.5" fill="var(--text-dim)" fontFamily="var(--font-mono)">
            {start}
          </text>
        )}
        {Array.from({ length: rows + 1 }, (_, r) => (
          <line key={`f${String(r)}`} x1={x0} x2={width - x0} y1={y0 + r * gapY} y2={y0 + r * gapY} stroke="var(--line-strong)" strokeWidth="0.8" />
        ))}
        {columns.map((_, c) => (
          <line key={`s${String(c)}`} x1={x0 + c * gapX} x2={x0 + c * gapX} y1={y0} y2={y0 + rows * gapY} stroke="var(--text-dim)" strokeWidth={0.5 + (strings - c) * 0.12} />
        ))}
        {barreFrom >= 0 && barre && (
          <rect
            x={x0 + barreFrom * gapX - 3.4}
            y={y0 + (barre - start + 0.5) * gapY - 3.4}
            width={(barreTo - barreFrom) * gapX + 6.8}
            height="6.8"
            rx="3.4"
            fill="var(--accent)"
          />
        )}
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
          const y = y0 + (fret - start + 0.5) * gapY;
          const finger = hands?.[c];
          const underBarre = fret === barre && c > barreFrom && c <= barreTo;
          return (
            <g key={`d${String(c)}`}>
              {!underBarre && <circle cx={x} cy={y} r="3.4" fill="var(--accent)" />}
              {finger && !underBarre ? (
                <text x={x} y={y + 1.9} fontSize="5.4" fontWeight="700" textAnchor="middle" fill="var(--on-accent)" fontFamily="var(--font-mono)">
                  {finger}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      {note && <span className="text-caption text-text-dim">{note}</span>}
    </>
  );

  if (!onClick) {
    return (
      <figure className="flex flex-col items-center gap-1.5" style={{ width: size }}>
        {diagram}
      </figure>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title="Взять аккорд по-другому"
      className="rounded-[12px] p-1.5 transition-colors hover:bg-surface focus-visible:outline-2 focus-visible:outline-accent"
    >
      <figure className="flex flex-col items-center gap-1.5" style={{ width: size }}>
        {diagram}
      </figure>
    </button>
  );
}
