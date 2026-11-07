import * as alphaTab from "@coderline/alphatab";

import { applyTone, DRY_PROGRAM, isTone, type Tone } from "./tone";

/**
 * Студийный звук партий: alphaTab рендерит каждую партию отдельно «сухой» гитарой,
 * дальше tone.ts пропускает её через свой тракт, и всё сводится в один WAV.
 * Плеер играет этот WAV в такт табам (useRecording) — так звук не ограничен синтезатором.
 */

// Только 44.1 кГц: на других частотах синтезатор alphaTab 1.9 при выгрузке выдаёт NaN вместо звука.
const RATE = 44_100;

export interface RenderedPart {
  key: string; // от чего зависит звук: текст партитуры, номер партии, тембр, банк звуков
  buffer: AudioBuffer;
}

/** Сухая партия: один трек партитуры, программа подменена на «чистую» гитару для тракта. */
async function renderDry(
  api: alphaTab.AlphaTabApi,
  index: number,
  tone: Tone,
  onProgress: (fraction: number) => void,
  cancelled: () => boolean,
): Promise<AudioBuffer | null> {
  const score = api.score;
  const track = score?.tracks[index];
  if (!score || !track) return null;
  const options = new alphaTab.synth.AudioExportOptions();
  options.sampleRate = RATE;
  options.useSyncPoints = false;
  options.masterVolume = 1;
  options.metronomeVolume = 0;
  score.tracks.forEach((_, i) => options.trackVolume.set(i, i === index ? 1 : 0));
  // Партитура для экспорта собирается сразу при вызове — подменяем программу только на этот момент.
  const program = track.playbackInfo.program;
  track.playbackInfo.program = DRY_PROGRAM[tone];
  const pending = api.exportAudio(options);
  track.playbackInfo.program = program;
  const exporter = await pending;
  const chunks: Float32Array[] = [];
  let samples = 0;
  try {
    for (;;) {
      if (cancelled()) return null;
      const chunk = await exporter.render(8000);
      if (!chunk) break;
      chunks.push(chunk.samples);
      samples += chunk.samples.length;
      onProgress(chunk.endTime ? Math.min(1, chunk.currentTime / chunk.endTime) : 0);
    }
  } finally {
    exporter.destroy();
  }
  const frames = Math.floor(samples / 2);
  const buffer = new AudioBuffer({ numberOfChannels: 2, length: Math.max(1, frames), sampleRate: RATE });
  const left = buffer.getChannelData(0);
  const right = buffer.getChannelData(1);
  let frame = 0;
  for (const chunk of chunks) {
    for (let i = 0; i + 1 < chunk.length; i += 2) {
      left[frame] = chunk[i] ?? 0;
      right[frame] = chunk[i + 1] ?? 0;
      frame++;
    }
  }
  return buffer;
}

export interface RenderJob {
  parts: { index: number; tone: string }[];
  tex: string;
  beat: number; // длина доли в секундах — под неё эхо в тембрах с дилеем
  bank: "hq" | "base"; // каким банком звуков рендерили: большой приходит позже — тогда заново
}

/** Рендер всех партий; уже готовые (тот же текст и тембр) берутся из кэша. */
export async function renderParts(
  api: alphaTab.AlphaTabApi,
  job: RenderJob,
  cache: Map<string, RenderedPart>,
  onProgress: (fraction: number) => void,
  cancelled: () => boolean,
): Promise<RenderedPart[] | null> {
  const out: RenderedPart[] = [];
  const total = job.parts.length;
  for (const [n, part] of job.parts.entries()) {
    const tone: Tone = isTone(part.tone) ? part.tone : "clean";
    const key = `${String(hash(job.tex))}:${String(part.index)}:${tone}:${job.bank}`;
    const cached = cache.get(key);
    if (cached) {
      out.push(cached);
      continue;
    }
    const dry = await renderDry(
      api,
      part.index,
      tone,
      (f) => {
        onProgress((n + f * 0.85) / total);
      },
      cancelled,
    );
    if (!dry || cancelled()) return null;
    const wet = await applyTone(dry, tone, job.beat);
    const rendered = { key, buffer: wet };
    cache.set(key, rendered);
    out.push(rendered);
    onProgress((n + 1) / total);
  }
  return out;
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Сведение партий с громкостями микшера → WAV (16 бит) для аудиоплеера. */
export function mixToWav(parts: AudioBuffer[], gains: number[]): Blob {
  const length = Math.max(1, ...parts.map((p) => p.length));
  const left = new Float32Array(length);
  const right = new Float32Array(length);
  parts.forEach((part, i) => {
    const gain = gains[i] ?? 1;
    if (gain <= 0) return;
    const l = part.getChannelData(0);
    const r = part.numberOfChannels > 1 ? part.getChannelData(1) : l;
    for (let j = 0; j < part.length; j++) {
      left[j] = (left[j] ?? 0) + (l[j] ?? 0) * gain;
      right[j] = (right[j] ?? 0) + (r[j] ?? 0) * gain;
    }
  });
  let top = 0;
  for (let j = 0; j < length; j += 2) top = Math.max(top, Math.abs(left[j] ?? 0), Math.abs(right[j] ?? 0));
  const scale = top > 0.98 ? 0.98 / top : 1;
  const bytes = new ArrayBuffer(44 + length * 4);
  const view = new DataView(bytes);
  const write = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + length * 4, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 2, true);
  view.setUint32(24, RATE, true);
  view.setUint32(28, RATE * 4, true);
  view.setUint16(32, 4, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, length * 4, true);
  let offset = 44;
  for (let j = 0; j < length; j++) {
    view.setInt16(offset, Math.max(-1, Math.min(1, (left[j] ?? 0) * scale)) * 0x7fff, true);
    view.setInt16(offset + 2, Math.max(-1, Math.min(1, (right[j] ?? 0) * scale)) * 0x7fff, true);
    offset += 4;
  }
  return new Blob([bytes], { type: "audio/wav" });
}
