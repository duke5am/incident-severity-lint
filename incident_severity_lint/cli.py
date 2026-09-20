#!/usr/bin/env python3
"""Incident severity classifier and record linter.

Two problems this solves, both of which make postmortems worthless:

  1. Severity is declared by feel, so a "SEV3" that took the checkout down sits
     next to a "SEV1" that broke an internal dashboard. The classification below
     asks about USER IMPACT, because that is what severity is supposed to mean -
     not how interesting the bug is, and not who noticed it.

  2. Incidents get recorded without the fields needed to learn from them: no
     owner, no timeline, no user-visible impact, no action items. The linter
     names what is missing and refuses to call it done.

Usage:
  incident-severity-lint classify --help
  incident-severity-lint classify --users-affected all --core-flow down
  incident-severity-lint lint incident.json
  incident-severity-lint lint incident.json --json

  # from a checkout, without installing:
  python3 severity_tool.py lint incident.json
  python3 -m incident_severity_lint lint incident.json

Standard library only: argparse, json, os, sys. There is no package data.

Exit codes: 0 = no findings (only MTTD notes), 1 = findings, 2 = the record
could not be read, is not valid JSON, or is not a JSON object.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ordered worst-first. Each level states the user-facing condition, so the
# question is answerable during an incident without debate.
LEVELS = [
    ("SEV1", "Critical",
     "A core flow is unusable for all or nearly all users, or there is data loss "
     "or exposure. Someone must be woken up now."),
    ("SEV2", "Major",
     "A core flow is degraded or unusable for a subset of users, or a "
     "non-core flow is fully down. Page the on-call team."),
    ("SEV3", "Minor",
     "Reduced quality or availability with a workaround, or impact limited to a "
     "small group. Handle in hours, not at 3am."),
    ("SEV4", "Low",
     "Cosmetic, or impact with no measurable user effect. Handle in normal hours."),
]

# (id, question, the answer that escalates, why it matters)
QUESTIONS = [
    ("core_flow", "What is the state of your CORE user flow (login, checkout, the main thing the product does)?",
     {"down": "SEV1", "degraded": "SEV2", "fine": None}),
    ("users_affected", "How many users are affected?",
     {"all": "SEV1", "many": "SEV2", "some": "SEV3", "few": "SEV4"}),
    ("data_integrity", "Is data lost, corrupted, or exposed?",
     {"yes": "SEV1", "unknown": "SEV2", "no": None}),
    ("workaround", "Is there a workaround for affected users?",
     {"no": "SEV2", "yes": None}),
    ("duration", "How long has it been going on?",
     {"hours": "SEV2", "days": "SEV2", "minutes": None}),
    ("revenue", "Is revenue directly affected?",
     {"yes": "SEV2", "no": None}),
]

ORDER = {name: i for i, (name, _, _) in enumerate(LEVELS)}
REQUIRED_FIELDS = [
    ("id", "a stable incident id"),
    ("title", "a short title"),
    ("severity", "a severity level (SEV1-SEV4)"),
    ("started_at", "when it started (ISO 8601)"),
    ("detected_at", "when it was detected - the gap to started_at is your detection time"),
    ("impact", "the user-visible impact, not the technical cause"),
    ("commander", "who ran the incident"),
    ("timeline", "timestamped events"),
    ("resolution", "what actually stopped the impact"),
    ("action_items", "follow-ups, each with an owner and a due date"),
]


def classify(answers: dict) -> tuple:
    """Return (severity, reasons). Blank/unknown answers never escalate."""
    worst = None
    reasons = []
    for qid, question, mapping in QUESTIONS:
        ans = answers.get(qid)
        if ans in (None, "", "unknown"):
            continue
        sev = mapping.get(ans)
        if sev is None:
            continue
        if worst is None or ORDER[sev] < ORDER[worst]:
            worst = sev
        reasons.append(f"{qid}={ans} -> {sev}")
    if worst is None:
        worst = "SEV4"
        reasons.append("no escalating answer given -> SEV4 (lowest)")
    return worst, reasons


def lint(record: dict) -> list:
    """Return a list of findings about an incident record."""
    out = []
    for field, why in REQUIRED_FIELDS:
        v = record.get(field)
        if v in (None, "", [], {}):
            out.append(f"missing {field}: needs {why}")
    # ordering: detected_at must not precede started_at
    s, d = record.get("started_at"), record.get("detected_at")
    if s and d:
        if str(d) < str(s):
            out.append(f"detected_at ({d}) is before started_at ({s}) - "
                       f"one of them is wrong")
        else:
            out.append(f"note: detection delay {d} - {s} (this is your MTTD)")
    # action items must be actionable
    items = record.get("action_items") or []
    if isinstance(items, list):
        for i, it in enumerate(items, 1):
            if not isinstance(it, dict):
                out.append(f"action_items[{i}]: must be an object with owner and due")
                continue
            if not it.get("owner"):
                out.append(f"action_items[{i}]: no owner - an action without an owner "
                           f"is a wish")
            if not it.get("due"):
                out.append(f"action_items[{i}]: no due date - these rot in a backlog")
    sev = record.get("severity")
    if sev and sev not in ORDER:
        out.append(f"severity {sev!r} is not one of {', '.join(ORDER)}")
    # the honest one
    if sev and "impact" in record and record.get("impact"):
        impact = str(record["impact"]).lower()
        if any(w in impact for w in ("error", "exception", "stack", "timeout", "500")):
            out.append("impact reads like a technical symptom; severity is about "
                       "user impact - say what users could not do")
        # The mismatch check: this is the whole reason the tool exists. A stored
        # severity that is LOWER than the recorded impact implies is the costly
        # mistake - it delays the page and understates the postmortem.
        implied = None
        if any(w in impact for w in ("all users", "everyone", "unusable", "data loss",
                                     "exposed", "breach", "down for all")):
            implied = "SEV1"
        elif any(w in impact for w in ("degraded", "some users", "intermittent",
                                       "slow for", "partial")):
            implied = "SEV2"
        if implied and sev in ORDER and ORDER[sev] > ORDER[implied]:
            out.append(f"severity {sev} looks too LOW for the stated impact - the "
                       f"impact wording implies {implied}. Declaring too low delays "
                       f"the page and understates the postmortem")
    return out


def read_record(path: str):
    """Read the record the user pointed at.

    Returns (raw_text, error_message); exactly one of the two is None. Every way
    the input can be unusable is turned into a message here, so the caller never
    sees a traceback for a missing file, a directory, or an unreadable path.
    """
    if path == "-":
        return sys.stdin.read(), None
    if os.path.isdir(path):
        return None, (f"{path} is a directory - pass a JSON file, or - to read "
                      f"stdin")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), None
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Incident severity classifier and record linter.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("classify", help="classify an incident by user impact")
    for qid, question, mapping in QUESTIONS:
        c.add_argument(f"--{qid.replace('_', '-')}",
                       choices=sorted(mapping.keys()), help=question)
    c.add_argument("--json", action="store_true")

    l = sub.add_parser("lint", help="check an incident record for completeness",
                       epilog="Exit codes: 0 no findings, 1 findings, 2 the record "
                              "could not be read or is not a JSON object.")
    l.add_argument("record", help="JSON file, or - for stdin")
    l.add_argument("--json", action="store_true")

    a = ap.parse_args()

    if a.cmd == "classify":
        answers = {q: getattr(a, q) for q, _, _ in QUESTIONS}
        sev, reasons = classify(answers)
        if a.json:
            print(json.dumps({"severity": sev, "reasons": reasons}, indent=2))
        else:
            desc = dict((n, d) for n, _, d in LEVELS)[sev]
            print(f"SEVERITY: {sev}")
            print(f"  {desc}")
            print("why:")
            for r in reasons:
                print(f"  - {r}")
            print("\nReminder: severity is about user impact, not how interesting the "
                  "bug is.\nDeclaring too low is the common and costly mistake - it "
                  "delays the page.")
        return 0

    raw, error = read_record(a.record)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        rec = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(rec, dict):
        print(f"error: an incident record must be a JSON object, got "
              f"{type(rec).__name__}", file=sys.stderr)
        return 2
    findings = lint(rec)
    if a.json:
        print(json.dumps({"findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"  - {f}")
        print(f"\n{len(findings)} finding(s)")
    return 1 if any(not f.startswith("note:") for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
