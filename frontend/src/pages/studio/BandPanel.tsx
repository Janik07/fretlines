import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import { Icon } from "../../components/Icon";
import { Segmented } from "../../components/Segmented";
import type { Arrangement, Difficulty, InstrumentKind, Meta, Player, Role, StudioSetup } from "../../lib/api";
import { EASE_FILM } from "../../lib/motion";
import { applyPreset, newPlayer, presetOf, rememberMyInstrument, ROLE_LABELS, ROLE_ORDER } from "./setup";
import { GUITAR_PRESET, isTone } from "./tone";

const PRESETS = [
  { value: "record", label: "Оригинал" },
  { value: "solo", label: "Соло" },
  { value: "duo", label: "Дуэт" },
  { value: "trio", label: "Трио" },
  { value: "quartet", label: "Квартет" },
];

const LEVELS: { value: Difficulty; label: string }[] = [
  { value: "easy", label: "Легко" },
  { value: "medium", label: "Средне" },
  { value: "full", label: "Полностью" },
];

const KINDS: { value: InstrumentKind; label: string }[] = [
  { value: "acoustic", label: "Акустика" },
  { value: "electric", label: "Электро" },
  { value: "bass", label: "Бас" },
];

/** Роль добавляется к ролям игрока. «Как в записи» — целая партия: она не сочетается с другими. */
function withRole(roles: Role[], role: Role): Role[] {
  if (role === "original") return ["original"];
  const rest: Role[] = roles.filter((r) => r !== "original");
  return ROLE_ORDER.filter((r) => r === role || rest.includes(r));
}

/** Фактура линии партии — та же, что в легенде дизайн-системы (SPEC §2.2). */
export function RoleMark({ role }: { role: Role }) {
  const style: Record<Role, { stroke: string; width: number; dash?: string; cap?: "round" }> = {
    original: { stroke: "var(--part-melody)", width: 2.6, dash: "10 2.5" },
    melody: { stroke: "var(--part-melody)", width: 1.6 },
    bass: { stroke: "var(--part-bass)", width: 3.6 },
    rhythm: { stroke: "var(--part-rhythm)", width: 2, dash: "5 3.5" },
    pad: { stroke: "var(--part-pad)", width: 2.6, dash: "0.01 4.5", cap: "round" },
    percussion: { stroke: "var(--part-perc)", width: 1 },
  };
  const s = style[role];
  return (
    <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
      {role === "percussion" ? (
        <rect x="1" y="1.5" width="20" height="5" rx="2.5" fill="none" stroke={s.stroke} strokeWidth="1" />
      ) : (
        <line x1="1" x2="21" y1="4" y2="4" stroke={s.stroke} strokeWidth={s.width} strokeDasharray={s.dash} strokeLinecap={s.cap ?? "butt"} />
      )}
    </svg>
  );
}

function PlayerCard({
  player,
  index,
  meta,
  mine,
  hint,
  warnings,
  tone,
  canRemove,
  onChange,
  onRemove,
  onMine,
  onDropRole,
}: {
  player: Player;
  index: number;
  meta: Meta | null;
  mine: boolean;
  hint: number | null;
  warnings: string[];
  tone: string | undefined;
  canRemove: boolean;
  onChange: (player: Player) => void;
  onRemove: () => void;
  onMine: () => void;
  onDropRole: (role: Role, from: string) => void;
}) {
  const [over, setOver] = useState(false);
  const tunings = (meta?.tunings ?? []).filter((t) => t.bass === (player.instrument === "bass"));
  const tones = meta?.tones[player.instrument] ?? [{ id: "auto", label: "Как в записи" }];
  // Во что «как в записи» превратилось для этой песни — и какой пресет включить на смарт-гитаре.
  const heard = tone ? tones.find((t) => t.id === tone)?.label : undefined;
  const preset = tone && isTone(tone) ? GUITAR_PRESET[tone] : undefined;

  function toggleRole(role: Role) {
    const has = player.roles.includes(role);
    if (has && player.roles.length === 1) return;
    onChange({ ...player, roles: has ? player.roles.filter((r) => r !== role) : withRole(player.roles, role) });
  }

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.3, ease: EASE_FILM }}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("application/x-fretlines-role")) {
          e.preventDefault();
          setOver(true);
        }
      }}
      onDragLeave={() => {
        setOver(false);
      }}
      onDrop={(e) => {
        setOver(false);
        const raw = e.dataTransfer.getData("application/x-fretlines-role");
        if (!raw) return;
        const { role, from } = JSON.parse(raw) as { role: Role; from: string };
        if (from !== player.id) onDropRole(role, from);
      }}
      className={`rounded-[16px] border p-4 transition-colors duration-300 ease-film ${
        mine ? "border-accent bg-surface-2" : over ? "border-text-dim bg-surface-2" : "border-line bg-surface"
      }`}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onMine}
          aria-pressed={mine}
          title={mine ? "Это твоя партия" : "Сделать моей партией"}
          className={`flex size-8 shrink-0 items-center justify-center rounded-full border text-caption font-bold transition-colors duration-300 ease-film ${
            mine ? "border-accent bg-accent text-on-accent" : "border-line-strong text-text-dim hover:text-text"
          }`}
        >
          {index + 1}
        </button>
        <input
          value={player.name}
          onChange={(e) => {
            onChange({ ...player, name: e.target.value });
          }}
          placeholder={`Игрок ${String(index + 1)}`}
          aria-label="Имя игрока"
          maxLength={40}
          className="min-w-0 flex-1 bg-transparent text-body font-semibold outline-none placeholder:text-text-dim"
        />
        {mine && <span className="eyebrow text-[10px] text-text">моя</span>}
        {canRemove && (
          <button type="button" onClick={onRemove} className="icon-btn size-8 text-text-dim" aria-label="Убрать игрока">
            <Icon name="close" size={14} />
          </button>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Роли">
        {ROLE_ORDER.map((role) => {
          const active = player.roles.includes(role);
          return (
            <button
              key={role}
              type="button"
              aria-pressed={active}
              draggable={active}
              onDragStart={(e) => {
                e.dataTransfer.setData("application/x-fretlines-role", JSON.stringify({ role, from: player.id }));
                e.dataTransfer.effectAllowed = "move";
              }}
              onClick={() => {
                toggleRole(role);
              }}
              className="chip"
              title={
                active
                  ? "Перетащи на другого игрока, чтобы передать роль"
                  : role === "original"
                    ? "Ноты и ритм гитары прямо из записи — звучит как в оригинале"
                    : undefined
              }
            >
              <RoleMark role={role} />
              {ROLE_LABELS[role]}
            </button>
          );
        })}
      </div>

      <div className="mt-4 space-y-3">
        <Segmented
          size="sm"
          label="Инструмент"
          value={player.instrument}
          onChange={(instrument) => {
            const bass = instrument === "bass";
            const wasBass = player.instrument === "bass";
            if (mine && !bass) rememberMyInstrument(instrument);
            onChange({
              ...player,
              instrument,
              tuning: bass === wasBass ? player.tuning : bass ? "bass-standard" : "standard",
              capo: bass ? 0 : player.capo,
              roles: bass ? ["bass"] : player.roles,
              tone: "auto",
            });
          }}
          options={KINDS}
        />
        <div>
          <label className="relative block">
            <span className="sr-only">Звук гитары</span>
            <select
              value={player.tone ?? "auto"}
              onChange={(e) => {
                onChange({ ...player, tone: e.target.value });
              }}
              className="field h-9 appearance-none pr-8 text-small"
              title="Звук в плеере: усилитель, кабинет и комната подбираются под тембр"
            >
              {tones.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id === "auto" && heard ? `Как в записи · ${heard}` : t.label}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-text-dim">
              <Icon name="chevron" size={14} />
            </span>
          </label>
          {preset && (
            <p className="mt-1.5 text-caption text-text-dim">На смарт-гитаре — пресет {preset}</p>
          )}
        </div>
        <Segmented
          size="sm"
          label="Сложность"
          value={player.difficulty}
          onChange={(difficulty) => {
            onChange({ ...player, difficulty });
          }}
          options={LEVELS}
        />
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <label className="relative">
            <span className="sr-only">Строй</span>
            <select
              value={player.tuning}
              onChange={(e) => {
                onChange({ ...player, tuning: e.target.value });
              }}
              className="field h-9 appearance-none pr-8 text-small"
            >
              {tunings.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-text-dim">
              <Icon name="chevron" size={14} />
            </span>
          </label>
          {player.instrument !== "bass" && (
            <div className="flex h-9 items-center rounded-[12px] border border-line-strong">
              <button
                type="button"
                className="icon-btn size-8"
                aria-label="Каподастр ниже"
                disabled={player.capo === 0}
                onClick={() => {
                  onChange({ ...player, capo: player.capo - 1 });
                }}
              >
                <Icon name="minus" size={14} />
              </button>
              <span className="w-[54px] text-center text-small font-semibold tabular" aria-live="polite">
                капо {player.capo}
              </span>
              <button
                type="button"
                className="icon-btn size-8"
                aria-label="Каподастр выше"
                disabled={player.capo >= 7}
                onClick={() => {
                  onChange({ ...player, capo: player.capo + 1 });
                }}
              >
                <Icon name="plus" size={14} />
              </button>
            </div>
          )}
        </div>
        {hint !== null && hint !== player.capo && (
          <button
            type="button"
            onClick={() => {
              onChange({ ...player, capo: hint });
            }}
            className="flex w-full items-center gap-2 rounded-[10px] bg-surface-3/60 px-3 py-2 text-left text-small text-text transition-colors duration-300 ease-film hover:bg-surface-3"
          >
            <Icon name="spark" size={16} />
            <span>
              С каподастром на {hint} — {hint === 0 ? "без каподастра" : "меньше баррэ"}. <span className="font-semibold underline decoration-line-strong underline-offset-4">Поставить</span>
            </span>
          </button>
        )}
        {warnings.map((warning) => (
          <p key={warning} className="text-caption text-text-dim">
            {warning}
          </p>
        ))}
      </div>
    </motion.li>
  );
}

export function BandPanel({
  setup,
  meta,
  arrangement,
  onChange,
}: {
  setup: StudioSetup;
  meta: Meta | null;
  arrangement: Arrangement | null;
  onChange: (setup: StudioSetup) => void;
}) {
  const preset = presetOf(setup.players);

  function updatePlayer(index: number, player: Player) {
    onChange({ ...setup, players: setup.players.map((p, i) => (i === index ? player : p)) });
  }

  function moveRole(role: Role, from: string, to: string) {
    const players = setup.players.map((p) => {
      if (p.id === from) {
        const roles = p.roles.filter((r) => r !== role);
        return { ...p, roles: roles.length ? roles : p.roles };
      }
      if (p.id === to && !p.roles.includes(role)) {
        return { ...p, roles: withRole(p.roles, role) };
      }
      return p;
    });
    onChange({ ...setup, players });
  }

  return (
    <section aria-labelledby="band-title" className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 id="band-title" className="eyebrow">
          Состав
        </h2>
        <span className="text-caption text-text-dim">{setup.players.length} из 4</span>
      </div>
      <Segmented
        size="sm"
        label="Пресет состава"
        fill
        value={preset ?? ""}
        onChange={(id) => {
          const players = applyPreset(meta, id, setup.players);
          onChange({ ...setup, players, mine: players[0]?.id ?? null });
        }}
        options={PRESETS}
      />
      <ul className="flex flex-col gap-3">
        <AnimatePresence initial={false}>
          {setup.players.map((player, index) => {
            const part = arrangement?.parts.find((p) => p.player_id === player.id);
            const hint = arrangement?.capo_hints[player.id]?.[0]?.capo ?? null;
            return (
              <PlayerCard
                key={player.id}
                player={player}
                index={index}
                meta={meta}
                mine={setup.mine === player.id}
                hint={hint}
                warnings={part?.warnings ?? []}
                tone={part?.tone}
                canRemove={setup.players.length > 1}
                onChange={(next) => {
                  updatePlayer(index, next);
                }}
                onRemove={() => {
                  const players = setup.players.filter((p) => p.id !== player.id);
                  onChange({ ...setup, players, mine: setup.mine === player.id ? (players[0]?.id ?? null) : setup.mine });
                }}
                onMine={() => {
                  onChange({ ...setup, mine: player.id });
                }}
                onDropRole={(role, from) => {
                  moveRole(role, from, player.id);
                }}
              />
            );
          })}
        </AnimatePresence>
      </ul>
      {setup.players.length < 4 && (
        <button
          type="button"
          onClick={() => {
            onChange({ ...setup, players: [...setup.players, newPlayer(setup.players.length)] });
          }}
          className="btn btn-ghost h-11 w-full text-small"
        >
          <Icon name="plus" size={16} /> Добавить игрока
        </button>
      )}
    </section>
  );
}
