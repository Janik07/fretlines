# Benchmarks

Fretlines is checked against [GuitarSet](https://zenodo.org/records/3371780) (Xi et al.,
ISMIR 2018, CC BY 4.0): 360 short recordings by six guitarists, where every note is annotated
with its string and fret. The dataset is not part of this repository. Download it into
`.bench/guitarset/` (the folder is git-ignored):

- `annotation.zip` (39 MB), unpacked into `.bench/guitarset/annotation/`
- `audio_mono-mic.zip` (657 MB), unpacked into `.bench/guitarset/audio_mono-mic/` (only for the
  note benchmark)

## Chord shapes: do we hold chords the way guitarists do?

```bash
python scripts/guitarset_bench.py --level full
```

The script takes the 180 accompaniment recordings. For every chord it finds where the guitarist
held it on the neck, asks Fretlines for shapes for the same chord sequence, and compares them.
Only chords from the Fretlines vocabulary are counted (2037 chords).

| Level `full` | Before (v0.2.0) | After |
|---|---|---|
| Strings where our fret equals the guitarist's | 30.5 % | 47.6 % |
| Hand position within 2 frets of the guitarist's | 45.3 % | 63.6 % |
| Mean distance between our hand position and theirs | 2.9 frets | 2.1 frets |
| Shapes with an open string while the hand is above fret 4 | 36 | 0 |
| Shapes with a barre and an open string under it | 84 | 0 |
| Mean hand shift per chord change (guitarists: 1.49 frets) | 0.34 | 0.92 |

"Before" picked shapes by brute-force search over the fretboard. It stayed close to the nut by
using shapes no hand can hold, which is why its hand shift looks so small. "After" takes shapes
from a library of open chords, E- and A-shape barre chords and small shapes on the top strings,
keeps one shape per chord for the whole part, and chooses the shapes together so that chord
changes are easy.

How to read these numbers:

- GuitarSet accompaniment is mostly jazz, funk and bossa nova. Those players often use
  three-note voicings up the neck, so full agreement with them is not the goal for pop and rock
  songs. The zero counts in the two "impossible shape" rows are the hard requirement.
- The comparison is per string, and a guitarist may play only part of a shape, so the agreement
  figure understates how often the shape is the same.

## Tabs: do we put the notes where guitarists do?

```bash
python scripts/guitarset_tab_bench.py --level full
```

The script feeds the annotated notes and chords into the "as recorded" part, as if note
recognition were perfect, and looks up every note of the guitarist in our tab. "Kept" is the
share of their notes that reach the tab at the same pitch and time; "extra" is the share of
our tab notes that the guitarist did not play; "same position" is the share of kept notes that
sit on the same string and fret. All 360 recordings, 62,476 notes.

| Kept / extra / same position | Before | After |
|---|---|---|
| Solo, level `full` | 85.2 % / 43.2 % / 42.1 % | 91.2 % / 11.0 % / 61.5 % |
| Solo, level `medium` | 67.8 % / 49.6 % / 43.3 % | 72.3 % / 18.0 % / 58.4 % |
| Accompaniment, level `full` | 77.3 % / 51.0 % / 72.0 % | 78.3 % / 49.7 % / 72.4 % |
| Accompaniment, level `medium` | 63.1 % / 53.7 % / 64.1 % | 62.9 % / 51.0 % / 63.8 % |

What changed in "After":

- The hand now covers four frets. Before, every change of fret counted as a move of the hand,
  even to a note under the next finger, so lines drifted to open strings and the nut.
- An open string no longer lets the hand jump to the other end of the neck for free, and it
  costs a little when the hand is above the third fret.
- Free notes (riffs and solos) are drawn towards the middle of the neck (fret 7) instead of
  the nut: GuitarSet players take a third of their solo notes on frets 6-8 and a tenth near
  the nut. The two weights were chosen on every second recording and checked on the rest
  (60.7 % same position on the held-out half, the same as on all recordings at that point).
- A melody that repeats its notes is no longer taken for strumming. The rule "a strum of which
  only the top string was heard" now also requires the top notes to be chord tones, with at
  most three different ones per chord. Before, it turned such melodies into full chord
  strokes; this is where most of the extra notes in solos came from.
- Notes that follow each other within one grid step are no longer stacked into a chord, a
  riff over power chords keeps its thirds, and a double stop in a melody is not replaced by
  the chord shape.

How to read these numbers: the input is the annotation, not our note recognition, so this
measures only the layout on the neck. In accompaniment "extra" is high and "kept" is below
100 % by design: in strummed bars the part plays the whole chord shape instead of the few
strings that were heard (on a separated stem the model misses strings), and GuitarSet players
often use other voicings than ours. The levels below `full` use an eighth-note grid. A different string for the same note is not an error in
itself; the figure shows how close the default is to what players choose.

## Notes: how well do we hear the guitar?

```bash
python scripts/guitarset_notes_bench.py
```

The script runs the same note recognition the song analysis uses (Basic Pitch plus cleanup) on
the GuitarSet microphone recordings. A note counts as found when the pitch is the same and the
onset is within 50 ms.

All 360 recordings (accompaniment and solo), precision / recall / F1:

| | Before (v0.2.0) | After |
|---|---|---|
| Accompaniment | 0.758 / 0.748 / 0.753 | 0.794 / 0.718 / 0.754 |
| Solo | 0.761 / 0.918 / 0.832 | 0.851 / 0.907 / 0.878 |
| All | 0.759 / 0.794 / 0.776 | 0.811 / 0.769 / 0.789 |

Precision is the share of found notes that are real; recall is the share of real notes that
were found. "After" changes two cleanup settings chosen on this benchmark: the detection
threshold is lowered only when a track has fewer than 2 notes per second (it used to be 4), and
notes quieter than 0.6 of the loud ones are dropped (it used to be 0.5). Fewer stray notes, at
the cost of some quiet real ones.

How to read these numbers: GuitarSet is a clean microphone recording of one guitar. In a real
song the guitar first has to be separated from the mix, so expect lower figures there. This
benchmark measures the note model and its cleanup, not the whole pipeline.
