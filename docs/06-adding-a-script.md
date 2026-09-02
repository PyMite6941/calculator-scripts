# Adding a script

There is no registry, no manifest, no list of files anywhere. Add a
file, run the build. That is deliberate: a build that needs registering
will one day silently skip the file you forgot to register, and you find
out on the calculator.

---

## TI-84

**1. Create `ti84/src/NAME.txt`.**

The filename is the program name the calculator will show, so it has to
be a legal one: 1–8 characters, first a letter, rest letters or digits.
`SIMPSON.txt` → `prgmSIMPSON`. Illegal names fail at build time.

Add `.locked` before the extension (`MENU.locked.txt`) for a program
that runs but cannot be opened in the handheld's editor.

**2. Write it.**

```
// what this does, and anything non-obvious about it
ClrHome
Prompt A,B
Disp "ANSWER",A+B
```

Comments (`//` at line start) and indentation are stripped before
tokenizing — neither reaches the calculator, so use both freely.

Keep `docs/02-ti84-basic.md` open the first few times. The traps section
is the part that matters.

**3. Build.**

```bash
python build.py 84
```

Errors block the build; warnings do not but should be read. Run
`python build.py --lint` to check without writing anything.

**4. Transfer and run** — `docs/04-transfer.md`.

---

## TI-Nspire

**1. Create `nspire/src/name.py`** — or `nspire/src/lib_name.py` for a
library other documents import.

The filename becomes the document name, and for a module the document
name *is* the module name. `lib_geom.py` → `geom.tns` → `import geom`.
Lowercase it, and make it a legal Python identifier.

**2. Write it**, keeping the maths pure and the I/O in `main()`:

```python
from math import sqrt


def area(a, b, c):
    """No input(), no print() — so this is testable on a PC."""
    s = (a + b + c) / 2
    return sqrt(s * (s - a) * (s - b) * (s - c))


def main():
    a = float(input("a: "))
    ...


if __name__ == "__main__":
    main()
```

**3. Test on the PC first** — most bugs are ordinary Python bugs:

```bash
cd nspire/src
python -c "from heron import area; print(area(3,4,5))"
```

**4. Build.**

```bash
python build.py nspire
```

Programs land in `nspire/dist/`, modules in `nspire/dist/PyLib/`. They
go to different places on the handheld — `docs/04-transfer.md`.

---

## Extending the tooling itself

The pieces are separated so each can grow without disturbing the others.

| Want to | Change |
|---|---|
| Add or adjust a lint rule | `tools/lint_84.py` — add a pass, append `Finding`s |
| Change a device limit | `tools/devices.py` — the only place any limit lives |
| Target a monochrome TI-84 Plus | `MODEL` in `tools/build_84.py` → `TI_84P` |
| Add a source-level convenience | `preprocess()` in `tools/basic84.py` |
| Understand a built file | `python tools/inspect_file.py <file>` |

A new lint rule is a loop over the token stream that appends `Finding`
objects. `Scanner.scan()` yields `(kind, text, line, col)` where kind is
`tok`, `str` or `unk`, and `Scanner.bits(name)` gives the token's actual
bytes — compare bits, not spelling, since `->` and `→` are the same
token written two ways.

Keep new rules at `ERROR` only when a false positive would be rare. An
`ERROR` blocks the build; a `WARN` does not. The lowercase rule
(`T002`) is an `ERROR` because every single lowercase letter on the CE
is a display character from the `0xBB` block — none is an operator or a
constant, so there is nothing legitimate for it to misfire on.

---

## Before you commit

```bash
python build.py
```

Exit status is non-zero if anything failed, so it works as a pre-commit
check. Both `dist/` folders are build output — regenerate rather than
edit, and consider whether they belong in version control at all.
