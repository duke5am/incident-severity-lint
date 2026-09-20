"""`python3 -m incident_severity_lint` - the same CLI as the console script.

This exists so the package can be run without installing it. Note that
`python3 -m incident_severity_lint.cli` also works but makes runpy emit a
RuntimeWarning, because the package `__init__` imports `cli`; going through
`__main__` avoids that.
"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
