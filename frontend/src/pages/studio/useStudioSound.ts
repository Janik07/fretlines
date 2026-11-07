import { useEffect, useMemo, useRef, useState } from "react";

import type { Arrangement } from "../../lib/api";
import type { TrackMix } from "./PlayerBar";
import { mixToWav, renderParts, type RenderedPart } from "./render";
import type { AlphaTabControls } from "./useAlphaTab";

/**
 * Студийный звук партий: рендер после каждой смены партитуры или тембров, сведение — после
 * каждого движения микшера (без нового рендера). Пока звук готовится, играет встроенный синтезатор.
 */

export interface StudioSound {
  status: "off" | "rendering" | "ready" | "error";
  progress: number;
  url: string | null;
}

function gains(mix: TrackMix[], count: number): number[] {
  const solo = mix.some((m) => m.solo);
  return Array.from({ length: count }, (_, i) => {
    const state = mix[i] ?? { mute: false, solo: false, volume: 1 };
    if (solo) return state.solo ? state.volume : 0;
    return state.mute ? 0 : state.volume;
  });
}

export function useStudioSound(
  controls: AlphaTabControls,
  arrangement: Arrangement | null,
  mix: TrackMix[],
  enabled: boolean,
): StudioSound {
  const cache = useRef(new Map<string, RenderedPart>());
  const [parts, setParts] = useState<RenderedPart[] | null>(null);
  const [status, setStatus] = useState<StudioSound["status"]>("off");
  const [progress, setProgress] = useState(0);
  const { view } = controls;
  const scoreReady = view.ready && !view.rendering && controls.bars.starts.length > 0;
  const tex = arrangement?.alphatex ?? null;
  const tones = useMemo(() => arrangement?.parts.map((p) => p.tone).join(",") ?? "", [arrangement]);

  useEffect(() => {
    if (!enabled || !tex || !scoreReady || !arrangement) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      const api = controls.api();
      if (!api?.score) return;
      setStatus("rendering");
      setProgress(0);
      const job = { tex, parts: arrangement.parts.map((p, index) => ({ index, tone: p.tone })) };
      renderParts(api, job, cache.current, setProgress, () => cancelled)
        .then((rendered) => {
          if (cancelled || !rendered) return;
          // В кэше держим только то, что звучит сейчас: партии весят десятки мегабайт.
          const keep = new Set(rendered.map((r) => r.key));
          for (const key of cache.current.keys()) if (!keep.has(key)) cache.current.delete(key);
          setParts(rendered);
          setStatus("ready");
        })
        .catch(() => {
          if (!cancelled) setStatus("error");
        });
    }, 700);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // controls пересоздаётся каждый рендер; важны текст партитуры, тембры и готовность плеера.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, tex, tones, scoreReady]);

  const levels = useMemo(() => gains(mix, parts?.length ?? 0).join(","), [mix, parts]);
  // Сведение — производное от партий и микшера: пересобирается только когда они меняются.
  const url = useMemo(
    () => (parts && enabled ? URL.createObjectURL(mixToWav(parts.map((p) => p.buffer), levels.split(",").map(Number))) : null),
    [parts, levels, enabled],
  );
  useEffect(() => {
    return () => {
      // Плеер ещё дочитывает старое сведение, пока грузит новое, — отпускаем его с запасом.
      if (url) {
        window.setTimeout(() => {
          URL.revokeObjectURL(url);
        }, 10_000);
      }
    };
  }, [url]);

  const live = enabled && status === "ready" && parts !== null;
  return { status: enabled ? status : "off", progress, url: live ? url : null };
}
