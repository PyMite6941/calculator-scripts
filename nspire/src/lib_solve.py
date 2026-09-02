"""lib_solve.py -- shared numerics, built as an importable PyLib module.

The lib_ prefix is what tells the builder to produce a MODULE document
rather than a program. The prefix is stripped, so this becomes solve.tns
and is used on the handheld as:

    from solve import bisect, newton

For that import to resolve, solve.tns has to be in the handheld's PyLib
folder, not next to your program. See docs/04-transfer.md.

A module document ships COMPILED bytecode, not source, which has one
consequence worth knowing up front: you cannot read or edit it on the
calculator. Keep this file as the only copy that matters and rebuild.

Nothing here uses ti_system or input(), deliberately -- a library that
prompts the user is a library you cannot reuse.
"""


def bisect(f, lo, hi, tol=1e-10, limit=200):
    """Find a root of f between lo and hi by bisection.

    Requires f(lo) and f(hi) to have opposite signs; that is the whole
    guarantee bisection rests on, so it is checked rather than assumed.
    Slower than Newton's method but it cannot diverge, which makes it
    the right default on a device where a runaway loop means pulling
    the batteries.
    """
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if (flo < 0) == (fhi < 0):
        raise ValueError("f(lo) and f(hi) must straddle zero")

    for _ in range(limit):
        mid = (lo + hi) / 2
        fmid = f(mid)
        if fmid == 0 or (hi - lo) / 2 < tol:
            return mid
        if (fmid < 0) == (flo < 0):
            lo, flo = mid, fmid
        else:
            hi = mid
    return (lo + hi) / 2


def newton(f, df, x0, tol=1e-12, limit=60):
    """Find a root of f near x0 using its derivative df.

    Fast, but it can walk off to infinity or stall on a flat spot, so
    both the iteration count and a zero derivative are treated as
    failures rather than being allowed to loop forever.
    """
    x = x0
    for _ in range(limit):
        slope = df(x)
        if slope == 0:
            raise ValueError("derivative is zero at %g" % x)
        step = f(x) / slope
        x -= step
        if abs(step) < tol:
            return x
    raise ValueError("did not converge from %g" % x0)


def integrate(f, a, b, n=200):
    """Definite integral by Simpson's rule.

    n is forced even because Simpson's rule consumes points in pairs;
    an odd n would silently drop the last interval.
    """
    if n % 2:
        n += 1
    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        total += f(a + i * h) * (4 if i % 2 else 2)
    return total * h / 3
