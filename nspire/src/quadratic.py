"""quadratic.py -- solve a*x^2 + b*x + c = 0 on a TI-Nspire CX II.

Builds to quadratic.tns, which you open and run like any other document.

This is MicroPython, not CPython. The differences that actually bite:

  * there is no `os`, no `io`, no file access, and no network. Anything
    that reaches outside the document does not exist.
  * the standard library is a subset. `math` is there; `decimal`,
    `fractions` and `statistics` are not.
  * memory is small. A list of a few thousand floats is already a lot,
    and running out mid-script can reset the handheld.

`ti_system` is TI's own module and is the bridge to the rest of the
document -- it is how a script reads and writes the variables your
Calculator and Graphs pages can see. It is imported lazily below so this
file still runs on a PC for testing.
"""

from math import sqrt


def roots(a, b, c):
    """Return the roots of a*x^2+b*x+c as a tuple.

    Two reals, one repeated real, or two complex written as
    (real, imaginary) pairs. Raises ValueError if a is zero, because
    then it is not a quadratic and silently returning one root would
    hide the caller's mistake.
    """
    if a == 0:
        raise ValueError("a is zero -- not a quadratic")
    d = b * b - 4 * a * c
    if d > 0:
        r = sqrt(d)
        return ((-b + r) / (2 * a), (-b - r) / (2 * a))
    if d == 0:
        return (-b / (2 * a),)
    r = sqrt(-d) / (2 * a)
    return ((-b / (2 * a), r), (-b / (2 * a), -r))


def ask(prompt):
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("numbers only")


def main():
    print("ax^2 + bx + c = 0")
    a = ask("a: ")
    while a == 0:
        print("a cannot be zero")
        a = ask("a: ")
    b = ask("b: ")
    c = ask("c: ")

    found = roots(a, b, c)
    if len(found) == 1:
        print("one root (repeated): %g" % found[0])
    elif isinstance(found[0], tuple):
        re, im = found[0]
        print("complex: %g + %gi" % (re, im))
        print("         %g - %gi" % (re, im))
    else:
        print("x1 = %g" % found[0])
        print("x2 = %g" % found[1])

    # Hand the answers back to the document so a Calculator page can use
    # them. Wrapped because ti_system exists only on the handheld.
    try:
        import ti_system
        ti_system.store_value("disc", b * b - 4 * a * c)
    except ImportError:
        pass


# The handheld runs a Python page as __main__, the same as CPython, so
# this guard fires on the device AND lets you `from quadratic import
# roots` on a PC to test the maths without being prompted for input.
# If a page ever fails to auto-run on the handheld, drop the guard and
# call main() directly -- nothing else here depends on it.
if __name__ == "__main__":
    main()
