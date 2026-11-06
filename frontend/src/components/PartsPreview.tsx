/** Витрина на главной: три партии одной песни — так выглядит результат разбора. */

const LANES = [
  {
    name: "Мелодия",
    who: "Аня · средне",
    notes: [[0, 3], [1, 5], [2, 5], [3, 3], [5, 1], [6, 3], [7, 0], [9, 1], [10, 3], [12, 5], [13, 3], [14, 1]],
    strings: [1, 1, 2, 1, 1, 2, 1, 2, 2, 1, 1, 2],
    texture: "solid",
  },
  {
    name: "Ритм",
    who: "Макс · упрощённо",
    chords: ["Am", "F", "C", "G"],
    texture: "dash",
  },
  {
    name: "Бас",
    who: "Лёша · полностью",
    notes: [[0, 0], [2, 0], [4, 1], [6, 1], [8, 3], [10, 3], [12, 3], [14, 2]],
    strings: [5, 5, 4, 4, 5, 5, 6, 6],
    texture: "thick",
  },
] as const;

function Staff({ children, lines = 6 }: { children: React.ReactNode; lines?: number }) {
  return (
    <div className="relative h-[92px]">
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          className="absolute inset-x-0 h-px bg-line-strong"
          style={{ top: `${String(8 + i * 15)}px` }}
        />
      ))}
      {children}
    </div>
  );
}

export function PartsPreview() {
  return (
    <div className="panel relative overflow-hidden p-5 sm:p-6" style={{ boxShadow: "var(--shadow)" }}>
      <div className="mb-4 flex items-center justify-between">
        <p className="eyebrow">Партитура · трио</p>
        <p className="font-mono text-caption text-text-dim">Am · 96 BPM · капо 0</p>
      </div>
      <div className="relative space-y-5">
        <div aria-hidden="true" className="playhead pointer-events-none absolute top-0 bottom-0 z-10 w-0.5 bg-accent shadow-[0_0_18px_4px_var(--glow)]" />
        {LANES.map((lane) => (
          <div key={lane.name} className="grid grid-cols-[88px_1fr] items-center gap-4">
            <div>
              <p className="text-small font-semibold">{lane.name}</p>
              <p className="text-caption text-text-dim">{lane.who}</p>
            </div>
            <Staff>
              {"chords" in lane
                ? lane.chords.map((chord, i) => (
                    <div key={chord} className="absolute top-0 bottom-0" style={{ left: `${String(i * 25 + 2)}%` }}>
                      <span className="absolute -top-0.5 font-display text-[17px] leading-none font-[700]">{chord}</span>
                      {[0, 1, 2, 3].map((s) => (
                        <span
                          key={s}
                          className="absolute h-[62px] w-[2px] bg-text-dim"
                          style={{ left: `${String(s * 22 + 2)}px`, top: "22px", opacity: s % 2 ? 0.45 : 0.9 }}
                        />
                      ))}
                    </div>
                  ))
                : lane.notes.map(([slot, fret], i) => (
                    <span
                      key={`${String(slot)}-${String(i)}`}
                      className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-[4px] bg-surface px-1 font-mono text-[12px] leading-none ${lane.texture === "thick" ? "font-semibold text-text" : "text-text"}`}
                      style={{
                        left: `${String(4 + slot * 6.2)}%`,
                        top: `${String(8 + ((lane.strings[i] ?? 1) - 1) * 15)}px`,
                      }}
                    >
                      {fret}
                    </span>
                  ))}
            </Staff>
          </div>
        ))}
      </div>
    </div>
  );
}
