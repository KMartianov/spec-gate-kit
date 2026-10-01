"""Tests for bin/spec-revoke, driving the CLI as a subprocess.

Every invocation passes ``--approvals-dir <fixture>/approvals`` where the fixture
lives under ``/tmp/opencode`` so the real
``~/.local/share/opencode/approvals`` store is never touched.  Approvals are
hand-crafted here (matching the documented record schema) instead of calling
``spec-approve``: the tests stay independent of that file and exercise the
reader/writer contract directly.  Stdlib only (plus pytest for the runner).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
CLI = BIN / "spec-revoke"
sys.path.insert(0, str(BIN))
import spec_scope  # noqa: E402

FIXTURE_BASE = Path("/tmp/opencode/spec-revoke-tests")

SCOPE_OK = '{"allow": ["src/**"], "deny": []}'
DOD_OK = '{"checks": [{"id": "smoke", "cmd": "true"}]}'
STAMP = "2020-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def ws():
    """A unique throwaway workspace under /tmp/opencode, removed afterwards."""
    base = FIXTURE_BASE / f"{os.getpid()}-{uuid.uuid4().hex[:10]}"
    base.mkdir(parents=True, exist_ok=True)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(Path(path).read_bytes())


def snapshot(root: Path) -> dict[str, str]:
    """Recursive ``relative path -> sha256`` snapshot (directories marked)."""
    if not root.exists():
        return {}
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        out[rel] = "<dir>" if path.is_dir() else sha_file(path)
    return out


def make_draft(path: Path) -> Path:
    lines = [
        "# Test spec",
        "",
        "- **Статус спецификации:** `draft`   <!-- draft | approved -->",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def approve_in_place(project: Path, spec: Path, approvals: Path) -> Path:
    """Flip ``spec`` to approved and write its matching record; return the record."""
    text = spec.read_text(encoding="utf-8")
    text = text.replace("`draft`", "`approved`", 1)
    text = text.replace(
        "\n\n```scope",
        f"\n- **Утверждено:** {STAMP} (human)\n\n```scope",
        1,
    )
    spec.write_text(text, encoding="utf-8")

    record = {
        "root": str(project.resolve()),
        "spec": str(spec.resolve()),
        "spec_sha256": sha_file(spec),
        "task": spec.stem,
        "approved_by": "human",
        "approved_at": STAMP,
    }
    rec_dir = approvals / spec_scope.root_hash(project.resolve())
    rec_dir.mkdir(parents=True, exist_ok=True)
    rec_file = rec_dir / f"{spec.stem}.json"
    rec_file.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec_file


def run(project: Path, approvals: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args, "--approvals-dir", str(approvals)],
        cwd=project,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# P0 regression: revoking one spec must never wipe another's approval
# ---------------------------------------------------------------------------


def test_p0_revoke_one_keeps_other_approval(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    first = make_draft(spec_dir / "alpha.md")
    second = make_draft(spec_dir / "beta.md")
    first_rec = approve_in_place(project, first, approvals)
    second_rec = approve_in_place(project, second, approvals)
    second_bytes = second_rec.read_bytes()
    second_spec_bytes = second.read_bytes()

    result = run(project, approvals, "alpha")

    assert result.returncode == 0, result.stderr
    # the other spec's record survives byte-for-byte ...
    assert second_rec.is_file()
    assert second_rec.read_bytes() == second_bytes
    assert sha_file(second_rec) == sha_bytes(second_bytes)
    # ... and still validates through the shared reader
    found_path, record = spec_scope.find_valid_approval(
        project.resolve(), second.resolve(), approvals
    )
    assert record is not None
    assert found_path == second_rec
    # ... and the other spec file itself is untouched
    assert second.read_bytes() == second_spec_bytes
    assert "`approved`" in second.read_text(encoding="utf-8")
    assert "- **Утверждено:**" in second.read_text(encoding="utf-8")

    # the targeted spec is gone from the store and back to draft
    assert not first_rec.exists()
    assert "`draft`" in first.read_text(encoding="utf-8")
    assert "- **Утверждено:**" not in first.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Only the matching record is removed; foreign records stay byte-identical
# ---------------------------------------------------------------------------


def test_only_matching_record_is_removed(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    for name in ("alpha", "beta", "gamma"):
        spec = make_draft(spec_dir / f"{name}.md")
        approve_in_place(project, spec, approvals)

    before = {str(p): sha_file(p) for p in sorted(approvals.rglob("*.json"))}
    assert len(before) == 3

    result = run(project, approvals, "beta")
    assert result.returncode == 0, result.stderr

    after = {str(p): sha_file(p) for p in sorted(approvals.rglob("*.json"))}
    assert str(approvals / spec_scope.root_hash(project.resolve()) / "beta.json") not in after
    assert set(after) == {k for k in before if not k.endswith("/beta.json")}
    for path in after:
        assert after[path] == before[path]

    # a foreign record is never unlinked even when a malformed JSON record exists
    rec_dir = approvals / spec_scope.root_hash(project.resolve())
    junk = rec_dir / "not-json.json"
    junk.write_text("{ this is not json", encoding="utf-8")
    again = run(project, approvals, "alpha")
    assert again.returncode == 0, again.stderr
    assert junk.read_bytes() == b"{ this is not json"


# ---------------------------------------------------------------------------
# No-arg default / --all: every active contract, then idempotent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["noarg", "all"])
def test_revoke_all_modes(ws: Path, mode: str) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    beta = make_draft(spec_dir / "beta.md")
    roadmap = make_draft(spec_dir / "ROADMAP.md")
    roadmap.write_text(
        roadmap.read_text(encoding="utf-8").replace("`draft`", "`roadmap`", 1),
        encoding="utf-8",
    )
    approve_in_place(project, alpha, approvals)
    approve_in_place(project, beta, approvals)

    args = [] if mode == "noarg" else ["--all"]
    result = run(project, approvals, *args)

    assert result.returncode == 0, result.stderr
    assert "revoking spec:" in result.stdout
    assert "`draft`" in alpha.read_text(encoding="utf-8")
    assert "`draft`" in beta.read_text(encoding="utf-8")
    # the index is not a contract: untouched
    assert "`roadmap`" in roadmap.read_text(encoding="utf-8")
    assert list(approvals.rglob("*.json")) == []


def test_second_run_is_idempotent(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    approve_in_place(project, alpha, approvals)

    assert run(project, approvals).returncode == 0
    second = run(project, approvals)

    assert second.returncode == 0, second.stderr
    assert "nothing to revert" in second.stdout


def test_all_conflicts_with_positional(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    make_draft(spec_dir / "alpha.md")

    result = run(project, approvals, "alpha", "--all")
    assert result.returncode == 1
    assert "cannot be combined" in result.stderr


# ---------------------------------------------------------------------------
# --list is read-only
# ---------------------------------------------------------------------------


def test_list_is_read_only(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    beta = make_draft(spec_dir / "beta.md")
    approve_in_place(project, alpha, approvals)
    approve_in_place(project, beta, approvals)

    before = snapshot(ws)
    result = run(project, approvals, "--list")

    assert result.returncode == 0, result.stderr
    assert snapshot(ws) == before
    assert "would revoke" in result.stdout
    assert "would remove approval record" in result.stdout
    assert "`approved`" in alpha.read_text(encoding="utf-8")
    assert "`approved`" in beta.read_text(encoding="utf-8")


def test_list_with_positional_is_read_only(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    approve_in_place(project, alpha, approvals)

    before = snapshot(ws)
    result = run(project, approvals, "alpha", "--list")

    assert result.returncode == 0, result.stderr
    assert snapshot(ws) == before
    assert "alpha" in result.stdout


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


def test_bare_slug_target(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    approve_in_place(project, alpha, approvals)

    result = run(project, approvals, "alpha")
    assert result.returncode == 0, result.stderr
    assert "`draft`" in alpha.read_text(encoding="utf-8")


def test_directory_target(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    beta = make_draft(spec_dir / "beta.md")
    archives = make_draft(spec_dir / "archive" / "old.md")
    approve_in_place(project, alpha, approvals)
    approve_in_place(project, beta, approvals)

    result = run(project, approvals, str(spec_dir))
    assert result.returncode == 0, result.stderr
    assert "`draft`" in alpha.read_text(encoding="utf-8")
    assert "`draft`" in beta.read_text(encoding="utf-8")
    # archive/** is never expanded by a directory target
    assert not archives.exists() or "`draft`" in archives.read_text(encoding="utf-8")


def test_missing_target_exits_1_with_slugs(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    make_draft(spec_dir / "alpha.md")

    result = run(project, approvals, "does-not-exist")

    assert result.returncode == 1
    assert "available slugs" in result.stderr
    assert "alpha" in result.stderr


def test_no_project_root_exits_2(ws: Path) -> None:
    sandbox = ws / "sandbox"
    (sandbox / ".git").mkdir(parents=True)
    approvals = ws / "approvals"

    result = run(sandbox, approvals)

    assert result.returncode == 2
    assert "no project root" in result.stderr


def test_help_exits_0(ws: Path) -> None:
    result = run(ws, ws / "approvals", "--help")
    assert result.returncode == 0
    assert "spec-revoke" in result.stdout


# ---------------------------------------------------------------------------
# Revert invalidates evidence but never deletes it
# ---------------------------------------------------------------------------


def test_revert_does_not_touch_verify(ws: Path) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    approve_in_place(project, alpha, approvals)

    verify_dir = project / "verify"
    verify_dir.mkdir(parents=True)
    evidence = verify_dir / "smoke.json"
    evidence.write_text(
        json.dumps(
            {
                "check": "smoke",
                "cmd": "true",
                "exit_code": 0,
                "spec": str(alpha.resolve()),
                "spec_sha256": sha_file(alpha),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    before = evidence.read_bytes()

    result = run(project, approvals, "alpha")

    assert result.returncode == 0, result.stderr
    assert evidence.read_bytes() == before
    assert "verify" in result.stderr.lower()
    assert "stale" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Bare-token status line (no backticks): legacy/hand-edited approval
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status_line", "expected"),
    [
        ("- **Статус спецификации:** approved", "- **Статус спецификации:** `draft`"),
        (
            "-   **Статус спецификации:**   approved   ",
            "-   **Статус спецификации:**   `draft`",
        ),
    ],
)
def test_bare_approved_token_is_reverted(ws: Path, status_line: str, expected: str) -> None:
    project = ws / "proj"
    spec_dir = project / ".slim" / "spec"
    approvals = ws / "approvals"
    alpha = make_draft(spec_dir / "alpha.md")
    rec = approve_in_place(project, alpha, approvals)

    text = alpha.read_text(encoding="utf-8")
    text = text.replace(
        "- **Статус спецификации:** `approved`   <!-- draft | approved -->",
        f"{status_line}   <!-- draft | approved -->",
        1,
    )
    assert "`approved`" not in text.split("<!--", 1)[0]
    alpha.write_text(text, encoding="utf-8")

    result = run(project, approvals, "alpha")

    assert result.returncode == 0, result.stderr
    updated = alpha.read_text(encoding="utf-8")
    status_lines = [
        line.strip()
        for line in updated.split("<!--", 1)[0].splitlines()
        if "Статус спецификации" in line
    ]
    assert status_lines == [expected.strip()]
    assert "- **Утверждено:**" not in updated
    assert not rec.exists()
