"""nspire/src/name.py  ->  nspire/dist/name.tns

Same rule as the TI-84 side: no registry, drop a file in nspire/src/
and it builds. The filename matters more here than there, because on
the handheld the DOCUMENT name is the MODULE name -- geom.tns is what
`import geom` finds.

Two kinds of artifact come out, and the difference is not cosmetic:

  program  a document you open and run. Ends up in dist/.
  module   a document you import from another one. Ends up in
           dist/PyLib/, and belongs in the handheld's PyLib folder.

They are different file formats. A program document carries magic
*TIMLP0900 and a `q.py` source entry; a module carries *TIMLP0901 and a
`<name>.mpy` bytecode entry. Copy a program into PyLib and it will never
import, whatever you name it -- that is exactly the "not a module"
error. Name a source file `lib_name.py` to build it as a module.

Why a template is required
--------------------------
A .tns is a zip-like container, but two of its entries (Document.xml,
Problem1.xml) use compression method 13, which is TI's own and is not
documented. Nothing here can generate them. They are copied byte for
byte out of a real TI document and never touched. That is the whole
reason Python documents can be built offline and TI-Basic or Lua
documents cannot -- see docs/05-LIMITATIONS.md.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from devices import NSPIRE_PAGE_LIMIT, MPY_MAGIC

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "nspire", "src")
DIST = os.path.join(ROOT, "nspire", "dist")
LIB_DIST = os.path.join(DIST, "PyLib")
TOOL = os.path.join(ROOT, "nspire", "tool")

TEMPLATE = os.path.join(TOOL, "plantilla.tns")
MODULE_TEMPLATE = os.path.join(TOOL, "module_template.tns")
MPY_CROSS = os.path.join(TOOL, "mpy-cross-1.11.exe")

# The CX II's interpreter loads exactly one bytecode version. A newer
# mpy-cross emits v5 and the import fails with no useful message, so the
# compiler is vendored at 1.11 and the header is checked after every
# compile rather than trusted.
MPY_FLAGS = ["-mcache-lookup-bc", "-msmall-int-bits=31"]

LIB_PREFIX = "lib_"


def _tool():
    if TOOL not in sys.path:
        sys.path.insert(0, TOOL)
    import code_to_tns
    import tns_reader
    return code_to_tns, tns_reader


def source_files():
    if not os.path.isdir(SRC):
        return []
    return sorted(n for n in os.listdir(SRC)
                  if n.endswith(".py") and not n.startswith("_"))


def module_name(filename):
    """lib_geom.py -> geom (the name you will `import`)."""
    stem = filename[:-3]
    return stem[len(LIB_PREFIX):] if stem.startswith(LIB_PREFIX) else stem


def compile_mpy(py_path, mpy_path, label):
    """Compile to bytecode and prove the header matches the handheld.

    Work happens in a temp directory: this workspace lives under a path
    with Japanese characters in it, and mpy-cross 1.11 is a C program
    using the ANSI file APIs -- handed such a path it fails with a bare
    "OSError: 22". Copying in and out keeps the path off the compiler
    entirely.
    """
    work = tempfile.mkdtemp(prefix="mpyx")
    try:
        tmp_py = os.path.join(work, label + ".py")
        tmp_mpy = os.path.join(work, label + ".mpy")
        shutil.copyfile(py_path, tmp_py)
        # Run from inside the temp dir with bare filenames: mpy-cross
        # bakes the path it was given into the bytecode as the source
        # name, and an on-device traceback should say "geom.py", not a
        # Windows temp path.
        result = subprocess.run(
            [MPY_CROSS] + MPY_FLAGS + ["-o", label + ".mpy", label + ".py"],
            capture_output=True, cwd=work)
        if result.returncode != 0:
            raise SystemExit("mpy-cross failed on %s:\n%s"
                             % (label, result.stderr.decode("utf-8", "replace")))
        shutil.copyfile(tmp_mpy, mpy_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    blob = Path(mpy_path).read_bytes()
    got = (blob[1], blob[2], blob[3])
    if blob[:1] != b"M" or got != MPY_MAGIC:
        raise SystemExit(
            "%s: bytecode header %r/%s, need 'M'/%s -- wrong mpy-cross"
            % (label, blob[:1], got, MPY_MAGIC))
    return blob


def pack_program(py_path, tns_path):
    """Build a runnable document and prove the source survived."""
    code_to_tns, tns_reader = _tool()
    source = Path(py_path).read_text(encoding="utf-8")
    code_to_tns.build_tns(Path(TEMPLATE), source, Path(tns_path))

    data = Path(tns_path).read_bytes()
    want = source.encode("utf-8")
    for entry in tns_reader.parse_central_directory(data):
        if entry.name == "q.py":
            if tns_reader.extract_entry(data, entry) != want:
                raise SystemExit("VERIFY FAILED: q.py in %s does not match "
                                 "its source" % os.path.basename(tns_path))
            return len(want), len(data)
    raise SystemExit("VERIFY FAILED: no q.py entry in "
                     + os.path.basename(tns_path))


def pack_module(py_path, tns_path, name):
    """Build an importable PyLib document from TI's own module template."""
    import binascii
    import dataclasses
    code_to_tns, tns_reader = _tool()

    template = Path(MODULE_TEMPLATE).read_bytes()
    entries = tns_reader.parse_central_directory(template)
    mpy_path = os.path.join(os.path.dirname(tns_path), name + ".mpy")
    payload = compile_mpy(py_path, mpy_path, name)

    rebuilt = bytearray()
    central = []
    for entry in entries:
        offset = len(rebuilt)
        if entry.name.endswith((".mpy", ".pyt")):
            entry = dataclasses.replace(entry, name=name + ".mpy")
            blob = code_to_tns.raw_deflate(payload)
            crc = binascii.crc32(payload) & 0xFFFFFFFF
            csize, usize = len(blob), len(payload)
        else:
            # method 13. Copied, never regenerated.
            blob = template[entry.data_offset:
                            entry.data_offset + entry.compressed_size]
            crc = entry.crc32
            csize, usize = entry.compressed_size, entry.uncompressed_size
        rebuilt.extend(code_to_tns.build_local_header(
            entry, crc, csize, usize, first=(offset == 0)))
        rebuilt.extend(blob)
        central.append((entry, crc, csize, usize, offset))

    central_offset = len(rebuilt)
    directory = bytearray()
    for entry, crc, csize, usize, offset in central:
        directory.extend(code_to_tns.build_central_header(
            entry, crc, csize, usize, offset))
    rebuilt.extend(directory)
    rebuilt.extend(code_to_tns.build_tipd(len(central), len(directory),
                                          central_offset))

    # code_to_tns hardcodes the PROGRAM magic (*TIMLP0900) into the first
    # local header. A module is *TIMLP0901 -- that trailing digit is the
    # document format version, so keep the template's rather than
    # stamping a program version onto a library.
    rebuilt[0:10] = template[0:10]
    Path(tns_path).write_bytes(bytes(rebuilt))

    written = Path(tns_path).read_bytes()
    for entry in tns_reader.parse_central_directory(written):
        if entry.name == name + ".mpy":
            if tns_reader.extract_entry(written, entry) != payload:
                raise SystemExit("VERIFY FAILED: %s bytecode differs"
                                 % os.path.basename(tns_path))
            os.remove(mpy_path)
            return len(payload), len(written)
    raise SystemExit("VERIFY FAILED: no %s.mpy entry" % name)


def main():
    if not os.path.isfile(TEMPLATE):
        print("missing nspire/tool/plantilla.tns")
        print("the TI 'Add Python' template is what makes this possible")
        return 1

    names = source_files()
    if not names:
        print("no .py sources in nspire/src/ -- nothing to build")
        return 0

    os.makedirs(DIST, exist_ok=True)
    programs = [n for n in names if not n.startswith(LIB_PREFIX)]
    modules = [n for n in names if n.startswith(LIB_PREFIX)]

    print("TI-Nspire CX II  (MicroPython)")
    print("")

    over = []
    for filename in programs:
        name = module_name(filename)
        raw, packed = pack_program(os.path.join(SRC, filename),
                                   os.path.join(DIST, name + ".tns"))
        flag = ""
        if raw > NSPIRE_PAGE_LIMIT:
            flag = "  <-- over %d, may reset the handheld" % NSPIRE_PAGE_LIMIT
            over.append(name)
        print("  ok     %-16s %6d -> %5d bytes%s"
              % (name + ".tns", raw, packed, flag))

    if modules:
        os.makedirs(LIB_DIST, exist_ok=True)
        print("")
        for filename in modules:
            name = module_name(filename)
            raw, packed = pack_module(os.path.join(SRC, filename),
                                      os.path.join(LIB_DIST, name + ".tns"),
                                      name)
            print("  module %-16s %6d bytecode -> %5d bytes  (import %s)"
                  % (name + ".tns", raw, packed, name))

    print("")
    print("%d program(s) in nspire/dist/" % len(programs))
    if modules:
        print("%d module(s) in nspire/dist/PyLib/ -- copy these into the "
              "handheld's PyLib folder" % len(modules))
    print("every payload extracted back out and compared byte for byte")
    if over:
        print("")
        print("ERROR: %s exceed the page limit" % ", ".join(over))
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main())
