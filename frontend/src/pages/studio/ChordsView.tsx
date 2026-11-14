import { useState } from "react";
import { ChordDiagram } from "../../components/ChordDiagram";
import type { Arrangement, ChartChord, ChordShape, PartInfo } from "../../lib/api";
import { prettyChord } from "../../lib/format";

function sameFrets(a: (number | null)[], b: (number | null)[]): boolean {
  return a.length === b.length && a.every((fret, i) => fret === b[i]);
}

/** Имена аккордов, которые понимает аранжировщик: C, G#m, F#7, Bbmaj7, Dsus4, E5, C/G… */
const CHORD_NAME = /^[A-G][#b]?(maj7|m7|m|7|dim|aug|sus2|sus4|5)?(\/[A-G][#b]?)?$/;

function cleanName(text: string): string {
  return text.trim().replace(/♯/g, "#").replace(/♭/g, "b");
}

/** Правка одного аккорда листа: новое имя — только здесь или по всей песне. */
function ChordFixForm({
  chord,
  onFix,
  onClose,
}: {
  chord: ChartChord;
  onFix: (chord: ChartChord, name: string | null, everywhere: boolean) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState(chord.name);
  const name = cleanName(text);
  const valid = CHORD_NAME.test(name);
  const apply = (value: string | null, everywhere: boolean) => {
    onFix(chord, value, everywhere);
    onClose();
  };
  return (
    <form
      className="absolute top-full left-0 z-20 mt-1 w-60 space-y-2 rounded-[12px] border border-line-strong bg-bg p-3 shadow-[var(--shadow)]"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) apply(name, false);
      }}
    >
      <label className="block text-caption text-text-dim">
        Какой здесь аккорд на самом деле
        <input
          autoFocus
          value={text}
          onChange={(e) => {
            setText(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            e.stopPropagation(); // пробел и стрелки — в поле, а не плееру
          }}
          aria-invalid={!valid}
          className="mt-1 block h-9 w-full rounded-[8px] border border-line bg-surface px-2 font-mono text-small text-text"
        />
      </label>
      {!valid && <p className="text-caption text-text-dim">Например: G#m, F#7, Bbmaj7, Dsus4, C/G</p>}
      <div className="flex flex-wrap gap-1.5">
        <button type="submit" disabled={!valid} className="btn btn-primary h-8 px-3 text-caption">
          Здесь
        </button>
        <button
          type="button"
          disabled={!valid}
          className="btn btn-ghost h-8 px-3 text-caption"
          title={`Заменить все ${chord.name} в песне`}
          onClick={() => {
            apply(name, true);
          }}
        >
          Везде
        </button>
        <button
          type="button"
          className="btn btn-ghost h-8 px-3 text-caption"
          title="Здесь аккорда нет"
          onClick={() => {
            apply(null, false);
          }}
        >
          Убрать
        </button>
        <button type="button" className="btn btn-ghost h-8 px-3 text-caption" onClick={onClose}>
          Отмена
        </button>
      </div>
    </form>
  );
}

/** Режим «Аккорды»: аппликатуры сверху и лист аккордов по тактам. */
export function ChordsView({
  arrangement,
  part,
  pinned,
  onPick,
  fixes = 0,
  onFix,
  onResetFixes,
}: {
  arrangement: Arrangement;
  part: PartInfo | null;
  /** Аккорды, для которых игрок сам выбрал аппликатуру. */
  pinned?: Record<string, (number | null)[]>;
  /** Взять аккорд по-другому; null — вернуть автоматический выбор. */
  onPick?: (name: string, frets: (number | null)[] | null) => void;
  /** Сколько правок аккордов внесено вручную. */
  fixes?: number;
  /** Исправить аккорд разбора: новое имя (null — убрать), только здесь или везде. */
  onFix?: (chord: ChartChord, name: string | null, everywhere: boolean) => void;
  onResetFixes?: () => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const barSteps = arrangement.beats_per_bar * arrangement.steps_per_beat;
  const own = Boolean(part?.shapes.length);
  const shapes = own && part ? part.shapes : (arrangement.parts.find((p) => p.shapes.length)?.shapes ?? []);
  const capo = part?.capo ?? 0;
  const anyPinned = Boolean(pinned && shapes.some((s) => s.name in pinned));
  // Такт без смены аккорда продолжает предыдущий — на листе это «%».
  const carried = arrangement.chart.map((_, index) => arrangement.chart.slice(0, index).some((bar) => bar.length > 0));

  function next(shape: ChordShape) {
    const options = shape.options ?? [];
    const current = options.findIndex((o) => sameFrets(o.frets, shape.frets));
    const picked = options[(current + 1) % options.length];
    if (picked && onPick) onPick(shape.name, picked.frets);
  }

  return (
    <div className="space-y-10 p-6 sm:p-8">
      {shapes.length > 0 && (
        <section aria-label="Аппликатуры">
          <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h3 className="eyebrow">Аккорды песни</h3>
            {capo > 0 && <span className="text-caption text-text-dim">формы с каподастром на {capo} ладу</span>}
            {own && onPick && <span className="text-caption text-text-dim">нажми на аккорд, чтобы взять его по-другому</span>}
            {anyPinned && onPick && (
              <button
                type="button"
                className="text-caption underline underline-offset-2"
                onClick={() => {
                  for (const shape of shapes) if (pinned && shape.name in pinned) onPick(shape.name, null);
                }}
              >
                вернуть подбор
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-4">
            {shapes.map((shape) => {
              const options = shape.options ?? [];
              const index = options.findIndex((o) => sameFrets(o.frets, shape.frets));
              const pickable = own && onPick && options.length > 1;
              return (
                <ChordDiagram
                  key={shape.name}
                  name={shape.name}
                  frets={shape.frets}
                  fingers={shape.fingers}
                  barre={shape.barre}
                  size={84}
                  note={pickable ? `${pinned && shape.name in pinned ? "свой · " : ""}${String(index + 1)} из ${String(options.length)}` : undefined}
                  onClick={
                    pickable
                      ? () => {
                          next(shape);
                        }
                      : undefined
                  }
                />
              );
            })}
          </div>
        </section>
      )}
      <section aria-label="Лист аккордов">
        <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="eyebrow">По тактам · звучание без каподастра</h3>
          {onFix && <span className="text-caption text-text-dim">разбор ошибся? нажми на аккорд и поправь</span>}
          {fixes > 0 && onResetFixes && (
            <button type="button" className="text-caption underline underline-offset-2" onClick={onResetFixes}>
              сбросить правки ({fixes})
            </button>
          )}
        </div>
        <ol className="grid grid-cols-2 gap-px rounded-[14px] border border-line bg-line sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
          {arrangement.chart.map((bar, index) => {
            return (
              <li key={index} className="relative min-h-[76px] bg-surface p-3 first:rounded-tl-[13px] last:rounded-br-[13px]">
                <span className="absolute top-2 right-2.5 font-mono text-[10px] text-text-dim">{index + 1}</span>
                <div className="flex h-full items-end gap-2">
                  {bar.length ? (
                    bar.map((chord) => {
                      const id = `${String(index)}:${String(chord.offset)}`;
                      const style = { marginLeft: chord.offset ? `${String((chord.offset / barSteps) * 30)}%` : undefined };
                      const label = "font-display text-[26px] leading-none font-[720]";
                      if (!onFix || chord.start === undefined) {
                        return (
                          <span key={id} className={label} style={style}>
                            {prettyChord(chord.name)}
                          </span>
                        );
                      }
                      return (
                        <span key={id} className="relative" style={style}>
                          <button
                            type="button"
                            className={`${label} rounded-[6px] hover:text-accent focus-visible:outline-2 focus-visible:outline-accent`}
                            title="Исправить аккорд"
                            onClick={() => {
                              setEditing(editing === id ? null : id);
                            }}
                          >
                            {prettyChord(chord.name)}
                          </button>
                          {editing === id && (
                            <ChordFixForm
                              chord={chord}
                              onFix={onFix}
                              onClose={() => {
                                setEditing(null);
                              }}
                            />
                          )}
                        </span>
                      );
                    })
                  ) : (
                    <span className="font-display text-[26px] leading-none text-text-dim">{carried[index] ? "%" : "—"}</span>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
