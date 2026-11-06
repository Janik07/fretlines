import { useEffect, useState } from "react";

import { api, type Song } from "../lib/api";
import { duration, prettyChord, shortDate } from "../lib/format";
import { navigate } from "../lib/router";
import { Cover } from "./Cover";

const peaksCache = new Map<string, number[]>();

function usePeaks(id: string, ready: boolean): number[] {
  const [peaks, setPeaks] = useState<number[]>(() => peaksCache.get(id) ?? []);
  useEffect(() => {
    if (!ready || peaksCache.has(id)) return;
    let alive = true;
    api
      .peaks(id)
      .then((data) => {
        peaksCache.set(id, data.peaks);
        if (alive) setPeaks(data.peaks);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [id, ready]);
  return peaks;
}

const STATUS: Record<Song["status"], string> = {
  queued: "в очереди",
  running: "разбирается",
  done: "",
  failed: "не вышло",
};

export function SongCard({ song, wide = false }: { song: Song; wide?: boolean }) {
  const peaks = usePeaks(song.id, song.status !== "queued");
  return (
    <a
      href={`/song/${song.id}`}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.button !== 0) return;
        event.preventDefault();
        navigate(`/song/${song.id}`);
      }}
      className={`group block shrink-0 ${wide ? "w-full" : "w-[220px] sm:w-[240px]"}`}
    >
      <div className="relative aspect-square overflow-hidden rounded-[16px] border border-line bg-surface transition-[transform,border-color] duration-400 ease-film group-hover:-translate-y-1 group-hover:border-line-strong">
        <Cover seed={song.id} peaks={peaks} className="absolute inset-0 h-full w-full" />
        {song.status !== "done" && (
          <span className="absolute top-3 left-3 rounded-full bg-bg/80 px-2.5 py-1 text-caption font-semibold backdrop-blur">
            {song.status === "running" ? `${String(Math.round(song.progress * 100))}% · ` : ""}
            {STATUS[song.status]}
          </span>
        )}
        {song.status === "done" && song.key && (
          <span className="absolute right-3 bottom-3 rounded-full bg-bg/80 px-2.5 py-1 font-mono text-caption backdrop-blur">
            {prettyChord(song.key)} · {Math.round(song.tempo ?? 0)} BPM
          </span>
        )}
      </div>
      <div className="mt-3 px-0.5">
        <p className="truncate text-body font-semibold">{song.title}</p>
        <p className="mt-0.5 truncate text-small text-text-dim">
          {song.artist ?? (song.source_kind === "url" ? "по ссылке" : "свой файл")} · {duration(song.duration)} ·{" "}
          {shortDate(song.created_at)}
        </p>
      </div>
    </a>
  );
}
