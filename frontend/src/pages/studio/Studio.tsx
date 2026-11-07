import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Header } from "../../components/Header";
import { Icon } from "../../components/Icon";
import { Segmented } from "../../components/Segmented";
import { useMeta } from "../../hooks/useApi";
import { api, type Arrangement, type Song, type StudioSetup } from "../../lib/api";
import { keyWords, prettyChord } from "../../lib/format";
import { EASE_FILM } from "../../lib/motion";
import { navigate, type Route } from "../../lib/router";
import { useThemeStore } from "../../store/theme";
import { BandPanel } from "./BandPanel";
import { ChordsView } from "./ChordsView";
import { PlayerBar, type TrackMix } from "./PlayerBar";
import { defaultSetup } from "./setup";
import { download, useAlphaTab } from "./useAlphaTab";

type Mode = "mine" | "score" | "chords";

function fileName(title: string): string {
  return title.replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 80) || "fretlines";
}

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function Studio({ song, route }: { song: Song; route: Route }) {
  const meta = useMeta();
  const theme = useThemeStore((s) => s.theme);
  const [setup, setSetup] = useState<StudioSetup>(() => song.setup ?? defaultSetup(null));
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [arranging, setArranging] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("mine");
  const [mix, setMix] = useState<TrackMix[]>([]);
  const [bandOpen, setBandOpen] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const firstSave = useRef(true);

  // Пересчёт партий по составу — без повторного анализа (SPEC §1.5).
  useEffect(() => {
    let alive = true;
    const timer = window.setTimeout(() => {
      setArranging(true);
      api
        .arrangement(song.id, setup)
        .then((result) => {
          if (!alive) return;
          setArrangement(result);
          setFailure(null);
          setMix((current) => result.parts.map((_, i) => current[i] ?? { mute: false, solo: false, volume: 1 }));
        })
        .catch((error: unknown) => {
          if (alive) setFailure(error instanceof Error ? error.message : "Не удалось собрать партии.");
        })
        .finally(() => {
          if (alive) setArranging(false);
        });
    }, 220);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [song.id, setup]);

  // Состав и правки сохраняются в разборе — откроешь завтра, всё на месте.
  useEffect(() => {
    if (firstSave.current) {
      firstSave.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      void api.update(song.id, { setup }).catch(() => undefined);
    }, 800);
    return () => {
      window.clearTimeout(timer);
    };
  }, [song.id, setup]);

  const mineIndex = Math.max(0, setup.players.findIndex((p) => p.id === setup.mine));
  const visible = useMemo(() => (mode === "mine" ? [mineIndex] : null), [mode, mineIndex]);
  const controls = useAlphaTab(host, scroller, arrangement?.alphatex ?? null, visible, theme);
  const { view } = controls;

  useEffect(() => {
    if (!view.ready || view.rendering) return;
    mix.forEach((state, index) => {
      controls.setTrackState(index, state);
    });
    // controls пересоздаётся каждый рендер; важны только состояние микшера и готовность плеера.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mix, view.ready, view.rendering, arrangement]);

  const toggleMineMute = useCallback(() => {
    setMix((current) =>
      current.map((state, i) => (i === mineIndex ? { ...state, mute: !state.mute } : state)),
    );
  }, [mineIndex]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (typing(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.code === "Space") {
        event.preventDefault();
        controls.playPause();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        controls.seekBar(-1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        controls.seekBar(1);
      } else if (event.key.toLowerCase() === "l" || event.key.toLowerCase() === "д") {
        controls.toggleLoop();
      } else if (event.key.toLowerCase() === "m" || event.key.toLowerCase() === "ь") {
        toggleMineMute();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [controls, toggleMineMute]);

  function onExport(kind: "pdf" | "gp" | "midi" | "tex") {
    const name = fileName(song.title);
    if (kind === "pdf") controls.print();
    if (kind === "gp") controls.exportGp(name);
    if (kind === "midi") controls.exportMidi();
    if (kind === "tex" && arrangement) download(new Blob([arrangement.alphatex], { type: "text/plain" }), `${name}.atex`);
  }

  const minePart = arrangement?.parts[mineIndex] ?? null;
  const key = arrangement?.key ?? song.key ?? "";

  return (
    <div className="flex h-dvh flex-col">
      <Header route={route} />
      <div className="flex min-h-0 flex-1">
        <aside
          className={`${bandOpen ? "fixed inset-0 z-40 block bg-bg" : "hidden"} w-full shrink-0 overflow-y-auto border-r border-line p-5 lg:static lg:block lg:w-[360px]`}
          aria-label="Состав группы"
        >
          {bandOpen && (
            <button type="button" onClick={() => { setBandOpen(false); }} className="icon-btn mb-3 lg:hidden" aria-label="Закрыть состав">
              <Icon name="close" size={18} />
            </button>
          )}
          <BandPanel setup={setup} meta={meta} arrangement={arrangement} onChange={setSetup} />
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line px-5 py-4 sm:px-7">
            <button type="button" onClick={() => { navigate("/library"); }} className="icon-btn -ml-2" aria-label="К разборам">
              <Icon name="back" size={18} />
            </button>
            {/* Не уже 220 px: на узком экране тональность уходит на следующую строку, а не съедает название. */}
            <div className="min-w-[220px] flex-1">
              <h1 className="truncate font-display text-[34px] leading-none font-[780] uppercase">{song.title}</h1>
              <p className="mt-1 flex items-center gap-2 text-small text-text-dim">
                <span className="truncate">{song.artist ?? (song.source_kind === "url" ? "по ссылке" : "свой файл")}</span>
                <span className="shrink-0 rounded-full border border-line-strong px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap" title="Автоматический разбор — черновик: меняй сложность, состав и строй, чтобы подогнать партии под себя.">
                  черновик, можно поправить
                </span>
              </p>
            </div>

            <div className="flex items-center gap-2" title={key ? keyWords(key) : undefined}>
              <span className="eyebrow">Тональность</span>
              <div className="flex h-10 items-center rounded-full border border-line-strong">
                <button type="button" className="icon-btn size-9" aria-label="Транспонировать на полтона вниз" disabled={setup.transpose <= -12} onClick={() => { setSetup({ ...setup, transpose: setup.transpose - 1 }); }}>
                  <Icon name="minus" size={14} />
                </button>
                <span className="min-w-[64px] text-center font-display text-[22px] leading-none font-[740] tabular" aria-live="polite">
                  {prettyChord(key)}
                  {setup.transpose !== 0 && (
                    <span className="ml-1 font-mono text-caption text-text-dim">{setup.transpose > 0 ? `+${String(setup.transpose)}` : setup.transpose}</span>
                  )}
                </span>
                <button type="button" className="icon-btn size-9" aria-label="Транспонировать на полтона вверх" disabled={setup.transpose >= 12} onClick={() => { setSetup({ ...setup, transpose: setup.transpose + 1 }); }}>
                  <Icon name="plus" size={14} />
                </button>
              </div>
              <span className="ml-2 font-display text-[22px] leading-none font-[740] tabular">{Math.round(arrangement?.tempo ?? song.tempo ?? 0)}</span>
              <span className="eyebrow">BPM</span>
            </div>

            <div className="flex w-full items-center justify-between gap-3 sm:w-auto">
              <button type="button" onClick={() => { setBandOpen(true); }} className="btn btn-ghost h-10 shrink-0 px-3 text-small lg:hidden" aria-label="Состав группы">
                <Icon name="user" size={16} /> <span className="hidden sm:inline">Состав</span>
              </button>
              <Segmented
                size="sm"
                label="Что показать"
                value={mode}
                onChange={setMode}
                options={[
                  { value: "mine", label: "Моя партия" },
                  { value: "score", label: "Партитура" },
                  { value: "chords", label: "Аккорды" },
                ]}
              />
            </div>
          </div>

          <div ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto">
            <AnimatePresence>
              {(arranging || view.rendering) && arrangement === null && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 text-text-dim"
                >
                  <span className="pulse-soft font-display text-[40px] leading-none font-[780] uppercase">Собираю партии</span>
                  <span className="text-small">Пара секунд — раскладываю ноты по грифу</span>
                </motion.div>
              )}
            </AnimatePresence>
            {failure && (
              <div className="m-6 rounded-[14px] border border-danger/40 p-4 text-small text-danger">{failure}</div>
            )}
            {minePart && mode === "mine" && (
              <div className="flex flex-wrap items-center gap-2 px-6 pt-5 text-small text-text-dim">
                <span className="font-semibold text-text">{minePart.title}</span>
                <span>·</span>
                <span>{meta?.tunings.find((t) => t.id === minePart.tuning)?.label ?? minePart.tuning}</span>
                {minePart.capo > 0 && <span>· каподастр на {minePart.capo}</span>}
                {arranging && <span className="pulse-soft">· пересчитываю…</span>}
              </div>
            )}
            {mode === "chords" && arrangement && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: EASE_FILM }}
              >
                <ChordsView arrangement={arrangement} part={minePart} />
              </motion.div>
            )}
            {/* Табы остаются в разметке (alphaTab не пересчитывает раскладку), просто скрыты. */}
            <div
              ref={host}
              aria-hidden={mode === "chords"}
              className={`at-surface px-2 pt-2 pb-24 ${mode === "chords" ? "invisible max-h-0 overflow-hidden" : ""}`}
            />
            {view.error && (
              <p className="m-6 text-small text-danger">Не получилось показать табы: {view.error}</p>
            )}
          </div>
        </main>
      </div>
      <PlayerBar
        controls={controls}
        parts={arrangement?.parts ?? []}
        mix={mix}
        onMix={(index, next) => {
          setMix((current) => current.map((state, i) => (i === index ? next : state)));
        }}
        onExport={onExport}
      />
    </div>
  );
}
