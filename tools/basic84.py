"""Reading TI-BASIC source the way the calculator will read it.

Two jobs live here, and both the builder and the linter need them, so
neither owns it:

  preprocess()  strips the things that exist only for your benefit as a
                human editing a file on a PC -- full-line comments and
                indentation -- because on the handheld a leading space
                is a real token that costs a real byte.

  scan()        walks the source the way TI's tokenizer does: longest
                match wins, at every position. This is the single most
                important thing to understand about TI-BASIC, and it is
                why the linter exists. See docs/02-ti84-basic.md.
"""

import re

from tivars.models import TI_84PCE

# Source-level comment. This is OUR syntax, not TI's -- TI-BASIC has no
# comment character. A full-line `//` is unambiguous because `/` is
# division and no expression can begin with it.
COMMENT = re.compile(r"^\s*//")


TRAILING_WORD = re.compile(r"([A-Za-z]+)$")


def restore_bare_command(line, names):
    """Put back the trailing space a bare command needs.

    Most TI token names carry their trailing space: the token is `Pause `,
    not `Pause`. Usually that space is present anyway because an argument
    follows. But `Pause` with no argument is ordinary, valid TI-BASIC --
    and stripping the line to kill indentation also kills the space the
    token name depends on, so it would scan as P, a, u, s, e.

    So: if the line ends in a word that is not a token but becomes one
    with a space after it, the space goes back.
    """
    match = TRAILING_WORD.search(line)
    if not match:
        return line
    word = match.group(1)
    if word not in names and word + " " in names:
        return line + " "
    return line


def preprocess(text, names=None):
    """Source text -> the exact text handed to the tokenizer.

    Returns (clean_text, line_map) where line_map[i] is the 1-based line
    in the ORIGINAL file that produced output line i, so the linter can
    report a position you can actually find in your editor.
    """
    if names is None:
        names = set(TI_84PCE.tokens.names)
    out, line_map = [], []
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if COMMENT.match(raw):
            continue
        line = raw.strip()
        if not line:
            continue
        out.append(restore_bare_command(line, names))
        line_map.append(n)
    return "\n".join(out) + "\n", line_map


class Scanner:
    """Longest-match tokenizer over one calculator model's token table."""

    def __init__(self, model=TI_84PCE):
        self.model = model
        self.table = model.tokens.names
        self.names = set(self.table)
        self.maxlen = max(len(n) for n in self.names)

    def bits(self, name):
        """The byte(s) a token name encodes to.

        Names are not unique per token -- `->`, an ASCII convenience, and
        the real arrow both encode to 0x04. Rules that care about what a
        token IS must compare bits, never the spelling in the source.
        """
        tok = self.table.get(name)
        return tok.bits if tok is not None else b""

    def scan(self, text):
        """Yield (kind, text, line, col) for the whole source.

        kind is 'tok'    a real token, `text` is its canonical name
                'str'    a quoted string literal, scanned as one unit
                'unk'    a character no token matches -- always a bug
        """
        i, line, col = 0, 1, 1
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "\n":
                yield ("tok", "\n", line, col)
                i, line, col = i + 1, line + 1, 1
                continue
            if ch == '"':
                # A string runs to the next quote or to end of line --
                # TI closes an unterminated string at the newline, so a
                # missing quote is legal, not an error.
                j = i + 1
                while j < n and text[j] not in '"\n':
                    j += 1
                closed = j < n and text[j] == '"'
                end = j + 1 if closed else j
                yield ("str", text[i:end], line, col)
                col += end - i
                i = end
                continue
            for length in range(min(self.maxlen, n - i), 0, -1):
                cand = text[i:i + length]
                if "\n" in cand:
                    continue
                if cand in self.names:
                    yield ("tok", cand, line, col)
                    i += length
                    col += length
                    break
            else:
                yield ("unk", ch, line, col)
                i += 1
                col += 1
