"""Classify incident severity by user impact, and lint the incident record.

Standard library only - the tool deliberately has no runtime dependencies.

The CLI lives in `incident_severity_lint.cli` and is installed as the
`incident-severity-lint` console script; `classify` and `lint` are importable
on their own if you want to use the rules from your own code.
"""
from .cli import classify, lint, LEVELS, QUESTIONS, ORDER, REQUIRED_FIELDS

__version__ = "0.1.0"
__all__ = ["classify", "lint", "LEVELS", "QUESTIONS", "ORDER", "REQUIRED_FIELDS"]
