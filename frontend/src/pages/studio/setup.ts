import type { Analysis, Meta, Player, Role, StemName, StudioSetup } from "../../lib/api";

export const ROLE_ORDER: Role[] = ["original", "melody", "rhythm", "bass", "pad", "percussion"];

export const ROLE_LABELS: Record<Role, string> = {
  original: "Как в записи",
  melody: "Мелодия",
  rhythm: "Ритм",
  bass: "Бас",
  pad: "Фон",
  percussion: "Перкуссия",
};

const FALLBACK_PRESETS: Record<string, { name: string; roles: Role[] }[]> = {
  record: [
    { name: "Гитара", roles: ["original"] },
    { name: "Мелодия", roles: ["melody"] },
    { name: "Бас", roles: ["bass"] },
  ],
  solo: [{ name: "Гитара", roles: ["melody", "bass", "rhythm"] }],
  duo: [
    { name: "Лид", roles: ["melody", "pad"] },
    { name: "Ритм", roles: ["rhythm", "bass"] },
  ],
  trio: [
    { name: "Мелодия", roles: ["melody"] },
    { name: "Ритм", roles: ["rhythm"] },
    { name: "Бас", roles: ["bass"] },
  ],
  quartet: [
    { name: "Мелодия", roles: ["melody"] },
    { name: "Ритм", roles: ["rhythm"] },
    { name: "Бас", roles: ["bass"] },
    { name: "Фон", roles: ["pad"] },
  ],
};

function presetDefinition(meta: Meta | null, id: string): { name: string; roles: Role[] }[] {
  const fromMeta = meta?.presets.find((p) => p.id === id)?.players;
  return fromMeta ?? FALLBACK_PRESETS[id] ?? FALLBACK_PRESETS.trio ?? [];
}

/** Пресет состава; инструменты и уровни прежних игроков сохраняем по порядку. */
export function applyPreset(meta: Meta | null, id: string, previous: Player[]): Player[] {
  return presetDefinition(meta, id).map((definition, i) => {
    const before = previous[i];
    const kind = before?.instrument === "bass" && !definition.roles.includes("bass") ? "acoustic" : before?.instrument;
    return {
      id: `p${String(i + 1)}`,
      name: definition.name,
      instrument: kind ?? "acoustic",
      tuning: kind === before?.instrument ? (before?.tuning ?? "standard") : "standard",
      capo: before?.capo ?? 0,
      roles: [...definition.roles],
      difficulty: before?.difficulty ?? "medium",
    };
  });
}

/** Новый разбор: если в записи нашлась гитара — сразу партия «как в записи», иначе трио. */
export function defaultSetup(meta: Meta | null, analysis?: Analysis | null): StudioSetup {
  const record = (analysis?.counts.guitar ?? 0) >= 40;
  return {
    players: applyPreset(meta, record ? "record" : "trio", []),
    transpose: 0,
    mine: "p1",
    sound: "record",
  };
}

/** Какие дорожки записи берут на себя игроки группы — их глушим в режиме «Вместе». */
export function coveredStems(players: Player[]): StemName[] {
  const out = new Set<StemName>();
  for (const player of players) {
    if (player.roles.some((r) => r !== "melody" && r !== "bass")) out.add("guitar");
    if (player.roles.includes("bass")) out.add("bass");
  }
  return [...out];
}

export function presetOf(players: Player[]): string | null {
  for (const [id, definition] of Object.entries(FALLBACK_PRESETS)) {
    if (
      definition.length === players.length &&
      definition.every((d, i) => {
        const roles = players[i]?.roles ?? [];
        return roles.length === d.roles.length && d.roles.every((r) => roles.includes(r));
      })
    ) {
      return id;
    }
  }
  return null;
}

export function newPlayer(index: number): Player {
  return {
    id: `p${String(Date.now() % 100000)}${String(index)}`,
    name: `Игрок ${String(index + 1)}`,
    instrument: "acoustic",
    tuning: "standard",
    capo: 0,
    roles: ["rhythm"],
    difficulty: "medium",
  };
}
