import { useEffect, useMemo, useRef } from "react";

import type { Arrangement, LyricLine, Lyrics } from "../../lib/api";
import { prettyChord } from "../../lib/format";
import { buildSheet, chordMarks, dedupe, lineAt, sourceLabel } from "./sheet";

/** Текст песни: караоке-строка под табами и режим «Текст» — слова с аккордами над ними. */

/** Слово с «заливкой»: спетая часть — акцентом, остальное — приглушённо. */
function Word({ text, start, end, seconds }: { text: string; start: number; end: number; seconds: number }) {
  const progress = seconds <= start ? 0 : seconds >= end ? 1 : (seconds - start) / Math.max(0.05, end - start);
  if (progress <= 0) return <span className="text-text-dim">{text}</span>;
  if (progress >= 1) return <span className="text-text">{text}</span>;
  const pct = `${String(Math.round(progress * 100))}%`;
  return (
    <span
      style={{
        backgroundImage: `linear-gradient(90deg, var(--accent) ${pct}, var(--text-dim) ${pct})`,
        WebkitBackgroundClip: "text",
        backgroundClip: "text",
        color: "transparent",
      }}
    >
      {text}
    </span>
  );
}

function LineWords({ line, seconds }: { line: LyricLine; seconds: number }) {
  return (
    <>
      {line.words.map((word, i) => (
        <span key={`${String(i)}-${word.text}`}>
          {i > 0 && " "}
          <Word text={word.text} start={word.start} end={word.end} seconds={seconds} />
        </span>
      ))}
    </>
  );
}

/** Строка караоке над плеером: текущая строка крупно, следующая — тише. */
export function KaraokeStrip({
  lyrics,
  seconds,
  onSeek,
}: {
  lyrics: Lyrics;
  seconds: number;
  onSeek: (seconds: number) => void;
}) {
  const index = lineAt(lyrics.lines, seconds);
  const current = index >= 0 ? lyrics.lines[index] : undefined;
  const live = current !== undefined && seconds <= current.end + 1.2;
  const next = lyrics.lines[index + 1];
  const wait = next ? next.start - seconds : null;

  return (
    <div className="border-t border-line bg-surface/70 px-5 py-2 sm:px-7 sm:py-3" aria-live="off">
      <div className="mx-auto flex max-w-[900px] flex-col items-center gap-1 text-center">
        <button
          type="button"
          className="min-h-[30px] text-[19px] leading-tight font-semibold sm:text-[26px]"
          onClick={() => {
            if (current) onSeek(current.start);
          }}
          title="Перейти к началу строки"
        >
          {live ? (
            <LineWords line={current} seconds={seconds} />
          ) : (
            <span className="text-text-dim">
              {wait !== null && wait < 6 && wait > 0 ? `♪ ещё ${String(Math.ceil(wait))} с` : "♪"}
            </span>
          )}
        </button>
        <button
          type="button"
          className="min-h-[20px] text-small text-text-dim transition-colors duration-300 ease-film hover:text-text"
          onClick={() => {
            if (next) onSeek(next.start);
          }}
          title="Перейти к следующей строке"
        >
          {next ? next.words.map((w) => w.text).join(" ") : ""}
        </button>
      </div>
    </div>
  );
}

/** Режим «Текст»: песенник с аккордами. Текущая строка подсвечена и сама прокручивается. */
export function LyricsSheet({
  lyrics,
  arrangement,
  seconds,
  onSeek,
}: {
  lyrics: Lyrics;
  arrangement: Arrangement;
  seconds: number;
  onSeek: (seconds: number) => void;
}) {
  const rows = useMemo(() => buildSheet(lyrics, chordMarks(arrangement)), [lyrics, arrangement]);
  const current = lineAt(lyrics.lines, seconds);
  const refs = useRef(new Map<number, HTMLElement>());

  useEffect(() => {
    const element = refs.current.get(current);
    element?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [current]);

  if (!lyrics.lines.length) {
    return <p className="p-8 text-body text-text-dim">Текста у этой песни нет.</p>;
  }
  return (
    <div className="mx-auto max-w-[760px] px-6 pt-6 pb-28 sm:px-8">
      <p className="mb-6 text-caption text-text-dim">{sourceLabel(lyrics)} · нажми на строку, чтобы перейти к ней</p>
      <ol className="space-y-5">
        {rows.map((row) =>
          row.kind === "gap" ? (
            <li key={`gap-${String(row.index)}`} className="flex flex-wrap items-baseline gap-3 text-text-dim">
              <span className="eyebrow">проигрыш</span>
              <span className="font-display text-[22px] leading-none font-[720] text-text">
                {dedupe(row.gapChords).map(prettyChord).join("  ")}
              </span>
            </li>
          ) : (
            <li
              key={`line-${String(row.index)}`}
              ref={(element) => {
                if (element) refs.current.set(row.index, element);
                else refs.current.delete(row.index);
              }}
            >
              <button
                type="button"
                onClick={() => {
                  if (row.line) onSeek(row.line.start);
                }}
                className={`-mx-3 block w-[calc(100%+24px)] rounded-[12px] px-3 py-1.5 text-left transition-colors duration-300 ease-film ${
                  row.index === current ? "bg-surface-2" : "hover:bg-surface"
                }`}
              >
                <span className="flex flex-wrap items-end gap-x-[0.4em] gap-y-1">
                  {row.line?.words.map((word, i) => {
                    const names = row.chords.get(i);
                    return (
                      <span key={`${String(i)}-${word.text}`} className="inline-flex flex-col">
                        <span className="h-[22px] font-display text-[19px] leading-none font-[740] text-accent">
                          {names ? names.map(prettyChord).join(" ") : " "}
                        </span>
                        <span className="text-[19px] leading-snug">
                          {row.index === current ? (
                            <Word text={word.text} start={word.start} end={word.end} seconds={seconds} />
                          ) : (
                            <span className={row.index < current ? "text-text-dim" : "text-text"}>{word.text}</span>
                          )}
                        </span>
                      </span>
                    );
                  })}
                </span>
              </button>
            </li>
          ),
        )}
      </ol>
    </div>
  );
}
