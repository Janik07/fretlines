/** Клиент API (backend/fretlines_api/routes). Ошибки сервера приходят по-русски в `detail`. */

export type SongStatus = "queued" | "running" | "done" | "failed";
export type Role = "original" | "melody" | "bass" | "rhythm" | "pad" | "percussion";
export type StemName = "vocals" | "bass" | "drums" | "guitar" | "piano" | "other";
export const STEMS: StemName[] = ["vocals", "guitar", "bass", "drums", "piano", "other"];
export type Difficulty = "easy" | "medium" | "full";
export type InstrumentKind = "acoustic" | "electric" | "bass";

export interface Song {
  id: string;
  title: string;
  artist: string | null;
  source_kind: "file" | "url";
  source_url: string | null;
  status: SongStatus;
  stage: string | null;
  progress: number;
  error: { code: string; message: string } | null;
  duration: number | null;
  tempo: number | null;
  key: string | null;
  device: string | null;
  setup: StudioSetup | null;
  created_at: string;
}

export interface Player {
  id: string;
  name: string;
  instrument: InstrumentKind;
  tuning: string;
  capo: number;
  roles: Role[];
  difficulty: Difficulty;
  /** Звук гитары: «auto» — как в записи (см. Meta.tones). */
  tone?: string;
}

/** Что звучит в плеере: партии синтезатором, запись или запись без партий группы + партии. */
export type SoundSource = "parts" | "record" | "together";

export interface StudioSetup {
  players: Player[];
  transpose: number;
  mine: string | null;
  sound?: SoundSource;
  /** Дорожки записи, которые заглушены (в режиме «Вместе» — сверх тех, что играет группа). */
  muted?: StemName[];
  lyricsInTabs?: boolean;
}

export interface Meta {
  tunings: { id: string; label: string; bass: boolean; notes: string[] }[];
  instruments: { id: InstrumentKind; label: string }[];
  roles: { id: Role; label: string }[];
  tones: Record<InstrumentKind, { id: string; label: string }[]>;
  difficulties: { id: Difficulty; label: string }[];
  presets: { id: string; label: string; players: { name: string; roles: Role[] }[] }[];
  limits: { max_upload_mb: number; max_video_upload_mb: number; max_minutes: number };
}

export interface Analysis {
  version: number;
  /** Разбор сделан старой версией: нет темпа по тактам, гитары из записи и текста. */
  outdated: boolean;
  duration: number;
  tempo: number;
  beats_per_bar: number;
  bars: number;
  bar_times: number[];
  bar_seconds: number[];
  key: string;
  key_confidence: number | null;
  stems: string[];
  warnings: string[];
  guitar_source: "" | "guitar" | "keys";
  /** Какая гитара в записи: acoustic, clean, distorted; пусто — не определили. */
  guitar_tone: "" | "acoustic" | "clean" | "distorted";
  /** Какой пресет электро ближе к записи (funk, ambient, metal…); пусто — не электро или старый разбор. */
  guitar_sound?: string;
  counts: { chords: number; melody: number; bass: number; guitar: number; lyrics_lines: number };
  /** Как разделяли на дорожки: max — вокал отдельной моделью, потом Demucs по инструменталу. */
  separation: { quality: "standard" | "max"; models: string[] };
  /** Дорожки, которые можно скачать без потерь (FLAC). */
  lossless: string[];
  device: string | null;
  timings: Record<string, number>;
}

export interface LyricWord {
  text: string;
  start: number;
  end: number;
}

export interface LyricLine {
  start: number;
  end: number;
  words: LyricWord[];
}

export interface Lyrics {
  source: "lrclib" | "lrclib+whisper" | "whisper" | "edited" | null;
  language?: string | null;
  lines: LyricLine[];
}

export interface ChordShape {
  name: string;
  frets: (number | null)[];
}

export interface PartInfo {
  player_id: string;
  title: string;
  roles: Role[];
  difficulty: Difficulty;
  instrument: InstrumentKind;
  tuning: string;
  capo: number;
  /** Звук партии (уже без «auto»): steel, nylon, clean, funk, chorus, ambient, jazz, blues, crunch,
   *  drive, fuzz, lead, metal, finger, pick. */
  tone: string;
  notes: number;
  shapes: ChordShape[];
  warnings: string[];
}

export interface Arrangement {
  title: string;
  artist: string | null;
  tempo: number;
  beats_per_bar: number;
  steps_per_beat: number;
  bars: number;
  key: string;
  transpose: number;
  parts: PartInfo[];
  chart: { offset: number; name: string }[][];
  capo_hints: Record<string, { capo: number; score: number; barre_chords: number }[]>;
  /** Начала тактов в секундах записи и конец последнего. Пусто — старый разбор. */
  bar_seconds: number[];
  alphatex: string;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  device: string;
  torch_build: string;
  busy_with: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("Нет связи с Fretlines. Проверь, что окно с сервером не закрыто.", 0);
  }
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : "Что-то пошло не так. Попробуй ещё раз.";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

function json(method: string, data: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
}

export const api = {
  health: () => request<Health>("/health"),
  meta: () => request<Meta>("/meta"),
  songs: () => request<Song[]>("/songs"),
  song: (id: string) => request<Song>(`/songs/${id}`),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Song>("/songs", { method: "POST", body: form });
  },
  importUrl: (url: string) => request<Song>("/songs/import", json("POST", { url })),
  update: (id: string, patch: { title?: string; artist?: string; setup?: StudioSetup }) =>
    request<Song>(`/songs/${id}`, json("PATCH", patch)),
  remove: (id: string) => request<undefined>(`/songs/${id}`, { method: "DELETE" }),
  retry: (id: string) => request<Song>(`/songs/${id}/retry`, { method: "POST" }),
  peaks: (id: string) => request<{ peaks: number[]; duration: number | null }>(`/songs/${id}/peaks`),
  analysis: (id: string) => request<Analysis>(`/songs/${id}/analysis`),
  arrangement: (id: string, setup: StudioSetup) =>
    request<Arrangement>(
      `/songs/${id}/arrangement`,
      json("POST", {
        players: setup.players,
        transpose: setup.transpose,
        lyrics_in_tabs: setup.lyricsInTabs ?? true,
      }),
    ),
  lyrics: (id: string) => request<Lyrics>(`/songs/${id}/lyrics`),
  saveLyrics: (id: string, lyrics: Lyrics) => request<Lyrics>(`/songs/${id}/lyrics`, json("PUT", lyrics)),
  audioUrl: (id: string, stem: string) => `/api/songs/${id}/audio/${stem}`,
  /** Запись без выбранных дорожек (сводится на сервере один раз и кэшируется). */
  mixUrl: (id: string, without: StemName[]) =>
    without.length ? `/api/songs/${id}/mix?without=${[...without].sort().join(",")}` : `/api/songs/${id}/mix`,
};
