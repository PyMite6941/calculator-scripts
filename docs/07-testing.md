# Testing without transferring

Three ways to run a TI-BASIC program without walking it to the
calculator, in increasing order of truth and decreasing order of speed.
Use all three; they catch different things.

---

## 1. The simulator — seconds, no setup

```bash
python tools/simulate_84.py ti84/src/QUADFORM.txt
python tools/simulate_84.py ti84/src/QUADFORM.txt --input 1 --input -3 --input 2
python tools/simulate_84.py ti84/src/QUADFORM.txt --trace
python tools/simulate_84.py ti84/src/QUADFORM.txt --narrow
```

Runs your source on a simulated 26×10 home screen and prints it:

```
    +--------------------------+
  1 |SIDES A,B,C               |
  2 |AREA                      |
  3 |                         6|
  4 |ANGLE A                   |
  5 |               .6435011088|
    +--------------------------+
         5    0    5    0    5

  variables: A=3  B=4  C=5  E=6  F=.6435011088  P=6
```

**It executes the same token stream the calculator would** — the scanner
from `tools/basic84.py`, not a friendlier re-parse. So `Dispp X` fails
here the way it fails there.

It deliberately reproduces the things that bite:

| | |
|---|---|
| 26 columns, and `Disp` **truncates** | you see the cut-off, and it's reported at the end |
| TI number formatting | `.6435011088` — no leading zero, 10 significant digits |
| the two minus signs | `-B` and `~B` behave differently, as they must |
| `ERR:` names | `ERR:DATA TYPE`, `ERR:LABEL`, `ERR:DIVIDE BY 0` |
| globals surviving | the variable dump at the end is the machine state |

**Flags**

- `--input V` — feed one answer to the next prompt; repeat for each.
  Makes runs scriptable and repeatable.
- `--trace` — print every statement as it executes. This is your
  debugger; TI-BASIC has none.
- `--narrow` — 16×8, the monochrome TI-84 Plus screen. Run it once to
  see how badly your output degrades on the older model.

**What it does not do.** Lists, matrices, graphing, `Text(`, `getKey`,
`prgm` calls to other programs, `seq(`, statistics. It **raises** on
those rather than guessing — a `SIMULATOR LIMIT` message means the tool
stopped, not that your program is wrong. Run `python
tools/simulate_84.py --help` for the current supported list.

It is also not cycle-accurate and knows nothing about memory
exhaustion, so it cannot tell you a program is too slow or too big.

---

## 2. SourceCoder 3 — an online editor, no install

<https://www.cemetech.net/sc/>

Paste TI-BASIC source or upload a `.8xp`, and it shows you the program
tokenized, with TI's real glyphs. Exports either direction.

Useful for: checking that a token is spelled the way you think, sanity-
checking a `.8xp` this toolchain produced, and grabbing a program
someone posted on a forum in a form you can paste into `ti84/src/`.

It does not execute anything.

---

## 3. A real emulator — the only ground truth

This runs TI's actual operating system. It is the only thing that can
tell you a program really works.

| | |
|---|---|
| **jsTIfied** <https://www.cemetech.net/projects/jstified/> | runs in the browser, nothing to install |
| **CEmu** | free desktop TI-84 Plus CE emulator, highest fidelity |
| **TI-SmartView CE** | TI's official one; paid, but ships its own ROM |

### The ROM

jsTIfied and CEmu need a **ROM image**, which is TI's copyrighted
operating system. They do not ship it. The legitimate route is to dump
it from a calculator you own, over USB — jsTIfied walks you through
this, and it is a few minutes with the cable you already have.

Do not download a ROM from a random site. Dumping your own is both the
legal path and the one that gives you *your* OS version, which is the
version your program has to work on.

### Once it is set up

```bash
python build.py 84
```

then drag `ti84/dist/QUADFORM.8xp` into the emulator and run it. This is
the loop for anything the simulator refuses: lists, matrices, `getKey`
input, graph-screen output, speed, and memory.

---

## Which to reach for

| Question | Tool |
|---|---|
| Is my logic right? | simulator |
| Does this line even tokenize? | `build.py --lint`, then simulator |
| Why is my output cut off? | simulator, read the TRUNCATED report |
| What is this variable at line 40? | simulator `--trace` |
| Is my token spelled right? | SourceCoder 3 |
| Does it *actually* work? | emulator |
| Is it fast enough / small enough? | emulator, then the real calculator |

The honest workflow is: lint and simulate constantly, emulate before you
believe it, and put it on the physical calculator before you rely on it.
