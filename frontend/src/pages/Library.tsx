import { motion } from "motion/react";
import { useState } from "react";

import { CONTAINER, Header } from "../components/Header";
import { Icon } from "../components/Icon";
import { SongCard } from "../components/SongCard";
import { useLoad } from "../hooks/useApi";
import { api } from "../lib/api";
import { plural } from "../lib/format";
import { fadeUp, stagger } from "../lib/motion";
import { navigate, type Route } from "../lib/router";

export function Library({ route }: { route: Route }) {
  const songs = useLoad(() => api.songs(), []);
  const [confirm, setConfirm] = useState<string | null>(null);

  async function remove(id: string) {
    await api.remove(id).catch(() => undefined);
    setConfirm(null);
    songs.reload();
  }

  return (
    <>
      <Header route={route} />
      <main className={`${CONTAINER} py-14`}>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="eyebrow">Библиотека</p>
            <h1 className="mt-3 font-display text-[clamp(56px,8vw,112px)] leading-[0.86] font-[820] uppercase">
              Мои разборы
            </h1>
            {songs.state === "ready" && (
              <p className="mt-4 text-body text-text-dim">
                {songs.data.length ? plural(songs.data.length, ["песня", "песни", "песен"]) : "Пока пусто"} · новые сверху
              </p>
            )}
          </div>
          <button type="button" onClick={() => { navigate("/"); }} className="btn btn-primary">
            <Icon name="plus" size={18} /> Новый разбор
          </button>
        </div>

        {songs.state === "error" && <p className="mt-12 text-danger">{songs.message}</p>}
        {songs.state === "ready" && songs.data.length === 0 && (
          <div className="panel mt-12 flex flex-col items-center gap-4 px-6 py-20 text-center">
            <Icon name="guitar" size={32} />
            <p className="text-lead font-semibold">Здесь появятся твои песни</p>
            <p className="max-w-md text-small text-text-dim">
              Загрузи файл или вставь ссылку на главной — разбор займёт пару минут.
            </p>
          </div>
        )}
        {songs.state === "ready" && songs.data.length > 0 && (
          <motion.ul
            variants={stagger}
            initial="hidden"
            animate="shown"
            className="mt-12 grid grid-cols-2 gap-x-5 gap-y-10 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
          >
            {songs.data.map((song) => (
              <motion.li key={song.id} variants={fadeUp} className="group/item relative">
                <SongCard song={song} wide />
                <div className="absolute top-2 right-2 opacity-0 transition-opacity duration-300 ease-film group-hover/item:opacity-100 focus-within:opacity-100">
                  {confirm === song.id ? (
                    <span className="flex items-center gap-1 rounded-full bg-bg/90 p-1 backdrop-blur">
                      <button type="button" onClick={() => void remove(song.id)} className="h-8 rounded-full bg-danger px-3 text-caption font-semibold text-white">
                        Удалить
                      </button>
                      <button type="button" onClick={() => { setConfirm(null); }} className="icon-btn size-8" aria-label="Отмена">
                        <Icon name="close" size={14} />
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => { setConfirm(song.id); }}
                      className="icon-btn size-9 bg-bg/80 backdrop-blur"
                      aria-label={`Удалить «${song.title}»`}
                    >
                      <Icon name="trash" size={16} />
                    </button>
                  )}
                </div>
              </motion.li>
            ))}
          </motion.ul>
        )}
      </main>
    </>
  );
}
