# incident-severity-lint

[![PyPI](https://img.shields.io/pypi/v/incident-severity-lint)](https://pypi.org/project/incident-severity-lint/)

Classify an incident's severity by **user impact**, and lint the record so the
postmortem is actually useful.

No dependencies. Standard library only.

```bash
pip install incident-severity-lint          # from PyPI, Python 3.9+
incident-severity-lint classify --core-flow down --users-affected all
incident-severity-lint lint incident.json
```

Or straight from a clone, with no install at all — the same CLI:

```bash
git clone https://github.com/duke5am/incident-severity-lint
cd incident-severity-lint
python3 severity_tool.py classify --core-flow down --users-affected all
python3 severity_tool.py lint examples/example-incident.json
```

And from the package without installing it, straight from a checkout:

```bash
python3 -m incident_severity_lint lint examples/example-incident.json
```

Exit codes: `0` no findings (MTTD notes only) · `1` findings · `2` the record
could not be read, is not valid JSON, or is not a JSON object.

The linter API is importable too, if you want the rules inside your own tooling:

```python
from incident_severity_lint import classify, lint
classify({"core_flow": "down", "users_affected": "all"})   # ('SEV1', [...])
```

## Severity by impact, not by feel

Severity drifts because it is declared by instinct. A "SEV3" that took checkout
down ends up sitting next to a "SEV1" that broke an internal dashboard, and
nobody trusts the levels afterwards.

```
SEVERITY: SEV1
  A core flow is unusable for all or nearly all users, or there is data loss or
  exposure. Someone must be woken up now.
why:
  - core_flow=down -> SEV1
  - users_affected=all -> SEV1
  - data_integrity=yes -> SEV1
```

Six questions about **user impact** — core flow state, how many users, data
integrity, workaround availability, duration, revenue. The worst answer wins.
Unknown answers never escalate, so an honest "we don't know yet" does not inflate
the level.

## The linter catches the mistake that matters

```
$ python3 severity_tool.py lint incident.json
  - missing commander: needs who ran the incident
  - detected_at (…01:55:00Z) is before started_at (…02:10:00Z) - one of them is wrong
  - action_items[1]: no owner - an action without an owner is a wish
  - action_items[1]: no due date - these rot in a backlog
  - impact reads like a technical symptom; severity is about user impact
  - severity SEV3 looks too LOW for the stated impact - the impact wording implies
    SEV1. Declaring too low delays the page and understates the postmortem
```

That last check is the point of the tool: **a stored severity lower than the
recorded impact implies** is the costly mistake, because it delays the page and
understates what happened. Exit code 1, so it works as a pre-commit hook on your
postmortem files.

It also reports your **detection delay** (MTTD) from the gap between `started_at`
and `detected_at` — usually the number worth improving, and the one nobody records.

## What it does not do

- It does not page anyone, run anything, or talk to your monitoring.
- The classifier reads *your answers*, so it is only as honest as the person
  answering. It cannot see your systems.
- It is not a compliance artefact: notification duties depend on your own
  regulatory obligations.
- Response times and paging rules are yours to set. A short process people follow
  beats a complete one they ignore.

## Included templates

`SEVERITY-MATRIX.md` — the full scale with definitions, examples, who to page, and
why declaring too low is the common and costly failure.

`POSTMORTEM-TEMPLATE.md` — a blameless template with a timestamped timeline, the
**"where we got lucky"** section, contributing factors rather than "the root
cause", and action items with owners and dates.

## The full pack

The paid pack adds `RUNBOOK.md` (mitigation first, and why rolling back usually
beats debugging live), `ROLES.md` (what an incident commander must *not* do),
`COMMS-TEMPLATES.md`, `DRILLS.md` and `ONCALL-HANDOFF.md`.

<!-- RELATED:START -->

## Related tools

- **[n8n-dead-branch-lint](https://github.com/duke5am/n8n-dead-branch-lint)** — Lint an exported n8n workflow for dead branches, dangling connections, unreachable nodes and hardcoded secrets, before it silently stops working.
  *(if you were searching for "n8n workflow not running")*

All 28 tools in this set, grouped by what they check: **[dev-tools-index](https://duke5am.github.io/dev-tools-index/)**

If you arrived here searching for one of these, this is the tool: **incident severity matrix** · **sev level classification** · **postmortem template review** · **on call severity guide**

<!-- RELATED:END -->

→ **[Incident Response Playbook](https://duke5am.gumroad.com/l/12-incident-response-playbook)** — $24 on Gumroad <!-- GUMROAD-LINK -->
