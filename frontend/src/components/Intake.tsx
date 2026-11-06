import { AnimatePresence, motion } from "motion/react";
import { useRef, useState, type DragEvent, type SyntheticEvent } from "react";

import { useMeta } from "../hooks/useApi";
import { api } from "../lib/api";
import { EASE_FILM } from "../lib/motion";
import { navigate } from "../lib/router";
import { Icon } from "./Icon";
import { Segmented } from "./Segmented";

type Mode = "file" | "link";

const ACCEPT = ".mp3,.wav,.m4a,.flac,.ogg,.opus,.aac,.mp4,.mov,.webm,audio/*,video/mp4";

/** Шесть струн внутри зоны загрузки: при наведении файла начинают дрожать. */
function Strings({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 400 120" preserveAspectRatio="none" aria-hidden="true" className={`absolute inset-x-0 bottom-3 h-16 w-full ${active ? "strings-active" : ""}`}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <line
          key={i}
          x1="0"
          x2="400"
          y1={10 + i * 20}
          y2={10 + i * 20}
          stroke="var(--accent)"
          strokeOpacity={active ? 0.5 : 0.1 + i * 0.03}
          strokeWidth={0.6 + i * 0.25}
          vectorEffect="non-scaling-stroke"
          style={{ animationDelay: `${String(i * 23)}ms` }}
        />
      ))}
    </svg>
  );
}

export function Intake() {
  const meta = useMeta();
  const [mode, setMode] = useState<Mode>("file");
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const limit = meta?.limits.max_upload_mb ?? 50;

  async function start(event?: SyntheticEvent) {
    event?.preventDefault();
    setError(null);
    if (mode === "file" && !file) {
      input.current?.click();
      return;
    }
    if (mode === "link" && !url.trim()) {
      setError("Вставь ссылку на видео с YouTube или TikTok.");
      return;
    }
    setBusy(true);
    try {
      const song = mode === "file" && file ? await api.upload(file) : await api.importUrl(url.trim());
      navigate(`/song/${song.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не получилось начать разбор.");
      setBusy(false);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) {
      setMode("file");
      setFile(dropped);
      setError(null);
      return;
    }
    const text = event.dataTransfer.getData("text/uri-list") || event.dataTransfer.getData("text/plain");
    if (text.startsWith("http")) {
      setMode("link");
      setUrl(text.trim());
    }
  }

  async function paste() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setUrl(text.trim());
    } catch {
      setError("Браузер не дал доступ к буферу — вставь ссылку сочетанием Ctrl+V.");
    }
  }

  return (
    <form
      onSubmit={(e) => void start(e)}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={onDrop}
      className="panel relative overflow-hidden p-2"
      style={{ boxShadow: "var(--shadow)" }}
    >
      <div className="flex items-center justify-between gap-3 px-3 pt-2 pb-3">
        <Segmented
          label="Откуда взять песню"
          value={mode}
          onChange={(value) => {
            setMode(value);
            setError(null);
          }}
          options={[
            { value: "file", label: "Файл" },
            { value: "link", label: "Ссылка" },
          ]}
        />
        <span className="hidden text-caption text-text-dim sm:block">до 15 минут</span>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {mode === "file" ? (
          <motion.button
            key="file"
            type="button"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: EASE_FILM }}
            onClick={() => input.current?.click()}
            className={`relative flex h-[232px] w-full flex-col items-center justify-center gap-3 overflow-hidden rounded-[14px] border border-dashed transition-[border-color,background-color,box-shadow] duration-300 ease-film ${
              dragging
                ? "border-accent bg-surface-2 shadow-[inset_0_0_60px_var(--glow)]"
                : "border-line-strong hover:border-text-dim hover:bg-surface-2/60"
            }`}
          >
            <Strings active={dragging} />
            <span className="relative -mt-6 flex size-14 items-center justify-center rounded-full bg-accent text-on-accent">
              <Icon name="upload" size={22} />
            </span>
            <span className="relative text-center">
              <span className="block text-lead font-semibold">
                {file ? file.name : dragging ? "Отпускай" : "Перетащи песню сюда"}
              </span>
              <span className="mt-1 block text-small text-text-dim">
                {file
                  ? `${(file.size / 1024 / 1024).toFixed(1)} МБ · нажми, чтобы выбрать другой`
                  : `mp3, wav, m4a, flac или видео mp4 · до ${String(limit)} МБ`}
              </span>
            </span>
          </motion.button>
        ) : (
          <motion.div
            key="link"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: EASE_FILM }}
            className="flex h-[232px] flex-col justify-center gap-4 rounded-[14px] border border-line px-5"
          >
            <label htmlFor="song-url" className="text-lead font-semibold">
              Ссылка на видео
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <span className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-text-dim">
                  <Icon name="link" size={18} />
                </span>
                <input
                  id="song-url"
                  type="url"
                  inputMode="url"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="https://youtu.be/… или tiktok.com/@…"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                  }}
                  className="field h-12 pl-11 text-body"
                />
              </div>
              <button type="button" onClick={() => void paste()} className="btn btn-ghost h-12 px-4 text-small">
                Вставить
              </button>
            </div>
            <p className="text-small text-text-dim">
              YouTube, TikTok, SoundCloud и другие — звук скачается сюда и останется у тебя.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          const picked = e.target.files?.[0];
          if (picked) {
            setFile(picked);
            setError(null);
          }
        }}
      />

      <div className="flex flex-col gap-3 px-3 pt-4 pb-2 sm:flex-row sm:items-center sm:justify-between">
        <p role="status" aria-live="polite" className={`min-h-5 text-small ${error ? "text-danger" : "text-text-dim"}`}>
          {error ?? "Состав, сложность и тональность настроишь после разбора."}
        </p>
        <button type="submit" disabled={busy} className="btn btn-primary shrink-0">
          {busy ? "Отправляю…" : "Разобрать"}
          {!busy && <Icon name="next" size={18} />}
        </button>
      </div>
    </form>
  );
}
