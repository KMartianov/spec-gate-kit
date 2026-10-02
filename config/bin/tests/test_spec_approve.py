"""Tests for bin/spec-approve, driving the CLI as a subprocess.

Every invocation passes ``--approvals-dir <tmp>/approvals`` so the real
``~/.local/share/opencode/approvals`` store is never touched.  Stdlib only
(plus pytest for the runner).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]  # config/bin (repo-local, never the live machine)
CLI = BIN / "spec-approve"

SCOPE_OK = '{"allow": ["src/**"], "deny": []}'
DOD_OK = '{"checks": [{"id": "smoke", "cmd": "true"}]}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(Path(path).read_bytes())


def make_spec(
    path: Path,
    *,
    token: str = "`draft`",
    scope: str | None = SCOPE_OK,
    dod: str | None = DOD_OK,
    approved: str | None = None,
    status_line: bool = True,
) -> Path:
    """Build a minimal spec carrying a status line, a scope fence and a dod fence."""
    lines = ["# Test spec", ""]
    if status_line:
        lines.append(f"- **Статус спецификации:** {token}   <!-- draft | approved -->")
        if approved is not None:
            lines.append(f"- **Утверждено:** {approved} (human)")
    lines.append("")
    if scope is not None:
        lines.extend(["```scope", scope, "```", ""])
    if dod is not None:
        lines.extend(["```dod", dod, "```", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(project: Path, approvals: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args, "--approvals-dir", str(approvals)],
        cwd=project,
        capture_output=True,
        text=True,
    )


def records(approvals: Path) -> list[Path]:
    if not approvals.exists():
        return []
    return sorted(approvals.rglob("*.json"))


def record_root_hash(project: Path) -> str:
    return sha_bytes(str(project.resolve()).encode("utf-8"))[:16]


# ---------------------------------------------------------------------------
# 1. happy path
# ---------------------------------------------------------------------------


def test_happy_path(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec = make_spec(project / ".slim" / "spec" / "alpha.md")
    approvals = tmp_path / "approvals"

    result = run(project, approvals, "alpha")

    assert result.returncode == 0, result.stderr
    text = spec.read_text(encoding="utf-8")
    assert "`approved`" in text
    assert "- **Утверждено:**" in text
    found = records(approvals)
    assert len(found) == 1
    record = json.loads(found[0].read_text(encoding="utf-8"))
    assert record["spec_sha256"] == sha_file(spec)
    assert "gate: allow" in result.stdout


# ---------------------------------------------------------------------------
# 2. re-approve preserves the spec bytes (P0-1)
# ---------------------------------------------------------------------------


def test_reapprove_preserves_spec_bytes(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec = make_spec(project / ".slim" / "spec" / "alpha.md")
    approvals = tmp_path / "approvals"

    first = run(project, approvals, "alpha")
    assert first.returncode == 0, first.stderr
    digest_after_first = sha_file(spec)

    second = run(project, approvals, "alpha")
    assert second.returncode == 0, second.stderr
    assert sha_file(spec) == digest_after_first
    assert "unchanged" in second.stdout


# ---------------------------------------------------------------------------
# 3. --restamp rewrites the stamp and warns about staleness
# ---------------------------------------------------------------------------


def test_restamp_rewrites_stamp_and_warns(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec = make_spec(project / ".slim" / "spec" / "alpha.md")
    approvals = tmp_path / "approvals"

    assert run(project, approvals, "alpha").returncode == 0
    digest_before = sha_file(spec)

    result = run(project, approvals, "alpha", "--restamp")

    assert result.returncode == 0, result.stderr
    assert sha_file(spec) != digest_before
    assert "stale" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 4. bare slug resolution (P0-2)
# ---------------------------------------------------------------------------


def test_bare_slug_resolution(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    make_spec(project / ".slim" / "spec" / "alpha.md")
    approvals = tmp_path / "approvals"

    assert run(project, approvals, "alpha").returncode == 0
    assert run(project, approvals, "alpha.md").returncode == 0

    missing = run(project, approvals, "does-not-exist")
    assert missing.returncode == 1
    assert "alpha" in missing.stderr


# ---------------------------------------------------------------------------
# 5. index refused (P0-3)
# ---------------------------------------------------------------------------


def test_index_refused(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    roadmap = make_spec(project / ".slim" / "spec" / "ROADMAP.md", token="`roadmap`")
    before = sha_file(roadmap)
    approvals = tmp_path / "approvals"

    result = run(project, approvals, "ROADMAP")

    assert result.returncode == 2
    assert records(approvals) == []
    assert sha_file(roadmap) == before


# ---------------------------------------------------------------------------
# 6. archive refused (P0-3)
# ---------------------------------------------------------------------------


def test_archive_refused(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    archived = make_spec(project / ".slim" / "spec" / "archive" / "x.md")
    approvals = tmp_path / "approvals"

    result = run(project, approvals, str(archived))

    assert result.returncode == 2
    assert records(approvals) == []


# ---------------------------------------------------------------------------
# 7. outside .slim/spec refused (P0-3)
# ---------------------------------------------------------------------------


def test_outside_spec_dir_refused(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / ".slim" / "spec").mkdir(parents=True)
    outside = make_spec(project / "other.md")
    approvals = tmp_path / "approvals"

    result = run(project, approvals, str(outside))

    assert result.returncode == 2
    assert records(approvals) == []


# ---------------------------------------------------------------------------
# 8. no status line -> undeclared, refused
# ---------------------------------------------------------------------------


def test_no_status_line_refused(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec = make_spec(project / ".slim" / "spec" / "empty.md", status_line=False)
    before = sha_file(spec)
    approvals = tmp_path / "approvals"

    result = run(project, approvals, "empty")

    assert result.returncode == 2
    assert sha_file(spec) == before
    assert records(approvals) == []


# ---------------------------------------------------------------------------
# 9. bare (non-backticked) token still flips (P0-4)
# ---------------------------------------------------------------------------


def test_bare_token_flips(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec = make_spec(project / ".slim" / "spec" / "beta.md", token="draft")
    approvals = tmp_path / "approvals"

    result = run(project, approvals, "beta")

    assert result.returncode == 0, result.stderr
    assert "`approved`" in spec.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 10. missing scope fence: warning, or refusal under --strict
# ---------------------------------------------------------------------------


def test_missing_scope_warns_or_refuses(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec = make_spec(project / ".slim" / "spec" / "gamma.md", scope=None)
    before = sha_file(spec)
    approvals = tmp_path / "approvals"

    strict = run(project, approvals, "gamma", "--strict")
    assert strict.returncode == 2
    assert sha_file(spec) == before
    assert records(approvals) == []

    relaxed = run(project, approvals, "gamma")
    assert relaxed.returncode == 0, relaxed.stderr
    assert "warning" in relaxed.stderr
    assert len(records(approvals)) == 1


# ---------------------------------------------------------------------------
# 11. missing dod fence: warning, or refusal under --strict
# ---------------------------------------------------------------------------


def test_missing_dod_warns_or_refuses(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    make_spec(project / ".slim" / "spec" / "delta.md", dod=None)
    approvals = tmp_path / "approvals"

    strict = run(project, approvals, "delta", "--strict")
    assert strict.returncode == 2
    assert records(approvals) == []

    relaxed = run(project, approvals, "delta")
    assert relaxed.returncode == 0, relaxed.stderr
    assert "warning" in relaxed.stderr


# ---------------------------------------------------------------------------
# 12. --list is read-only and prints one row per file
# ---------------------------------------------------------------------------


def test_list_is_read_only(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec_dir = project / ".slim" / "spec"
    make_spec(spec_dir / "a.md")
    make_spec(spec_dir / "ROADMAP.md", token="`roadmap`")
    make_spec(spec_dir / "broken.md", status_line=False)
    approvals = tmp_path / "approvals"

    before = {p: sha_file(p) for p in spec_dir.glob("*.md")}
    result = run(project, approvals, "--list")

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 3
    for slug in ("a", "ROADMAP", "broken"):
        assert slug in result.stdout
    assert not approvals.exists()
    for path, digest in before.items():
        assert sha_file(path) == digest


# ---------------------------------------------------------------------------
# 13. --all leaves approved bytes untouched, approves drafts, skips ROADMAP
# ---------------------------------------------------------------------------


def test_all_bulk(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec_dir = project / ".slim" / "spec"
    c1 = make_spec(spec_dir / "c1.md")
    c2 = make_spec(spec_dir / "c2.md")
    c3 = make_spec(
        spec_dir / "c3.md",
        token="`approved`",
        approved="2020-01-01T00:00:00+00:00",
    )
    make_spec(spec_dir / "ROADMAP.md", token="`roadmap`")
    c3_before = sha_file(c3)
    approvals = tmp_path / "approvals"

    result = run(project, approvals, "--all")

    assert result.returncode == 0, result.stderr
    assert "`approved`" in c1.read_text(encoding="utf-8")
    assert "`approved`" in c2.read_text(encoding="utf-8")
    assert sha_file(c3) == c3_before
    assert "ROADMAP" in result.stdout
    assert "summary:" in result.stdout


# ---------------------------------------------------------------------------
# 14. no-clobber: a foreign record is never touched
# ---------------------------------------------------------------------------


def test_foreign_record_untouched(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    make_spec(project / ".slim" / "spec" / "alpha.md")
    approvals = tmp_path / "approvals"

    record_dir = approvals / record_root_hash(project)
    record_dir.mkdir(parents=True)
    foreign = record_dir / "foreign.json"
    foreign_payload = (
        json.dumps(
            {
                "root": str(project.resolve()),
                "spec": str(project / "elsewhere" / "other.md"),
                "spec_sha256": "deadbeef",
                "task": "other",
                "approved_by": "human",
                "approved_at": "2020-01-01T00:00:00+00:00",
            },
            indent=2,
        )
        + "\n"
    )
    foreign.write_text(foreign_payload, encoding="utf-8")

    result = run(project, approvals, "alpha")

    assert result.returncode == 0, result.stderr
    assert foreign.read_text(encoding="utf-8") == foreign_payload


# ---------------------------------------------------------------------------
# 15. no temp litter survives any run
# ---------------------------------------------------------------------------


def test_no_temp_litter(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    spec_dir = project / ".slim" / "spec"
    make_spec(spec_dir / "a.md")
    make_spec(spec_dir / "ROADMAP.md", token="`roadmap`")
    approvals = tmp_path / "approvals"

    assert run(project, approvals, "a").returncode == 0
    assert run(project, approvals, "nope").returncode == 1
    assert run(project, approvals, "--all").returncode == 0

    leftovers = [p for p in tmp_path.rglob("*.tmp-*")]
    assert leftovers == []
