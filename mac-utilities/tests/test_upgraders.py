#!/usr/bin/env python3
"""
Black-box tests for brewmaster.py and PakMan.py.

Each test runs the real script in a subprocess against a throwaway $HOME and a
fake `brew`, `uv` or `pip`, so nothing on the machine is queried or upgraded.

    python3 -m unittest discover -s mac-utilities/tests -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BREWMASTER = ROOT / "brewmaster.py"
PAKMAN = ROOT / "PakMan.py"
SYSTEM_PATH = "/usr/bin:/bin"


def formula(name, old="1.0", new="2.0", **extra):
    return {"name": name, "installed_versions": [old], "current_version": new, **extra}


def cask(name, old="1.0", new="2.0"):
    return {"name": name, "installed_versions": old, "current_version": new}


class Sandbox(unittest.TestCase):
    """A temporary $HOME plus a bin directory for fake executables."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="upgraders_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.bin = self.tmp / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        self.calls = self.tmp / "calls.log"

    def script(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + textwrap.dedent(body))
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    def env(self, **extra):
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:{SYSTEM_PATH}",
               "CALLS": str(self.calls), "TERM": "dumb", "LANG": "en_US.UTF-8"}
        env.update(extra)
        return env

    def called(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def log_text(self, name):
        return (self.home / name).read_text()


class BrewCase(Sandbox):

    def fake_brew(self, formulae=(), casks=(), pinned=(), upgrade="", fetch="", extra=""):
        """A brew that answers queries from canned data. `upgrade` and `fetch`
        are shell snippets run for those subcommands."""
        data = self.tmp / "outdated.json"
        data.write_text(json.dumps({"formulae": list(formulae), "casks": list(casks)}))
        self.script("brew", f"""\
            echo "$*" >> "$CALLS"
            case "$1" in
              --repository|--prefix) echo "{self.tmp}";;
              outdated) cat "{data}";;
              list) printf '%s\\n' {' '.join(pinned) if pinned else "''"};;
              upgrade) {upgrade or ':'};;
              fetch) {fetch or ':'};;
              cleanup) :;;
              update) :;;
              {extra}
            esac
            """)

    def brew(self, *args, env=None, **kwargs):
        return subprocess.run(
            [sys.executable, str(BREWMASTER), "--ascii", "--no-update", *args],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            env=env or self.env(), timeout=60, **kwargs,
        )


class TestBrewSelection(BrewCase):

    def test_pinned_formula_does_not_hide_same_named_cask(self):
        self.fake_brew(formulae=[formula("docker")], casks=[cask("docker")], pinned=["docker"])
        res = self.brew("-y", "--no-prefetch", "--no-cleanup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        upgrades = [c for c in self.called() if c.startswith("upgrade")]
        self.assertEqual(upgrades, ["upgrade --cask --greedy docker"])

    def test_formula_upgrade_is_explicit_about_kind(self):
        self.fake_brew(formulae=[formula("docker")], casks=[cask("docker")])
        res = self.brew("-y", "--no-prefetch", "--no-cleanup")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("upgrade --formula docker", self.called())
        self.assertIn("upgrade --cask --greedy docker", self.called())

    def test_same_named_formula_and_cask_are_both_prefetched(self):
        self.fake_brew(formulae=[formula("docker")], casks=[cask("docker")])
        self.brew("-y", "--no-cleanup")
        self.assertIn("fetch --formula docker", self.called())
        self.assertIn("fetch --cask docker", self.called())

    def test_tapped_formula_is_matched_by_short_name(self):
        self.fake_brew(formulae=[formula("acme/tap/foo"), formula("acme/tap/bar")],
                       pinned=["bar"])
        res = self.brew("-y", "--no-prefetch", "--no-cleanup", "--skip", "foo")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual([c for c in self.called() if c.startswith("upgrade")], [])

    def test_pinned_field_in_outdated_json_is_honoured_without_list_pinned(self):
        self.fake_brew(formulae=[formula("foo", pinned=True)])
        self.brew("-y", "--no-prefetch", "--no-cleanup")
        self.assertEqual([c for c in self.called() if c.startswith("upgrade")], [])

    def test_option_like_package_name_never_reaches_brew(self):
        self.fake_brew(formulae=[formula("--force"), formula("evil\n"), formula("good")])
        res = self.brew("-y", "--no-prefetch", "--no-cleanup")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        upgrades = [c for c in self.called() if c.startswith("upgrade")]
        self.assertEqual(upgrades, ["upgrade --formula good"])

    def test_cli_only_overrides_config_skip(self):
        (self.home / ".brewmasterrc.json").write_text(json.dumps({"skip": ["foo"]}))
        self.fake_brew(formulae=[formula("foo")])
        self.brew("-y", "--no-prefetch", "--no-cleanup", "--only", "foo")
        self.assertIn("upgrade --formula foo", self.called())

    def test_bad_color_in_config_is_rejected_not_silently_ignored(self):
        (self.home / ".brewmasterrc.json").write_text(json.dumps({"color": "purple"}))
        self.fake_brew()
        res = self.brew("--check-only")
        self.assertIn("color", res.stdout + res.stderr)
        self.assertEqual(res.returncode, 0)

    def test_non_utf8_config_warns_instead_of_crashing(self):
        (self.home / ".brewmasterrc.json").write_bytes(b"\xff\xfe{")
        self.fake_brew()
        res = self.brew("--check-only")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("Traceback", res.stderr)


class TestBrewCheckOnly(BrewCase):

    def test_exit_3_and_json_list_outdated(self):
        self.fake_brew(formulae=[formula("foo")], casks=[cask("bar")])
        res = self.brew("--check-only", "--json")
        self.assertEqual(res.returncode, 3, res.stderr)
        record = json.loads(res.stdout)
        self.assertEqual([p["name"] for p in record["outdated"]], ["foo", "bar"])
        self.assertEqual(record["exit_code"], 3)
        self.assertEqual(record["upgraded"], [])

    def test_does_not_take_a_backup(self):
        self.fake_brew(formulae=[formula("foo")])
        res = self.brew("--check-only", "--backup")
        self.assertEqual(res.returncode, 3)
        self.assertFalse([c for c in self.called() if c.startswith("bundle")])
        self.assertEqual(list(self.home.glob(".brewmaster_backup_*")), [])

    def test_backup_is_not_rotated_when_nothing_is_outdated(self):
        self.fake_brew()
        self.brew("-y", "--backup")
        self.assertFalse([c for c in self.called() if c.startswith("bundle")])

    def test_quiet_still_reports_a_fatal_query_failure(self):
        self.script("brew", """\
            case "$1" in
              outdated) echo "Error: boom" >&2; exit 1;;
              --repository|--prefix) echo /tmp;;
            esac
            """)
        res = self.brew("--check-only", "-q")
        self.assertEqual(res.returncode, 1)
        self.assertIn("boom", res.stdout + res.stderr)


class TestBrewFailures(BrewCase):

    def test_reported_error_is_the_error_not_a_leading_warning(self):
        self.fake_brew(formulae=[formula("foo")], upgrade="""
            echo "Warning: something unrelated" >&2
            echo "Error: the real reason" >&2
            exit 1""")
        res = self.brew("-y", "--no-prefetch", "--no-cleanup", "--retries", "1", "--json")
        self.assertEqual(res.returncode, 2)
        self.assertIn("the real reason", res.stderr)

    def test_verbose_keeps_failure_reason_and_stdout_stays_parseable(self):
        self.fake_brew(formulae=[formula("foo")], upgrade="""
            echo "==> raw brew chatter"
            echo "Error: no available formula foo" >&2
            exit 1""")
        res = self.brew("-y", "-v", "--no-prefetch", "--no-cleanup", "--retries", "3", "--json")
        self.assertEqual(res.returncode, 2)
        record = json.loads(res.stdout)
        self.assertIn("no available formula", record["failures"][0]["error"])
        self.assertIn("raw brew chatter", res.stderr)
        # Recognised as permanent, so it was not retried.
        self.assertEqual(len([c for c in self.called() if c.startswith("upgrade")]), 1)

    def test_non_utf8_output_does_not_crash_the_run(self):
        self.fake_brew(formulae=[formula("foo")], upgrade=r"""printf 'caf\xe9\n'; exit 0""")
        res = self.brew("-y", "--no-prefetch", "--no-cleanup")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("Traceback", res.stderr)

    def test_long_error_survives_a_non_tty(self):
        reason = "x" * 300 + "END"
        self.fake_brew(formulae=[formula("foo")],
                       upgrade=f'echo "Error: {reason}" >&2; exit 1')
        res = self.brew("-y", "--no-prefetch", "--no-cleanup", "--retries", "1")
        self.assertIn("END", res.stdout)

    def test_timeout_kills_grandchildren(self):
        marker = self.tmp / "survivor"
        self.fake_brew(formulae=[formula("foo")], upgrade=f"""
            (sleep 3; touch "{marker}") &
            wait""")
        res = self.brew("-y", "--no-prefetch", "--no-cleanup", "--retries", "1", "--timeout", "1")
        self.assertEqual(res.returncode, 2)
        self.assertIn("timed out", res.stdout)
        time.sleep(3.5)
        self.assertFalse(marker.exists(), "a timed-out upgrade left a live grandchild")

    def test_background_daemon_holding_the_pipe_does_not_hang_the_run(self):
        self.fake_brew(formulae=[formula("foo")], upgrade="sleep 40 & exit 0")
        started = time.monotonic()
        res = self.brew("-y", "--no-prefetch", "--no-cleanup")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertLess(time.monotonic() - started, 20)


class TestBrewDryRun(BrewCase):

    def test_does_not_claim_upgrades_in_the_log_or_record(self):
        self.fake_brew(formulae=[formula("foo")])
        res = self.brew("--dry-run", "--json", "--no-cleanup")
        self.assertEqual(res.returncode, 0, res.stderr)
        record = json.loads(res.stdout)
        self.assertTrue(record["dry_run"])
        self.assertNotIn("Upgraded formula", self.log_text(".brewmaster.log"))
        self.assertFalse([c for c in self.called() if c.startswith("upgrade")])


class TestBrewDiscovery(BrewCase):

    def test_symlinked_brew_in_a_known_location_is_not_flagged(self):
        # Intel installs: /usr/local/bin/brew -> ../Homebrew/bin/brew
        self.fake_brew()
        res = self.brew("--check-only")
        self.assertIn("Unusual brew location", res.stdout)  # the control: a fake path warns
        code = (
            "import sys, importlib.util as u;"
            f"s = u.spec_from_file_location('bm', {str(BREWMASTER)!r});"
            "m = u.module_from_spec(s); sys.modules['bm'] = m; s.loader.exec_module(m);"
            f"real = {str(self.bin / 'brew')!r};"
            f"link = {str(self.tmp / 'link_brew')!r};"
            "import os; os.symlink(real, link);"
            "m.KNOWN_BREW_PATHS = (link,);"
            "m.shutil.which = lambda n: link;"
            "print(m.resolve_brew(m.UI()))"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=self.env()).stdout
        self.assertIn("''", out, out)

    def test_known_location_is_used_when_brew_is_not_on_path(self):
        # cron and launchd start with a PATH that has no Homebrew directory.
        real = self.fake_brew() or self.bin / "brew"
        code = (
            "import sys, importlib.util as u;"
            f"s = u.spec_from_file_location('bm', {str(BREWMASTER)!r});"
            "m = u.module_from_spec(s); sys.modules['bm'] = m; s.loader.exec_module(m);"
            f"m.KNOWN_BREW_PATHS = ({str(real)!r},);"
            "print(m.resolve_brew(m.UI()))"
        )
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=self.env(PATH=SYSTEM_PATH))
        self.assertIn(str(real), res.stdout, res.stdout + res.stderr)


class TestBrewSignals(BrewCase):

    def _interrupt(self, sig, *args, upgrade="", fetch=""):
        pid_file = self.tmp / "child.pid"
        self.fake_brew(formulae=[formula("foo")],
                       upgrade=upgrade or f'echo $$ > "{pid_file}"; sleep 60 & wait',
                       fetch=fetch)
        proc = subprocess.Popen(
            [sys.executable, str(BREWMASTER), "--ascii", "--no-update", "-y", *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            stdin=subprocess.DEVNULL, env=self.env(),
        )
        deadline = time.monotonic() + 15
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(pid_file.exists(), "fake brew never started")
        child = int(pid_file.read_text().strip())
        proc.send_signal(sig)
        started = time.monotonic()
        out, err = proc.communicate(timeout=30)
        return proc.returncode, time.monotonic() - started, child, out, err

    def _assert_gone(self, pid):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        self.fail(f"child {pid} outlived the run")

    def test_sigterm_exits_130_and_stops_the_child(self):
        rc, took, child, _, err = self._interrupt(signal.SIGTERM, "--no-prefetch")
        self.assertEqual(rc, 130, err)
        self.assertLess(took, 15)
        self._assert_gone(child)

    def test_sigint_exits_130_and_stops_the_child(self):
        rc, _, child, _, err = self._interrupt(signal.SIGINT, "--no-prefetch")
        self.assertEqual(rc, 130, err)
        self._assert_gone(child)

    def test_sigterm_does_not_wait_for_inflight_prefetch(self):
        rc, took, child, _, err = self._interrupt(
            signal.SIGTERM,
            upgrade=":",
            fetch=f'echo $$ > "{self.tmp / "child.pid"}"; sleep 60 & wait',
        )
        self.assertEqual(rc, 130, err)
        self.assertLess(took, 15, "exit blocked on a running prefetch")
        self._assert_gone(child)

    def test_interrupt_is_audited(self):
        self._interrupt(signal.SIGTERM, "--no-prefetch")
        self.assertRegex(self.log_text(".brewmaster.log"),
                         r"AUDIT: .*upgrade --formula foo -> exit 130 \(interrupted\)")


class TestBrewLockAndFiles(BrewCase):

    def test_refused_run_does_not_erase_the_holders_pid(self):
        self.fake_brew(formulae=[formula("foo")], upgrade="sleep 4")
        first = subprocess.Popen(
            [sys.executable, str(BREWMASTER), "--ascii", "--no-update", "-y",
             "--no-prefetch", "--no-cleanup"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, env=self.env(),
        )
        self.addCleanup(first.wait)
        lock = self.home / ".brewmaster.lock"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if lock.exists() and lock.read_text().strip():
                break
            time.sleep(0.05)
        res = self.brew("-y")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(lock.read_text().strip(), str(first.pid))
        self.assertIn(str(first.pid), res.stdout + res.stderr)

    def test_private_files_are_0600(self):
        self.fake_brew(formulae=[formula("foo")], extra='bundle) echo \'brew "foo"\';;')
        res = self.brew("-y", "--backup", "--log-json", "--no-prefetch", "--no-cleanup")
        self.assertEqual(res.returncode, 0, res.stderr)
        paths = [self.home / ".brewmaster.log", self.home / ".brewmaster_history.jsonl",
                 self.home / ".brewmaster.lock", *self.home.glob(".brewmaster_backup_*")]
        self.assertEqual(len(paths), 4)
        for path in paths:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path)

    def test_history_survives_corrupt_records(self):
        (self.home / ".brewmaster_history.jsonl").write_bytes(
            b'\xff\xfe\n{"exit_code": "bad", "elapsed_secs": "x", "upgraded": 3}\n')
        self.fake_brew()
        res = self.brew("--history")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("Traceback", res.stderr)

    def test_closed_stdout_does_not_abort_the_upgrade_or_hide_the_exit_code(self):
        self.fake_brew(formulae=[formula(f"p{i}") for i in range(5)])
        cmd = (f'"{sys.executable}" "{BREWMASTER}" --ascii --no-update --check-only | true; '
               'echo "rc=${PIPESTATUS[0]}"')
        res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=self.env())
        self.assertIn("rc=3", res.stdout, res.stderr)


class PakCase(Sandbox):
    """PakMan shells out to sys.executable, so pointing that at a shell script
    answering `-m pip ...` lets tests script pip's behaviour. The real PakMan.py
    still runs, on the real interpreter, with sys.executable overridden."""

    def fake_pip(self, outdated=(), *, install="", check="", listing=None):
        data = self.tmp / "outdated.json"
        data.write_text(json.dumps(list(outdated)))
        listing_file = self.tmp / "listing.json"
        listing_file.write_text(json.dumps(listing if listing is not None else []))
        self.pip_script = self.script("fakepython", f"""\
            shift 2  # -m pip
            echo "$*" >> "$CALLS"
            case "$1" in
              list)
                case "$*" in
                  *--outdated*) cat "{data}";;
                  *) cat "{listing_file}";;
                esac;;
              install) {install or ':'};;
              check) {check or ':'};;
              download) :;;
              freeze) echo "foo==2.0";;
            esac
            """)

    def pak(self, *args, env=None, has_pip=True):
        boot = (
            "import sys, runpy, importlib.util as u;"
            f"sys.executable = {str(self.pip_script)!r};"
            f"sys.argv = ['PakMan.py'] + {list(args)!r};"
            f"real = u.find_spec;"
            f"u.find_spec = lambda n, *a: (object() if {has_pip!r} else None) if n == 'pip' else real(n, *a);"
            f"runpy.run_path({str(PAKMAN)!r}, run_name='__main__')"
        )
        return subprocess.run(
            [sys.executable, "-c", boot],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
            env=env or self.env(), timeout=60,
        )


def pip_pkg(name, old="1.0", new="2.0", filetype="wheel"):
    return {"name": name, "version": old, "latest_version": new, "latest_filetype": filetype}


class TestPakResults(PakCase):

    def test_exit_ok_with_all_packages_upgraded(self):
        self.fake_pip([pip_pkg("foo")], listing=[{"name": "foo", "version": "2.0"}])
        res = self.pak("-y", "--no-uv", "--ascii", "--summary-json", "--no-rollback")
        self.assertEqual(res.returncode, 0, res.stderr)
        record = json.loads(res.stdout)
        self.assertEqual(record["upgraded"], ["foo"])
        self.assertEqual(record["held_back"], [])

    def test_resolver_holding_a_package_back_is_not_reported_as_upgraded(self):
        self.fake_pip([pip_pkg("foo"), pip_pkg("Bar_Baz")],
                      listing=[{"name": "foo", "version": "1.0"},
                               {"name": "bar-baz", "version": "2.0"}])
        res = self.pak("-y", "--no-uv", "--ascii", "--summary-json", "--no-rollback")
        self.assertEqual(res.returncode, 0, res.stderr)
        record = json.loads(res.stdout)
        self.assertEqual(record["upgraded"], ["Bar_Baz"])
        self.assertEqual(record["held_back"], ["foo"])
        self.assertNotIn("Upgraded (batch): foo", self.log_text(".pakman.log"))

    def test_environment_wide_failure_stops_after_the_batch(self):
        self.fake_pip([pip_pkg("a"), pip_pkg("b"), pip_pkg("c")], install="""
            echo "error: externally-managed-environment" >&2; exit 1""")
        res = self.pak("-y", "--no-uv", "--ascii", "--summary-json", "--no-rollback")
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertEqual(len(json.loads(res.stdout)["failures"]), 3)
        self.assertEqual(len([c for c in self.called() if c.startswith("install")]), 1)
        self.assertFalse([c for c in self.called() if c.startswith("download")])

    def test_batch_failure_still_isolates_per_package(self):
        self.fake_pip([pip_pkg("good"), pip_pkg("bad")],
                      listing=[{"name": "good", "version": "2.0"}],
                      install="""
            case "$*" in
              *bad*) echo "ERROR: No matching distribution found" >&2; exit 1;;
            esac""")
        res = self.pak("-y", "--no-uv", "--ascii", "--summary-json", "--no-rollback",
                       "--no-prefetch")
        self.assertEqual(res.returncode, 2, res.stderr)
        record = json.loads(res.stdout)
        self.assertEqual(record["upgraded"], ["good"])
        self.assertEqual([f["name"] for f in record["failures"]], ["bad"])


class TestPakChecks(PakCase):

    def test_failed_pip_check_is_not_reported_as_healthy(self):
        self.fake_pip([pip_pkg("foo")], check="echo 'No module named x' >&2; exit 1",
                      listing=[{"name": "foo", "version": "2.0"}])
        res = self.pak("-y", "--no-uv", "--ascii", "--no-rollback")
        self.assertNotIn("No broken dependencies", res.stdout)
        self.assertIn("Could not verify", res.stdout)

    def test_only_new_conflicts_are_blamed_on_the_run(self):
        state = self.tmp / "installed"
        self.fake_pip([pip_pkg("foo")],
                      install=f'touch "{state}"',
                      check=f"""
            echo "old has requirement x, but you have y."
            [ -e "{state}" ] && echo "new has requirement a, but you have b."
            exit 1""",
                      listing=[{"name": "foo", "version": "2.0"}])
        res = self.pak("-y", "--no-uv", "--ascii", "--summary-json", "--no-rollback")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)["new_conflicts"],
                         ["new has requirement a, but you have b."])


class TestPakReadOnlyModes(PakCase):

    def test_check_only_does_not_upgrade_pip(self):
        self.fake_pip([pip_pkg("foo")])
        res = self.pak("--check-only", "--upgrade-pip", "--no-uv", "--ascii")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertFalse([c for c in self.called() if c.startswith("install")])

    def test_json_with_check_only_keeps_exit_3(self):
        self.fake_pip([pip_pkg("foo")])
        res = self.pak("--json", "--check-only", "--no-uv", "--ascii")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertEqual(json.loads(res.stdout)[0]["name"], "foo")

    def test_json_alone_stays_exit_0(self):
        self.fake_pip([pip_pkg("foo")])
        res = self.pak("--json", "--no-uv", "--ascii")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_json_honours_filters(self):
        self.fake_pip([pip_pkg("foo"), pip_pkg("bar")])
        res = self.pak("--json", "--no-uv", "--ascii", "--exclude", "foo")
        self.assertEqual([p["name"] for p in json.loads(res.stdout)], ["bar"])

    def test_check_only_summary_json_lists_outdated(self):
        self.fake_pip([pip_pkg("foo")])
        res = self.pak("--check-only", "--summary-json", "--no-uv", "--ascii")
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertEqual(json.loads(res.stdout)["outdated"][0]["name"], "foo")

    def test_read_only_runs_do_not_need_the_lock(self):
        self.fake_pip([pip_pkg("foo")])
        import fcntl
        with open(self.home / ".pakman.lock", "w") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            res = self.pak("--check-only", "--no-uv", "--ascii")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)

    def test_dry_run_claims_nothing(self):
        self.fake_pip([pip_pkg("foo")])
        res = self.pak("--dry-run", "--no-uv", "--ascii", "--summary-json")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(json.loads(res.stdout)["dry_run"])
        self.assertNotIn("Upgraded (batch)", self.log_text(".pakman.log"))
        self.assertFalse([c for c in self.called() if c.startswith("install")])


class TestPakOutdatedQuery(PakCase):

    def test_editable_installs_are_left_alone(self):
        self.fake_pip()
        self.pak("--check-only", "--no-uv", "--ascii")
        listing = [c for c in self.called() if c.startswith("list --outdated")][0]
        self.assertIn("--exclude-editable", listing)

    def test_pre_reaches_the_outdated_query(self):
        self.fake_pip()
        self.pak("--check-only", "--no-uv", "--ascii", "--pre")
        listing = [c for c in self.called() if c.startswith("list --outdated")][0]
        self.assertIn("--pre", listing)

    def _fake_uv(self, outdated):
        data = self.tmp / "uv.json"
        data.write_text(json.dumps(outdated))
        self.script("uv", f"""\
            echo "uv $*" >> "$CALLS"
            case "$2" in
              list)
                case "$*" in
                  *--outdated*) cat "{data}";;
                  *) cat "{data}";;
                esac;;
              check) echo "Using Python 3 environment at: x" >&2
                     echo "Checked 1 package in 1ms" >&2
                     echo "Found 1 incompatibility" >&2
                     echo 'The package `a` requires `b<2`, but `2.0` is installed' >&2
                     exit 1;;
              install) :;;
            esac
            """)

    def test_uv_query_excludes_editables(self):
        self.fake_pip()
        self._fake_uv([])
        self.pak("--check-only", "--ascii")
        self.assertIn("--exclude-editable", [c for c in self.called() if c.startswith("uv")][0])

    def test_pre_skips_uv_because_its_list_cannot_see_prereleases(self):
        self.fake_pip()
        self._fake_uv([])
        self.pak("--check-only", "--ascii", "--pre")
        self.assertFalse([c for c in self.called() if c.startswith("uv pip list")])

    def test_venv_without_pip_uses_uv_throughout(self):
        self.fake_pip()
        self._fake_uv([pip_pkg("a")])
        res = self.pak("-y", "--ascii", "--no-rollback", "--summary-json", has_pip=False)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual([c for c in self.called() if not c.startswith("uv")], [])
        record = json.loads(res.stdout)
        self.assertEqual(record["installer"], "uv")
        self.assertEqual(record["conflicts"],
                         ['The package `a` requires `b<2`, but `2.0` is installed'])

    def test_no_pip_and_no_uv_is_a_clear_fatal(self):
        self.fake_pip()
        res = self.pak("--check-only", "--ascii", "--no-uv", has_pip=False)
        self.assertEqual(res.returncode, 1)
        self.assertRegex(res.stdout + res.stderr, r"(?i)neither pip")


class TestPakConfig(PakCase):

    def test_cli_no_uv_overrides_config_uv(self):
        (self.home / ".pakmanrc.json").write_text(json.dumps({"uv": True}))
        self.fake_pip()
        res = self.pak("--check-only", "--no-uv", "--ascii")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_cli_only_overrides_config_exclude(self):
        (self.home / ".pakmanrc.json").write_text(json.dumps({"exclude": ["foo"]}))
        self.fake_pip([pip_pkg("foo")])
        res = self.pak("--check-only", "--no-uv", "--ascii", "--only", "foo")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)

    def test_overlap_given_on_the_command_line_is_still_an_error(self):
        self.fake_pip()
        res = self.pak("--check-only", "--no-uv", "--only", "foo", "--exclude", "foo")
        self.assertEqual(res.returncode, 2)
        self.assertIn("both --only and --exclude", res.stderr)


class TestPakFailureText(PakCase):

    def test_verbose_preserves_failure_reason_and_json(self):
        self.fake_pip([pip_pkg("foo")], install="""
            echo "Collecting foo"
            echo "ERROR: No matching distribution found for foo" >&2
            exit 1""")
        res = self.pak("-y", "-v", "--no-uv", "--ascii", "--no-batch", "--no-prefetch",
                       "--no-rollback", "--summary-json", "--retries", "3")
        self.assertEqual(res.returncode, 2)
        record = json.loads(res.stdout)
        self.assertIn("No matching distribution", record["failures"][0]["error"])
        self.assertEqual(len([c for c in self.called() if c.startswith("install")]), 1)

    def test_quiet_shows_warnings(self):
        self.fake_pip([pip_pkg("foo")], check="echo 'x has requirement y, but you have z.'; exit 1",
                      listing=[{"name": "foo", "version": "1.0"}])
        res = self.pak("-y", "-q", "--no-uv", "--ascii", "--no-rollback")
        self.assertIn("foo stayed at its current version", res.stdout)
        self.assertIn("pre-existing conflict", res.stdout)


class TestPakFiles(PakCase):

    def test_rollback_is_0600_and_pins_old_versions(self):
        self.fake_pip([pip_pkg("foo")], listing=[{"name": "foo", "version": "2.0"}])
        res = self.pak("-y", "--no-uv", "--ascii")
        self.assertEqual(res.returncode, 0, res.stderr)
        files = list(self.home.glob(".pakman_rollback_*.txt"))
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assertEqual(files[0].read_text(), "foo==1.0\n")

    def test_every_subprocess_is_audited(self):
        self.fake_pip([pip_pkg("foo")], listing=[{"name": "foo", "version": "2.0"}])
        self.pak("-y", "--no-uv", "--ascii", "--no-rollback")
        log = self.log_text(".pakman.log")
        audited = re.findall(r"AUDIT: \S+ -m pip (\w+)", log)
        self.assertEqual(sorted(audited), sorted(c.split()[0] for c in self.called()))


if __name__ == "__main__":
    unittest.main()
