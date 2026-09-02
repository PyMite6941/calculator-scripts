"""Build everything.

    python build.py            both platforms
    python build.py 84         TI-84 Plus CE only
    python build.py nspire     TI-Nspire CX II only
    python build.py --lint     check the TI-84 sources, write nothing

Exit status is non-zero if anything failed, so this can gate a commit.

Adding a script is not a code change. Put a .txt in ti84/src/ or a .py
in nspire/src/ and run this -- there is no list of files to update
anywhere. That is deliberate: a build that needs a registry entry will
one day silently skip the file you forgot to register, and you will
find out on the calculator.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))


def main(argv):
    want = [a for a in argv if not a.startswith("-")]
    lint_only = "--lint" in argv

    if lint_only:
        import lint_84
        from glob import glob
        sources = sorted(glob(os.path.join(HERE, "ti84", "src", "*.txt")))
        if not sources:
            print("no TI-84 sources to lint")
            return 0
        return lint_84.main(sources)

    status = 0
    if not want or "84" in want:
        import build_84
        status |= build_84.main()
        print("")
    if not want or "nspire" in want:
        import build_nspire
        status |= build_nspire.main()
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
