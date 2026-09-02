"""web/template.html + the tested interpreter -> web/runner.html

    python web/build_page.py

The published page has to be a single file, but the interpreter it runs
must be the same one web/test_ti84.mjs checks against the Python
reference. So the interpreter is never pasted into the HTML by hand --
it is inlined here, from the file the tests import.

Run the tests before publishing:

    node web/test_ti84.mjs && python web/build_page.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TEMPLATE = os.path.join(HERE, "template.html")
INTERPRETER = os.path.join(HERE, "ti84.js")
TOKENS = os.path.join(ROOT, "tools", "tokens_84.json")
SRC = os.path.join(ROOT, "ti84", "src")
OUT = os.path.join(HERE, "runner.html")

# Sources that are not ready to ship in the page. A program that does not
# build has no business being the first thing a visitor runs.
SKIP = {"ENERGY"}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def programs():
    """Every buildable .txt in ti84/src/, newest interesting one first."""
    found = {}
    for filename in sorted(os.listdir(SRC)):
        if not filename.endswith(".txt"):
            continue
        name = filename[:-4].upper()
        if name in SKIP:
            continue
        found[name] = read(os.path.join(SRC, filename))
    if not found:
        raise SystemExit("no programs in ti84/src/")
    return found


def main():
    page = read(TEMPLATE)

    table = json.loads(read(TOKENS))
    loaded = programs()

    # The payloads go inside <script> elements, so the one sequence that
    # must never appear literally is a closing script tag. json.dumps
    # does not escape it; this does.
    def embed(value):
        return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")

    page = page.replace("/*{{TOKENS}}*/", embed(table))
    page = page.replace("/*{{PROGRAMS}}*/", embed(loaded))
    page = page.replace("/*{{INTERPRETER}}*/", read(INTERPRETER))

    for marker in ("{{TOKENS}}", "{{PROGRAMS}}", "{{INTERPRETER}}"):
        if marker in page:
            raise SystemExit("template placeholder %s was not filled" % marker)

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)

    print("web/runner.html  %.1f KB" % (len(page.encode("utf-8")) / 1024.0))
    print("  %d tokens, %d program(s): %s"
          % (len(table), len(loaded), ", ".join(sorted(loaded))))
    if SKIP:
        print("  skipped: %s" % ", ".join(sorted(SKIP)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
