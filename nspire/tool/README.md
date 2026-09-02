# nspire/tool — third-party files

This directory holds the machinery for writing `.tns` documents. Two of
the files here did not originate in this project, and they are treated
differently in git.

## Not in this repository — you must supply them

```
plantilla.tns          not tracked
module_template.tns    not tracked
```

These are **Texas Instruments' own documents**, taken from TI-Nspire
software. They are the only source of the `Document.xml` and
`Problem1.xml` entries, which use compression method 13 — TI's
undocumented format that nothing here can generate (see
`docs/01-how-conversion-works.md`). The builder copies those entries
byte for byte and never regenerates them.

They are excluded from version control because no licence grants the
right to redistribute TI's files. This repository is public; those files
are not ours to publish.

**Without them, `python build.py nspire` will not run.** The TI-84 half
is unaffected.

### How to supply them

`plantilla.tns` is a **program** document (magic `*TIMLP0900`, one `q.py`
entry). Any document containing a single empty Python page works:

1. In TI-Nspire CX Student Software, create a new document
2. Insert → Python → New, leave it empty, save it
3. Copy it here as `plantilla.tns`

`module_template.tns` is a **module** document (magic `*TIMLP0901`, one
`.mpy` entry). Take one from your TI-Nspire installation:

```
TI-Nspire CX Student Software/res/documents/PyLib/ti_system.tns
```

Copy it here as `module_template.tns`.

Verify either one with:

```bash
python tools/inspect_file.py nspire/tool/plantilla.tns
```

The magic must read `*TIMLP0900` for the program template and
`*TIMLP0901` for the module template, and the metadata entries must show
`method 13`.

## Tracked, but not written here

```
mpy-cross-1.11.exe
```

The MicroPython cross-compiler, version 1.11, from the MicroPython
project — MIT licensed, which permits redistribution. It is vendored
rather than downloaded because **the version is load-bearing**: the
TI-Nspire CX II loads bytecode version 4 only, and MicroPython 1.12 and
later emit version 5, which fails to import with a message about the
document not being a module. `tools/build_nspire.py` checks the header
bytes after every compile rather than trusting them.

MicroPython is Copyright (c) 2013-2019 Damien P. George and contributors,
released under the MIT licence. Source: <https://github.com/micropython/micropython>

```
code_to_tns.py
tns_reader.py
```

Written for this workspace's `nspire-math-hub` project and carried over
here. Ours, and the reason the container work did not have to be
rediscovered.
