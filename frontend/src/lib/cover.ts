/** Генеративная обложка: волна песни, сложенная в чёрно-белую композицию (SPEC §1.4, «Библиотека»). */

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Детерминированный генератор: одна песня — всегда одна обложка. */
export function random(seed: string): () => number {
  let state = hash(seed) || 1;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return ((state >>> 0) % 100000) / 100000;
  };
}

export interface CoverShape {
  bars: { x: number; height: number }[];
  rings: { r: number; opacity: number }[];
  tilt: number;
  horizon: number;
  style: "bars" | "rings" | "lines";
}

/** Пики волны (0…1) → геометрия обложки в квадрате 100×100. */
export function coverShape(seed: string, peaks: number[]): CoverShape {
  const rnd = random(seed);
  const count = 44;
  const source = peaks.length ? peaks : Array.from({ length: count }, () => 0.2 + rnd() * 0.8);
  const bars = Array.from({ length: count }, (_, i) => {
    const start = Math.floor((i / count) * source.length);
    const end = Math.max(start + 1, Math.floor(((i + 1) / count) * source.length));
    const slice = source.slice(start, end);
    const height = slice.reduce((a, b) => Math.max(a, b), 0);
    return { x: 4 + (i * 92) / (count - 1), height: 0.08 + height * 0.92 };
  });
  const rings = Array.from({ length: 6 }, (_, i) => ({
    r: 10 + i * 7 + rnd() * 3,
    opacity: 0.15 + rnd() * 0.5,
  }));
  const styles: CoverShape["style"][] = ["bars", "rings", "lines"];
  return {
    bars,
    rings,
    tilt: (rnd() - 0.5) * 18,
    horizon: 40 + rnd() * 25,
    style: styles[Math.floor(rnd() * styles.length)] ?? "bars",
  };
}
