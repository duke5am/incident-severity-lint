#!/usr/bin/env python3
"""Tests for incident-severity-lint, run against the repo source.

They exercise the CLI the way a user does - as a subprocess - through both
entry points that ship:

  * `python3 severity_tool.py ...`, the workflow the README has always
    documented, now a thin wrapper around the package;
  * `python3 -m incident_severity_lint ...`, which runs the same
    `incident_severity_lint.cli:main` that the installed
    `incident-severity-lint` console script calls.

Scratch files go under /root (NOT /tmp: this environment's Python, and the
harness, treat /tmp as unreliable) and are removed in tearDown.

Run from the repo root:
  python3 -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "example-incident.json")

sys.path.insert(0, ROOT)

from incident_severity_lint import classify, lint  # noqa: E402

# A record with nothing wrong except the (informational) detection delay, so it
# must exit 0 - this is what separates "findings" from "notes".
CLEAN_RECORD = {
    "id": "INC-2026-044",
    "title": "Stale numbers in a dashboard widget",
    "severity": "SEV3",
    "started_at": "2026-09-17T02:10:00Z",
    "detected_at": "2026-09-17T02:12:00Z",
    # No escalating word here on purpose: SEV3 is the honest level for this, so
    # the only thing the linter may report is the MTTD note.
    "impact": "A dashboard widget showed stale numbers for a few users; nothing "
              "was blocked and no data was lost",
    "commander": "sam",
    "timeline": [{"at": "2026-09-17T02:12:00Z", "what": "alert fired"}],
    "resolution": "raised the indexer replica count",
    "action_items": [{"what": "add a latency alert", "owner": "sam",
                      "due": "2026-09-24"}],
}

ENTRIES = ("script", "module")


def run_proc(args, entry="script", stdin_text=None):
    """Run the CLI in a subprocess; return the CompletedProcess (text mode)."""
    if entry == "script":
        cmd = [sys.executable, os.path.join(ROOT, "severity_tool.py")] + list(args)
    elif entry == "module":
        cmd = [sys.executable, "-m", "incident_severity_lint"] + list(args)
    else:  # pragma: no cover - guards a typo in a test, not tool behaviour
        raise ValueError(f"unknown entry point {entry!r}")
    env = dict(os.environ, PYTHONPATH=ROOT)
    return subprocess.run(cmd, cwd=ROOT, env=env, input=stdin_text,
                          capture_output=True, text=True, timeout=120)


def run_cli(args, entry="script", stdin_text=None):
    """Run the CLI in a subprocess; return (exit_code, stdout+stderr)."""
    proc = run_proc(args, entry=entry, stdin_text=stdin_text)
    return proc.returncode, proc.stdout + proc.stderr


class IncidentSeverityLintTest(unittest.TestCase):

    def setUp(self):
        # Under /root, not /tmp, and unique per test so cleanup cannot race.
        self.scratch = tempfile.mkdtemp(dir="/root", prefix="isl-test-scratch-")
        self.empty_dir = os.path.join(self.scratch, "empty-dir")
        os.mkdir(self.empty_dir)
        self.missing = os.path.join(self.scratch, "does-not-exist.json")
        self.malformed = os.path.join(self.scratch, "malformed.json")
        with open(self.malformed, "w", encoding="utf-8") as fh:
            fh.write('{ "id": "INC-1", "title": ')  # truncated JSON
        self.json_list = os.path.join(self.scratch, "list.json")
        with open(self.json_list, "w", encoding="utf-8") as fh:
            fh.write('[1, 2, 3]')  # valid JSON, not a record object
        self.clean = os.path.join(self.scratch, "clean.json")
        with open(self.clean, "w", encoding="utf-8") as fh:
            json.dump(CLEAN_RECORD, fh)

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    # ---- the positive cases ------------------------------------------------

    def test_classify_reports_sev1_exactly_as_documented(self):
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(
                    ["classify", "--core-flow", "down",
                     "--users-affected", "all", "--data-integrity", "yes"],
                    entry=entry)
                self.assertEqual(code, 0, out)
                self.assertIn("SEVERITY: SEV1", out)
                self.assertIn("core_flow=down -> SEV1", out)
                self.assertIn("users_affected=all -> SEV1", out)
                self.assertNotIn("Traceback", out)

    def test_unknown_answer_never_escalates(self):
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(
                    ["classify", "--data-integrity", "unknown",
                     "--users-affected", "some"], entry=entry)
                self.assertEqual(code, 0, out)
                # README: "Unknown answers never escalate". So the level comes
                # from users_affected=some alone (SEV3), and "we don't know yet"
                # is not treated as an escalating answer at all.
                self.assertIn("SEVERITY: SEV3", out)
                self.assertIn("users_affected=some -> SEV3", out)
                self.assertNotIn("data_integrity", out)

    def test_example_record_behaves_as_documented(self):
        """The repo's own example must produce the README's lint output, exit 1.

        The example stores SEV3 for an impact that says "unusable for all users;
        data loss is possible", which is the mistake the tool exists to catch.
        """
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(["lint", EXAMPLE], entry=entry)
                self.assertEqual(code, 1, out)
                self.assertIn(
                    "severity SEV3 looks too LOW for the stated impact", out)
                self.assertIn("the impact wording implies SEV1", out)
                self.assertIn("note: detection delay", out)
                self.assertIn("this is your MTTD", out)
                self.assertIn("2 finding(s)", out)
                self.assertNotIn("Traceback", out)

    def test_example_json_output_matches_the_library(self):
        """--json must be parseable on its own, and agree with the library API."""
        proc = run_proc(["lint", EXAMPLE, "--json"], entry="module")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stderr, "", "the CLI wrote to stderr on a good run")
        with open(EXAMPLE, encoding="utf-8") as fh:
            record = json.load(fh)
        self.assertEqual(json.loads(proc.stdout)["findings"], lint(record))
        # One finding that is not a note -> exit 1; the MTTD note alone exits 0.

    def test_clean_record_exits_zero(self):
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(["lint", self.clean], entry=entry)
                self.assertEqual(code, 0, out)
                self.assertIn("note: detection delay", out)
                self.assertIn("1 finding(s)", out)

    def test_library_api_is_importable(self):
        sev, reasons = classify({"core_flow": "down", "users_affected": "all"})
        self.assertEqual(sev, "SEV1")
        self.assertIn("core_flow=down -> SEV1", reasons)
        self.assertEqual(classify({})[0], "SEV4")  # nothing given -> lowest

    def test_stdin_record(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            payload = fh.read()
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(["lint", "-"], entry=entry, stdin_text=payload)
                self.assertEqual(code, 1, out)
                self.assertIn("severity SEV3 looks too LOW", out)

    # ---- the negative cases ------------------------------------------------

    def assert_clean_failure(self, code, out, *expected):
        """Non-zero exit, a clear message, and NO Python traceback."""
        self.assertNotEqual(code, 0, f"expected a non-zero exit, got 0:\n{out}")
        self.assertNotIn("Traceback", out, f"a traceback leaked to the user:\n{out}")
        for fragment in expected:
            self.assertIn(fragment, out)

    def test_missing_file(self):
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(["lint", self.missing], entry=entry)
                self.assert_clean_failure(code, out, "error:", "cannot read",
                                          self.missing)

    def test_malformed_json(self):
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(["lint", self.malformed], entry=entry)
                self.assert_clean_failure(code, out, "error:", "not valid JSON")
                self.assertEqual(code, 2, out)

    def test_empty_directory(self):
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(["lint", self.empty_dir], entry=entry)
                self.assert_clean_failure(code, out, "error:", "is a directory",
                                          self.empty_dir)

    def test_json_that_is_not_an_object(self):
        for entry in ENTRIES:
            with self.subTest(entry=entry):
                code, out = run_cli(["lint", self.json_list], entry=entry)
                self.assert_clean_failure(code, out, "error:",
                                          "must be a JSON object", "list")
                self.assertEqual(code, 2, out)

    def test_errors_go_to_stderr_not_stdout(self):
        proc = run_proc(["lint", self.missing], entry="module")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertIn("cannot read", proc.stderr)


if __name__ == "__main__":
    unittest.main()
