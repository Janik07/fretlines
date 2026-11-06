/** Клиент API (backend/fretlines_api/routes). Ошибки сервера приходят по-русски в `detail`. */

export type SongStatus = "queued" | "running" | "done" | "failed";
export type Role = "melody" | "bass" | "rhythm" | "pad" | "percussion";
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
}

export interface StudioSetup {
  players: Player[];
  transpose: number;
  mine: string | null;
}

export interface Meta {
  tunings: { id: string; label: string; bass: boolean; notes: string[] }[];
  instruments: { id: InstrumentKind; label: string }[];
  roles: { id: Role; label: string }[];
  difficulties: { id: Difficulty; label: string }[];
  presets: { id: string; label: string; players: { name: string; roles: Role[] }[] }[];
  limits: { max_upload_mb: number; max_video_upload_mb: number; max_minutes: number };
}

export interface Analysis {
  duration: number;
  tempo: number;
  beats_per_bar: number;
  bars: number;
  bar_times: number[];
  key: string;
  key_confidence: number | null;
  stems: string[];
  warnings: string[];
  counts: { chords: number; melody: number; bass: number };
  device: string | null;
  timings: Record<string, number>;
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
      json("POST", { players: setup.players, transpose: setup.transpose }),
    ),
  audioUrl: (id: string, stem: string) => `/api/songs/${id}/audio/${stem}`,
};
