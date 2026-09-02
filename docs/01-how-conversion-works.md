# How conversion works

This is the doc you asked for: what actually has to happen to turn text
on a PC into something a calculator will run. The two platforms solve it
in completely different ways.

Everything below can be checked against a real file from your own
calculator with `python tools/inspect_file.py <file>`. Do that at least
once — it is the difference between believing this document and knowing
it.

---

## TI-84: text becomes *tokens*

A TI-84 does not store your program as text. It stores it as **tokens**:
one or two bytes per command. `Disp ` is a single byte, `0xDE`. The word
"Disp" never exists on the calculator.

This is why you cannot just rename a `.txt` to `.8xp`. Conversion is a
real encode.

### The token table

There are 1,188 token names for a TI-84 Plus CE. Some are one byte, some
are two — `0x5C`, `0x5D`, `0x5E`, `0xBB` and `0xEF` are prefix bytes that
introduce a second byte, which is how TI added commands over the years
without running out of space.

A few landmarks, so the hex dumps in `inspect_file.py` mean something:

| Bytes | Token |
|---|---|
| `0x30`–`0x39` | digits `0`–`9` |
| `0x41`–`0x5A` | letters `A`–`Z` |
| `0x5B` | `θ` |
| `0x3F` | newline |
| `0x04` | `→` (store) |
| `0x70` `0x71` `0x82` `0x83` `0xF0` | `+` `-` `*` `/` `^` |
| `0xB0` | `⁻` (negation — **not** the same as `0x71`) |
| `0x6A`–`0x6F` | `=` `<` `>` `≤` `≥` `≠` |
| `0xCE` `0xCF` `0xD4` | `If ` `Then` `End` |
| `0xDE` | `Disp ` |
| `0x5D` `0x00` | `L₁` (two-byte: list prefix + index) |

Note that `Disp ` includes its trailing space and `sqrt(` includes its
opening paren. The space and the paren are *part of the token*, not
separate bytes.

### Tokenizing is longest-match, and that is the whole problem

At each position the encoder takes the longest token name that matches.
There is no grammar, no parse, no validation. Which means:

```
Dispp X   ->   D  i  s  p  p  ␣  X      seven perfectly legal tokens
```

`Disp ` did not match (no space after `Disp`), so it fell back to the
single-letter tokens `D`, `i`, `s`, `p`, `p`. The file builds. It
transfers. It dies with `ERR:SYNTAX` on the calculator and does not tell
you which line.

Round-tripping does not save you either: decode those seven tokens and
you get back `Dispp X`, exactly what you wrote.

**This is why `tools/lint_84.py` exists.** A build-time check cannot come
from the encoder, so it comes from rules about what real TI-BASIC looks
like. The strongest one is lowercase: TI-BASIC variables are uppercase,
lowercase letters exist as tokens but almost never appear outside a
string, and every mistyped command decays into a run of them.

### The .8xp container

Once you have token bytes, they get wrapped:

```
offset  size  what
0x00    8     "**TI83F*"
0x08    3     1A 0A xx        xx varies by writer; not load-bearing
0x0B    42    comment, null-padded
0x35    2     length of the data section (little-endian)
0x37    ...   the data section
end     2     checksum: low 16 bits of the sum of the data section
```

And the data section holds one variable entry:

```
2   length of the entry header that follows (0x0D on modern files)
2   data length
1   type      0x05 program, 0x06 protected (edit-locked) program
8   name, null-padded, uppercase
1   version           } only present when the header
1   archive flag      } length above is 0x0D
2   data length, repeated
N   the data
```

For a program, that data is itself `2 bytes of token-stream length`
followed by the tokens.

Every length is little-endian. The two-byte data length is why
`PROGRAM_HARD_MAX` in `tools/devices.py` is 65535 — the format cannot
describe a bigger one.

`tools/inspect_file.py` parses all of this by hand, deliberately, so you
can read the code next to the table above.

---

## TI-Nspire: source becomes a *document*

The Nspire runs real MicroPython, so there is no tokenizing. The problem
is the container.

A `.tns` is a zip-like archive with a `TIPD` end-of-directory record
instead of the usual one. Look inside TI's own "Add Python" document:

```
Document.xml   method 13   <- TI's own compression. Opaque.
Problem1.xml   method 13   <- TI's own compression. Opaque.
q.py           method  8   <- ordinary deflate
```

Method 13 is not a documented compression method. Nothing here can
generate those two entries, and nothing here tries. **They are copied
byte for byte out of a real TI document** (`nspire/tool/plantilla.tns`)
and never regenerated.

Your Python source is the `q.py` entry, and that one is plain deflate —
ordinary zip work. Swap it, fix the CRCs and offsets, rebuild the
directory, done.

That asymmetry is the single most important fact about this format:

> Python documents can be built offline **because and only because**
> their payload entry is ordinary deflate. A TI-Basic or Lua document is
> method 13 all the way down, so it cannot be built this way at all.

### Programs and modules are different formats

```
program   magic *TIMLP0900   payload entry "q.py"      source
module    magic *TIMLP0901   payload entry "name.mpy"  compiled bytecode
```

A module ships *compiled bytecode*, not source, and the bytecode version
is load-bearing: the handheld's interpreter accepts version 4 (which
means MicroPython ≤ 1.11 — 1.12 already emits version 5). A version-5
`.mpy` fails to import with a message that says the document is "not a
module", which sends you looking at names and folders when the real
problem is the compiler.

That is why `mpy-cross-1.11.exe` is vendored in `nspire/tool/` and why
`build_nspire.py` checks the header bytes after every compile instead of
trusting them.

---

## What the builders verify

Both builders check their own output rather than assuming it worked.

**TI-84** (`tools/build_84.py`):
1. re-open the `.8xp` from disk and compare token bytes to what was
   encoded — proves the container round-tripped
2. decode it back to text, re-encode that text, and require identical
   bytes — proves the ASCII stand-ins (`sqrt(`, `->`, `~`) normalise
   stably

**TI-Nspire** (`tools/build_nspire.py`):
1. extract the payload back out of the built `.tns` and compare it byte
   for byte to the source (or to the compiled bytecode)
2. for modules, check the `.mpy` header is `M`/version 4/flags 0x03

None of this proves your program is *correct*. It proves the file is
what you meant to write. Correctness is the linter's job on the TI-84
and yours everywhere.
