import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { Icon } from "../../components/Icon";
import type { PartInfo } from "../../lib/api";
import { clock } from "../../lib/format";
import { EASE_FILM } from "../../lib/motion";
import { RoleMark } from "./BandPanel";
import type { AlphaTabControls } from "./useAlphaTab";

export interface TrackMix {
  mute: boolean;
  solo: boolean;
  volume: number;
}

function Popover({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: React.ReactNode; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={ref}
          role="dialog"
          aria-label={label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.25, ease: EASE_FILM }}
          className="panel absolute right-0 bottom-[calc(100%+12px)] z-30 w-[min(92vw,380px)] p-4"
          style={{ boxShadow: "var(--shadow)" }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function PlayerBar({
  controls,
  parts,
  mix,
  onMix,
  onExport,
}: {
  controls: AlphaTabControls;
  parts: PartInfo[];
  mix: TrackMix[];
  onMix: (index: number, next: TrackMix) => void;
  onExport: (kind: "pdf" | "gp" | "midi" | "tex") => void;
}) {
  const { view } = controls;
  const [panel, setPanel] = useState<"mixer" | "export" | null>(null);
  const progress = view.endTime ? view.time / view.endTime : 0;
  const speedPct = Math.round(view.speed * 100);

  return (
    <div className="border-t border-line bg-bg/92 backdrop-blur-xl">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-1">
          <button type="button" className="icon-btn" onClick={() => { controls.seekBar(-1); }} aria-label="Предыдущий такт (←)" title="Предыдущий такт (←)">
            <Icon name="prev" size={18} />
          </button>
          <button
            type="button"
            onClick={controls.playPause}
            disabled={!view.ready}
            aria-label={view.playing ? "Пауза (пробел)" : "Играть (пробел)"}
            title={view.playing ? "Пауза (пробел)" : "Играть (пробел)"}
            className="flex size-12 items-center justify-center rounded-full bg-accent text-on-accent transition-[box-shadow,opacity] duration-300 ease-film hover:shadow-[0_0_0_8px_var(--glow)] disabled:opacity-40"
          >
            <Icon name={view.playing ? "pause" : "play"} size={20} />
          </button>
          <button type="button" className="icon-btn" onClick={() => { controls.seekBar(1); }} aria-label="Следующий такт (→)" title="Следующий такт (→)">
            <Icon name="next" size={18} />
          </button>
          <button type="button" className="icon-btn" onClick={controls.stop} aria-label="В начало" title="В начало">
            <Icon name="stop" size={16} />
          </button>
        </div>

        <div className="order-last flex min-w-[220px] flex-1 items-center gap-3 sm:order-none">
          <span className="w-11 text-right font-mono text-caption text-text-dim tabular">{clock(view.time)}</span>
          <button
            type="button"
            className="group relative h-8 flex-1"
            aria-label="Перемотка"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              controls.seekRatio((e.clientX - rect.left) / rect.width);
            }}
          >
            <span className="absolute inset-x-0 top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-line-strong" />
            <span className="absolute top-1/2 left-0 h-[3px] -translate-y-1/2 rounded-full bg-accent" style={{ width: `${String(progress * 100)}%` }} />
            <span
              className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent opacity-0 shadow-[0_0_0_6px_var(--glow)] transition-opacity duration-300 ease-film group-hover:opacity-100"
              style={{ left: `${String(progress * 100)}%` }}
            />
          </button>
          <span className="w-11 font-mono text-caption text-text-dim tabular">{clock(view.endTime)}</span>
          <span className="hidden w-[86px] font-mono text-caption text-text-dim tabular md:block">
            такт {view.bars ? view.bar + 1 : 0}/{view.bars}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button type="button" className="icon-btn" aria-pressed={view.looping} onClick={controls.toggleLoop} title="Петля A–B (L)" aria-label="Петля A–B (L)">
            <Icon name="loop" size={18} />
          </button>
          <button type="button" className="icon-btn" aria-pressed={view.metronome} onClick={controls.toggleMetronome} title="Метроном" aria-label="Метроном">
            <Icon name="metronome" size={18} />
          </button>
          <button type="button" className="icon-btn" aria-pressed={view.countIn} onClick={controls.toggleCountIn} title="Отсчёт перед стартом" aria-label="Отсчёт перед стартом">
            <Icon name="countin" size={18} />
          </button>
          <div className="mx-1 flex h-10 items-center rounded-full border border-line-strong" title="Темп без изменения высоты">
            <button type="button" className="icon-btn size-9" aria-label="Медленнее" disabled={speedPct <= 50} onClick={() => { controls.setSpeed(Math.max(0.5, (speedPct - 5) / 100)); }}>
              <Icon name="minus" size={14} />
            </button>
            <span className="w-12 text-center font-mono text-caption tabular">{speedPct}%</span>
            <button type="button" className="icon-btn size-9" aria-label="Быстрее" disabled={speedPct >= 120} onClick={() => { controls.setSpeed(Math.min(1.2, (speedPct + 5) / 100)); }}>
              <Icon name="plus" size={14} />
            </button>
          </div>
          <div className="relative">
            <button type="button" className="icon-btn" aria-expanded={panel === "mixer"} onClick={() => { setPanel(panel === "mixer" ? null : "mixer"); }} title="Микшер" aria-label="Микшер">
              <Icon name="sliders" size={18} />
            </button>
            <Popover open={panel === "mixer"} onClose={() => { setPanel(null); }} label="Микшер">
              <p className="eyebrow mb-3">Микшер</p>
              <ul className="space-y-3">
                {parts.map((part, index) => {
                  const state = mix[index] ?? { mute: false, solo: false, volume: 1 };
                  return (
                    <li key={part.player_id} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5">
                      <span className="flex min-w-0 items-center gap-2 text-small font-semibold">
                        {part.roles[0] && <RoleMark role={part.roles[0]} />}
                        <span className="truncate">{part.title}</span>
                      </span>
                      <span className="flex gap-1">
                        <button type="button" className="chip h-7 px-2.5" aria-pressed={state.mute} onClick={() => { onMix(index, { ...state, mute: !state.mute }); }} title="Заглушить (M — твою партию)">
                          M
                        </button>
                        <button type="button" className="chip h-7 px-2.5" aria-pressed={state.solo} onClick={() => { onMix(index, { ...state, solo: !state.solo }); }} title="Соло">
                          S
                        </button>
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={1.5}
                        step={0.05}
                        value={state.volume}
                        aria-label={`Громкость: ${part.title}`}
                        onChange={(e) => { onMix(index, { ...state, volume: Number(e.target.value) }); }}
                        className="col-span-2 accent-[var(--accent)]"
                      />
                    </li>
                  );
                })}
              </ul>
            </Popover>
          </div>
          <div className="relative">
            <button type="button" className="icon-btn" aria-expanded={panel === "export"} onClick={() => { setPanel(panel === "export" ? null : "export"); }} title="Экспорт" aria-label="Экспорт">
              <Icon name="download" size={18} />
            </button>
            <Popover open={panel === "export"} onClose={() => { setPanel(null); }} label="Экспорт">
              <p className="eyebrow mb-3">Скачать</p>
              <div className="grid gap-1">
                {(
                  [
                    ["pdf", "PDF / печать", "print", "видимые партии"],
                    ["gp", "Guitar Pro (.gp)", "download", "все партии"],
                    ["midi", "MIDI", "download", "все партии"],
                    ["tex", "alphaTex", "download", "текстом"],
                  ] as const
                ).map(([kind, label, icon, note]) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => {
                      onExport(kind);
                      setPanel(null);
                    }}
                    className="flex items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition-colors duration-300 ease-film hover:bg-surface-2"
                  >
                    <Icon name={icon} size={18} />
                    <span className="flex-1 text-small font-semibold">{label}</span>
                    <span className="text-caption text-text-dim">{note}</span>
                  </button>
                ))}
              </div>
            </Popover>
          </div>
        </div>
      </div>
      {!view.ready && (
        <div className="h-0.5 bg-line">
          <div className="h-full bg-accent transition-[width] duration-300 ease-film" style={{ width: `${String(Math.round(view.soundProgress * 100))}%` }} />
        </div>
      )}
    </div>
  );
}
