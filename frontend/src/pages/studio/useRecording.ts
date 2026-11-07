import { useCallback, useEffect, useRef, useState } from "react";

import { tickToSeconds, usable, type Timeline } from "./timeline";
import type { AlphaTabControls } from "./useAlphaTab";

/**
 * Запись песни (оригинал или без дорожек группы) звучит в такт плееру alphaTab.
 *
 * Часы — синтезатор alphaTab: темп в табах повторяет запись по тактам, поэтому позиция в табах
 * однозначно переводится в секунды записи. Аудио догоняет: небольшой разбег выбирается чуть
 * более быстрой или медленной игрой (высота не меняется), большой — перемоткой.
 */

const HARD_SEEK = 0.3; // с — разбег больше: перематываем
// Разбег до 70 мс не трогаем: позиция плеера и время аудио сами по себе расходятся на десятки
// миллисекунд (буферы звука), и подгонять скорость под эту разницу — только дёргать запись.
const DEADBAND = 0.07;
const CAUGHT_UP = 0.02; // догоняем, пока разбег не станет меньше этого
const NUDGE = 0.03; // ±3 % скорости при догонялках — на слух незаметно
const SETTLE_MS = 400; // после перемотки и старта даём аудио устояться

export interface Recording {
  ready: boolean;
  loading: boolean;
  error: string | null;
  /** Вызвать прямо в обработчике нажатия «Играть»: браузеры разрешают звук только после жеста. */
  unlock: () => void;
}

export function useRecording(
  controls: AlphaTabControls,
  src: string | null,
  timeline: Timeline | null,
  volume: number,
  offset = 0, // сдвиг в секундах: студийный звук партий начинается с начала первого такта
): Recording {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const settleUntil = useRef(0);
  const wantPlay = useRef(false);
  const timelineRef = useRef<Timeline | null>(timeline);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { subscribe } = controls;

  const offsetRef = useRef(offset);
  useEffect(() => {
    timelineRef.current = timeline;
    offsetRef.current = offset;
  }, [timeline, offset]);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "auto";
    audio.preservesPitch = true;
    // В документе — чтобы было видно в инструментах разработчика (data-target — где должна быть запись).
    audio.hidden = true;
    audio.dataset.role = "recording";
    document.body.appendChild(audio);
    audioRef.current = audio;
    const onReady = () => {
      setReady(true);
      setLoading(false);
    };
    const onWait = () => {
      setLoading(true);
    };
    const onError = () => {
      setLoading(false);
      setError("Запись не загрузилась — попробуй обновить страницу.");
    };
    audio.addEventListener("canplay", onReady);
    audio.addEventListener("waiting", onWait);
    audio.addEventListener("playing", onReady);
    audio.addEventListener("error", onError);
    return () => {
      audio.pause();
      audio.removeEventListener("canplay", onReady);
      audio.removeEventListener("waiting", onWait);
      audio.removeEventListener("playing", onReady);
      audio.removeEventListener("error", onError);
      audio.removeAttribute("src");
      audio.load();
      audio.remove();
      audioRef.current = null;
    };
  }, []);

  // Смена сведения (например, «без гитары»): то же место песни, та же игра/пауза.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!src) {
      audio.pause();
      return;
    }
    const absolute = new URL(src, window.location.href).href;
    if (audio.src === absolute) return;
    const wasPlaying = !audio.paused;
    const position = audio.currentTime;
    setReady(false);
    setLoading(true);
    setError(null);
    audio.src = src;
    const restore = () => {
      audio.currentTime = position;
      settleUntil.current = performance.now() + SETTLE_MS;
      if (wasPlaying) void audio.play().catch(() => undefined);
    };
    audio.addEventListener("loadedmetadata", restore, { once: true });
  }, [src]);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio) audio.volume = Math.max(0, Math.min(1, volume));
  }, [volume]);

  useEffect(() => {
    let lastTick = -1;
    let chasing = false;
    let smoothed = 0;
    return subscribe(({ tick, playing, speed }) => {
      const audio = audioRef.current;
      const map = timelineRef.current;
      // Плеер «играет», но позиция стоит — это отсчёт перед стартом или первый миг после
      // нажатия: запись ждёт, пока табы реально пойдут.
      const moving = tick > lastTick;
      lastTick = tick;
      wantPlay.current = playing && src !== null;
      if (!audio || !src || !usable(map)) {
        if (audio && !audio.paused) audio.pause();
        return;
      }
      const target = tickToSeconds(map, tick) - offsetRef.current;
      audio.dataset.target = target.toFixed(3);
      if (target < 0) {
        // Первый такт начинается раньше записи (затакт до первого звука): запись ждёт нуля.
        if (!audio.paused) audio.pause();
        if (audio.currentTime > 0.05 && audio.readyState >= 1) audio.currentTime = 0;
        return;
      }
      if (!playing || !moving) {
        if (!audio.paused) audio.pause();
        if (Math.abs(audio.currentTime - target) > 0.05 && audio.readyState >= 1) {
          audio.currentTime = target;
        }
        return;
      }
      if (audio.paused) {
        audio.currentTime = target;
        audio.playbackRate = speed;
        settleUntil.current = performance.now() + SETTLE_MS;
        chasing = false;
        smoothed = 0;
        void audio.play().catch(() => undefined);
        return;
      }
      if (performance.now() < settleUntil.current) return;
      const drift = audio.currentTime - target;
      if (Math.abs(drift) > HARD_SEEK) {
        audio.currentTime = target;
        audio.playbackRate = speed;
        settleUntil.current = performance.now() + SETTLE_MS;
        chasing = false;
        smoothed = 0;
        return;
      }
      // Отдельные замеры скачут на ±20 мс — решаем по сглаженному разбегу.
      smoothed = smoothed * 0.7 + drift * 0.3;
      if (!chasing && Math.abs(smoothed) > DEADBAND) chasing = true;
      if (chasing && Math.abs(smoothed) < CAUGHT_UP) chasing = false;
      // Отстали — чуть быстрее, убежали — чуть медленнее.
      const rate = chasing ? speed * (1 + (smoothed < 0 ? NUDGE : -NUDGE)) : speed;
      if (Math.abs(audio.playbackRate - rate) > 1e-3) audio.playbackRate = rate;
    });
  }, [subscribe, src]);

  const unlock = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !src || !audio.paused) return;
    // Беззвучный старт в момент нажатия «разрешает» звук; дальше аудио ведёт синхронизация.
    audio.muted = true;
    void audio
      .play()
      .then(() => {
        audio.muted = false;
        if (!wantPlay.current) audio.pause();
      })
      .catch(() => {
        audio.muted = false;
      });
  }, [src]);

  return { ready, loading, error, unlock };
}
