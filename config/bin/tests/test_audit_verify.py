r"""Behavioral tests for bin/audit-verify and the canonicalization vectors.

The CLI is driven as a subprocess against fixture journals built under
``/tmp/opencode`` (never the live journal), with ``HOME`` redirected to a
scratch directory.  Fixtures are hashed by an *independent* reimplementation of
the spec §3.1 formula -- the CLI is never imported for fixture generation:

$$H_n = \operatorname{sha256}\big(\operatorname{prev}_n \,\Vert\,
\operatorname{canon}(\operatorname{entry}_n)\big), \qquad
\operatorname{canon}(e) = \operatorname{UTF\text{-}8}\big(\text{compact-sorted}
\big(e \setminus \{\texttt{entry\_hash}\}\big)\big)$$

The normative expectations for canon/chain live in
``config/tools/gov/audit_vectors.json`` (the language-neutral table both the TS
and the Python side must pass); the CLI module is loaded only to check that it
reproduces those hardcoded vectors byte-for-byte.

Covered behavior (spec §3.7 / §4): linear -> exit 0; fork -> exit 0 + list;
removed middle line -> exit 1 naming the gap; tampered ``entry_hash`` -> exit 1;
``DETACHED`` -> exit 0; legacy preamble + marker -> exit 0; Cyrillic ``reason``
-> canonicalization round-trips; no marker -> exit 2; unparseable line after the
marker -> exit 1; boot records -> count, pids, ``kill=on``.  Stdlib + pytest.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]  # config/bin (repo-local, never the live machine)
CONFIG = BIN.parent
CLI = BIN / "audit-verify"
VECTORS = CONFIG / "tools" / "gov" / "audit_vectors.json"
SCRATCH = Path("/tmp/opencode")  # approved scratch dir

GENESIS = "GENESIS"
DETACHED = "DETACHED"


# ---------------------------------------------------------------------------
# Independent canonicalization (implements spec §3.1 directly)
# ---------------------------------------------------------------------------


def canon(entry: dict) -> str:
    payload = {key: value for key, value in entry.items() if key != "entry_hash"}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hash_of(prev: str, entry: dict) -> str:
    return hashlib.sha256(prev.encode("utf-8") + canon(entry).encode("utf-8")).hexdigest()


def make_entry(prev: str, seq: int, **overrides: object) -> dict:
    """A realistic journal record, hashed per §3.1 (``entry_hash`` excluded)."""
    entry: dict = {
        "ts": f"2026-10-01T00:00:{seq:02d}.000Z",
        "sessionID": "ses_fixture",
        "tool": "edit",
        "targets": ["src/app.py"],
        "root": "/home/u/proj",
        "decision": "allowed",
        "reason": "allowed-via:alpha",
        "spec": "alpha",
        "prev_hash": prev,
        "pid": 4242,
        "seq": seq,
        "plugin": "0123456789abcdef",
    }
    entry.update(overrides)
    entry.pop("entry_hash", None)
    entry["entry_hash"] = hash_of(prev, entry)
    return entry


def legacy_line(index: int = 0) -> dict:
    return {
        "ts": f"2026-09-30T23:59:{index:02d}Z",
        "sessionID": "ses_legacy",
        "tool": "edit",
        "targets": ["old/file.py"],
        "root": "/home/u/old",
        "decision": "allowed",
        "reason": "allowed-via:old",
        "spec": None,
    }


def chain_start(prev: str = GENESIS, **overrides: object) -> dict:
    return make_entry(
        prev,
        0,
        tool="spec-gate",
        targets=[],
        decision="allowed",
        spec=None,
        reason=(
            "audit:chain-start legacy_lines=0 legacy_tail_ts=- "
            "legacy_tail_sha256=" + "a" * 64
        ),
        **overrides,
    )


def dump_lines(path: Path, lines: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
        encoding="utf-8",
    )


def linear_journal(path: Path, count: int = 3) -> list[dict]:
    entries: list[dict] = []
    prev = GENESIS
    for seq in range(count):
        entry = make_entry(prev, seq)
        entries.append(entry)
        prev = entry["entry_hash"]
    dump_lines(path, entries)
    return entries


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def workdir():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="audit-verify-test-", dir=str(SCRATCH)))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(scope="module")
def vectors() -> dict:
    return json.loads(VECTORS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cli_module():
    """The CLI loaded as a module (no side effects; guarded __main__)."""
    loader = importlib.machinery.SourceFileLoader("audit_verify_cli", str(CLI))
    spec = importlib.util.spec_from_loader("audit_verify_cli", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(journal: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the CLI on an explicit fixture path with HOME redirected.

    The real journal is never passed and never reachable through $HOME here.
    """
    env = {**os.environ, "HOME": str(journal.parent / "fake-home")}
    return subprocess.run(
        [sys.executable, str(CLI), str(journal), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def report_of(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def assert_partition(report: dict) -> None:
    """legacy + one category per chain line + gaps == totals."""
    assert report["lines_total"] == report["legacy_lines"] + report["chain_lines"]
    counted = (
        report["legacy_lines"]
        + report["linear_lines"]
        + report["fork_lines"]
        + report["detached_lines"]
        + report["boot_lines"]
        + len(report["gaps"])
    )
    assert counted == report["lines_total"]


# ---------------------------------------------------------------------------
# 1. linear journal -> exit 0
# ---------------------------------------------------------------------------


def test_linear_chain_exit_zero(workdir: Path) -> None:
    journal = workdir / "linear.jsonl"
    entries = linear_journal(journal, 3)

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["ok"] is True
    assert report["lines_total"] == 3
    assert report["legacy_lines"] == 0
    assert report["legacy_tail_ts"] is None
    assert report["chain_lines"] == 3
    assert report["marker_line"] == 1
    assert report["marker_entry_hash"] == entries[0]["entry_hash"]
    assert report["linear_lines"] == 3
    assert report["fork_lines"] == 0
    assert report["detached_lines"] == 0
    assert report["boot_lines"] == 0
    assert report["forks"] == []
    assert report["gaps"] == []
    assert_partition(report)


def test_quiet_ok_prints_nothing(workdir: Path) -> None:
    journal = workdir / "linear.jsonl"
    linear_journal(journal, 2)

    result = run(journal, "--quiet")

    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# 2. fork -> exit 0 + the fork is listed (head + children)
# ---------------------------------------------------------------------------


def test_fork_is_legal_and_listed(workdir: Path) -> None:
    journal = workdir / "fork.jsonl"
    root = make_entry(GENESIS, 0)
    head = make_entry(root["entry_hash"], 1)
    left = make_entry(head["entry_hash"], 2)
    right = make_entry(head["entry_hash"], 2, pid=9999)
    dump_lines(journal, [root, head, left, right])

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["ok"] is True
    assert len(report["forks"]) == 1
    fork = report["forks"][0]
    assert fork["head"] == head["entry_hash"]
    assert fork["head_line"] == 2
    assert [child["line"] for child in fork["children"]] == [3, 4]
    assert [child["entry_hash"] for child in fork["children"]] == [
        left["entry_hash"],
        right["entry_hash"],
    ]
    assert report["fork_lines"] == 2
    assert report["linear_lines"] == 2
    assert report["gaps"] == []
    assert_partition(report)

    human = run(journal)
    assert human.returncode == 0
    assert "forks        : 1" in human.stdout
    assert "head" in human.stdout


def test_two_roots_are_legal(workdir: Path) -> None:
    journal = workdir / "two-roots.jsonl"
    first = chain_start()
    second = chain_start()
    https = make_entry(first["entry_hash"], 1)
    dump_lines(journal, [first, second, https])

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["gaps"] == []
    assert report["forks"] == []
    assert report["linear_lines"] == 3


# ---------------------------------------------------------------------------
# 3. removed middle line -> exit 1, the gap is named
# ---------------------------------------------------------------------------


def test_removed_middle_line_is_gap(workdir: Path) -> None:
    journal = workdir / "removed.jsonl"
    entries = linear_journal(journal, 4)
    lines = journal.read_text(encoding="utf-8").splitlines(keepends=True)
    del lines[2]  # remove the third record; its child's prev_hash now dangles
    journal.write_text("".join(lines), encoding="utf-8")

    result = run(journal, "--json")

    assert result.returncode == 1, result.stdout + result.stderr
    report = report_of(result)
    assert report["ok"] is False
    assert len(report["gaps"]) == 1
    assert report["gaps"][0]["line"] == 3
    assert report["gaps"][0]["kind"] == "dangling-prev"
    assert entries[2]["entry_hash"] in report["gaps"][0]["detail"]

    human = run(journal)
    assert human.returncode == 1
    assert "line 3" in human.stdout
    assert "dangling" in human.stdout

    quiet = run(journal, "--quiet")
    assert quiet.returncode == 1
    assert "gaps" in quiet.stdout  # a failing report is never silenced


# ---------------------------------------------------------------------------
# 4. tampered entry_hash byte -> exit 1 (replay mismatch)
# ---------------------------------------------------------------------------


def test_tampered_entry_hash_is_gap(workdir: Path) -> None:
    journal = workdir / "tampered.jsonl"
    entries = linear_journal(journal, 3)
    tampered = dict(entries[1])
    original = tampered["entry_hash"]
    tampered["entry_hash"] = ("0" if original[0] != "0" else "1") + original[1:]
    dump_lines(journal, [entries[0], tampered, entries[2]])

    result = run(journal, "--json")

    assert result.returncode == 1, result.stdout + result.stderr
    report = report_of(result)
    assert report["ok"] is False
    kinds = [gap["kind"] for gap in report["gaps"]]
    assert kinds == ["hash-mismatch", "dangling-prev"]
    assert report["gaps"][0]["line"] == 2
    assert "expected" in report["gaps"][0]["detail"]


# ---------------------------------------------------------------------------
# 5. DETACHED -> exit 0 (honest mark, not a gap)
# ---------------------------------------------------------------------------


def test_detached_is_legal(workdir: Path) -> None:
    journal = workdir / "detached.jsonl"
    detached = make_entry(DETACHED, 0)
    child = make_entry(detached["entry_hash"], 1)
    dump_lines(journal, [detached, child])

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["ok"] is True
    assert report["detached_lines"] == 1
    assert report["linear_lines"] == 1
    assert report["gaps"] == []
    assert_partition(report)


# ---------------------------------------------------------------------------
# 6. legacy preamble + marker -> exit 0
# ---------------------------------------------------------------------------


def test_legacy_preamble_and_marker(workdir: Path) -> None:
    journal = workdir / "legacy.jsonl"
    marker = chain_start()
    child = make_entry(marker["entry_hash"], 1)
    dump_lines(journal, [legacy_line(0), legacy_line(1), marker, child])

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["ok"] is True
    assert report["legacy_lines"] == 2
    assert report["legacy_tail_ts"] == legacy_line(1)["ts"]
    assert report["chain_lines"] == 2
    assert report["marker_line"] == 3
    assert report["gaps"] == []
    assert_partition(report)


def test_legacy_only_journal_exit_2(workdir: Path) -> None:
    journal = workdir / "legacy-only.jsonl"
    dump_lines(journal, [legacy_line(0), legacy_line(1)])

    result = run(journal)

    assert result.returncode == 2
    assert "no chain marker" in result.stderr
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# 7. unparseable line after the marker -> exit 1
# ---------------------------------------------------------------------------


def test_unparseable_line_after_marker(workdir: Path) -> None:
    journal = workdir / "garbage.jsonl"
    root = make_entry(GENESIS, 0)
    journal.write_text(json.dumps(root, ensure_ascii=False) + "\n{not json}\n", encoding="utf-8")

    result = run(journal, "--json")

    assert result.returncode == 1, result.stdout + result.stderr
    report = report_of(result)
    assert [gap["kind"] for gap in report["gaps"]] == ["unparseable"]
    assert report["gaps"][0]["line"] == 2
    assert_partition(report)


# ---------------------------------------------------------------------------
# 8. boot provenance: count, pids, kill=on
# ---------------------------------------------------------------------------


def test_boot_entries_and_kill_flag(workdir: Path) -> None:
    journal = workdir / "boot.jsonl"
    first = make_entry(
        GENESIS,
        0,
        pid=777,
        reason="audit:boot kill=on plugin=0123456789abcdef pid=777",
    )
    second = make_entry(
        first["entry_hash"],
        1,
        pid=888,
        reason="audit:boot kill=off plugin=0123456789abcdef pid=888",
    )
    child = make_entry(second["entry_hash"], 2)
    dump_lines(journal, [first, second, child])

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["boot_lines"] == 2
    assert report["boot_pids"] == [777, 888]
    assert report["kill_on"] is True
    assert report["gaps"] == []
    assert_partition(report)


def test_kill_off_is_reported(workdir: Path) -> None:
    journal = workdir / "kill-off.jsonl"
    boot = make_entry(
        GENESIS,
        0,
        pid=555,
        reason="audit:boot kill=off plugin=0123456789abcdef pid=555",
    )
    dump_lines(journal, [boot])

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["boot_lines"] == 1
    assert report["boot_pids"] == [555]
    assert report["kill_on"] is False


# ---------------------------------------------------------------------------
# 9. Cyrillic reason -> canonicalization round-trips (raw UTF-8)
# ---------------------------------------------------------------------------


def test_cyrillic_reason_round_trips(workdir: Path) -> None:
    journal = workdir / "cyrillic.jsonl"
    root = make_entry(
        GENESIS,
        0,
        reason="мандат: «Кириллица» — allowed",
        targets=["проект/файл.py", "src/a.py"],
    )
    child = make_entry(root["entry_hash"], 1, reason="allowed-via:альфа")
    dump_lines(journal, [root, child])

    raw = journal.read_bytes()
    assert "Кириллица".encode("utf-8") in raw  # fixture pinned as raw UTF-8
    assert b"\\u04" not in raw

    result = run(journal, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_of(result)
    assert report["ok"] is True
    assert report["legacy_lines"] == 0
    assert report["gaps"] == []


# ---------------------------------------------------------------------------
# 10. the vectors are the normative minimum and the CLI matches byte-for-byte
# ---------------------------------------------------------------------------


def test_vectors_shape_and_required_cases(vectors: dict) -> None:
    assert vectors["version"] == 1
    canon_ids = [case["id"] for case in vectors["canon_cases"]]
    chain_ids = [case["id"] for case in vectors["chain_cases"]]
    assert canon_ids and chain_ids
    assert len(set(canon_ids + chain_ids)) == len(canon_ids + chain_ids)

    raw = VECTORS.read_bytes()
    assert b"\\u04" not in raw  # Cyrillic is pinned as raw UTF-8, not \uXXXX
    assert "мандат".encode("utf-8") in raw

    # At least one Cyrillic case and one non-empty (multi-element) targets case.
    assert any(
        any(ord(ch) > 127 for ch in case["canon"]) for case in vectors["canon_cases"]
    )
    assert any(len(case["entry"].get("targets", [])) >= 2 for case in vectors["canon_cases"])
    assert any(
        all(ord(ch) < 128 for ch in case["canon"]) for case in vectors["canon_cases"]
    )

    for case in vectors["canon_cases"]:
        assert case["canon"] == canon(case["entry"]), case["id"]
        parsed = json.loads(case["canon"])
        expected = {
            key: value for key, value in case["entry"].items() if key != "entry_hash"
        }
        assert parsed == expected
        assert list(parsed) == sorted(parsed)  # compact-sorted key order
        assert ", " not in case["canon"]  # no spaces after separators

    known: set[str] = set()
    for case in vectors["chain_cases"]:
        assert re.fullmatch(r"[0-9a-f]{64}", case["entry_hash"])
        assert case["entry_hash"] == hash_of(case["prev"], case["entry"]), case["id"]
        if case["prev"] in (GENESIS, DETACHED):
            assert case["entry"]["prev_hash"] == case["prev"]
        else:
            assert case["prev"] in known  # self-consistent chain
            assert case["entry"]["prev_hash"] == case["prev"]
        known.add(case["entry_hash"])


def test_vectors_canon_cases_match_cli(cli_module, vectors: dict) -> None:
    for case in vectors["canon_cases"]:
        assert cli_module.canon(case["entry"]) == case["canon"], case["id"]
        assert cli_module.canon(case["entry"]).encode("utf-8") == case["canon"].encode(
            "utf-8"
        ), case["id"]


def test_vectors_chain_cases_match_cli(cli_module, vectors: dict) -> None:
    for case in vectors["chain_cases"]:
        assert (
            cli_module.entry_hash(case["prev"], case["entry"]) == case["entry_hash"]
        ), case["id"]


# ---------------------------------------------------------------------------
# 11. usage, default path, read-only guarantees
# ---------------------------------------------------------------------------


def test_help_and_usage_errors(workdir: Path) -> None:
    journal = workdir / "linear.jsonl"
    linear_journal(journal, 1)

    help_result = subprocess.run(
        [sys.executable, str(CLI), "--help"], capture_output=True, text=True
    )
    assert help_result.returncode == 0
    assert "Usage" in help_result.stdout

    unknown = run(journal, "--nope")
    assert unknown.returncode == 2
    assert "unknown option" in unknown.stderr

    extra = run(journal, "other.jsonl")
    assert extra.returncode == 2
    assert "unexpected argument" in extra.stderr


def test_default_journal_under_home_is_used(workdir: Path) -> None:
    """With no path, $HOME decides; a scratch HOME must not find the live journal."""
    fake_home = workdir / "empty-home"
    fake_home.mkdir()
    env = {**os.environ, "HOME": str(fake_home)}

    result = subprocess.run(
        [sys.executable, str(CLI)], capture_output=True, text=True, env=env
    )

    assert result.returncode == 2
    assert "journal not found" in result.stderr
    assert str(fake_home) in result.stderr


def test_cli_is_read_only_on_fixture(workdir: Path) -> None:
    journal = workdir / "linear.jsonl"
    linear_journal(journal, 3)
    before = journal.read_bytes()
    mtime = journal.stat().st_mtime_ns

    for _ in range(2):
        assert run(journal).returncode == 0
        assert run(journal, "--json").returncode == 0

    assert journal.read_bytes() == before
    assert journal.stat().st_mtime_ns == mtime
