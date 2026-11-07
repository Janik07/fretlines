import type { Arrangement, LyricLine, Lyrics } from "../../lib/api";
import { stepToSeconds } from "./timeline";

/** Данные для текста песни: откуда текст, какая строка звучит, аккорды над словами. */

const SOURCE_LABEL: Record<string, string> = {
  lrclib: "текст: lrclib.net",
  "lrclib+whisper": "текст: lrclib.net, тайминг — по вокалу",
  whisper: "текст распознан по вокалу — возможны ошибки",
  edited: "текст поправлен вручную",
};

export function sourceLabel(lyrics: Lyrics): string {
  return lyrics.source ? (SOURCE_LABEL[lyrics.source] ?? "") : "";
}

export function lineAt(lines: LyricLine[], seconds: number): number {
  let found = -1;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line && line.start <= seconds + 0.05) found = i;
    else break;
  }
  return found;
}


export interface ChordMark {
  time: number;
  name: string;
}

export interface SheetRow {
  kind: "line" | "gap";
  line?: LyricLine;
  index: number;
  // аккорд над словом: номер слова → имена
  chords: Map<number, string[]>;
  gapChords: string[];
  start: number;
}

export function chordMarks(arrangement: Arrangement): ChordMark[] {
  const barSteps = arrangement.beats_per_bar * arrangement.steps_per_beat;
  const marks: ChordMark[] = [];
  arrangement.chart.forEach((bar, index) => {
    for (const chord of bar) {
      marks.push({
        time: stepToSeconds(arrangement.bar_seconds, index, chord.offset, barSteps),
        name: chord.name,
      });
    }
  });
  return marks;
}

/** Строки текста + аккорды: каждый аккорд — над словом, на котором он звучит. */
export function buildSheet(lyrics: Lyrics, marks: ChordMark[]): SheetRow[] {
  const rows: SheetRow[] = [];
  const lines = lyrics.lines;
  let cursor = 0; // первый ещё не размещённый аккорд
  let sounding: string | null = null;
  lines.forEach((line, index) => {
    const nextStart = lines[index + 1]?.start ?? Infinity;
    // Проигрыш перед строкой: аккорды задолго до первого слова.
    const gap: string[] = [];
    while (cursor < marks.length && (marks[cursor]?.time ?? 0) < line.start - 1.2) {
      const mark = marks[cursor];
      if (mark) {
        gap.push(mark.name);
        sounding = mark.name;
      }
      cursor++;
    }
    if (gap.length) rows.push({ kind: "gap", index, chords: new Map(), gapChords: gap, start: line.start });

    const chords = new Map<number, string[]>();
    const add = (word: number, name: string) => {
      const list = chords.get(word) ?? [];
      if (list[list.length - 1] !== name) list.push(name);
      chords.set(word, list);
    };
    const limit = Math.min(nextStart - 0.3, line.end + 1.5);
    const atStart = sounding; // аккорд, который звучит, когда строка начинается
    while (cursor < marks.length && (marks[cursor]?.time ?? 0) < limit) {
      const mark = marks[cursor];
      cursor++;
      if (!mark) continue;
      let word = 0;
      line.words.forEach((w, i) => {
        if (w.start <= mark.time + 0.15) word = i;
      });
      add(word, mark.name);
      sounding = mark.name;
    }
    // Как в песеннике: у каждой строки над первым словом — аккорд, с которого она поётся.
    if (!chords.has(0) && atStart) chords.set(0, [atStart]);
    rows.push({ kind: "line", line, index, chords, gapChords: [], start: line.start });
  });
  const tail = marks.slice(cursor).map((m) => m.name);
  if (tail.length) rows.push({ kind: "gap", index: lines.length, chords: new Map(), gapChords: tail, start: Infinity });
  return rows;
}

export function dedupe(names: string[]): string[] {
  return names.filter((name, i) => names[i - 1] !== name);
}

