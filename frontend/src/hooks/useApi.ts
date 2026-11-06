import { useCallback, useEffect, useState } from "react";

import { api, type Meta, type Song } from "../lib/api";

export type Loadable<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; message: string };

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Что-то пошло не так.";
}

/** Загрузка один раз при монтировании (и по `reload`). */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): Loadable<T> & { reload: () => void } {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    load()
      .then((data) => {
        if (alive) setValue({ state: "ready", data });
      })
      .catch((error: unknown) => {
        if (alive) setValue({ state: "error", message: message(error) });
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps передаёт вызывающий
  }, [tick, ...deps]);

  const reload = useCallback(() => {
    setTick((t) => t + 1);
  }, []);
  return { ...value, reload };
}

let metaPromise: Promise<Meta> | null = null;

export function useMeta(): Meta | null {
  const [meta, setMeta] = useState<Meta | null>(null);
  useEffect(() => {
    metaPromise ??= api.meta();
    let alive = true;
    metaPromise
      .then((data) => {
        if (alive) setMeta(data);
      })
      .catch(() => {
        metaPromise = null;
      });
    return () => {
      alive = false;
    };
  }, []);
  return meta;
}

/** Песня с автообновлением, пока идёт разбор. */
export function useSong(id: string): { song: Song | null; error: string | null; refresh: () => void } {
  const [song, setSong] = useState<Song | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    async function poll(): Promise<void> {
      try {
        const data = await api.song(id);
        if (!alive) return;
        setSong(data);
        setError(null);
        if (data.status === "queued" || data.status === "running") {
          timer = window.setTimeout(() => void poll(), 900);
        }
      } catch (e) {
        if (!alive) return;
        setError(message(e));
        timer = window.setTimeout(() => void poll(), 3000);
      }
    }
    void poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [id, tick]);

  const refresh = useCallback(() => {
    setTick((t) => t + 1);
  }, []);
  return { song, error, refresh };
}
