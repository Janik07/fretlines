import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Header } from "../../components/Header";
import { Icon } from "../../components/Icon";
import { Segmented } from "../../components/Segmented";
import { useMeta } from "../../hooks/useApi";
import {
  api,
  type Analysis,
  type Arrangement,
  type Lyrics,
  type Song,
  type SoundSource,
  type StemName,
  type StudioSetup,
} from "../../lib/api";
import { keyWords, prettyChord } from "../../lib/format";
import { EASE_FILM } from "../../lib/motion";
import { navigate, type Route } from "../../lib/router";
import { useThemeStore } from "../../store/theme";
import { BandPanel } from "./BandPanel";
import { ChordsView } from "./ChordsView";
import { KaraokeStrip, LyricsSheet } from "./Lyrics";
import { PlayerBar, type TrackMix } from "./PlayerBar";
import { StemsView } from "./StemsView";
import { coveredStems, defaultSetup } from "./setup";
import { secondsToTick, tickToSeconds, usable, type Timeline } from "./timeline";
import { download, useAlphaTab } from "./useAlphaTab";
import { useRecording } from "./useRecording";
import { useStudioSound } from "./useStudioSound";

type Mode = "mine" | "score" | "chords" | "text" | "stems";

function fileName(title: string): string {
  return title.replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 80) || "fretlines";
}

/** Узкий экран (телефон): подписи короче, переключатели — на всю ширину. */
function useNarrow(): boolean {
  const query = "(max-width: 639px)";
  const [narrow, setNarrow] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => {
      setNarrow(list.matches);
    };
    list.addEventListener("change", onChange);
    return () => {
      list.removeEventListener("change", onChange);
    };
  }, []);
  return narrow;
}

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function Studio({ song, route, onRefresh }: { song: Song; route: Route; onRefresh: () => void }) {
  const meta = useMeta();
  const theme = useThemeStore((s) => s.theme);
  const narrow = useNarrow();
  const [setup, setSetup] = useState<StudioSetup | null>(song.setup);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [lyrics, setLyrics] = useState<Lyrics | null>(null);
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [arranging, setArranging] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("mine");
  const [mix, setMix] = useState<TrackMix[]>([]);
  const [bandOpen, setBandOpen] = useState(false);
  const [karaoke, setKaraoke] = useState(true);
  const [recordVolume, setRecordVolume] = useState(0.9);
  const [reanalyzing, setReanalyzing] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const firstSave = useRef(true);

  useEffect(() => {
    let alive = true;
    api
      .analysis(song.id)
      .then((data) => {
        if (!alive) return;
        setAnalysis(data);
        // Новый разбор: состав по умолчанию зависит от того, нашлась ли гитара в записи.
        setSetup((current) => current ?? defaultSetup(meta, data));
      })
      .catch(() => {
        if (alive) setSetup((current) => current ?? defaultSetup(meta));
      });
    api
      .lyrics(song.id)
      .then((data) => {
        if (alive) setLyrics(data.lines.length ? data : null);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
    // meta нужна только для подписей пресета — ждать её незачем
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [song.id]);

  // Пересчёт партий по составу — без повторного анализа (SPEC §1.5).
  useEffect(() => {
    if (!setup) return;
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
    // Звук и заглушённые дорожки на партии не влияют — пересчёт только по составу.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [song.id, setup?.players, setup?.transpose, setup?.lyricsInTabs]);

  // Состав и правки сохраняются в разборе — откроешь завтра, всё на месте.
  useEffect(() => {
    if (!setup) return;
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

  const players = useMemo(() => setup?.players ?? [], [setup?.players]);

  // Новый режим — с начала страницы, а не с того места, где остановились табы.
  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
  }, [mode]);
  const mineIndex = Math.max(0, players.findIndex((p) => p.id === setup?.mine));
  // Какие табы показаны, решают только режимы с табами: в «Аккордах», «Тексте» и «Дорожках»
  // остаётся прежний выбор — иначе alphaTab перерисует скрытые табы и прокрутит страницу к курсору.
  const [tabsMode, setTabsMode] = useState<"mine" | "score">("mine");
  if ((mode === "mine" || mode === "score") && mode !== tabsMode) setTabsMode(mode);
  const visible = useMemo(() => (tabsMode === "mine" ? [mineIndex] : null), [tabsMode, mineIndex]);
  const controls = useAlphaTab(host, scroller, arrangement?.alphatex ?? null, visible, theme);
  const { view } = controls;

  const timeline = useMemo<Timeline | null>(
    () =>
      arrangement
        ? { barTicks: controls.bars.starts, barDurations: controls.bars.durations, barSeconds: arrangement.bar_seconds }
        : null,
    [arrangement, controls.bars],
  );
  const synced = usable(timeline) && controls.bars.starts.length === arrangement?.bars;
  const sound: SoundSource = synced ? (setup?.sound ?? "record") : "parts";
  const muted = useMemo(() => setup?.muted ?? [], [setup?.muted]);
  const without = useMemo<StemName[]>(() => {
    if (sound === "record") return muted;
    return [...new Set<StemName>([...coveredStems(players), ...muted])];
  }, [sound, muted, players]);
  const recordSrc = sound === "parts" ? null : api.mixUrl(song.id, without);
  const recording = useRecording(controls, recordSrc, synced ? timeline : null, recordVolume);
  // Партии студийным звуком (усилитель, кабинет, комната) — см. tone.ts. Синтезатор тогда только ведёт время.
  const studio = useStudioSound(controls, arrangement, mix, synced && sound !== "record");
  const partsSrc = sound === "record" ? null : studio.url;
  const partsPlayer = useRecording(
    controls,
    partsSrc,
    synced ? timeline : null,
    1,
    arrangement?.bar_seconds[0] ?? 0,
  );
  const seconds = synced ? tickToSeconds(timeline, view.tick) : view.time / 1000;

  useEffect(() => {
    if (!view.ready || view.rendering) return;
    mix.forEach((state, index) => {
      // В режиме «Запись» синтезатор только ведёт время — партии не звучат.
      const silent = sound === "record" || partsSrc !== null;
      controls.setTrackState(index, { ...state, mute: state.mute || silent });
    });
    // controls пересоздаётся каждый рендер; важны только состояние микшера и готовность плеера.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mix, view.ready, view.rendering, arrangement, sound, partsSrc]);

  const toggleMineMute = useCallback(() => {
    setMix((current) =>
      current.map((state, i) => (i === mineIndex ? { ...state, mute: !state.mute } : state)),
    );
  }, [mineIndex]);

  const { unlock } = recording;
  const { unlock: unlockParts } = partsPlayer;
  const playPause = useCallback(() => {
    unlock();
    unlockParts();
    controls.playPause();
  }, [unlock, unlockParts, controls]);

  const seekSeconds = useCallback(
    (value: number) => {
      if (synced) controls.seekTick(secondsToTick(timeline, value));
    },
    [synced, timeline, controls],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (typing(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.code === "Space") {
        event.preventDefault();
        playPause();
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
  }, [controls, toggleMineMute, playPause]);

  function onExport(kind: "pdf" | "gp" | "midi" | "tex") {
    const name = fileName(song.title);
    if (kind === "pdf") controls.print();
    if (kind === "gp") controls.exportGp(name);
    if (kind === "midi") controls.exportMidi();
    if (kind === "tex" && arrangement) download(new Blob([arrangement.alphatex], { type: "text/plain" }), `${name}.atex`);
  }

  function reanalyze() {
    setReanalyzing(true);
    api
      .retry(song.id)
      .then(onRefresh)
      .catch(() => {
        setReanalyzing(false);
      });
  }

  const minePart = arrangement?.parts[mineIndex] ?? null;
  const key = arrangement?.key ?? song.key ?? "";
  const update = (next: Partial<StudioSetup>) => {
    setSetup((current) => (current ? { ...current, ...next } : current));
  };
  const modes: { value: Mode; label: string }[] = [
    { value: "mine", label: narrow ? "Моя" : "Моя партия" },
    { value: "score", label: narrow ? "Все" : "Партитура" },
    { value: "chords", label: "Аккорды" },
  ];
  if (lyrics) modes.push({ value: "text", label: "Текст" });
  if (synced) modes.push({ value: "stems", label: "Дорожки" });

  return (
    <div className="flex h-dvh flex-col">
      <Header route={route} />
      <div className="flex min-h-0 flex-1">
        <aside
          className={`${bandOpen ? "fixed inset-0 z-[1100] block bg-bg" : "hidden"} w-full shrink-0 overflow-y-auto border-r border-line p-5 lg:static lg:block lg:w-[360px]`}
          aria-label="Состав группы"
        >
          {bandOpen && (
            <button type="button" onClick={() => { setBandOpen(false); }} className="icon-btn mb-3 lg:hidden" aria-label="Закрыть состав">
              <Icon name="close" size={18} />
            </button>
          )}
          {setup && <BandPanel setup={setup} meta={meta} arrangement={arrangement} onChange={setSetup} />}
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
                <button type="button" className="icon-btn size-9" aria-label="Транспонировать на полтона вниз" disabled={!setup || setup.transpose <= -12} onClick={() => { if (setup) update({ transpose: setup.transpose - 1 }); }}>
                  <Icon name="minus" size={14} />
                </button>
                <span className="min-w-[64px] text-center font-display text-[22px] leading-none font-[740] tabular" aria-live="polite">
                  {prettyChord(key)}
                  {setup && setup.transpose !== 0 && (
                    <span className="ml-1 font-mono text-caption text-text-dim">{setup.transpose > 0 ? `+${String(setup.transpose)}` : setup.transpose}</span>
                  )}
                </span>
                <button type="button" className="icon-btn size-9" aria-label="Транспонировать на полтона вверх" disabled={!setup || setup.transpose >= 12} onClick={() => { if (setup) update({ transpose: setup.transpose + 1 }); }}>
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
              <div className="min-w-0 flex-1 sm:flex-none">
                <Segmented size="sm" label="Что показать" value={mode} onChange={setMode} options={modes} fill={narrow} />
              </div>
            </div>
          </div>

          {analysis?.outdated && (
            <div className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-5 py-3 text-small sm:px-7">
              <Icon name="spark" size={16} />
              <span className="min-w-[200px] flex-1 text-text-dim">
                Этот разбор сделан старой версией. Обнови его — появятся звук записи в такт табам, партия
                «как в записи», текст песни и точнее аккорды.
              </span>
              <button type="button" className="btn btn-primary h-9 px-4 text-small" disabled={reanalyzing} onClick={reanalyze}>
                <Icon name="retry" size={15} /> {reanalyzing ? "Запускаю…" : "Обновить разбор"}
              </button>
            </div>
          )}

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
            {mode === "text" && arrangement && lyrics && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: EASE_FILM }}
              >
                <LyricsSheet lyrics={lyrics} arrangement={arrangement} seconds={seconds} onSeek={seekSeconds} />
              </motion.div>
            )}
            {mode === "stems" && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: EASE_FILM }}
              >
                <StemsView
                  songId={song.id}
                  analysis={analysis}
                  sound={sound}
                  muted={muted}
                  playing={view.playing}
                  onListen={(next) => {
                    update({ sound: "record", muted: next });
                    if (!view.playing) playPause();
                  }}
                  onMuted={(next) => {
                    update({ muted: next });
                  }}
                  onReanalyze={reanalyze}
                />
              </motion.div>
            )}
            {/* Табы остаются в разметке (alphaTab не пересчитывает раскладку), просто скрыты. */}
            <div
              ref={host}
              aria-hidden={mode === "chords" || mode === "text" || mode === "stems"}
              className={`at-surface px-2 pt-2 pb-24 ${mode === "chords" || mode === "text" || mode === "stems" ? "invisible max-h-0 overflow-hidden" : ""}`}
            />
            {view.error && (
              <p className="m-6 text-small text-danger">Не получилось показать табы: {view.error}</p>
            )}
          </div>
          {lyrics && karaoke && mode !== "text" && mode !== "stems" && synced && (
            <KaraokeStrip lyrics={lyrics} seconds={seconds} onSeek={seekSeconds} />
          )}
        </main>
      </div>
      <PlayerBar
        controls={controls}
        onPlayPause={playPause}
        parts={arrangement?.parts ?? []}
        mix={mix}
        onMix={(index, next) => {
          setMix((current) => current.map((state, i) => (i === index ? next : state)));
        }}
        onExport={onExport}
        sound={sound}
        soundAvailable={synced}
        onSound={(value) => {
          update({ sound: value });
        }}
        stems={analysis?.stems.filter((s): s is StemName => s !== "mix") ?? []}
        muted={muted}
        covered={sound === "together" ? coveredStems(players) : []}
        onMuted={(value) => {
          update({ muted: value });
        }}
        recordVolume={recordVolume}
        onRecordVolume={setRecordVolume}
        recordLoading={sound !== "parts" && recording.loading}
        recordError={sound !== "parts" ? recording.error : null}
        studio={studio}
        lyricsAvailable={lyrics !== null}
        karaoke={karaoke}
        onKaraoke={setKaraoke}
        lyricsInTabs={setup?.lyricsInTabs ?? true}
        onLyricsInTabs={(value) => {
          update({ lyricsInTabs: value });
        }}
      />
    </div>
  );
}
