"""Take a calculator file apart and explain it.

    python tools/inspect_file.py somefile.8xp
    python tools/inspect_file.py somefile.tns

This exists for two reasons.

The first is learning. Both formats are described in
docs/01-how-conversion-works.md, and reading that description next to
real bytes from your own calculator is worth more than either alone.

The second is verification, and it matters more. Everything this
toolchain writes is built from a spec, and a spec can be wrong. The
honest way to check is to send one program FROM the handheld to the PC
and run this on it: if the field layout printed here matches what the
builders produce, the spec holds for your device and OS version. If it
does not, this is where you will see it -- rather than on a calculator
that resets in an exam.

The .8xp section deliberately parses the header by hand rather than
handing the file to tivars, because the whole point is to show the
bytes. The decoded listing at the end does use tivars, since
detokenizing 1,188 tokens by hand would teach nothing.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TI83F_SIG = b"**TI83F*"

# The type byte in a variable entry. Only the ones a script project is
# likely to meet are named; anything else prints as a number.
VAR_TYPES = {
    0x00: "real",
    0x01: "real list",
    0x02: "matrix",
    0x03: "equation",
    0x04: "string",
    0x05: "program",
    0x06: "protected program (edit-locked)",
    0x07: "picture",
    0x08: "graph database",
    0x0C: "complex",
    0x0D: "complex list",
    0x15: "application variable",
    0x17: "group",
}


def u16(data, offset):
    """Little-endian, which is what every length field in these files is."""
    return data[offset] | (data[offset + 1] << 8)


def inspect_8xp(path):
    data = open(path, "rb").read()
    print("%s  (%d bytes on disk)" % (os.path.basename(path), len(data)))
    print("")

    if data[:8] != TI83F_SIG:
        print("  NOT a TI-83/84 variable file: signature is %r, expected %r"
              % (data[:8], TI83F_SIG))
        return 1

    print("  file header")
    print("    0x00  signature      %s" % data[:8].decode("ascii"))
    print("    0x08  magic          %s" % data[8:11].hex(" "))
    comment = data[11:53].rstrip(b"\x00").decode("ascii", "replace")
    print("    0x0B  comment        %r" % comment)
    section_len = u16(data, 53)
    print("    0x35  data length    %d" % section_len)

    # The checksum is the low 16 bits of the sum of every byte in the
    # data section. Recomputing it is the cheapest possible proof that
    # the file is intact and that the length field is being read right.
    body = data[55:55 + section_len]
    stored = u16(data, 55 + section_len)
    computed = sum(body) & 0xFFFF
    ok = "matches" if stored == computed else "MISMATCH"
    print("    end   checksum       0x%04X (%s, computed 0x%04X)"
          % (stored, ok, computed))
    print("")

    offset = 0
    index = 0
    while offset + 4 <= len(body):
        header_len = u16(body, offset)
        data_len = u16(body, offset + 2)
        var_type = body[offset + 4]
        name = body[offset + 5:offset + 13].rstrip(b"\x00")
        print("  entry %d" % index)
        print("    header length  %d %s" % (
            header_len,
            "(includes version + archive flag)" if header_len == 0x0D
            else "(older short form)"))
        print("    type           0x%02X  %s"
              % (var_type, VAR_TYPES.get(var_type, "unknown")))
        print("    name           %s" % name.decode("ascii", "replace"))

        cursor = offset + 2 + header_len
        if header_len == 0x0D:
            print("    version        %d" % body[offset + 13])
            flag = body[offset + 14]
            print("    archived       %s (flag 0x%02X)"
                  % ("yes" if flag & 0x80 else "no", flag))
        repeat = u16(body, cursor)
        payload = body[cursor + 2:cursor + 2 + data_len]
        print("    data length    %d (repeated as %d%s)"
              % (data_len, repeat,
                 "" if repeat == data_len else "  <-- SHOULD MATCH"))

        if var_type in (0x05, 0x06) and len(payload) >= 2:
            tokens = u16(payload, 0)
            print("    token bytes    %d" % tokens)
            print("    first bytes    %s" % payload[2:18].hex(" "))
        print("")

        offset = cursor + 2 + data_len
        index += 1

    if index == 0:
        print("  no variable entries found")
        return 1

    try:
        from tivars import TIProgram, TIProtectedProgram
        cls = TIProtectedProgram if var_type == 0x06 else TIProgram
        program = cls.open(path)
        print("  decoded TI-BASIC")
        print("  " + "-" * 60)
        for line in program.string().split("\n"):
            print("  " + line)
    except ImportError:
        print("  (install tivars to see the decoded listing)")
    except Exception as exc:
        print("  could not decode: %s: %s" % (type(exc).__name__, exc))
    return 0


def inspect_tns(path):
    sys.path.insert(0, os.path.join(ROOT, "nspire", "tool"))
    import tns_reader

    data = open(path, "rb").read()
    print("%s  (%d bytes on disk)" % (os.path.basename(path), len(data)))
    print("")
    print("  magic          %s" % data[:10].decode("ascii", "replace"))
    print("    *TIMLP0900 is a program document, *TIMLP0901 a PyLib module")
    print("  trailer        %s"
          % ("TIPD found" if b"TIPD" in data[-64:] else "NO TIPD - not a .tns"))
    print("")

    entries = tns_reader.parse_central_directory(data)
    print("  %d entries" % len(entries))
    for entry in entries:
        note = ""
        if entry.method == 13:
            note = "  <-- TI's own compression; opaque, copied not generated"
        elif entry.method == 8:
            note = "  <-- ordinary deflate; this is the part we can write"
        print("    %-20s method %2d  %6d -> %6d%s"
              % (entry.name, entry.method,
                 entry.uncompressed_size, entry.compressed_size, note))
    print("")

    for entry in entries:
        if entry.name.endswith(".py"):
            payload = tns_reader.extract_entry(data, entry)
            print("  source in %s" % entry.name)
            print("  " + "-" * 60)
            for line in payload.decode("utf-8", "replace").split("\n"):
                print("  " + line)
            break
        if entry.name.endswith(".mpy"):
            payload = tns_reader.extract_entry(data, entry)
            print("  bytecode in %s" % entry.name)
            print("    header       %r version %d flags 0x%02X small-int %d"
                  % (payload[:1], payload[1], payload[2], payload[3]))
            print("    the handheld accepts version 4 only -- a newer")
            print("    mpy-cross produces a module that will not import")
            break
    return 0


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    status = 0
    for path in argv:
        if not os.path.isfile(path):
            print("no such file: %s" % path)
            status = 1
            continue
        if path.lower().endswith(".tns"):
            status |= inspect_tns(path)
        else:
            status |= inspect_8xp(path)
        print("")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
