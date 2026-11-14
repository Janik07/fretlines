import { ChordDiagram } from "../../components/ChordDiagram";
import type { Arrangement, ChordShape, PartInfo } from "../../lib/api";
import { prettyChord } from "../../lib/format";

function sameFrets(a: (number | null)[], b: (number | null)[]): boolean {
  return a.length === b.length && a.every((fret, i) => fret === b[i]);
}

/** Режим «Аккорды»: аппликатуры сверху и лист аккордов по тактам. */
export function ChordsView({
  arrangement,
  part,
  pinned,
  onPick,
}: {
  arrangement: Arrangement;
  part: PartInfo | null;
  /** Аккорды, для которых игрок сам выбрал аппликатуру. */
  pinned?: Record<string, (number | null)[]>;
  /** Взять аккорд по-другому; null — вернуть автоматический выбор. */
  onPick?: (name: string, frets: (number | null)[] | null) => void;
}) {
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
        <h3 className="eyebrow mb-4">По тактам · звучание без каподастра</h3>
        <ol className="grid grid-cols-2 gap-px overflow-hidden rounded-[14px] border border-line bg-line sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
          {arrangement.chart.map((bar, index) => {
            return (
              <li key={index} className="relative min-h-[76px] bg-surface p-3">
                <span className="absolute top-2 right-2.5 font-mono text-[10px] text-text-dim">{index + 1}</span>
                <div className="flex h-full items-end gap-2">
                  {bar.length ? (
                    bar.map((chord) => (
                      <span
                        key={`${String(chord.offset)}${chord.name}`}
                        className="font-display text-[26px] leading-none font-[720]"
                        style={{ marginLeft: chord.offset ? `${String((chord.offset / barSteps) * 30)}%` : undefined }}
                      >
                        {prettyChord(chord.name)}
                      </span>
                    ))
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
