# Start here

A route through this, in the order that makes each step pay off. Do not
read the docs front to back — most of them are references you come back
to when something breaks.

## Step 0 — decide what you are actually targeting

This matters more than anything else, and getting it wrong wastes days.

| You have | You write | This toolchain |
|---|---|---|
| TI-84 Plus CE / CE-T | TI-BASIC | yes |
| TI-84 Plus CE Python | TI-BASIC, or Python on-calc | TI-BASIC side, yes |
| TI-84 Plus (monochrome) | TI-BASIC | yes, change `MODEL` (see below) |
| TI-Nspire **CX II** | MicroPython | yes |
| TI-Nspire **CX** (original) | TI-Basic or Lua | **no** — see `05-LIMITATIONS.md` |

For a monochrome TI-84 Plus, edit `MODEL` in `tools/build_84.py` to
`TI_84P`. Colour-model tokens then fail at build time instead of on the
desk.

If you are on an original Nspire CX, stop and read `05-LIMITATIONS.md`
now. There is a real wall there and no way through it offline.

## Step 1 — prove the round trip before writing anything

Do not write a program first. Write *any* trivial program **on the
calculator**, send it to the PC, and inspect it:

```bash
python tools/inspect_file.py MYPROG.8xp
```

You are checking two things: that you can move files in both directions
at all, and that the format this toolchain assumes matches your actual
device. Both will bite you later if you skip this.

Then go the other way: `python build.py`, send `ti84/dist/QUADFORM.8xp`
to the handheld, and run it. Once a file has made the full loop you can
trust the pipeline and stop thinking about it.

`04-transfer.md` covers the cables and software.

## Step 2 — learn the language, not the tool

The build system is fifteen minutes. The languages are where the time
goes, and they have very little in common.

- **TI-84 → `02-ti84-basic.md`.** TI-BASIC is not BASIC. Every variable
  is global, there are no functions, there are 27 numeric variables in
  the entire machine, and the tokenizer will silently encode your typos.
  Read the whole thing once; it is short and every section is a trap
  someone hit.

- **TI-Nspire → `03-nspire-python.md`.** If you know Python you already
  know 90% of this. Read it for the 10% that is different: no file
  access, a cut-down standard library, tight memory, and `ti_system` as
  the only bridge to the rest of the document.

Start on whichever platform you actually need first. They do not build
on each other.

## Step 3 — read the two example programs

They are commented to be read, not just run.

- `ti84/src/QUADFORM.txt` — input, branching, the negation trap
- `ti84/src/TRIANGLE.txt` — menus and labels, and how branches fall
  through into each other if you forget `Stop`
- `nspire/src/quadratic.py` — a runnable Python page
- `nspire/src/lib_solve.py` — a library other documents import

## Step 4 — write your own

`06-adding-a-script.md` is the recipe. It is three steps and one of them
is "run the build".

## Step 5 — when something is wrong

In this order:

1. `python build.py --lint` — most TI-84 problems are caught here
2. `python tools/inspect_file.py <artifact>` — is the file what you think
3. `05-LIMITATIONS.md` — is what you are attempting actually possible

## What to read when

| Question | File |
|---|---|
| How does a .txt become something the calculator runs? | `01-how-conversion-works.md` |
| Why does my TI-84 program say ERR:SYNTAX? | `02-ti84-basic.md` |
| What can I import on the Nspire? | `03-nspire-python.md` |
| How do I get the file onto the device? | `04-transfer.md` |
| Can this thing even do X? | `05-LIMITATIONS.md` |
| How do I add another program? | `06-adding-a-script.md` |
| How do I run it without a calculator? | `07-testing.md` |
