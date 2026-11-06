import * as alphaTab from "@coderline/alphatab";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import type { Theme } from "../../store/theme";

/**
 * alphaTab: табы в SVG и встроенный синтезатор с гитарным SoundFont.
 * Плеер играет все партии сразу — «моя» показывается крупно, остальные звучат вокруг (SPEC §1.3).
 */

export interface PlayerView {
  ready: boolean;
  soundProgress: number;
  playing: boolean;
  time: number;
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
  playing: false,
  time: 0,
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

export interface AlphaTabControls {
  view: PlayerView;
  playPause: () => void;
  stop: () => void;
  seekBar: (delta: number) => void;
  seekRatio: (ratio: number) => void;
  toggleLoop: () => void;
  setSpeed: (speed: number) => void;
  toggleMetronome: () => void;
  toggleCountIn: () => void;
  setTrackState: (index: number, state: { mute: boolean; solo: boolean; volume: number }) => void;
  print: () => void;
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
  const [view, setView] = useState<PlayerView>(INITIAL);
  const patch = useCallback((next: Partial<PlayerView>) => {
    setView((current) => ({ ...current, ...next }));
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
    api.playerReady.on(() => {
      patch({ ready: true, soundProgress: 1 });
    });
    api.renderStarted.on(() => {
      patch({ rendering: true });
    });
    api.renderFinished.on(() => {
      patch({ rendering: false });
    });
    api.scoreLoaded.on((score) => {
      barStarts.current = score.masterBars.map((bar) => bar.start);
      patch({ bars: score.masterBars.length, error: null });
    });
    api.playerStateChanged.on((e) => {
      patch({ playing: e.state === alphaTab.synth.PlayerState.Playing });
    });
    api.playerPositionChanged.on((e) => {
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
      patch({ time: e.currentTime, endTime: e.endTime, bar });
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
  }, [host, scroller, patch]);

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

  return {
    view,
    playPause: () => {
      withApi((api) => {
        api.playPause();
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
