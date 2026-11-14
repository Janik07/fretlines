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

## Notes: how well do we hear the guitar?

```bash
python scripts/guitarset_notes_bench.py
```

The script runs the same note recognition the song analysis uses (Basic Pitch plus cleanup) on
the GuitarSet microphone recordings. A note counts as found when the pitch is the same and the
onset is within 50 ms.

Results: see the table in the README once the run has been recorded there.
