import { Icon } from "../../components/Icon";
import { STEMS, type Analysis, type SoundSource, type StemName } from "../../lib/api";

/** Режим «Дорожки»: инструментал и каждая дорожка — послушать отдельно, заглушить, скачать. */

const TRACKS: Record<StemName | "instrumental", { label: string; note: string }> = {
  instrumental: { label: "Инструментал", note: "вся песня без голоса" },
  vocals: { label: "Вокал", note: "голос, бэк-вокал — для караоке наоборот" },
  guitar: { label: "Гитара", note: "все гитары записи" },
  bass: { label: "Бас", note: "бас-гитара или синт-бас" },
  drums: { label: "Барабаны", note: "ударные и перкуссия" },
  piano: { label: "Клавиши", note: "фортепиано, синтезаторы" },
  other: { label: "Остальное", note: "струнные, духовые, эффекты" },
};

const MODEL_LABELS: Record<string, string> = {
  "UVR-MDX-NET-Inst_HQ_4.onnx": "MDX-Net Inst HQ4",
  "model_bs_roformer_ep_317_sdr_12.9755.ckpt": "BS-RoFormer",
  htdemucs_6s: "Demucs 6s",
};

function Download({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      download
      className="chip h-8 px-3"
      title={label === "FLAC" ? "Без потерь, 24 бита — для монтажа и DAW" : "mp3 192 кбит/с — для телефона"}
    >
      <Icon name="download" size={14} /> {label}
    </a>
  );
}

export function StemsView({
  songId,
  analysis,
  sound,
  muted,
  playing,
  onListen,
  onMuted,
  onReanalyze,
}: {
  songId: string;
  analysis: Analysis | null;
  sound: SoundSource;
  muted: StemName[];
  playing: boolean;
  onListen: (muted: StemName[]) => void;
  onMuted: (muted: StemName[]) => void;
  onReanalyze: () => void;
}) {
  const lossless = new Set(analysis?.lossless ?? []);
  const available = STEMS.filter((s) => analysis?.stems.includes(s));
  const quality = analysis?.separation.quality ?? "standard";
  const models = (analysis?.separation.models ?? []).map((m) => MODEL_LABELS[m] ?? m).join(" + ");
  const recording = sound !== "parts";
  const link = (track: string, format: "flac" | "mp3") =>
    `/api/songs/${songId}/download/${track}?format=${format}`;
  const instrumentalOn = recording && muted.length === 1 && muted[0] === "vocals";

  return (
    <div className="mx-auto max-w-[820px] space-y-8 px-6 pt-6 pb-28 sm:px-8">
      <header className="space-y-2">
        <h2 className="font-display text-[34px] leading-none font-[780] uppercase">Инструментал и дорожки</h2>
        <p className="text-small text-text-dim">
          Песня разделена на дорожки нейросетями: {models || "Demucs"} ·{" "}
          {quality === "max" ? "максимальное качество" : "обычное качество"}.
          {quality !== "max" && " Обнови разбор — вокал отделится сильной моделью, инструментал станет чище."}
        </p>
        {(quality !== "max" || lossless.size === 0) && (
          <button type="button" className="btn btn-ghost h-9 px-4 text-small" onClick={onReanalyze}>
            <Icon name="retry" size={15} /> Разделить в максимальном качестве
          </button>
        )}
      </header>

      <section className="panel flex flex-wrap items-center gap-4 p-5" aria-label="Инструментал">
        <div className="min-w-[200px] flex-1">
          <p className="font-display text-[26px] leading-none font-[740] uppercase">{TRACKS.instrumental.label}</p>
          <p className="mt-1 text-small text-text-dim">{TRACKS.instrumental.note} — играй и пой поверх</p>
        </div>
        <button
          type="button"
          className={`btn h-10 px-4 text-small ${instrumentalOn ? "btn-primary" : "btn-ghost"}`}
          aria-pressed={instrumentalOn}
          onClick={() => {
            onListen(["vocals"]);
          }}
        >
          <Icon name={instrumentalOn && playing ? "pause" : "play"} size={16} /> Слушать
        </button>
        <div className="flex gap-1.5">
          {lossless.has("instrumental") && <Download href={link("instrumental", "flac")} label="FLAC" />}
          <Download href={link("instrumental", "mp3")} label="MP3" />
        </div>
      </section>

      <section aria-label="Дорожки">
        <ul className="divide-y divide-line overflow-hidden rounded-[16px] border border-line">
          {available.map((stem) => {
            const on = !muted.includes(stem);
            const solo = recording && muted.length === available.length - 1 && on;
            return (
              <li key={stem} className="flex flex-wrap items-center gap-3 bg-surface px-4 py-3">
                <div className="min-w-[150px] flex-1">
                  <p className="text-body font-semibold">{TRACKS[stem].label}</p>
                  <p className="text-caption text-text-dim">{TRACKS[stem].note}</p>
                </div>
                <button
                  type="button"
                  className="chip h-8"
                  aria-pressed={on}
                  title={on ? "Заглушить в записи" : "Включить в запись"}
                  onClick={() => {
                    onMuted(on ? [...muted, stem] : muted.filter((s) => s !== stem));
                  }}
                >
                  {on ? "звучит" : "выключена"}
                </button>
                <button
                  type="button"
                  className="chip h-8"
                  aria-pressed={solo}
                  title="Только эта дорожка"
                  onClick={() => {
                    onListen(available.filter((s) => s !== stem));
                  }}
                >
                  соло
                </button>
                <div className="flex gap-1.5">
                  {lossless.has(stem) && <Download href={link(stem, "flac")} label="FLAC" />}
                  <Download href={link(stem, "mp3")} label="MP3" />
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {lossless.size > 0 && (
        <a href={`/api/songs/${songId}/download-all`} download className="btn btn-ghost h-10 px-4 text-small">
          <Icon name="download" size={16} /> Скачать всё одним архивом (FLAC)
        </a>
      )}
    </div>
  );
}
