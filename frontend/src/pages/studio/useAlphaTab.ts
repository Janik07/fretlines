import * as alphaTab from "@coderline/alphatab";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import type { Theme } from "../../store/theme";

/**
 * alphaTab: табы в SVG и встроенный синтезатор с гитарным SoundFont.
 * Плеер играет все партии сразу — «моя» показывается крупно, остальные звучат вокруг (SPEC §1.3).
 * Он же — часы для записи (useRecording): позиция в тиках переводится в секунды записи.
 */

export interface PlayerView {
  ready: boolean;
  soundProgress: number;
  /** Загружен большой банк гитарных звуков (иначе — маленький встроенный). */
  hqSound: boolean;
  playing: boolean;
  time: number;
  tick: number;
  endTime: number;
  bar: number;
  bars: number;
  speed: number;
  looping: boolean;
  loop: [number, number] | null;
  metronome: boolean;
  countIn: boolean;
  rendering: boolean;
  error: string | null;
}

const INITIAL: PlayerView = {
  ready: false,
  soundProgress: 0,
  hqSound: false,
  playing: false,
  time: 0,
  tick: 0,
  endTime: 0,
  bar: 0,
  bars: 0,
  speed: 1,
  looping: false,
  loop: null,
  metronome: false,
  countIn: false,
  rendering: true,
  error: null,
};

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function resources(): alphaTab.json.RenderingResourcesJson {
  const text = cssVar("--text");
  const dim = cssVar("--text-dim");
  const line = cssVar("--line-strong");
  const sans = "'Sofia Sans Variable', sans-serif";
  return {
    mainGlyphColor: text,
    secondaryGlyphColor: dim,
    scoreInfoColor: text,
    staffLineColor: line,
    barSeparatorColor: line,
    barNumberColor: dim,
    tablatureFont: `13px 'IBM Plex Mono', monospace`,
    graceFont: `11px 'IBM Plex Mono', monospace`,
    elementFonts: new Map([
      ["BarNumber", `11px ${sans}`],
      ["EffectMarker", `bold 14px ${sans}`],
      ["ChordDiagramFretboardNumbers", `11px ${sans}`],
      ["TrackNames", `600 13px ${sans}`],
      ["GuitarTuning", `12px ${sans}`],
    ]),
  };
}

const HIDDEN = [
  "ScoreTitle",
  "ScoreSubTitle",
  "ScoreArtist",
  "ScoreAlbum",
  "ScoreWords",
  "ScoreMusic",
  "ScoreWordsAndMusic",
  "ScoreCopyright",
  "EffectTempo",
  "EffectDynamics",
] as const;

export interface PlayerTick {
  tick: number;
  playing: boolean;
  speed: number;
}

export interface BarTicks {
  starts: number[];
  durations: number[];
}

export interface AlphaTabControls {
  view: PlayerView;
  /** Такты партитуры в тиках — для перевода позиции в секунды записи. */
  bars: BarTicks;
  /** Подписка на позицию плеера без перерисовки React — для синхронизации записи. */
  subscribe: (listener: (state: PlayerTick) => void) => () => void;
  playPause: () => void;
  stop: () => void;
  seekBar: (delta: number) => void;
  seekRatio: (ratio: number) => void;
  seekTick: (tick: number) => void;
  toggleLoop: () => void;
  setSpeed: (speed: number) => void;
  toggleMetronome: () => void;
  toggleCountIn: () => void;
  setTrackState: (index: number, state: { mute: boolean; solo: boolean; volume: number }) => void;
  print: () => void;
  /** Сам плеер — для рендера студийного звука (render.ts). */
  api: () => alphaTab.AlphaTabApi | null;
  exportGp: (filename: string) => void;
  exportMidi: () => void;
}

export function useAlphaTab(
  host: RefObject<HTMLDivElement | null>,
  scroller: RefObject<HTMLDivElement | null>,
  tex: string | null,
  visible: number[] | null,
  theme: Theme,
): AlphaTabControls {
  const apiRef = useRef<alphaTab.AlphaTabApi | null>(null);
  const barStarts = useRef<number[]>([]);
  const [bars, setBars] = useState<BarTicks>({ starts: [], durations: [] });
  const [view, setView] = useState<PlayerView>(INITIAL);
  const listeners = useRef(new Set<(state: PlayerTick) => void>());
  const live = useRef<PlayerTick>({ tick: 0, playing: false, speed: 1 });
  const patch = useCallback((next: Partial<PlayerView>) => {
    setView((current) => ({ ...current, ...next }));
  }, []);
  const emit = useCallback((next: Partial<PlayerTick>) => {
    live.current = { ...live.current, ...next };
    for (const listener of listeners.current) listener(live.current);
  }, []);

  useEffect(() => {
    const element = host.current;
    const scroll = scroller.current;
    if (!element || !scroll) return;
    const settings: alphaTab.json.SettingsJson = {
      core: { engine: "svg", fontDirectory: "/font/", logLevel: "warning" },
      display: {
        layoutMode: "page",
        staveProfile: "tab",
        scale: 1,
        resources: resources(),
      },
      notation: { elements: new Map(HIDDEN.map((name) => [name, false])) },
      player: {
        playerMode: "EnabledSynthesizer",
        soundFont: "/soundfont/sonivox.sf3",
        scrollElement: scroll,
        scrollOffsetY: -96,
        enableCursor: true,
        enableAnimatedBeatCursor: true,
        enableUserInteraction: true,
      },
    };
    const api = new alphaTab.AlphaTabApi(element, settings);
    apiRef.current = api;

    api.soundFontLoad.on((e) => {
      patch({ soundProgress: e.total ? e.loaded / e.total : 0 });
    });
    let upgraded = false;
    api.playerReady.on(() => {
      patch({ ready: true, soundProgress: 1 });
      if (!upgraded) {
        upgraded = true;
        void loadBetterSound(api).then((ok) => {
          if (ok) patch({ hqSound: true });
        });
      }
    });
    api.renderStarted.on(() => {
      patch({ rendering: true });
    });
    api.renderFinished.on(() => {
      patch({ rendering: false });
    });
    api.scoreLoaded.on((score) => {
      barStarts.current = score.masterBars.map((bar) => bar.start);
      setBars({
        starts: barStarts.current,
        durations: score.masterBars.map((bar) => bar.calculateDuration()),
      });
      patch({ bars: score.masterBars.length, error: null });
    });
    api.playerStateChanged.on((e) => {
      const playing = e.state === alphaTab.synth.PlayerState.Playing;
      patch({ playing });
      emit({ playing, tick: api.tickPosition });
    });
    api.playerPositionChanged.on((e) => {
      emit({ tick: e.currentTick });
      const starts = barStarts.current;
      let bar = 0;
      let lo = 0;
      let hi = starts.length - 1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if ((starts[mid] ?? 0) <= e.currentTick) {
          bar = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }
      patch({ time: e.currentTime, tick: e.currentTick, endTime: e.endTime, bar });
    });
    api.playbackRangeChanged.on((e) => {
      const range = e.playbackRange;
      patch({ loop: range ? [range.startTick, range.endTick] : null });
    });
    api.error.on((error) => {
      patch({ error: error.message, rendering: false });
    });

    return () => {
      api.destroy();
      apiRef.current = null;
    };
  }, [host, scroller, patch, emit]);

  useEffect(() => {
    const api = apiRef.current;
    if (!api || !tex) return;
    api.tex(tex, visible ?? "all");
    // Видимые треки меняет отдельный эффект ниже — без повторного разбора текста.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tex]);

  useEffect(() => {
    const api = apiRef.current;
    if (!api?.score) return;
    const tracks = visible ? visible.map((i) => api.score?.tracks[i]).filter((t) => t !== undefined) : api.score.tracks;
    if (tracks.length) api.renderTracks(tracks);
  }, [visible]);

  useEffect(() => {
    const api = apiRef.current;
    if (!api) return;
    const next = resources();
    const target = api.settings.display.resources;
    target.mainGlyphColor = alphaTab.model.Color.fromJson(next.mainGlyphColor) ?? target.mainGlyphColor;
    target.secondaryGlyphColor = alphaTab.model.Color.fromJson(next.secondaryGlyphColor) ?? target.secondaryGlyphColor;
    target.scoreInfoColor = alphaTab.model.Color.fromJson(next.scoreInfoColor) ?? target.scoreInfoColor;
    target.staffLineColor = alphaTab.model.Color.fromJson(next.staffLineColor) ?? target.staffLineColor;
    target.barSeparatorColor = alphaTab.model.Color.fromJson(next.barSeparatorColor) ?? target.barSeparatorColor;
    target.barNumberColor = alphaTab.model.Color.fromJson(next.barNumberColor) ?? target.barNumberColor;
    api.updateSettings();
    if (api.score) api.render();
  }, [theme]);

  const withApi = useCallback((action: (api: alphaTab.AlphaTabApi) => void) => {
    const api = apiRef.current;
    if (api) action(api);
  }, []);

  const subscribe = useCallback((listener: (state: PlayerTick) => void) => {
    listeners.current.add(listener);
    listener(live.current);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  return {
    view,
    bars,
    subscribe,
    playPause: () => {
      withApi((api) => {
        api.playPause();
      });
    },
    seekTick: (tick) => {
      withApi((api) => {
        api.tickPosition = Math.max(0, tick);
      });
    },
    stop: () => {
      withApi((api) => {
        api.stop();
      });
    },
    seekBar: (delta) => {
      withApi((api) => {
        const starts = barStarts.current;
        const target = Math.max(0, Math.min(starts.length - 1, view.bar + delta));
        api.tickPosition = starts[target] ?? 0;
      });
    },
    seekRatio: (ratio) => {
      withApi((api) => {
        api.timePosition = Math.max(0, Math.min(1, ratio)) * (view.endTime || api.endTime);
      });
    },
    toggleLoop: () => {
      withApi((api) => {
        if (api.isLooping) {
          api.isLooping = false;
          patch({ looping: false });
          return;
        }
        if (!api.playbackRange) {
          const starts = barStarts.current;
          const range = new alphaTab.synth.PlaybackRange();
          range.startTick = starts[view.bar] ?? 0;
          range.endTick = starts[Math.min(view.bar + 2, starts.length - 1)] ?? api.endTick;
          if (range.endTick <= range.startTick) range.endTick = api.endTick;
          api.playbackRange = range;
          patch({ loop: [range.startTick, range.endTick] });
        }
        api.isLooping = true;
        patch({ looping: true });
      });
    },
    setSpeed: (speed) => {
      withApi((api) => {
        api.playbackSpeed = speed;
      });
      patch({ speed });
      emit({ speed });
    },
    toggleMetronome: () => {
      withApi((api) => {
        const on = api.metronomeVolume === 0;
        api.metronomeVolume = on ? 1 : 0;
        patch({ metronome: on });
      });
    },
    toggleCountIn: () => {
      withApi((api) => {
        const on = api.countInVolume === 0;
        api.countInVolume = on ? 1 : 0;
        patch({ countIn: on });
      });
    },
    setTrackState: (index, state) => {
      withApi((api) => {
        const track = api.score?.tracks[index];
        if (!track) return;
        api.changeTrackMute([track], state.mute);
        api.changeTrackSolo([track], state.solo);
        api.changeTrackVolume([track], state.volume);
      });
    },
    api: () => apiRef.current,
    print: () => {
      withApi((api) => {
        api.print();
      });
    },
    exportGp: (filename) => {
      withApi((api) => {
        if (!api.score) return;
        const data = new alphaTab.exporter.Gp7Exporter().export(api.score, api.settings);
        const blob = new Blob([data.slice().buffer], { type: "application/octet-stream" });
        download(blob, `${filename}.gp`);
      });
    },
    exportMidi: () => {
      withApi((api) => {
        api.downloadMidi();
      });
    },
  };
}

/**
 * Большой банк звуков (MuseScore General, MIT, ~40 МБ) — гитары в нём записаны по-настоящему.
 * Сервер скачивает его сам; пока его нет, играет маленький встроенный банк. Подменяем, когда
 * плеер стоит, — чтобы не оборвать звук посреди игры.
 */
const SOUNDFONT_URL = "/api/soundfont";
const SOUNDFONT_STORE = "fretlines-soundfont-v1";

/**
 * Большой банк звуков (40 МБ): из хранилища браузера, иначе с сервера — и сразу туда.
 * HTTP-кэш такой файл через облачный прокси не держит, а по медленному каналу он качается
 * минуты; длинную загрузку канал иногда рвёт — тогда пробуем ещё раз.
 */
async function fetchSoundFont(): Promise<Uint8Array<ArrayBuffer> | null> {
  let store: Cache | null;
  try {
    store = await caches.open(SOUNDFONT_STORE);
    const hit = await store.match(SOUNDFONT_URL);
    if (hit) return new Uint8Array(await hit.arrayBuffer());
  } catch {
    store = null; // нет хранилища (приватный режим, не https) — просто качаем
  }
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const response = await fetch(SOUNDFONT_URL);
      if (!response.ok) return null; // сервер ещё сам качает банк
      const data = new Uint8Array(await response.arrayBuffer());
      await store?.put(SOUNDFONT_URL, new Response(data)).catch(() => undefined);
      return data;
    } catch {
      // обрыв — ещё одна попытка
    }
  }
  return null;
}

async function loadBetterSound(api: alphaTab.AlphaTabApi): Promise<boolean> {
  try {
    const data = await fetchSoundFont();
    if (!data) return false;
    for (let i = 0; i < 600 && api.playerState === alphaTab.synth.PlayerState.Playing; i++) {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    return api.loadSoundFont(data, false);
  } catch {
    return false;
  }
}

export function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 2000);
}
