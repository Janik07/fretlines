/**
 * Время табов ↔ время записи. В alphaTab позиция — в тиках, у каждого такта своё начало и длина;
 * разбор знает, на какой секунде записи начинается каждый такт (bar_seconds). Внутри такта —
 * линейно: темп в табах повторяет запись по тактам, так что ошибка — доли миллисекунды.
 */

export interface Timeline {
  barTicks: number[]; // начало каждого такта в тиках
  barDurations: number[]; // длина такта в тиках
  barSeconds: number[]; // начало каждого такта в секундах записи (+ конец последнего)
}

function barAtTick(starts: number[], tick: number): number {
  let lo = 0;
  let hi = starts.length - 1;
  let found = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if ((starts[mid] ?? 0) <= tick) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

export function usable(timeline: Timeline | null): timeline is Timeline {
  return (
    timeline !== null &&
    timeline.barTicks.length > 0 &&
    timeline.barSeconds.length >= timeline.barTicks.length + 1
  );
}

export function tickToSeconds(timeline: Timeline, tick: number): number {
  const bar = barAtTick(timeline.barTicks, tick);
  const start = timeline.barTicks[bar] ?? 0;
  const length = Math.max(1, timeline.barDurations[bar] ?? 1);
  const begin = timeline.barSeconds[bar] ?? 0;
  const end = timeline.barSeconds[bar + 1] ?? begin;
  const fraction = Math.min(1, Math.max(0, (tick - start) / length));
  return begin + fraction * (end - begin);
}

export function secondsToTick(timeline: Timeline, seconds: number): number {
  const marks = timeline.barSeconds;
  let bar = 0;
  for (let i = 0; i < timeline.barTicks.length; i++) {
    if ((marks[i] ?? Infinity) <= seconds) bar = i;
    else break;
  }
  const begin = marks[bar] ?? 0;
  const end = marks[bar + 1] ?? begin;
  const fraction = end > begin ? Math.min(1, Math.max(0, (seconds - begin) / (end - begin))) : 0;
  return Math.round((timeline.barTicks[bar] ?? 0) + fraction * (timeline.barDurations[bar] ?? 0));
}

/** Секунда записи, на которой начинается шаг (шестнадцатая) такта — для аккордов над текстом. */
export function stepToSeconds(barSeconds: number[], bar: number, step: number, barSteps: number): number {
  const begin = barSeconds[bar] ?? 0;
  const end = barSeconds[bar + 1] ?? begin;
  return begin + (step / Math.max(1, barSteps)) * (end - begin);
}
