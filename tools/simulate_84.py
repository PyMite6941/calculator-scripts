"""Run a TI-BASIC program on the PC, on a simulated handheld screen.

    python tools/simulate_84.py ti84/src/QUADFORM.txt
    python tools/simulate_84.py ti84/src/FACTOR.txt --input 6 --input 1 --input -2
    python tools/simulate_84.py ti84/src/FACTOR.txt --trace

This is NOT an emulator. An emulator runs TI's actual OS and is the only
thing that can tell you the truth -- see docs/07-testing.md for how to
set one up. This is a fast loop for the other 95% of your time: change a
line, see the answer, without a build and a cable.

What makes it worth trusting as far as it goes: it executes the SAME
token stream the calculator would. It runs `tools/basic84.py`'s scanner
over your source, so if you write `Dispp X` this fails the way the
handheld does, rather than quietly doing what you meant.

What it deliberately reproduces, because these are the bugs you will
actually hit:

  * a 26x10 home screen, with Disp TRUNCATING rather than wrapping
  * TI number formatting -- `.5` with no leading zero, 10 significant
    digits
  * the two minus signs as genuinely different operators
  * every variable global, surviving between programs

Read the SUPPORTED list at the bottom of this file before trusting a
result. Anything outside it raises rather than guessing.
"""

import os
import sys

from basic84 import Scanner, preprocess

# TI-84 Plus CE home screen. The monochrome models are 16x8 -- pass
# --narrow to see how your output degrades there.
COLS, ROWS = 26, 10
NARROW_COLS, NARROW_ROWS = 16, 8

SEPARATORS = {0x3F, 0x3E}          # newline, colon -- interchangeable
OPENERS = {"Then", "For(", "While ", "Repeat "}


class TIError(Exception):
    """An ERR: the handheld would raise. Carries the TI-style name."""

    def __init__(self, name, detail=""):
        self.name, self.detail = name, detail
        super().__init__("ERR:%s%s" % (name, "  (" + detail + ")" if detail else ""))


class Unsupported(Exception):
    """This simulator cannot do it. Not the same as a program error."""


class Frac(str):
    """The result of ►Frac.

    A string, because that is what it is on screen -- but tagged so Disp
    still right-aligns it the way it right-aligns a number.
    """


def to_frac(value):
    """►Frac, including the part where it gives up.

    The handheld converts to a fraction only while the denominator stays
    small; past that it leaves the decimal alone. Reproducing the giving
    up matters, because a root that displays as .3333333333 instead of
    1/3 is how you learn your arithmetic went through a float.
    """
    from fractions import Fraction
    if isinstance(value, str):
        return value
    approximation = Fraction(value).limit_denominator(9999)
    if abs(float(approximation) - value) > 1e-9:
        return value
    if approximation.denominator == 1:
        return float(approximation.numerator)
    return Frac("%d/%d" % (approximation.numerator,
                           approximation.denominator))


# ----------------------------------------------------------------------
# number formatting -- TI's, not Python's
# ----------------------------------------------------------------------

def ti_str(value):
    """Format a number the way the home screen shows it.

    TI drops the leading zero (`.5`, not `0.5`) and shows 10 significant
    digits in the default float mode. Getting this right matters more
    than it looks: `.3333333333` on screen is how you discover you are
    doing float maths where you wanted exact integers.
    """
    if isinstance(value, str):
        return value
    if value != value:                       # NaN
        return "NAN"
    if value in (float("inf"), float("-inf")):
        return "INF"

    if value == int(value) and abs(value) < 1e10:
        text = "%d" % int(value)
    else:
        text = "%.10g" % value
        if "e" in text:                      # TI writes exponents with E
            mantissa, exponent = text.split("e")
            return mantissa + "E" + str(int(exponent))

    if text.startswith("0."):
        text = text[1:]
    elif text.startswith("-0."):
        text = "-" + text[2:]
    return text


# ----------------------------------------------------------------------
# the screen
# ----------------------------------------------------------------------

class Screen:
    """A home screen that truncates, because the real one does."""

    def __init__(self, cols=COLS, rows=ROWS):
        self.cols, self.rows = cols, rows
        self.grid = [[" "] * cols for _ in range(rows)]
        self.cursor = 0
        self.truncated = []

    def clear(self):
        self.grid = [[" "] * self.cols for _ in range(self.rows)]
        self.cursor = 0

    def _scroll(self):
        self.grid.pop(0)
        self.grid.append([" "] * self.cols)
        self.cursor = self.rows - 1

    def write(self, text, row=None, col=0, right=False):
        if row is None:
            if self.cursor >= self.rows:
                self._scroll()
            row = self.cursor
            self.cursor += 1
        if len(text) > self.cols - col:
            self.truncated.append(text)
            text = text[:self.cols - col]
        if right:
            col = max(0, self.cols - len(text))
        for i, ch in enumerate(text):
            if 0 <= col + i < self.cols:
                self.grid[row][col + i] = ch

    def render(self):
        top = "    +" + "-" * self.cols + "+"
        out = [top]
        for i, row in enumerate(self.grid):
            out.append("%3d |%s|" % (i + 1, "".join(row)))
        out.append(top)
        out.append("     " + "".join(
            str((c + 1) % 10) if (c + 1) % 5 == 0 else " "
            for c in range(self.cols)))
        return "\n".join(out)


# ----------------------------------------------------------------------
# statements
# ----------------------------------------------------------------------

def split_statements(tokens, scanner):
    """Token stream -> list of statements, each a list of tokens.

    Newline and colon are the same thing to the calculator, so they are
    the same thing here.
    """
    statements, current = [], []
    for token in tokens:
        kind, text = token[0], token[1]
        if kind == "tok" and len(scanner.bits(text)) == 1 \
                and scanner.bits(text)[0] in SEPARATORS:
            statements.append(current)
            current = []
        else:
            current.append(token)
    statements.append(current)
    return [s for s in statements if s]


def match_blocks(statements):
    """Map each block opener to its Else and its End.

    Precomputed so Goto works: a jump can land anywhere, and the
    interpreter must still know what block it is inside.
    """
    ends, elses, stack = {}, {}, []
    for index, statement in enumerate(statements):
        head = statement[0][1] if statement else ""
        if head in OPENERS:
            stack.append(index)
        elif head == "Else":
            if not stack:
                raise TIError("SYNTAX", "Else with no If")
            elses[stack[-1]] = index
        elif head == "End":
            if not stack:
                raise TIError("SYNTAX", "End with no open block")
            ends[stack.pop()] = index
    if stack:
        raise TIError("SYNTAX", "unclosed block")
    return ends, elses


# ----------------------------------------------------------------------
# expressions
# ----------------------------------------------------------------------

class Parser:
    """Recursive descent over TI's token stream.

    Precedence, loosest to tightest, matching the handheld:
        or/xor  <  and  <  relational  <  + -  <  * / implicit  <
        unary neg  <  ^  <  atom
    Negation sitting BELOW ^ is why TI evaluates -2^2 as -4.
    """

    def __init__(self, tokens, machine):
        self.tokens, self.machine = tokens, machine
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def name(self):
        token = self.peek()
        return token[1] if token else None

    def kind(self):
        token = self.peek()
        return token[0] if token else None

    def take(self):
        token = self.peek()
        self.pos += 1
        return token

    def accept(self, *names):
        if self.name() in names:
            return self.take()[1]
        return None

    def at_end(self):
        return self.pos >= len(self.tokens)

    @staticmethod
    def num(value, where):
        """Arithmetic on a string is ERR:DATA TYPE on the handheld.

        Worth routing every operator through this rather than letting
        Python decide: Python would happily evaluate "AB"*3, and the
        whole point of this simulator is to fail where the calculator
        fails.
        """
        if isinstance(value, str):
            raise TIError("DATA TYPE", "%s got the string %r" % (where, value))
        return value

    # --- precedence ladder ---------------------------------------------

    def expr(self):
        left = self.and_expr()
        while True:
            operator = self.accept(" or ", " xor ")
            if operator is None:
                return left
            right = self.and_expr()
            if operator == " or ":
                left = float(bool(left) or bool(right))
            else:
                left = float(bool(left) != bool(right))

    def and_expr(self):
        left = self.rel()
        while self.accept(" and ") is not None:
            left = float(bool(left) and bool(self.rel()))
        return left

    def rel(self):
        left = self.add()
        while True:
            operator = self.accept("=", "<", ">", "<=", "≤",
                                   ">=", "≥", "!=", "≠")
            if operator is None:
                return left
            right = self.add()
            if operator == "=":
                left = float(left == right)
            elif operator == "<":
                left = float(left < right)
            elif operator == ">":
                left = float(left > right)
            elif operator in ("<=", "≤"):
                left = float(left <= right)
            elif operator in (">=", "≥"):
                left = float(left >= right)
            else:
                left = float(left != right)

    def add(self):
        left = self.mul()
        while True:
            operator = self.accept("+", "-")
            if operator is None:
                return left
            right = self.mul()
            if operator == "+":
                if isinstance(left, str) or isinstance(right, str):
                    if not (isinstance(left, str) and isinstance(right, str)):
                        raise TIError("DATA TYPE", "string + number")
                    left = left + right
                else:
                    left = left + right
            else:
                left = self.num(left, "-") - self.num(right, "-")

    def mul(self):
        left = self.unary()
        while True:
            operator = self.accept("*", "/")
            if operator is not None:
                right = self.unary()
                if operator == "*":
                    left = self.num(left, "*") * self.num(right, "*")
                else:
                    if self.num(right, "/") == 0:
                        raise TIError("DIVIDE BY 0")
                    left = self.num(left, "/") / right
                continue
            # Implicit multiplication: 2A, 2(X+1), A(B+C).
            #
            # This is also where a mistyped command lands. MENU( is not
            # Menu( -- it scans as M*E*N*U*(...), five variables times a
            # parenthesised group, and only fails here when one of those
            # turns out to be a string.
            if self.starts_value():
                left = self.num(left, "implicit *") \
                    * self.num(self.unary(), "implicit *")
                continue
            return left

    def starts_value(self):
        """Can the next token begin a value? Then juxtaposition means
        multiply -- which is why `2A` works and why you must never name
        a variable something that reads as two."""
        token = self.peek()
        if token is None:
            return False
        kind, text = token[0], token[1]
        if kind == "str":
            return False
        if text in ("(",):
            return True
        if len(text) == 1 and (text.isdigit() or text in self.machine.VARS):
            return True
        if text in ("pi", "π", "e", "Ans", "rand"):
            return True
        return text.endswith("(") and text not in (")",)

    def unary(self):
        if self.accept("~", "⁻", "|-") is not None:
            return -self.num(self.unary(), "negation")
        return self.power()

    def power(self):
        base = self.atom()
        if self.accept("^") is not None:
            base = self.num(base, "^") ** self.num(self.unary(), "^")
        elif self.accept("²", "^^2") is not None:
            # Both spellings, because the scanner yields whichever the
            # source used and they are the same single token.
            base = self.num(base, "squared") ** 2

        # Postfix display conversions bind after the value is complete.
        while True:
            if self.accept("►Frac", ">Frac") is not None:
                base = to_frac(base)
            elif self.accept("►Dec", ">Dec") is not None:
                base = float(base) if not isinstance(base, str) else base
            else:
                return base

    def atom(self):
        token = self.peek()
        if token is None:
            raise TIError("SYNTAX", "expression ended early")
        kind, text = token[0], token[1]

        if kind == "str":
            self.take()
            return text.strip('"')

        if text == "(":
            self.take()
            value = self.expr()
            self.accept(")")          # closing paren optional, as on TI
            return value

        if text.isdigit() or text == ".":
            return self.number()

        if text.endswith("(") and len(text) > 1:
            return self.call()

        if text in ("pi", "π"):
            self.take()
            import math
            return math.pi

        if text == "e":
            self.take()
            import math
            return math.e

        if text == "Ans":
            self.take()
            return self.machine.ans

        if text.startswith("Str"):
            self.take()
            return self.machine.strings.get(text, "")

        if len(text) == 1 and text in self.machine.VARS:
            self.take()
            return self.machine.vars.get(text, 0.0)

        raise Unsupported("cannot evaluate token %r" % text)

    def number(self):
        digits = ""
        while not self.at_end():
            text = self.name()
            if text is not None and (text.isdigit() or text == "."):
                digits += self.take()[1]
            else:
                break
        return float(digits) if digits else 0.0

    def call(self):
        import math
        function = self.take()[1]
        args = []
        if not self.at_end() and self.name() != ")":
            args.append(self.expr())
            while self.accept(",") is not None:
                args.append(self.expr())
        self.accept(")")

        one = args[0] if args else 0.0
        try:
            if function == "sqrt(" or function == "√(":
                if one < 0:
                    raise TIError("NONREAL ANS")
                return math.sqrt(one)
            if function == "abs(":
                return abs(one)
            if function == "int(":
                return float(math.floor(one))
            if function == "iPart(":
                return float(int(one))
            if function == "fPart(":
                return one - int(one)
            if function == "round(":
                digits = int(args[1]) if len(args) > 1 else 9
                return round(one, digits)
            if function == "gcd(":
                return float(math.gcd(int(one), int(args[1])))
            if function == "lcm(":
                return float(abs(int(one) * int(args[1]))
                             // math.gcd(int(one), int(args[1])))
            if function == "remainder(":
                return float(int(one) % int(args[1]))
            if function == "max(":
                return max(one, args[1])
            if function == "min(":
                return min(one, args[1])
            if function == "not(":
                return float(not bool(one))
            if function == "length(":
                return float(len(one))
            if function == "sub(":
                start = int(args[1]) - 1
                return one[start:start + int(args[2])]
            if function == "inString(":
                start = int(args[2]) - 1 if len(args) > 2 else 0
                return float(one.find(args[1], start) + 1)
            if function == "toString(":
                return ti_str(one)
            if function == "expr(":
                return self.machine.eval_text(one)
            if function in ("sin(", "cos(", "tan("):
                angle = math.radians(one) if self.machine.degrees else one
                return getattr(math, function[:-1])(angle)
            if function in ("sin^-1(", "cos^-1(", "tan^-1("):
                result = getattr(math, "a" + function[:3])(one)
                return math.degrees(result) if self.machine.degrees else result
            if function == "ln(":
                return math.log(one)
            if function == "log(":
                return math.log10(one)
            if function == "e^(":
                return math.exp(one)
            if function == "10^(":
                return 10.0 ** one
        except TIError:
            raise
        except (ValueError, OverflowError):
            raise TIError("DOMAIN", function)
        except ZeroDivisionError:
            raise TIError("DIVIDE BY 0")
        except IndexError:
            raise TIError("ARGUMENT", function + " needs more arguments")

        raise Unsupported("function %s is not implemented" % function)


# ----------------------------------------------------------------------
# the machine
# ----------------------------------------------------------------------

class Machine:
    VARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZθ"

    def __init__(self, scanner, screen, inputs=None, trace=False):
        self.scanner, self.screen = scanner, screen
        self.vars = {}
        self.strings = {}
        self.ans = 0.0
        self.degrees = False
        self.trace = trace
        self.inputs = list(inputs or [])
        self.steps = 0

    # --- input ---------------------------------------------------------

    def read(self, prompt):
        if self.inputs:
            raw = self.inputs.pop(0)
            print("%s%s" % (prompt, raw))
        else:
            print(self.screen.render())
            raw = input(prompt)
        return raw

    def eval_text(self, text):
        tokens = list(self.scanner.scan(text))
        return Parser(tokens, self).expr()

    # --- running -------------------------------------------------------

    def run(self, source):
        clean, _ = preprocess(source)
        tokens = list(self.scanner.scan(clean))

        for token in tokens:
            if token[0] == "unk":
                raise TIError("SYNTAX", "no token matches %r" % token[1])

        statements = split_statements(tokens, self.scanner)
        ends, elses = match_blocks(statements)
        labels = {}
        for index, statement in enumerate(statements):
            if statement[0][1] == "Lbl ":
                labels[self.label_of(statement)] = index

        loops = []
        pc = 0
        while pc < len(statements):
            self.steps += 1
            if self.steps > 500000:
                raise TIError("BREAK", "500,000 steps -- probably an "
                                       "infinite loop")
            statement = statements[pc]
            head = statement[0][1]
            if self.trace:
                print("  [%3d] %s" % (pc, self.render(statement)))

            pc = self.step(statement, head, pc, statements,
                           ends, elses, labels, loops)
            if pc is None:
                return

    def render(self, statement):
        return "".join(t[1] for t in statement)

    def label_of(self, statement):
        return "".join(t[1] for t in statement[1:3]).strip()

    def step(self, statement, head, pc, statements, ends, elses, labels, loops):
        rest = statement[1:]

        if head == "ClrHome":
            self.screen.clear()
            return pc + 1

        if head == "Disp ":
            for value in self.arglist(rest):
                self.screen.write(ti_str(value),
                                  right=self.aligns_right(value))
            return pc + 1

        if head == "Output(":
            args = self.arglist(rest)
            self.screen.write(ti_str(args[2]), row=int(args[0]) - 1,
                              col=int(args[1]) - 1)
            return pc + 1

        if head == "Pause ":
            if rest:
                for value in self.arglist(rest):
                    self.screen.write(ti_str(value),
                                      right=self.aligns_right(value))
            print(self.screen.render())
            # Only block for a human. Piped runs are how you regression-test
            # a program, and a Pause must not stall them.
            if not self.inputs and sys.stdin.isatty():
                input("      [ENTER]")
            return pc + 1

        if head == "Prompt ":
            for token in rest:
                if token[1] == ",":
                    continue
                name = token[1]
                self.assign(name, float(self.read("%s=?" % name)))
            return pc + 1

        if head == "Input ":
            prompt = "?"
            index = 0
            if rest and rest[0][0] == "str":
                prompt = rest[0][1].strip('"')
                index = 2 if len(rest) > 1 else 1
            name = rest[index][1]
            if name.startswith("Str"):
                self.strings[name] = self.read(prompt)
            else:
                self.assign(name, float(self.read(prompt)))
            return pc + 1

        if head == "If ":
            condition = self.eval(rest)
            following = statements[pc + 1] if pc + 1 < len(statements) else None
            if following is not None and following[0][1] == "Then":
                if condition:
                    return pc + 2
                target = elses.get(pc + 1)
                return (target + 1) if target is not None else ends[pc + 1] + 1
            return pc + 1 if condition else pc + 2

        if head == "Then":
            return pc + 1

        if head == "Else":
            return ends[self.opener_of(pc, statements)] + 1

        if head == "For(":
            args = self.arglist(rest, names=True)
            name = args[0]
            start, stop = args[1], args[2]
            step = args[3] if len(args) > 3 else 1.0
            self.assign(name, start)
            if (step > 0 and start > stop) or (step < 0 and start < stop):
                return ends[pc] + 1
            loops.append(("For(", pc, name, stop, step))
            return pc + 1

        if head == "While ":
            if self.eval(rest):
                loops.append(("While ", pc, rest, None, None))
                return pc + 1
            return ends[pc] + 1

        if head == "Repeat ":
            loops.append(("Repeat ", pc, rest, None, None))
            return pc + 1

        if head == "End":
            if not loops:
                return pc + 1
            kind, start, a, b, c = loops[-1]
            if ends.get(start) != pc:
                return pc + 1
            if kind == "For(":
                self.vars[a] = self.vars.get(a, 0.0) + c
                value = self.vars[a]
                if (c > 0 and value <= b) or (c < 0 and value >= b):
                    return start + 1
                loops.pop()
                return pc + 1
            if kind == "While ":
                if self.eval(a):
                    return start + 1
                loops.pop()
                return pc + 1
            if self.eval(a):          # Repeat exits when TRUE
                loops.pop()
                return pc + 1
            return start + 1

        if head == "Lbl ":
            return pc + 1

        if head == "Goto ":
            label = self.label_of(statement)
            if label not in labels:
                raise TIError("LABEL", "no Lbl " + label)
            del loops[:]              # TI leaks here; we simply drop it
            return labels[label]

        if head in ("Stop", "Return"):
            return None

        if head == "DelVar ":
            self.vars.pop(rest[0][1], None)
            return pc + 1

        if head == "Menu(":
            return self.menu(rest, labels)

        if head in ("Degree", "Radian"):
            self.degrees = (head == "Degree")
            return pc + 1

        if head == "Wait ":
            return pc + 1

        # Not a command, so it is an expression -- possibly a store.
        self.expression_statement(statement)
        return pc + 1

    def opener_of(self, pc, statements):
        depth = 0
        for index in range(pc - 1, -1, -1):
            head = statements[index][0][1]
            if head == "End":
                depth += 1
            elif head in OPENERS:
                if depth == 0:
                    return index
                depth -= 1
        raise TIError("SYNTAX", "Else with no If")

    def menu(self, rest, labels):
        parser = Parser(rest, self)
        parser.expr()                      # the title
        options = []
        while parser.accept(",") is not None:
            text = parser.expr()
            parser.accept(",")
            label = ""
            # Stop at ")" as well as ",". The final option is followed by
            # the closing paren, so without this the last label reads as
            # "5)" and only the LAST menu entry is ever broken -- which
            # is exactly the kind of bug that survives casual testing.
            while not parser.at_end() and parser.name() not in (",", ")"):
                label += parser.take()[1]
            options.append((text, label.strip()))

        print(self.screen.render())
        print("")
        for number, (text, _) in enumerate(options, 1):
            print("   %d: %s" % (number, text))
        choice = self.read("choice: ")
        label = options[int(choice) - 1][1]
        if label not in labels:
            raise TIError("LABEL", "no Lbl " + label)
        return labels[label]

    def expression_statement(self, statement):
        parser = Parser(statement, self)
        value = parser.expr()
        if parser.accept("->", "→") is not None:
            target = parser.take()[1]
            if target.startswith("Str"):
                self.strings[target] = value
            else:
                self.assign(target, value)
        else:
            self.ans = value
            self.screen.write(ti_str(value), right=self.aligns_right(value))

    @staticmethod
    def aligns_right(value):
        """Disp right-aligns numbers and left-aligns text -- and a
        Frac result counts as a number though it is carried as text."""
        return isinstance(value, Frac) or not isinstance(value, str)

    def assign(self, name, value):
        if name.startswith("Str"):
            self.strings[name] = value
        else:
            self.vars[name] = value
        self.ans = value

    def eval(self, tokens):
        return Parser(tokens, self).expr()

    def arglist(self, tokens, names=False):
        parser = Parser(tokens, self)
        args = []
        if parser.at_end():
            return args
        if names:
            args.append(parser.take()[1])
            parser.accept(",")
        args.append(parser.expr())
        while parser.accept(",") is not None:
            args.append(parser.expr())
        return args


# ----------------------------------------------------------------------

SUPPORTED = """
commands   ClrHome Disp Output( Pause Prompt Input If/Then/Else/End
           For( While Repeat End Lbl Goto Stop Return DelVar Menu(
           Degree Radian Wait  and bare expressions with -> store
functions  sqrt( abs( int( iPart( fPart( round( gcd( lcm( remainder(
           max( min( not( length( sub( inString( toString( expr(
           sin( cos( tan( and inverses, ln( log( e^( 10^(
values     A-Z theta, Str0-9, Ans, pi, e

NOT supported: lists, matrices, graphing, Text(, getKey, prgm calls,
seq(, sorting, statistics, anything touching the graph screen.
Those raise rather than guessing.
"""


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        print(SUPPORTED)
        return 2

    path = argv[0]
    trace = "--trace" in argv
    narrow = "--narrow" in argv
    inputs = [argv[i + 1] for i, a in enumerate(argv) if a == "--input"]

    if not os.path.isfile(path):
        print("no such file: %s" % path)
        return 1

    screen = Screen(*( (NARROW_COLS, NARROW_ROWS) if narrow else (COLS, ROWS) ))
    machine = Machine(Scanner(), screen, inputs=inputs, trace=trace)

    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    status = 0
    try:
        machine.run(source)
    except TIError as err:
        print(screen.render())
        print("")
        print("  %s" % err)
        print("  the handheld would stop here and offer Goto")
        return 1
    except Unsupported as err:
        print(screen.render())
        print("")
        print("  SIMULATOR LIMIT: %s" % err)
        print("  not a bug in your program -- see SUPPORTED in this file")
        return 2
    except (KeyboardInterrupt, EOFError):
        print("")
        return 1

    print(screen.render())
    print("")
    print("  %d statements executed" % machine.steps)
    if screen.truncated:
        print("")
        print("  %d line(s) TRUNCATED at %d columns:"
              % (len(screen.truncated), screen.cols))
        for text in screen.truncated:
            print("    %r" % text)
            print("     -> shown as %r" % text[:screen.cols])
    used = {k: v for k, v in machine.vars.items()}
    if used:
        print("")
        print("  variables: " + "  ".join(
            "%s=%s" % (k, ti_str(v)) for k, v in sorted(used.items())))
    return status


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main(sys.argv[1:]))
