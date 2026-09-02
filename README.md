# calculator-scripts

Maths programs for TI graphing calculators, written on a PC and compiled
into the formats the handhelds actually accept.

Two targets, two entirely different languages, one build:

| Target | Language | Source | Artifact |
|---|---|---|---|
| TI-84 Plus CE | TI-BASIC | `ti84/src/NAME.txt` | `ti84/dist/NAME.8xp` |
| TI-Nspire CX II | MicroPython | `nspire/src/name.py` | `nspire/dist/name.tns` |

## Quickstart

```bash
pip install -r requirements.txt
python build.py
```

That builds everything in both `src/` folders. To add a program you add
a file — there is no registry, no manifest, no list to update.

```bash
python build.py 84         # one platform only
python build.py nspire
python build.py --lint     # check TI-84 sources, write nothing
```

## What is here

```
build.py                one entry point
requirements.txt        tivars, for the TI-84 token table

ti84/src/*.txt          TI-BASIC source        -> ti84/dist/*.8xp
nspire/src/*.py         MicroPython source     -> nspire/dist/*.tns
nspire/src/lib_*.py     importable library     -> nspire/dist/PyLib/*.tns
nspire/tool/            the .tns container tool + TI's document templates

tools/devices.py        every hard device limit, in one place
tools/basic84.py        the TI-BASIC preprocessor and tokenizer scan
tools/lint_84.py        the checks the TI tokenizer will not do for you
tools/build_84.py       lint -> encode -> verify
tools/build_nspire.py   pack -> verify
tools/simulate_84.py    run TI-BASIC on a simulated 26x10 home screen
tools/inspect_file.py   take a .8xp or .tns apart and explain it
tools/tokens_84.json    the token table, exported for the browser

web/ti84.js             the same interpreter, ported for the browser
web/test_ti84.mjs       checks that port against the Python reference
web/build_page.py       assembles web/runner.html from the two above

docs/                   start at docs/00-START-HERE.md
```

## Running a program without a calculator

```bash
python tools/simulate_84.py ti84/src/QUADFORM.txt --trace
```

Or in a browser, with a clickable screen and step-through:
**[TI-84 Bench](https://claude.ai/code/artifact/7f1ab5c0-22ea-42e6-ad6d-08111a085c72)**

Rebuild that page after changing the interpreter, and never without
running the cross-check first:

```bash
node web/test_ti84.mjs && python web/build_page.py
```

There are two interpreters, which is a liability unless they agree. The
Python one is the reference -- it shares its scanner with the builder,
so it sees the token stream that actually gets written into the `.8xp`.
`web/test_ti84.mjs` runs both over the same programs and diffs the
resulting screen character for character.

`docs/07-testing.md` covers this, plus SourceCoder and setting up a real
emulator -- which is the only thing that can tell you the truth.

## The Nspire half needs two files you must supply

`nspire/tool/plantilla.tns` and `module_template.tns` are Texas
Instruments' own documents and are **not in this repository** -- no
licence permits redistributing them. `python build.py nspire` will not
run until you supply them; `nspire/tool/README.md` explains how. The
TI-84 half is unaffected.

## Read this before trusting anything here

**Nothing in this repository has been run on a physical calculator.** The
file formats are implemented from a documented spec, and every artifact
is verified against that spec — but a spec can be wrong, and TI has
shipped OS revisions that changed behaviour.

There is a cheap way to close that gap, and it should be the first thing
you do:

1. Write any small program on the handheld itself.
2. Send it to the PC with TI Connect CE / TI-Nspire Student Software.
3. Run `python tools/inspect_file.py thatfile.8xp`.

If the fields it prints line up with what the builders produce, the spec
holds for your device and OS. If they do not, you have found out here
rather than in an exam. See `docs/01-how-conversion-works.md`.

## The one thing to know per platform

**TI-84:** the tokenizer never rejects anything. `Dispp X` encodes
cleanly into five valid tokens and dies with `ERR:SYNTAX` on the
calculator with no line number. That is what `tools/lint_84.py` exists
to catch. Read `docs/02-ti84-basic.md`.

**TI-Nspire:** Python is a **CX II** feature. On an original CX there is
no Python at all, and this toolchain cannot help you — the TI-Basic and
Lua document formats are not generatable offline. Read
`docs/05-LIMITATIONS.md` before planning around it.
