import { ChordDiagram } from "../../components/ChordDiagram";
import type { Arrangement, PartInfo } from "../../lib/api";
import { prettyChord } from "../../lib/format";

/** Режим «Аккорды»: аппликатуры сверху и лист аккордов по тактам. */
export function ChordsView({ arrangement, part }: { arrangement: Arrangement; part: PartInfo | null }) {
  const barSteps = arrangement.beats_per_bar * arrangement.steps_per_beat;
  const shapes = part?.shapes.length ? part.shapes : (arrangement.parts.find((p) => p.shapes.length)?.shapes ?? []);
  const capo = part?.capo ?? 0;
  // Такт без смены аккорда продолжает предыдущий — на листе это «%».
  const carried = arrangement.chart.map((_, index) => arrangement.chart.slice(0, index).some((bar) => bar.length > 0));
  return (
    <div className="space-y-10 p-6 sm:p-8">
      {shapes.length > 0 && (
        <section aria-label="Аппликатуры">
          <div className="mb-4 flex items-baseline gap-3">
            <h3 className="eyebrow">Аккорды песни</h3>
            {capo > 0 && <span className="text-caption text-text-dim">формы с каподастром на {capo} ладу</span>}
          </div>
          <div className="flex flex-wrap gap-6">
            {shapes.map((shape) => (
              <ChordDiagram key={shape.name} name={shape.name} frets={shape.frets} size={84} />
            ))}
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
