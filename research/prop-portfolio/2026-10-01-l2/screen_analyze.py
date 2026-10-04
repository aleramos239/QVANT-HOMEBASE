#!/usr/bin/env python3
"""Stage A screen analysis of the NQ Level-2 pilot: the command line.

    python screen_analyze.py score | nullc1 | gates | stress | report | status      (options: screen_analysis.py's docstring)

The code is in `screen_analysis.py`. This file is only the entry point, because the module NAME `screen_analyze` belongs to
the previous pilot: R/screen_analyze.py is imported lazily by R's own modules (wf_offline, a3p3, a3_pass2, funded_search ...,
reached through score.walk_forward and the equivalence tests), and this directory comes before R on sys.path. So:
  run as a script            -> screen_analysis.main()
  imported as screen_analyze -> the import is handed to R/screen_analyze.py, unchanged (read-only, no bytecode written into R).
"""
import sys

if __name__ == "__main__":
    import screen_analysis
    sys.exit(screen_analysis.main())
elif __name__ == "screen_analyze":
    import importlib.util
    from pathlib import Path

    sys.dont_write_bytecode = True                       # never drop __pycache__ into R
    _path = Path(__file__).resolve().parent.parent / "2026-09-29" / "screen_analyze.py"
    _spec = importlib.util.spec_from_file_location(__name__, _path)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[__name__] = _mod                         # `import screen_analyze` returns R's module
    _spec.loader.exec_module(_mod)
