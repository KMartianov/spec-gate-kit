"""Tests for bin/dod-run: atomic evidence writes, readback and the foreign guard.

Every test drives the CLI as a subprocess (``sys.executable`` + the ``dod-run``
path) against a throwaway git repository under pytest's ``tmp_path``; the real
project's ``verify/`` is never touched and nothing under ``/tmp/opencode`` is
used.  The fixture checks are instant (``cmd: "true"``).  Stdlib + pytest only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
CLI = BIN / "dod-run"

CHECK_ID = "smoke"
SCOPE_OK = '{"allow": ["src/**"], "deny": []}'
DOD_OK = '{"checks": [{"id": "smoke", "cmd": "true"}]}'
EVIDENCE_KEYS = {
    "check",
    "cmd",
    "exit_code",
    "started_at",
    "finished_at",
    "duration_s",
    "spec",
    "spec_sha256",
    "tail",
    "git_head",
    "tree_dirty",
    "scope_sha256",
}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(project), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def make_spec(project: Path, name: str) -> Path:
    spec_dir = project / ".slim" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec = spec_dir / f"{name}.md"
    spec.write_text(
        "\n".join(
            [
                f"# {name}",
                "",
                "- **Статус спецификации:** `draft`",
                "",
                "```scope",
                SCOPE_OK,
                "```",
                "",
                "```dod",
                DOD_OK,
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return spec


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A temp git repository with a real HEAD and one active contract."""
    root = tmp_path / "proj"
    make_spec(root, "alpha")
    git(root, "init")
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "fixture",
    )
    return root


def run_dod(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "--root", str(root), *args],
        capture_output=True,
        text=True,
    )


def evidence_file(root: Path, check_id: str = CHECK_ID) -> Path:
    return root / "verify" / f"{check_id}.json"


def temp_leftovers(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if ".tmp-" in p.name)


# ---------------------------------------------------------------------------
# Atomic write + readback
# ---------------------------------------------------------------------------


def test_atomic_write_and_readback(project: Path) -> None:
    result = run_dod(project, "--spec", "alpha")
    assert result.returncode == 0, result.stderr

    out = evidence_file(project)
    record = json.loads(out.read_text(encoding="utf-8"))
    assert set(record) == EVIDENCE_KEYS
    assert record["check"] == CHECK_ID
    assert record["cmd"] == "true"
    assert record["exit_code"] == 0
    assert record["spec"] == str((project / ".slim" / "spec" / "alpha.md").resolve())
    assert len(record["spec_sha256"]) == 64
    assert record["git_head"] is not None
    assert temp_leftovers(project / "verify") == []


def test_same_spec_rerun_overwrites_cleanly(project: Path) -> None:
    first = run_dod(project, "--spec", "alpha")
    assert first.returncode == 0, first.stderr
    out = evidence_file(project)

    # Same spec path but a stale digest (the spec was edited): the record is
    # still our own evidence, so a re-run overwrites it -- the sentinel key
    # must disappear and no temp file may survive.
    spec_path = str((project / ".slim" / "spec" / "alpha.md").resolve())
    out.write_text(
        json.dumps({"spec": spec_path, "spec_sha256": "0" * 64, "sentinel": True}) + "\n",
        encoding="utf-8",
    )

    second = run_dod(project, "--spec", "alpha")
    assert second.returncode == 0, second.stderr
    record = json.loads(out.read_text(encoding="utf-8"))
    assert set(record) == EVIDENCE_KEYS
    assert "sentinel" not in record
    assert temp_leftovers(project / "verify") == []


def test_same_spec_rerun_with_unchanged_digest(project: Path) -> None:
    first = run_dod(project, "--spec", "alpha")
    assert first.returncode == 0, first.stderr
    out = evidence_file(project)
    first_record = json.loads(out.read_text(encoding="utf-8"))

    # Deterministic replacement probe: age the file to the epoch; a re-run that
    # overwrites it (the guard's spec_sha256 branch, spec unchanged) must leave
    # a fresh mtime instead of refusing.
    os.utime(out, (0, 0))

    second = run_dod(project, "--spec", "alpha")

    assert second.returncode == 0, second.stderr
    second_record = json.loads(out.read_text(encoding="utf-8"))
    assert second_record["spec"] == first_record["spec"]
    assert second_record["spec_sha256"] == first_record["spec_sha256"]
    assert out.stat().st_mtime_ns != 0  # the file was replaced by the fresh run
    assert set(second_record) == EVIDENCE_KEYS
    assert temp_leftovers(project / "verify") == []


# ---------------------------------------------------------------------------
# Foreign-record and corrupt-record guard (flat verify/ store)
# ---------------------------------------------------------------------------


def test_foreign_record_refused_and_untouched(project: Path) -> None:
    other = make_spec(project, "other")  # another contract reusing the same dod.id
    out = evidence_file(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    before = (
        json.dumps(
            {
                "check": CHECK_ID,
                "cmd": "true",
                "exit_code": 0,
                "spec": str(other.resolve()),
                "spec_sha256": "f" * 64,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    out.write_bytes(before)

    result = run_dod(project, "--spec", "alpha")

    assert result.returncode == 3, result.stderr
    assert out.read_bytes() == before
    assert "another spec" in result.stderr
    assert "collision" in result.stderr
    assert temp_leftovers(project / "verify") == []


def test_corrupt_record_refused_and_untouched(project: Path) -> None:
    out = evidence_file(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    before = b"{ this is not json\n"
    out.write_bytes(before)

    result = run_dod(project, "--spec", "alpha")

    assert result.returncode == 3, result.stderr
    assert out.read_bytes() == before
    assert "unparseable" in result.stderr
    assert temp_leftovers(project / "verify") == []


def test_non_object_record_refused_and_untouched(project: Path) -> None:
    out = evidence_file(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    before = b"[1, 2]\n"
    out.write_bytes(before)

    result = run_dod(project, "--spec", "alpha")

    assert result.returncode == 3, result.stderr
    assert out.read_bytes() == before
    assert "not an object" in result.stderr
    assert temp_leftovers(project / "verify") == []
