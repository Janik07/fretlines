import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { CONTAINER, Header } from "../components/Header";
import { Icon } from "../components/Icon";
import { Waveform } from "../components/Waveform";
import { api, type Song } from "../lib/api";
import { duration, host } from "../lib/format";
import { fadeUp, stagger } from "../lib/motion";
import { navigate, type Route } from "../lib/router";

const STAGES = [
  { key: "download", label: "Скачиваем звук по ссылке", onlyUrl: true },
  { key: "decode", label: "Готовим запись" },
  { key: "stems", label: "Разделяем на инструменты" },
  { key: "rhythm", label: "Слушаем ритм" },
  { key: "harmony", label: "Ищем аккорды и тональность" },
  { key: "guitar", label: "Снимаем ноты гитары из записи" },
  { key: "melody", label: "Записываем мелодию" },
  { key: "bass", label: "Записываем бас" },
  { key: "lyrics", label: "Слушаем слова песни" },
  { key: "arrange", label: "Собираем партии" },
  { key: "save", label: "Сохраняем разбор" },
] as const;

function usePeaks(song: Song): number[] {
  const [peaks, setPeaks] = useState<number[]>([]);
  const ready = song.stage !== null && song.stage !== "download" && song.stage !== "decode";
  useEffect(() => {
    if (!ready || peaks.length) return;
    let alive = true;
    api
      .peaks(song.id)
      .then((data) => {
        if (alive && data.peaks.length) setPeaks(data.peaks);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [song.id, ready, peaks.length]);
  return peaks;
}

export function Processing({ song, route, onRetry }: { song: Song; route: Route; onRetry: () => void }) {
  const peaks = usePeaks(song);
  const stages = STAGES.filter((s) => !("onlyUrl" in s) || song.source_kind === "url");
  const current = stages.findIndex((s) => s.key === song.stage);
  const failed = song.status === "failed";
  const percent = Math.round(song.progress * 100);
  const source = song.source_kind === "url" ? host(song.source_url) : "свой файл";

  async function retry() {
    await api.retry(song.id).catch(() => undefined);
    onRetry();
  }

  return (
    <>
      <Header route={route} />
      <main className={`${CONTAINER} grid gap-12 py-12 lg:grid-cols-[1fr_360px] lg:gap-16 lg:py-16`}>
        <motion.section variants={stagger} initial="hidden" animate="shown" aria-live="polite">
          <motion.p variants={fadeUp} className="eyebrow">
            {source}
            {song.duration ? ` · ${duration(song.duration)}` : ""}
          </motion.p>
          <motion.h1 variants={fadeUp} className="mt-4 font-display text-[clamp(48px,7vw,104px)] leading-[0.86] font-[820] uppercase [overflow-wrap:anywhere]">
            {song.title}
          </motion.h1>
          {song.artist && (
            <motion.p variants={fadeUp} className="mt-3 text-lead text-text-dim">
              {song.artist}
            </motion.p>
          )}
          <motion.div variants={fadeUp} className="panel stage-light mt-10 overflow-hidden px-6 py-8">
            <Waveform peaks={peaks} progress={song.progress} sweeping={!failed} bars={180} className="h-36 w-full" />
          </motion.div>
          <motion.div variants={fadeUp} className="mt-8 flex items-end gap-6">
            <span className="font-display text-[clamp(88px,12vw,160px)] leading-[0.8] font-[820] tabular">
              {failed ? "—" : `${String(percent)}%`}
            </span>
            <span className="pb-3 text-body text-text-dim">
              {failed
                ? "Разбор остановился"
                : song.status === "queued"
                  ? "Ждёт очереди — сейчас разбирается другая песня"
                  : (stages[current]?.label ?? "Начинаем") + "…"}
            </span>
          </motion.div>
        </motion.section>

        <aside>
          <ol className="space-y-1">
            {stages.map((stage, index) => {
              const done = song.status === "done" || index < current;
              const active = index === current && !failed;
              const broken = failed && index === current;
              return (
                <li
                  key={stage.key}
                  className={`flex items-center gap-4 rounded-[12px] px-3 py-3 transition-colors duration-300 ease-film ${active ? "bg-surface-2" : ""}`}
                >
                  <span
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full border ${
                      done ? "border-accent bg-accent text-on-accent" : broken ? "border-danger text-danger" : active ? "border-accent" : "border-line-strong"
                    }`}
                  >
                    {done ? <Icon name="check" size={14} /> : broken ? <Icon name="close" size={12} /> : active ? <span className="pulse-soft size-2 rounded-full bg-accent" /> : null}
                  </span>
                  <span className={`text-body ${done || active ? "text-text" : "text-text-dim"} ${active ? "font-semibold" : ""}`}>{stage.label}</span>
                </li>
              );
            })}
          </ol>

          {failed ? (
            <div className="panel mt-8 p-5">
              <p className="text-body font-semibold text-danger">{song.error?.message ?? "Разбор не удался."}</p>
              <div className="mt-5 flex flex-wrap gap-2">
                <button type="button" onClick={() => void retry()} className="btn btn-primary h-11 text-small">
                  <Icon name="retry" size={16} /> Попробовать снова
                </button>
                <button type="button" onClick={() => { navigate("/"); }} className="btn btn-ghost h-11 text-small">
                  Другой файл
                </button>
              </div>
            </div>
          ) : (
            <p className="mt-8 px-3 text-small text-text-dim">
              Можно закрыть вкладку — разбор продолжится, а песня появится в «Моих разборах». На видеокарте
              это пара минут, на процессоре — подольше.
            </p>
          )}
        </aside>
      </main>
    </>
  );
}
