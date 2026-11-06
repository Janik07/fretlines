import * as alphaTab from "@coderline/alphatab";
import { readFileSync } from "node:fs";
const tex = process.argv[2] ? readFileSync(process.argv[2], "utf8") : `\tempo 100
\track ("Test" "T") { instrument 25 }
\staff {tabs}
\tuning (E4 B3 G3 D3 A2 E2)
\capo 2
\ts (4 4) 0.1.4 2.1.4 0.6.4 r.4 |`;
const importer = new alphaTab.importer.AlphaTexImporter();
importer.initFromString(tex, new alphaTab.Settings());
try {
  const score = importer.readScore();
  for (const track of score.tracks) {
    const staff = track.staves[0];
    const notes = staff.bars[0].voices[0].beats.flatMap((b) => b.notes).slice(0, 4);
    console.log(track.name, "| capo", staff.capo, "| bars", staff.bars.length, "| first notes", notes.map((n) => `${n.fret}.${n.string}→${n.realValue}`).join(" "));
  }
} catch (e) {
  const d = e.cause?.parserDiagnostics?.items ?? e.cause?.lexerDiagnostics?.items ?? [];
  console.log("PARSE ERROR", d.slice(0, 5).map((x) => `${x.severity} ${x.code}: ${x.message} @${x.start?.line}:${x.start?.col}`));
}
