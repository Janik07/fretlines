/**
 * Студийный звук партии: чистая гитара из синтезатора → свой тракт под тембр.
 *
 * Перегруз у сэмплов General MIDI «запечён» в звук одной ноты, поэтому аккорды с ним звучат
 * игрушечно. Настоящий перегруз появляется, когда искажается сумма струн. Поэтому электро-тембры
 * строятся так: чистая гитара → эквалайзер «педали» → ламповое (несимметричное) ограничение →
 * эквалайзер усилителя → кабинет (динамик 4×12 срезает верх) → комната. Ритм с перегрузом
 * дублируется на два канала, как его пишут в студии.
 */

export type Tone = "steel" | "nylon" | "clean" | "crunch" | "drive" | "lead" | "jazz" | "finger" | "pick";

/** Программа General MIDI, которая звучит «сухой» перед трактом: электро — всегда чистая. */
export const DRY_PROGRAM: Record<Tone, number> = {
  steel: 25,
  nylon: 24,
  clean: 27,
  crunch: 27,
  drive: 27,
  lead: 27,
  jazz: 26,
  finger: 33,
  pick: 34,
};

/** Как называется похожий пресет на смарт-гитаре (Enya Inspire: Clean, Crunch, Overdrive, Lead). */
export const GUITAR_PRESET: Partial<Record<Tone, string>> = {
  clean: "Clean",
  crunch: "Crunch",
  drive: "Overdrive",
  lead: "Lead",
  jazz: "Clean",
};

export function isTone(value: string): value is Tone {
  return value in DRY_PROGRAM;
}

interface Amp {
  preHighpass: number; // Гц — что срезать до перегруза (меньше «каши» на басах)
  midHump: number; // дБ подъёма середины перед перегрузом (как у овердрайв-педали)
  drive: number; // сила ограничения
  asym: number; // несимметричность — чётные гармоники, «ламповость»
  presence: number; // дБ на 2–3 кГц после усилителя
  scoop: number; // дБ провала на 400 Гц
  room: number; // доля ревера
  roomSeconds: number;
  echo: number; // доля эха (для соло)
  doubled: boolean; // дубль на два канала
}

const AMPS: Partial<Record<Tone, Amp>> = {
  clean: { preHighpass: 70, midHump: 0, drive: 1.3, asym: 0.05, presence: 3, scoop: 1.5, room: 0.2, roomSeconds: 1.8, echo: 0, doubled: false },
  crunch: { preHighpass: 95, midHump: 4, drive: 5, asym: 0.18, presence: 2.5, scoop: 2, room: 0.13, roomSeconds: 1.3, echo: 0, doubled: true },
  drive: { preHighpass: 110, midHump: 6, drive: 11, asym: 0.2, presence: 3.5, scoop: 3, room: 0.1, roomSeconds: 1.1, echo: 0, doubled: true },
  lead: { preHighpass: 120, midHump: 7, drive: 22, asym: 0.22, presence: 4, scoop: 2, room: 0.15, roomSeconds: 1.7, echo: 0.2, doubled: false },
};

function biquad(ctx: BaseAudioContext, type: BiquadFilterType, frequency: number, gain = 0, q = 0.707): BiquadFilterNode {
  const node = ctx.createBiquadFilter();
  node.type = type;
  node.frequency.value = frequency;
  node.gain.value = gain;
  node.Q.value = q;
  return node;
}

/** Мягкое несимметричное ограничение (tanh) — так звучит перегруженная лампа. */
function shaperCurve(drive: number, asym: number): Float32Array<ArrayBuffer> {
  const size = 8192;
  const curve = new Float32Array(new ArrayBuffer(size * 4));
  const top = Math.tanh(drive);
  for (let i = 0; i < size; i++) {
    const x = (i * 2) / (size - 1) - 1;
    const k = x >= 0 ? drive : drive * (1 - asym);
    curve[i] = Math.tanh(k * x) / top;
  }
  return curve;
}

/** Импульс комнаты: стерео-шум с экспоненциальным затуханием и ранними отражениями. */
function roomImpulse(ctx: BaseAudioContext, seconds: number): AudioBuffer {
  const rate = ctx.sampleRate;
  const length = Math.max(1, Math.floor(rate * seconds));
  const impulse = ctx.createBuffer(2, length, rate);
  for (let channel = 0; channel < 2; channel++) {
    const data = impulse.getChannelData(channel);
    let seed = channel === 0 ? 0x1234567 : 0x7654321;
    for (let i = 0; i < length; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      const noise = (seed / 0x7fffffff) * 2 - 1;
      const t = i / rate;
      data[i] = noise * Math.exp((-6.9 * t) / seconds) * (t < 0.012 ? 0.3 : 1);
    }
  }
  return impulse;
}

/** Кабинет 4×12: срез низа и верха, «гул» корпуса, характерные пики динамика. */
function cabinet(ctx: BaseAudioContext, input: AudioNode): AudioNode {
  const chain = [
    biquad(ctx, "highpass", 80, 0, 0.7),
    biquad(ctx, "peaking", 110, 3, 1.1),
    biquad(ctx, "peaking", 1900, 2.5, 1.2),
    biquad(ctx, "peaking", 3600, 2, 2),
    biquad(ctx, "lowpass", 5300, 0, 0.9),
    biquad(ctx, "lowpass", 7600, 0, 0.7),
  ];
  let node: AudioNode = input;
  for (const filter of chain) {
    node.connect(filter);
    node = filter;
  }
  return node;
}

function peak(buffer: AudioBuffer): number {
  let top = 0;
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const data = buffer.getChannelData(c);
    for (let i = 0; i < data.length; i += 4) top = Math.max(top, Math.abs(data[i] ?? 0));
  }
  return top;
}

/** Громкость партии к общему уровню, чтобы тембры не спорили по громкости. */
function normalize(buffer: AudioBuffer, target = 0.32): void {
  let sum = 0;
  let count = 0;
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const data = buffer.getChannelData(c);
    for (let i = 0; i < data.length; i += 8) {
      const v = data[i] ?? 0;
      if (Math.abs(v) > 1e-4) {
        sum += v * v;
        count++;
      }
    }
  }
  if (!count) return;
  const rms = Math.sqrt(sum / count);
  const gain = Math.min(8, target / Math.max(rms, 1e-6));
  const limit = 0.98 / Math.max(peak(buffer) * gain, 1e-6);
  const scale = gain * Math.min(1, limit);
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const data = buffer.getChannelData(c);
    for (let i = 0; i < data.length; i++) data[i] = (data[i] ?? 0) * scale;
  }
}

function mixInto(ctx: BaseAudioContext, from: AudioNode, to: AudioNode, gain: number): void {
  const node = ctx.createGain();
  node.gain.value = gain;
  from.connect(node);
  node.connect(to);
}

/** Тракт для электро-тембров. Возвращает узел, с которого берётся готовый звук. */
function amp(ctx: BaseAudioContext, input: AudioNode, settings: Amp, inputPeak: number, out: AudioNode): void {
  const pre = ctx.createGain();
  pre.gain.value = 0.5 / Math.max(inputPeak, 1e-4); // одинаковый уровень на входе «педали»
  input.connect(pre);
  const highpass = biquad(ctx, "highpass", settings.preHighpass, 0, 0.7);
  const hump = biquad(ctx, "peaking", 750, settings.midHump, 0.9);
  const shaper = ctx.createWaveShaper();
  shaper.curve = shaperCurve(settings.drive, settings.asym);
  shaper.oversample = "4x";
  pre.connect(highpass);
  highpass.connect(hump);
  hump.connect(shaper);
  const scoop = biquad(ctx, "peaking", 420, -settings.scoop, 1);
  const presence = biquad(ctx, "peaking", 2400, settings.presence, 1);
  shaper.connect(scoop);
  scoop.connect(presence);
  const speaker = cabinet(ctx, presence);

  const dry = ctx.createGain();
  dry.gain.value = 1;
  if (settings.doubled) {
    // Дубль: тот же звук чуть позже во второй канал — широкая стерео-стена, как на записях.
    const split = ctx.createChannelSplitter(2);
    const merge = ctx.createChannelMerger(2);
    const late = ctx.createDelay(0.1);
    late.delayTime.value = 0.017;
    speaker.connect(split);
    split.connect(merge, 0, 0);
    split.connect(late, 0);
    late.connect(merge, 0, 1);
    merge.connect(dry);
  } else {
    speaker.connect(dry);
  }
  dry.connect(out);

  if (settings.echo > 0) {
    const delay = ctx.createDelay(1);
    delay.delayTime.value = 0.36;
    const feedback = ctx.createGain();
    feedback.gain.value = 0.28;
    const tone = biquad(ctx, "lowpass", 3200);
    dry.connect(delay);
    delay.connect(tone);
    tone.connect(feedback);
    feedback.connect(delay);
    mixInto(ctx, tone, out, settings.echo);
  }
  const room = ctx.createConvolver();
  room.buffer = roomImpulse(ctx, settings.roomSeconds);
  dry.connect(room);
  mixInto(ctx, room, out, settings.room);
}

/** Акустика, джаз, бас: эквалайзер корпуса, лёгкая компрессия, комната. */
function body(ctx: BaseAudioContext, input: AudioNode, tone: Tone, out: AudioNode): void {
  const filters: BiquadFilterNode[] =
    tone === "steel"
      ? [biquad(ctx, "highpass", 70), biquad(ctx, "peaking", 120, 2.5, 1), biquad(ctx, "peaking", 320, -2, 1), biquad(ctx, "highshelf", 6500, 3)]
      : tone === "nylon"
        ? [biquad(ctx, "highpass", 65), biquad(ctx, "peaking", 200, 2, 1), biquad(ctx, "lowpass", 9000)]
        : tone === "jazz"
          ? [biquad(ctx, "highpass", 70), biquad(ctx, "peaking", 250, 2, 1), biquad(ctx, "lowpass", 3200)]
          : [biquad(ctx, "lowshelf", 90, 3), biquad(ctx, "peaking", tone === "pick" ? 1600 : 800, tone === "pick" ? 3 : 1, 1), biquad(ctx, "lowpass", 4200)];
  const compressor = ctx.createDynamicsCompressor();
  compressor.threshold.value = tone === "finger" || tone === "pick" ? -22 : -26;
  compressor.ratio.value = tone === "finger" || tone === "pick" ? 4 : 2.5;
  compressor.attack.value = 0.01;
  compressor.release.value = 0.2;
  let node: AudioNode = input;
  for (const filter of filters) {
    node.connect(filter);
    node = filter;
  }
  node.connect(compressor);
  compressor.connect(out);
  if (tone !== "finger" && tone !== "pick") {
    const room = ctx.createConvolver();
    room.buffer = roomImpulse(ctx, tone === "nylon" ? 1.9 : 1.6);
    compressor.connect(room);
    mixInto(ctx, room, out, tone === "jazz" ? 0.14 : 0.18);
  }
}

/** Сухая партия → партия в своём тембре (стерео, выровненная по громкости). */
export async function applyTone(dry: AudioBuffer, tone: Tone): Promise<AudioBuffer> {
  const tail = Math.floor(dry.sampleRate * 2);
  const ctx = new OfflineAudioContext(2, dry.length + tail, dry.sampleRate);
  const source = ctx.createBufferSource();
  source.buffer = dry;
  // Электро-тракт работает с моно, как настоящая гитара с одним датчиком.
  const mono = ctx.createGain();
  mono.channelCount = 1;
  mono.channelCountMode = "explicit";
  mono.channelInterpretation = "speakers";
  source.connect(mono);
  const out = ctx.createGain();
  out.connect(ctx.destination);
  const settings = AMPS[tone];
  if (settings) amp(ctx, mono, settings, peak(dry), out);
  else body(ctx, source, tone, out);
  source.start();
  const rendered = await ctx.startRendering();
  normalize(rendered);
  return rendered;
}
