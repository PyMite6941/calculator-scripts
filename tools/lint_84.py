"""Catch the mistakes the TI tokenizer will happily encode for you.

The tokenizer never rejects anything. Feed it `Dispp X` and it emits
five tokens -- D, i, s, p, p -- because every one of those is a legal
token on its own. You get a .8xp that transfers fine and dies with
ERR:SYNTAX on the handheld, with no clue which line. Round-tripping the
file does not help either: it decodes back to `Dispp X`, byte-identical
to what you wrote.

So a build-time check cannot come from the tokenizer. It has to come
from rules about what real TI-BASIC looks like. These are those rules.

The load-bearing one is LOWERCASE. TI-BASIC variables are uppercase;
the lowercase letters exist as tokens but almost never appear outside a
string in a real program. Every mistyped command decays into a run of
them, which makes "a lowercase letter outside a string" a near-perfect
typo detector.
"""

import os
import sys

from basic84 import Scanner, preprocess
from devices import PROGRAM_WARN, PROGRAM_HARD_MAX, check_84_name

OPENERS = {"Then", "For(", "While ", "Repeat "}
CLOSER = "End"
LOWER = set("abcdefghijklmnopqrstuvwxyz")

# TI has TWO minus signs and they are different tokens. 0x71 is binary
# subtraction; 0xB0 is unary negation, the key printed (-) on the
# keypad. Source written in ASCII always produces 0x71, so `-B` encodes
# as "subtract B from nothing" and dies with ERR:SYNTAX on the handheld.
# Write negation as ~ instead. These are the bytes after which a value,
# not an operator, must come.
MINUS = bytes([0x71])
VALUE_EXPECTED_AFTER = {bytes([b]) for b in (
    0x10,                                # (
    0x2B,                                # ,
    0x3E,                                # :
    0x3F,                                # newline
    0x04,                                # -> (store)
    0x70, 0x71, 0x82, 0x83, 0xF0,        # + - * / ^
    0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F,  # = < > <= >= !=
    0xB0,                                # ~ itself
)}
NEWLINE = chr(10)
LABEL_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789θ")


class Finding:
    def __init__(self, level, code, line, message, hint=""):
        self.level, self.code = level, code
        self.line, self.message, self.hint = line, message, hint

    def __str__(self):
        s = "  %-5s %s  line %-4d %s" % (self.level, self.code,
                                         self.line, self.message)
        if self.hint:
            s += "\n              -> " + self.hint
        return s


def open_blocks_at(toks, index):
    """Which blocks are open just before `index`.

    Recomputed rather than threaded through the label pass, so the two
    passes stay independent and neither can corrupt the other's state.
    """
    stack = []
    for kind, text, _, _ in toks[:index]:
        if kind != "tok":
            continue
        if text in OPENERS:
            stack.append(text)
        elif text == CLOSER and stack:
            stack.pop()
    return stack


def menu_label_uses(toks):
    """Labels that Menu( jumps to.

    Menu("TITLE","OPTION",A,"OTHER",B) transfers control to Lbl A or
    Lbl B with no Goto anywhere in sight. Without this pass every
    menu-driven program -- which is most of them -- would be reported
    as having unused labels.

    Returns (label, line) pairs rather than a bare set, because a menu
    option pointing at a label that does not exist is an ERR:LABEL just
    like a bad Goto -- and reporting it needs a line number.
    """
    uses = []
    i = 0
    while i < len(toks):
        kind, text, _, _ = toks[i]
        if kind == "tok" and text == "Menu(":
            j = i + 1
            while j < len(toks):
                k, t, _, _ = toks[j]
                if k == "tok" and (t == ")" or t == NEWLINE):
                    break
                if k == "str":
                    # The title is also a string, but it is followed by
                    # another string rather than a label, so the label
                    # scan below simply finds nothing and moves on.
                    j += 1
                    if j < len(toks) and toks[j][1] == ",":
                        j += 1
                        chars, at = "", None
                        while j < len(toks) and len(chars) < 2:
                            k2, t2, line2, _ = toks[j]
                            if k2 == "tok" and t2 in LABEL_CHARS and len(t2) == 1:
                                if at is None:
                                    at = line2
                                chars += t2
                                j += 1
                            else:
                                break
                        if chars:
                            uses.append((chars, at))
                    continue
                j += 1
            i = j
            continue
        i += 1
    return uses


def _value_expected(prev, scanner):
    """True if a value, not an operator, must come next."""
    if prev is None:
        return True
    kind, text = prev
    if kind != "tok":
        return False
    if scanner.bits(text) in VALUE_EXPECTED_AFTER:
        return True
    # A command or function still waiting for its arguments: `Disp `,
    # `sqrt(`, `max(`. Their names carry the trailing space or paren.
    return len(text) > 1 and text[-1] in " ("


def lint(name, source, scanner=None):
    """Return a list of Findings for one program's source text."""
    scanner = scanner or Scanner()
    clean, line_map = preprocess(source)

    def orig(line):
        """Map a line in the preprocessed text back to the real file."""
        return line_map[line - 1] if 0 < line <= len(line_map) else line

    found = []
    for problem in check_84_name(name):
        found.append(Finding("ERROR", "N001", 1,
                             "program name %r: %s" % (name, problem),
                             "rename the source file -- its name is the "
                             "name the calculator will show"))

    toks = list(scanner.scan(clean))

    # --- typos and impossible characters ---------------------------------
    for kind, text, line, col in toks:
        if kind == "unk":
            found.append(Finding("ERROR", "T001", orig(line),
                                 "no token matches %r (col %d)" % (text, col),
                                 "this character does not exist on the "
                                 "handheld and would be silently dropped"))
        elif kind == "tok" and len(text) == 1 and text in LOWER:
            found.append(Finding("ERROR", "T002", orig(line),
                                 "lowercase %r outside a string (col %d)"
                                 % (text, col),
                                 "almost always a mistyped command -- the "
                                 "tokenizer split it into single letters"))

    # --- negation written as subtraction ----------------------------------
    prev = None
    for kind, text, line, col in toks:
        if kind == "str":
            prev = ("str", "")
            continue
        bits = scanner.bits(text)
        if bits == MINUS and _value_expected(prev, scanner):
            found.append(Finding("ERROR", "T003", orig(line),
                                 "'-' used as negation (col %d)" % col,
                                 "write ~ here. ASCII '-' is always the "
                                 "binary minus token; the handheld reads "
                                 "this as subtracting from nothing and "
                                 "raises ERR:SYNTAX"))
        prev = (kind, text)

    # --- block structure --------------------------------------------------
    stack = []
    for kind, text, line, col in toks:
        if kind != "tok":
            continue
        if text in OPENERS:
            stack.append((text, line))
        elif text == CLOSER:
            if not stack:
                found.append(Finding("ERROR", "B001", orig(line),
                                     "End with no open block",
                                     "delete it, or add the If/Then, For(, "
                                     "While or Repeat it was meant to close"))
            else:
                stack.pop()
    for opener, line in stack:
        found.append(Finding("ERROR", "B002", orig(line),
                             "%r is never closed" % opener.strip(),
                             "every Then, For(, While and Repeat needs its "
                             "own End"))

    # --- labels and jumps --------------------------------------------------
    labels, gotos = {}, []
    i = 0
    while i < len(toks):
        kind, text, line, col = toks[i]
        if kind == "tok" and text in ("Lbl ", "Goto "):
            # A label name is one or two characters from A-Z, 0-9, theta.
            chars, j = "", i + 1
            while j < len(toks) and len(chars) < 2:
                k, t, _, _ = toks[j]
                if k == "tok" and len(t) == 1 and t in LABEL_CHARS:
                    chars += t
                    j += 1
                else:
                    break
            label = chars or "?"
            if text == "Lbl ":
                if label in labels:
                    found.append(Finding("WARN", "L003", orig(line),
                                         "Lbl %s redefined (first at line %d)"
                                         % (label, orig(labels[label])),
                                         "Goto always finds the FIRST one; "
                                         "the second is unreachable"))
                else:
                    labels[label] = line
            else:
                gotos.append((label, line, open_blocks_at(toks, i)))
            i = j
            continue
        i += 1

    for label, line, open_now in gotos:
        if label not in labels:
            found.append(Finding("ERROR", "L001", orig(line),
                                 "Goto %s has no matching Lbl" % label,
                                 "ERR:LABEL at runtime -- and only if the "
                                 "jump is ever actually reached"))
        if open_now:
            found.append(Finding("WARN", "L002", orig(line),
                                 "Goto %s jumps out of an open %s"
                                 % (label, open_now[-1].strip()),
                                 "TI-BASIC leaks memory on every such jump "
                                 "and never reclaims it -- close the block "
                                 "before jumping"))
    # A menu option is a jump, so a missing target is the same runtime
    # ERR:LABEL a bad Goto gives -- except a menu hides it better, since
    # only the option nobody picked during testing is broken.
    menu_uses = menu_label_uses(toks)
    for label, line in menu_uses:
        if label not in labels:
            found.append(Finding("ERROR", "L005", orig(line),
                                 "Menu( option jumps to Lbl %s, which does "
                                 "not exist" % label,
                                 "ERR:LABEL the first time someone picks "
                                 "that option"))

    used = {g[0] for g in gotos} | {m[0] for m in menu_uses}
    for label, line in labels.items():
        if label not in used:
            found.append(Finding("NOTE", "L004", orig(line),
                                 "Lbl %s is never jumped to" % label,
                                 "dead weight -- every label costs bytes"))

    found.sort(key=lambda f: (f.line, f.code))
    return found


def size_findings(size):
    """Findings that need the tokenized size, so they run after the build."""
    if size > PROGRAM_HARD_MAX:
        return [Finding("ERROR", "S001", 1,
                        "%d bytes exceeds the %d-byte hard maximum"
                        % (size, PROGRAM_HARD_MAX),
                        "a variable entry stores its length in two bytes; "
                        "split the program in two")]
    if size > PROGRAM_WARN:
        return [Finding("WARN", "S002", 1,
                        "%d bytes is large (soft limit %d)"
                        % (size, PROGRAM_WARN),
                        "it has to sit in RAM to run, next to every list "
                        "and matrix it creates")]
    return []


def worst(findings):
    for level in ("ERROR", "WARN", "NOTE"):
        if any(f.level == level for f in findings):
            return level
    return "OK"


def main(argv):
    scanner = Scanner()
    errors = 0
    for path in argv:
        name = os.path.splitext(os.path.basename(path))[0].upper()
        with open(path, encoding="utf-8") as fh:
            findings = lint(name, fh.read(), scanner)
        print("%s  [%s]" % (path, worst(findings)))
        for f in findings:
            print(f)
        errors += sum(1 for f in findings if f.level == "ERROR")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main(sys.argv[1:]))
