# TI-BASIC on the TI-84 Plus CE

TI-BASIC is not BASIC. It is closer to a keystroke macro language with a
maths engine attached. The things that will surprise you are not syntax;
they are the absence of features you assume every language has.

## The mental model

- **There are no functions.** No parameters, no return values, no local
  scope. You can call another program, but it shares every variable with
  you.
- **Every variable is global.** All 27 of them.
- **There are 27 numeric variables in the machine**: `A` to `Z` and `θ`.
  That is not per-program. That is the whole calculator.
- **Nothing is declared.** Everything exists already, holding whatever
  the last program left in it.
- **It is interpreted, and slowly.** Roughly thousands of operations per
  second, not millions.

Practically: a TI-BASIC program is a script that mutates a small shared
global state. Write accordingly — clean up after yourself with `DelVar`,
and never assume a variable starts at zero.

## The storage you have

| Kind | Names | Notes |
|---|---|---|
| Numbers | `A`–`Z`, `θ` | real or complex; 27 total |
| Lists | `L1`–`L6`, plus named lists | up to 999 elements |
| Strings | `Str0`–`Str9` | 10 total |
| Matrices | `[A]`–`[J]` | up to 99×99 |
| Equations | `Y1`–`Y0` | the graph screen's functions |
| Pictures | `Pic0`–`Pic9` | |

Named lists are the escape hatch when six is not enough — up to five
characters, e.g. `∟SCORE`. Write the `∟` as `|L` in source.

## Output and input

```
ClrHome                 clear the home screen
Disp X                  print, left-aligned, scrolling
Disp "TEXT",X,Y         several at once
Output(row,col,X)       print at an exact position, 1-indexed
Pause                   wait for ENTER
Pause X                 show X, then wait

Prompt A,B,C            asks "A=?" "B=?" "C=?"
Input "SIDE: ",A        your own prompt text
Input Str1              read a string
Menu("TITLE","OPT 1",A,"OPT 2",B)     jump to Lbl A / Lbl B
getKey                  key code of the key held right now, or 0
```

`getKey` does **not** wait. It returns immediately, which is why
interactive programs wrap it in `Repeat K`.

## Control flow

```
If X>0                        single statement, no End
Disp "POSITIVE"

If X>0                        block form
Then
Disp "POSITIVE"
End

If X>0
Then
...
Else
...
End

For(I,1,10)        For(I,1,10,2) for a step
...
End

While X<10
...
End

Repeat X>10        runs at least once, exits when TRUE
...
End

Lbl A / Goto A     unconditional jump
Stop               end the program
Return             return from a subprogram
```

Note `Repeat` exits when its condition is **true** — it is the opposite
of `While`. This catches everyone once.

---

# The traps

Each of these has cost someone a day. Most are checked by
`tools/lint_84.py`; the ones that are not are marked.

## 1. There are two minus signs

`-` is subtraction. `⁻` (the `(-)` key) is negation. They are different
tokens: `0x71` and `0xB0`.

Source written in ASCII always produces `0x71`, so:

```
-B/(2A)->X          WRONG. "subtract B from nothing" -> ERR:SYNTAX
~B/(2A)->X          right. ~ is this project's spelling of the (-) key
```

Checked: `T003`.

## 2. The tokenizer will encode your typos

`Dispp X` is seven valid tokens. It builds, it transfers, it fails on the
calculator with `ERR:SYNTAX` and no line number.

The tell is lowercase. Every single lowercase letter on the CE is a
*display character* from the `0xBB` block — none of them is an operator
or a constant. So a lowercase letter outside a string is essentially
always the wreckage of a mistyped command.

Checked: `T002`.

## 3. `Goto` out of an open block leaks memory permanently

Jumping out of an `If/Then`, `For(`, `While` or `Repeat` before its `End`
leaves the block's bookkeeping on the stack. TI-BASIC never reclaims it.
Do it in a loop and the calculator runs out of memory and freezes.

```
For(I,1,100)              LEAKS, 100 times
If L1(I)=X
Goto F
End

For(I,1,100)              fine
If L1(I)=X
Then
I->J
100->I
End
End
```

Checked: `L002` (as a warning — it builds, because sometimes you really
do mean it).

## 4. `Menu(` branches fall through

`Menu(` jumps to a label. There is no return, and nothing stops execution
at the next `Lbl`. Every branch must end in `Stop` or it runs straight
into the following branch's code.

```
Menu("PICK","ONE",A,"TWO",B)
Lbl A
Disp "ONE"
Stop                      <- without this, "TWO" prints as well
Lbl B
Disp "TWO"
```

**Not checked** — falling through is occasionally deliberate and the
linter cannot tell. This is the most common bug in menu programs; check
it by hand.

## 5. Angle mode belongs to the user, not to you

`sin(`, `cos(`, `tan(` read the calculator's Degree/Radian setting, which
you did not set and cannot see. A program that is correct on your desk
gives wrong answers on someone else's calculator.

Either force it per-expression — `cos(60°)`, `sin(X)ʳ`, written in source
as `cos(60^^o)` and `sin(X)^^r` — or set the mode with `Degree` /
`Radian` at the top, and be aware you have then changed a global setting
the user did not ask you to change and will not know to change back.

**Not checked.**

## 6. Closing parens and quotes are optional at end of line

`Disp "HI"` and `Disp "HI` are the same program, one byte apart. So are
`Output(1,1,X)` and `Output(1,1,X`. On a machine with 154 KB of RAM this
is a real optimisation, and you will see it in other people's code.

The linter does not complain about either form.

## 7. An archived program will not run

Archiving frees RAM but the OS refuses to execute from it —
`ERR:ARCHIVED`. Everything you ship has to sit in RAM at once, which is
why `tools/devices.py` warns at 16 KB rather than at the 65535-byte
format limit.

## 8. Program names are 8 characters, uppercase, letter-first

`QUADFORM` is exactly at the limit. The filename in `ti84/src/` *is* the
name, so `quad-form.txt` is rejected at build time rather than producing
a program you cannot call.

Checked: `N001`.

## 9. Speed

The interpreter is slow enough that structure matters:

- reading a list element is much cheaper than recomputing a value
- `seq(` and list arithmetic run in the OS, not the interpreter — one
  list operation beats a `For(` loop over the same data every time
- `Disp` inside a loop is often the slowest thing in the program
- `Goto` scans the program from the top to find its `Lbl`, so a jump to
  a label near the end of a long program is genuinely slow

---

## Writing source in this project

Three things in `ti84/src/*.txt` are conveniences that never reach the
calculator:

- **`//` at the start of a line** is a comment, stripped before
  tokenizing. TI-BASIC has no comment character.
- **Indentation** is stripped. On the handheld a leading space is a real
  token costing a real byte.
- **ASCII stand-ins** for symbols you cannot type.

Name a file `NAME.locked.txt` to build an edit-locked program — it runs
but cannot be opened in the handheld's program editor.

### ASCII stand-ins

| Write | Get | |
|---|---|---|
| `->` | `→` | store |
| `~` | `⁻` | negation |
| `sqrt(` | `√(` | |
| `cuberoot(` | `³√(` | |
| `xroot` | `ˣ√` | |
| `<=` `>=` `!=` | `≤` `≥` `≠` | |
| `sin^-1(` or `asin(` | `sin⁻¹(` | same for cos, tan |
| `|L` | `ʟ` | named-list prefix |
| `|E` | `ᴇ` | scientific-notation exponent |
| `theta` | `θ` | |
| `pi` | `π` | |
| `^^o` `^^r` | `°` `ʳ` | force degrees / radians |
| `>Frac` `>Dec` | `►Frac` `►Dec` | |

You can also paste the real glyphs directly; both encode identically.

**Watch the spaces on `and`, `or`, `xor`.** Their token names *include*
the surrounding spaces, so `A=1 or B=2` is one token and `A=1or B=2` is
not — it decays into `o` and `r`. The linter catches it as lowercase.

---

## Reading `ERR:` messages

| Message | Usually means |
|---|---|
| `ERR:SYNTAX` | a typo the tokenizer encoded anyway — run `--lint` |
| `ERR:ARCHIVED` | the program is in archive; unarchive it |
| `ERR:LABEL` | `Goto` to a `Lbl` that does not exist |
| `ERR:UNDEFINED` | a variable or list you never assigned |
| `ERR:DOMAIN` | argument out of range, e.g. `sin⁻¹(2)` |
| `ERR:DIM MISMATCH` | lists of different lengths in one expression |
| `ERR:INVALID DIM` | list index of 0, or past the end |
| `ERR:MEMORY` | out of RAM — often trap 3 above |
| `ERR:BREAK` | you pressed ON |

Choosing **Goto** at an error prompt jumps the editor to the offending
line. That is the fastest debugging tool the calculator has.
