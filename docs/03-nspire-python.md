# MicroPython on the TI-Nspire CX II

If you know Python you already know most of this. This doc is the part
that is different.

**Python is a CX II feature.** An original TI-Nspire CX has no Python at
all, and no OS update adds it. Check the back of the unit before you
plan around this.

## What you get

MicroPython — a real Python 3 implementation, cut down for
microcontrollers. Classes, closures, generators, exceptions,
comprehensions, `try/finally` all work.

Available modules include `math`, `random`, `cmath`, `time`, `sys`, plus
TI's own `ti_system`, `ti_plotlib`, `ti_hub` and `ti_rover`.

## What is missing, and why it matters

- **No filesystem.** No `open()`, no `os`, no `pathlib`. A script cannot
  read or write files. Anything you want to persist goes through
  `ti_system` into the document's variables.
- **No network.** No `socket`, no `urllib`, no `requests`.
- **A subset of the standard library.** `decimal`, `fractions`,
  `statistics`, `itertools`, `collections`, `re` and `datetime` are
  either absent or partial. If your algorithm depends on one, port it or
  pick a different algorithm.
- **Small memory.** A few thousand floats in a list is already a lot.
  Running out mid-script can reset the handheld and lose unsaved work.
- **No threads.** A long loop makes the handheld unresponsive until it
  finishes.
- **`float` is what you get.** No arbitrary-precision integers to lean
  on. Integer overflow behaviour differs from CPython.

## Talking to the rest of the document

`ti_system` is the bridge between a Python page and the Calculator,
Graphs and Lists pages in the same document.

```python
import ti_system

ti_system.store_value("disc", 17.0)      # write a document variable
x = ti_system.recall_value("width")      # read one
ti_system.store_list("xs", [1, 2, 3])
ys = ti_system.recall_list("ys")
```

That is the *only* way out of the script. Import it lazily, or in a
`try/except ImportError`, so your file still runs on a PC for testing —
see the bottom of `nspire/src/quadratic.py`.

## Programs vs modules

This is the distinction that costs people the most time, because the
failure mode is a message about the wrong thing.

**A program** is a document you open and run. Source lives inside it as
`q.py`. Build one by putting `name.py` in `nspire/src/`.

**A module** is a document you `import` from another one. It ships
*compiled bytecode*, lives in the handheld's `PyLib` folder, and is
imported by document name. Build one by naming the source
`lib_name.py` — the `lib_` prefix is stripped, so `lib_solve.py`
becomes `solve.tns` and is used as `from solve import bisect`.

They are genuinely different file formats, not the same file in
different folders (see `01-how-conversion-works.md`). Copying a program
document into `PyLib` produces a "not a module" error no matter what you
name it.

Two consequences of modules shipping bytecode:

- you cannot read or edit a module on the calculator. The source in
  `nspire/src/` is the only copy that matters — keep it.
- the bytecode version is pinned. `mpy-cross-1.11.exe` is vendored
  because the handheld accepts version 4 only, and the build checks the
  header after every compile rather than trusting it.

## Practical shape of a script

```python
from math import sqrt


def solve(a, b, c):
    """Pure. No input(), no print(), no ti_system."""
    ...


def main():
    """Everything interactive lives here."""
    a = float(input("a: "))
    ...


if __name__ == "__main__":
    main()
```

Keeping the maths pure and the I/O in `main()` is worth the small extra
effort: you can `from quadratic import roots` on a PC and test the
algorithm properly, instead of debugging on a calculator keypad.

The handheld runs a Python page as `__main__`, so the guard fires on the
device as well. If a page ever fails to auto-run, drop the guard and
call `main()` directly — nothing else depends on it.

## Testing before you transfer

Most bugs are ordinary Python bugs and CPython will find them:

```bash
cd nspire/src
python -c "from quadratic import roots; print(roots(1,-3,2))"
```

What CPython will *not* catch:

- modules that do not exist on the handheld (`import statistics`)
- memory exhaustion
- `ti_system` behaviour
- MicroPython/CPython differences in integer and float edge cases

For those, transfer and test on the device. Do it early with something
small rather than late with something large.

## Size

The page limit is 40,000 bytes of **source** (the handheld decompresses
before running, so the packed `.tns` size is not what counts). Past that
the handheld can run out of memory while loading and reset itself.

The build fails rather than warns at that limit. If you are near it,
split the shared parts into a `lib_` module — modules ship as bytecode
and are loaded on demand, so the cost lands differently.
