export function duration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  return `${String(minutes)}:${String(total % 60).padStart(2, "0")}`;
}

export function clock(ms: number): string {
  return duration(ms / 1000);
}

const DATE = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });

export function shortDate(iso: string): string {
  return DATE.format(new Date(iso)).replace(".", "");
}

const PLURAL = new Intl.PluralRules("ru-RU");

/** plural(3, ["игрок", "игрока", "игроков"]) → «3 игрока». */
export function plural(n: number, forms: [string, string, string]): string {
  const rule = PLURAL.select(n);
  const word = rule === "one" ? forms[0] : rule === "few" ? forms[1] : forms[2];
  return `${String(n)} ${word}`;
}

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];

/** «Am» → «ля минор»: тональность словами для подсказок. */
export function keyWords(key: string): string {
  const minor = key.endsWith("m");
  const tonic = minor ? key.slice(0, -1) : key;
  const index = Math.max(NAMES.indexOf(tonic), FLATS.indexOf(tonic));
  const words = ["до", "до-диез", "ре", "ми-бемоль", "ми", "фа", "фа-диез", "соль", "ля-бемоль", "ля", "си-бемоль", "си"];
  const word = index >= 0 ? (words[index] ?? tonic) : tonic;
  return `${word} ${minor ? "минор" : "мажор"}`;
}

/** Красивые знаки альтерации: Bb → B♭, F# → F♯. */
export function prettyChord(name: string): string {
  return name.replace(/([A-G])b/g, "$1♭").replace(/#/g, "♯");
}

export function host(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^(www|m)\./, "");
  } catch {
    return url;
  }
}
