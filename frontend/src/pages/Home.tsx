import { motion } from "motion/react";

import { CONTAINER, Header } from "../components/Header";
import { Icon, type IconName } from "../components/Icon";
import { Intake } from "../components/Intake";
import { PartsPreview } from "../components/PartsPreview";
import { SongCard } from "../components/SongCard";
import { BreathingLine } from "../components/Waveform";
import { useLoad } from "../hooks/useApi";
import { api } from "../lib/api";
import { fadeUp, stagger } from "../lib/motion";
import { navigate, type Route } from "../lib/router";

const STEPS: { icon: IconName; title: string; text: string }[] = [
  { icon: "wave", title: "Разделяем на инструменты", text: "Вокал, бас, барабаны, гитара и клавиши — каждый отдельно." },
  { icon: "metronome", title: "Слушаем ритм", text: "Темп, доли и такты — чтобы табы совпали с песней." },
  { icon: "spark", title: "Ищем аккорды", text: "Тональность и гармония по времени, с подсказкой каподастра." },
  { icon: "solo", title: "Записываем мелодию и бас", text: "Ноты с голоса и бас-гитары, без вибрато и мусора." },
  { icon: "guitar", title: "Раскладываем на гитары", text: "Партии на 1–4 игроков, каждому — по его уровню." },
];

export function Home({ route }: { route: Route }) {
  const recent = useLoad(() => api.songs(), []);
  const songs = recent.state === "ready" ? recent.data.slice(0, 8) : [];

  return (
    <>
      <Header route={route} overlay />
      <main>
        <section className="stage-light relative flex min-h-svh flex-col" aria-labelledby="hero-title">
          <div className={`${CONTAINER} grid flex-1 items-center gap-12 pt-28 pb-24 lg:grid-cols-[1.08fr_0.92fr] lg:gap-16`}>
            <motion.div variants={stagger} initial="hidden" animate="shown">
              <motion.p variants={fadeUp} className="eyebrow">
                Гитарный аранжировщик для ансамбля
              </motion.p>
              <motion.h1
                id="hero-title"
                variants={fadeUp}
                className="mt-6 font-display text-poster font-[820] tracking-[-0.005em] uppercase"
              >
                Разложи
                <br />
                песню
                <br />
                <span className="outline-text">на гитары</span>
              </motion.h1>
              <motion.p variants={fadeUp} className="mt-8 max-w-[34rem] text-lead text-text-dim">
                Кидай свой трек или ссылку с YouTube и TikTok. Fretlines разделит его на инструменты
                и раздаст партии на 1–4 гитары — мелодию, ритм, бас. Каждому по уровню, и всё сразу
                можно послушать.
              </motion.p>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.25, ease: [0.2, 0.8, 0.2, 1] }}>
              <Intake />
            </motion.div>
          </div>
          <BreathingLine className="pointer-events-none absolute inset-x-0 bottom-6 h-24 w-full" />
        </section>

        {songs.length > 0 && (
          <section className="border-t border-line" aria-labelledby="recent-title">
            <div className={`${CONTAINER} py-16`}>
              <div className="mb-8 flex items-end justify-between gap-4">
                <h2 id="recent-title" className="font-display text-display font-[760] uppercase">
                  Недавние разборы
                </h2>
                <button type="button" onClick={() => { navigate("/library"); }} className="btn btn-ghost h-10 text-small">
                  Все разборы <Icon name="next" size={16} />
                </button>
              </div>
              <div className="-mx-4 flex gap-5 overflow-x-auto px-4 pb-4 sm:-mx-8 sm:px-8 lg:-mx-12 lg:px-12">
                {songs.map((song) => (
                  <SongCard key={song.id} song={song} />
                ))}
              </div>
            </div>
          </section>
        )}

        <section className="border-t border-line" aria-labelledby="how-title">
          <div className={`${CONTAINER} grid gap-12 py-20 lg:grid-cols-[0.9fr_1.1fr] lg:items-center`}>
            <div>
              <p className="eyebrow">Как это работает</p>
              <h2 id="how-title" className="mt-4 font-display text-[clamp(44px,6vw,88px)] leading-[0.88] font-[800] uppercase">
                Одна песня —<br />несколько гитар
              </h2>
              <ol className="mt-10 space-y-6">
                {STEPS.map((step, i) => (
                  <li key={step.title} className="grid grid-cols-[44px_1fr] gap-4">
                    <span className="flex size-11 items-center justify-center rounded-full border border-line-strong text-text">
                      <Icon name={step.icon} size={18} />
                    </span>
                    <div>
                      <p className="text-body font-semibold">
                        <span className="mr-2 font-mono text-caption text-text-dim">0{i + 1}</span>
                        {step.title}
                      </p>
                      <p className="mt-1 text-small text-text-dim">{step.text}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
            <PartsPreview />
          </div>
        </section>
      </main>
      <footer className="border-t border-line">
        <div className={`${CONTAINER} flex flex-col gap-2 py-10 text-small text-text-dim sm:flex-row sm:items-center sm:justify-between`}>
          <p>Только твои файлы. Разборы хранятся на этом компьютере и никуда не уходят.</p>
          <p className="font-mono text-caption">Fretlines</p>
        </div>
      </footer>
    </>
  );
}
