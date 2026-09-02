"""ti84/src/NAME.txt  ->  ti84/dist/NAME.8xp

There is no registry to edit. Drop a .txt in ti84/src/ and it builds.
The filename is the program name the calculator will show, so
QUADFORM.txt becomes prgmQUADFORM.

Each build does three things in order, and stops at the first failure:

  1. lint    rules about real TI-BASIC (tools/lint_84.py). The tokenizer
             will not catch a typo, so this is where typos get caught.
  2. encode  hand the cleaned source to tivars, which owns the 1,188-entry
             token table. See docs/05-LIMITATIONS.md for why that table is
             not reimplemented here.
  3. verify  read the .8xp back off disk and require its token bytes to
             match what was encoded, then require those bytes to survive
             a decode/re-encode. This proves the container and payload
             survived; it does NOT prove the program is correct, which
             is what step 1 is for.
"""

import os
import sys

from tivars import TIProgram, TIProtectedProgram
from tivars.models import TI_84PCE

from basic84 import preprocess, Scanner
from lint_84 import lint, size_findings, worst

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "ti84", "src")
DIST = os.path.join(ROOT, "ti84", "dist")

# The model whose token table we encode against. A CE token that does not
# exist on an older TI-84 Plus will encode here and fail there, so if the
# target is a monochrome 84 Plus change this to TI_84P and rebuild -- the
# unsupported tokens then fail at build time instead of on the desk.
MODEL = TI_84PCE

# An "edit-locked" program still runs but cannot be opened in the program
# editor on the handheld. Name a source file NAME.locked.txt to get one.
LOCKED_SUFFIX = ".locked"


def source_files():
    if not os.path.isdir(SRC):
        return []
    return sorted(n for n in os.listdir(SRC) if n.endswith(".txt"))


def program_name(filename):
    """QUADFORM.txt -> QUADFORM;  MENU.locked.txt -> MENU."""
    stem = filename[:-4]
    if stem.endswith(LOCKED_SUFFIX):
        stem = stem[:-len(LOCKED_SUFFIX)]
    return stem.upper()


def discard_stale(name):
    """Delete the artifact for a program that no longer builds.

    Leaving it is the dangerous option: a .8xp in dist/ is a promise
    that it came from the source next to it, and the moment that stops
    being true you will transfer a version whose bug you already fixed.
    A failed build must not leave a plausible-looking file behind.

    The removal is verified rather than assumed -- this workspace is
    under OneDrive, where a delete can report success and leave the file
    in place.
    """
    path = os.path.join(DIST, name + ".8xp")
    if not os.path.isfile(path):
        return False
    os.remove(path)
    if os.path.isfile(path):
        raise SystemExit(
            "could not delete the stale %s -- it is out of date and would "
            "be transferred by mistake. Remove it by hand." % path)
    return True


def build_one(filename, scanner):
    """Returns (name, findings, size_or_None). None size means not built."""
    path = os.path.join(SRC, filename)
    name = program_name(filename)
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    findings = lint(name, source, scanner)
    if any(f.level == "ERROR" for f in findings):
        return name, findings, None

    clean, _ = preprocess(source)
    locked = filename[:-4].endswith(LOCKED_SUFFIX)
    program = (TIProtectedProgram if locked else TIProgram)(name=name)
    program.load_string(clean)

    out = os.path.join(DIST, name + ".8xp")
    program.save(out)

    # Verify against the file on disk, not the object in memory.
    #
    # Comparing decoded TEXT to the source would fail on every program,
    # and correctly so: `sqrt(` and `->` are ASCII stand-ins that decode
    # back as the real glyphs. The bytes are what the handheld runs, so
    # the bytes are what gets checked.
    cls = TIProtectedProgram if locked else TIProgram
    reread = cls.open(out)
    if reread.data != program.data:
        raise SystemExit(
            "VERIFY FAILED: %s did not survive the round trip to disk\n"
            "  wrote %d bytes, read back %d"
            % (out, len(program.data), len(reread.data)))

    # And prove the ASCII stand-ins normalise stably: re-encoding what
    # the file decodes to must land on the same bytes. If it does not,
    # some token in this program has no faithful text form and would
    # come back different every time it were edited on the handheld.
    again = cls(name=name)
    again.load_string(reread.string())
    if again.data != program.data:
        raise SystemExit(
            "VERIFY FAILED: %s does not re-encode to itself\n"
            "  a token in this program has no stable text form" % out)

    size = len(program.data)
    findings += size_findings(size)
    return name, findings, size


def main():
    os.makedirs(DIST, exist_ok=True)
    names = source_files()
    if not names:
        print("no .txt sources in ti84/src/ -- nothing to build")
        return 0

    scanner = Scanner(MODEL)
    failed, warned, total = 0, 0, 0
    print("TI-84 Plus CE  (token table: %s)" % MODEL.name)
    print("")
    for filename in names:
        name, findings, size = build_one(filename, scanner)
        if size is None:
            stale = discard_stale(name)
            print("  FAIL   %-12s not built%s"
                  % (name + ".8xp",
                     "  (removed the previous one)" if stale else ""))
            failed += 1
        else:
            print("  ok     %-12s %5d bytes on the handheld  [%s]"
                  % (name + ".8xp", size, worst(findings)))
            total += size
        for f in findings:
            print(f)

        warned += sum(1 for f in findings if f.level == "WARN")

    print("")
    built = len(names) - failed
    print("%d/%d built, %d bytes total, in ti84/dist/"
          % (built, len(names), total))
    if built:
        print("every .8xp re-read from disk and re-encoded to identical bytes")
    if warned:
        print("%d warning(s) -- these build, but read them" % warned)
    if failed:
        print("")
        print("%d program(s) had errors and were NOT built" % failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main())
