#!/usr/bin/env python3
"""severity_tool.py: the checkout entry point for incident-severity-lint.

This wrapper exists so the documented `python3 severity_tool.py ...` workflow
keeps working from a clone. The same CLI is installed as the
`incident-severity-lint` console script; the implementation lives in
`incident_severity_lint/cli.py` so that the installed package and the checkout
are the same code, not two versions of it.

Usage (unchanged):
  python3 severity_tool.py classify --users-affected all --core-flow down
  python3 severity_tool.py lint incident.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from incident_severity_lint.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
