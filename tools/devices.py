"""Every hard limit the two handhelds impose, in one place.

Nothing here is a style preference. Each number is a wall: cross it and
the program either refuses to transfer, refuses to run, or resets the
handheld. The builders read these and fail the build rather than let a
too-big artifact reach a device.

Sources are named per-constant so a future reader can re-check them
against TI's own documentation rather than trusting this file.
"""

# --------------------------------------------------------------------
# TI-84 Plus CE  (and the CE-T / Python editions -- same OS, same limits)
# --------------------------------------------------------------------

# A program name is a TI *variable* name: 1-8 characters, the first a
# letter (or theta), the rest letters or digits. Lowercase is not
# allowed here even though the CE has lowercase letter tokens.
NAME_MAX = 8
NAME_FIRST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "\u03b8"
NAME_REST = NAME_FIRST + "0123456789"

# The variable entry stores its payload length in two bytes, so 65535 is
# the absolute ceiling regardless of free memory.
PROGRAM_HARD_MAX = 65535

# User RAM on a TI-84 Plus CE is ~154 KB, but that is shared with every
# list, matrix, string and the OS's own scratch space. A single program
# over ~16 KB is already unwieldy to edit on-calc and leaves little room
# for the variables it creates, so the build warns well before the wall.
PROGRAM_WARN = 16384

# A TI-BASIC program must be in RAM to run. Archiving it frees RAM but
# the OS will not execute it -- you get ERR:ARCHIVED. This is not a size
# limit but it is the reason PROGRAM_WARN matters: everything you ship
# has to sit in RAM at once.
RUNS_FROM_ARCHIVE = False

LIST_MAX_ELEMENTS = 999
MATRIX_MAX_DIM = 99

# --------------------------------------------------------------------
# TI-Nspire CX II  (Python is a CX *II* feature -- see docs/05-LIMITATIONS.md)
# --------------------------------------------------------------------

# One .tns holds one Python page. The handheld decompresses the source
# before running it, so the limit is on the .py, not the packed document.
# Past roughly 40 KB of source the handheld can run out of memory while
# loading and reset itself, losing unsaved documents.
NSPIRE_PAGE_LIMIT = 40000

# The document name IS the module name on the handheld: mylib.tns is
# imported as `import mylib`. So a module's filename must be a legal
# Python identifier, and it must be lowercase to match how you will
# type the import.
NSPIRE_NAME_MAX = 32

# MicroPython bytecode header the CX II's interpreter accepts. A .mpy
# built by a newer mpy-cross will not import -- it fails silently as
# "not a module", which is why the vendored compiler is version-pinned.
MPY_MAGIC = (4, 0x03, 31)


def check_84_name(name):
    """Return a list of reasons `name` is not a legal TI-84 program name."""
    problems = []
    if not name:
        problems.append("empty name")
        return problems
    if len(name) > NAME_MAX:
        problems.append("%d characters, the limit is %d" % (len(name), NAME_MAX))
    if name[0] not in NAME_FIRST:
        problems.append("starts with %r; must start with A-Z or theta" % name[0])
    for ch in name[1:]:
        if ch not in NAME_REST:
            problems.append("contains %r; only A-Z, 0-9 and theta are allowed" % ch)
            break
    return problems
