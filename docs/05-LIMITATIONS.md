# Limitations

The point of this document is that you find out here rather than three
days into building something that cannot work.

Split into: walls that cannot be moved, things this toolchain does not
do yet but could, and what has and has not actually been verified.

---

## Hard walls — no workaround exists

### 1. TI-Nspire TI-Basic and Lua documents cannot be generated

A `.tns` holds `Document.xml` and `Problem1.xml` under **compression
method 13**, which is TI's own and undocumented. Nothing here can produce
those entries; they are copied byte for byte out of a real TI document
and never regenerated.

A Python document survives this only because its payload entry (`q.py`)
is ordinary deflate. A TI-Basic or Lua document is method 13 throughout.

**Consequence:** to write TI-Basic or Lua for the Nspire, you must use
TI-Nspire Student Software on a PC or write on the handheld. This
toolchain cannot help, and no amount of work on it will change that
without reverse-engineering method 13.

### 2. Python does not exist on an original TI-Nspire CX

Python is a **CX II** feature, in hardware and firmware. There is no OS
update that adds it to a CX. If the target is a CX, the answer is
TI-Basic, and see wall 1.

### 3. A TI-84 program cannot run from archive

`ERR:ARCHIVED`. Everything you ship sits in RAM at once, alongside every
list, matrix and string it creates. That is why the build warns at 16 KB
rather than at the format's 65535-byte ceiling.

### 4. TI-BASIC has no functions, no locals, and 27 numeric variables

Not a toolchain limitation — the language genuinely has no parameters,
no return values, and no scope. Programs share all state. Any design
that assumes reusable components has to be rethought as shared
conventions about which globals mean what.

### 5. The tokenizer cannot validate

There is no grammar to check against; encoding is longest-match at every
position. `tools/lint_84.py` is a set of heuristics about what real
TI-BASIC looks like, not a compiler. It will not catch:

- `Menu(` branches falling through into each other for want of `Stop`
- wrong angle mode
- uninitialised variables
- any logic error at all

### 6. Exam mode disables all of it

Press-to-Test on both platforms disables user programs. Assume anything
here is unavailable in a proctored exam.

---

## Not done yet — could be

These are real gaps, not walls. Roughly in order of how much they would
be missed.

- **The simulator covers only a subset.** `tools/simulate_84.py` runs
  TI-BASIC on the PC (see `docs/07-testing.md`), but has no lists,
  matrices, graphing, `getKey` or `prgm` calls. It raises on those
  rather than guessing. Extending it is the highest-value work left.
- **The simulator is not an emulator.** It knows nothing about speed or
  memory exhaustion, so it cannot tell you a program is too slow or too
  big. Only a real emulator or the handheld can.
- **No TI-84 program groups.** Shipping ten programs means ten
  transfers. `.8xg` group files would make it one; `tivars` has
  `TIGroup` and this is mostly plumbing.
- **No AppVar support.** Data too big for lists and strings goes in
  application variables. `tivars` supports them; nothing here uses them.
- **No `.8xv` / list / matrix generation.** A program that needs a
  1,000-element lookup table currently has to build it at runtime.
- **The linter has no dataflow.** It cannot tell you a variable is read
  before it is written, which is the most common remaining bug class.
- **No Nspire linting at all.** Python source is not checked against the
  handheld's module list, so `import statistics` builds cleanly and
  fails on the device.
- **No size breakdown.** The build reports a total; it cannot tell you
  which part of a program is expensive.
- **Nspire programs are single-page.** One `.tns`, one Python page. Real
  multi-page documents (a Python page next to a Graphs page) need
  method 13 — see wall 1.

---

## What has actually been verified

Be precise about this, because the difference matters.

**Verified on this machine:**

- TI-BASIC source encodes to `.8xp` and decodes back to identical token
  bytes, through a file on disk
- the `.8xp` header, variable entry layout and checksum parse correctly
  with an independent hand-written parser (`tools/inspect_file.py`)
  that agrees with `tivars` on every field
- `.tns` documents build with their payload extracting back byte for
  byte, and the method-13 metadata copied unaltered
- module bytecode carries the `M`/version 4/flags 0x03 header the
  handheld requires
- the Nspire Python examples produce correct results under CPython

**Not verified — no calculator was involved:**

- that any artifact actually runs on a physical TI-84 Plus CE
- that any `.tns` opens on a physical TI-Nspire CX II
- that a built module imports from `PyLib` on a real device
- every device limit in `tools/devices.py`. They come from TI's
  documentation and community reference material, not measurement.
- exam-mode behaviour on any specific device or OS version

**Close the gap like this:** write a small program on the handheld, send
it to the PC, and run `python tools/inspect_file.py` on it. If the field
layout matches what the builders produce, the spec holds for your device
and OS revision. This takes five minutes and is worth doing before the
first real program, not after.

---

## Version pins that are load-bearing

Not stylistic. Changing these breaks things quietly.

| Pin | Why |
|---|---|
| `mpy-cross-1.11.exe` | the handheld loads bytecode version 4 only; 1.12+ emits version 5 and the import fails as "not a module" |
| `-msmall-int-bits=31`, `-mcache-lookup-bc` | the flags TI's own PyLib modules were built with |
| `plantilla.tns`, `module_template.tns` | the only source of method-13 metadata. Losing these makes the Nspire half unbuildable. |
| `tivars` | owns the 1,188-entry token table. Reimplementing it from memory is how you get silently-wrong programs; it is not attempted here. |
