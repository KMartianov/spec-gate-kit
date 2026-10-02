r"""Behavioral tests for bin/spec-status: every derived lifecycle transition.

The tool is driven as a subprocess against throwaway git repositories under
pytest's ``tmp_path``; ``HOME`` is redirected to a fixture directory, so the
real ``~/.local/share/opencode/approvals`` store is never read or written.
Approval records are hand-crafted (matching the documented record schema) and
evidence files are written by hand on purpose: this file exercises the *reader*
contract of ``spec-status``, not the writers.

Derivation under test (``spec-status`` docstring):

$$
\begin{aligned}
\text{no spec} &\to \text{INTAKE} \\
\text{spec, no valid approval} &\to \text{SPEC\_DESIGN} \\
\text{approval, no valid evidence} &\to \text{APPROVED} \\
\text{approval, some evidence not passing} &\to \text{VERIFY} \\
\text{approval, every check passing} &\to \text{DONE}
\end{aligned}
$$

with

$$
\text{passing} = \text{hash\_matches} \land (\text{exit\_code}=0) \land \neg\,\text{stale},
\qquad
\text{stale} = (\text{git\_head}\ne\text{HEAD}) \lor \text{tree\_dirty} \lor \text{git\_head}=\varnothing
$$

INTAKE is observable as an empty contract listing: a project with
``.slim/spec/`` but no spec file yet has no report element at all.  Stdlib +
pytest only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]  # config/bin (repo-local, never the live machine)
CLI = BIN / "spec-status"
sys.path.insert(0, str(BIN))
import spec_scope  # noqa: E402

STAMP = "2026-01-01T00:00:00+00:00"
SCOPE_OK = '{"allow": ["src/**"], "deny": []}'
DOD_TWO = '{"checks": [{"id": "a1", "cmd": "true"}, {"id": "a2", "cmd": "true"}]}'

GIT_ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=GIT_ENV)


def git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )
    return result.stdout.strip()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_spec(
    root: Path,
    slug: str,
    *,
    status: str = "draft",
    scope: str | None = SCOPE_OK,
    dod_body: str | None = DOD_TWO,
) -> Path:
    lines = [f"# spec {slug}", "", f"- **Статус спецификации:** `{status}`", ""]
    if scope is not None:
        lines += ["```scope", scope, "```", ""]
    if dod_body is not None:
        lines += ["```dod", dod_body, "```", ""]
    path = root / ".slim" / "spec" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def make_repo(tmp_path: Path, *, with_spec: bool = True, name: str = "proj") -> Path:
    """A throwaway git repository with one commit and an optional draft spec."""
    root = tmp_path / name
    (root / ".slim" / "spec").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "common.py").write_text("# common\n", encoding="utf-8")
    if with_spec:
        write_spec(root, "alpha")
    git(root, "init", "-q")
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
        "-q",
        "-m",
        "fixture",
    )
    return root


def approve_fixture(root: Path, home: Path, spec: Path) -> None:
    """Flip a spec to approved and write its matching hand-crafted record."""
    text = spec.read_text(encoding="utf-8")
    text = text.replace("`draft`", "`approved`", 1)
    text = text.replace("\n\n```scope", f"\n- **Утверждено:** {STAMP} (human)\n\n```scope", 1)
    spec.write_text(text, encoding="utf-8")

    record = {
        "root": str(root.resolve()),
        "spec": str(spec.resolve()),
        "spec_sha256": sha_file(spec),
        "task": spec.stem,
        "approved_by": "human",
        "approved_at": STAMP,
    }
    rec_dir = (
        home
        / ".local"
        / "share"
        / "opencode"
        / "approvals"
        / spec_scope.root_hash(root.resolve())
    )
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / f"{spec.stem}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_evidence(
    root: Path,
    spec: Path,
    check_id: str,
    *,
    git_head_value: str | None,
    tree_dirty: bool = False,
    exit_code: int = 0,
    digest: str | None = None,
    include_git_head: bool = True,
) -> Path:
    """Evidence v2-shaped file; fields spec-status actually reads are explicit."""
    record: dict = {
        "check": check_id,
        "cmd": "true",
        "exit_code": exit_code,
        "started_at": STAMP,
        "finished_at": "2026-01-01T00:00:01+00:00",
        "duration_s": 0.001,
        "spec": str(spec.resolve()),
        "spec_sha256": digest if digest is not None else sha_file(spec),
        "tail": "",
        "tree_dirty": tree_dirty,
        "scope_sha256": None,
    }
    if include_git_head:
        record["git_head"] = git_head_value
    path = root / "verify" / f"{check_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    home.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def report_of(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert len(payload) == 1, payload
    return payload[0]


# ---------------------------------------------------------------------------
# Transition 1: INTAKE (no spec yet)
# ---------------------------------------------------------------------------


def test_intake_no_spec_yet_lists_nothing(tmp_path: Path) -> None:
    root = make_repo(tmp_path, with_spec=False)
    home = tmp_path / "home"

    human = run(root, home)
    assert human.returncode == 0, human.stdout + human.stderr
    assert "active contracts: none" in human.stdout

    payload = json.loads(run(root, home, "--json").stdout)
    assert payload == []  # no spec -> no report element; INTAKE has nothing to hash


# ---------------------------------------------------------------------------
# Transition 2: SPEC_DESIGN (spec, no valid approval)
# ---------------------------------------------------------------------------


def test_spec_design_draft_without_approval(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "SPEC_DESIGN"
    assert report["role"] == "spec" and report["active"] is True
    assert report["approval_record"] is None
    assert report["declared"] == "draft"
    assert [check["id"] for check in report["checks"]] == ["a1", "a2"]
    assert all(check["present"] is False for check in report["checks"])

    human = run(root, home, "--spec", "alpha")
    assert "Derived state (read-only, no store): SPEC_DESIGN" in human.stdout


# ---------------------------------------------------------------------------
# Transition 3: APPROVED (valid approval, no valid evidence)
# ---------------------------------------------------------------------------


def test_approved_valid_record_without_evidence(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"
    spec = root / ".slim" / "spec" / "alpha.md"
    approve_fixture(root, home, spec)

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "APPROVED"
    assert report["approval_record"] is not None
    assert report["checks"] and all(check["present"] is False for check in report["checks"])


# ---------------------------------------------------------------------------
# Transition 4: VERIFY (approval, evidence exists but not all passing)
# ---------------------------------------------------------------------------


def test_verify_when_check_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"
    spec = root / ".slim" / "spec" / "alpha.md"
    approve_fixture(root, home, spec)
    write_evidence(root, spec, "a1", git_head_value=git_head(root), exit_code=1)

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "VERIFY"
    a1 = report["checks"][0]
    assert a1["present"] is True and a1["passing"] is False
    assert a1["hash_matches"] is True and a1["exit_code"] == 1


# ---------------------------------------------------------------------------
# Transition 5: DONE (approval, every check passing)
# ---------------------------------------------------------------------------


def test_done_when_all_checks_pass(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"
    spec = root / ".slim" / "spec" / "alpha.md"
    approve_fixture(root, home, spec)
    head = git_head(root)
    for check_id in ("a1", "a2"):
        write_evidence(root, spec, check_id, git_head_value=head)

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "DONE"
    assert all(check["passing"] for check in report["checks"])
    assert report["worktree"] == {"head": head, "dirty": False}


# ---------------------------------------------------------------------------
# Stale branches: digest mismatch -> not present -> APPROVED
# ---------------------------------------------------------------------------


def test_wrong_digest_evidence_is_not_present(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"
    spec = root / ".slim" / "spec" / "alpha.md"
    approve_fixture(root, home, spec)
    write_evidence(root, spec, "a1", git_head_value=git_head(root), digest="0" * 64)

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "APPROVED"  # no evidence with a matching digest
    a1 = report["checks"][0]
    assert a1["hash_matches"] is False and a1["present"] is False


# ---------------------------------------------------------------------------
# Stale branches: head mismatch / dirty tree / legacy record -> VERIFY
# ---------------------------------------------------------------------------


def test_foreign_git_head_is_stale_and_verify(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"
    spec = root / ".slim" / "spec" / "alpha.md"
    approve_fixture(root, home, spec)
    write_evidence(root, spec, "a1", git_head_value="f" * 40)

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "VERIFY"
    a1 = report["checks"][0]
    assert a1["present"] is True and a1["stale"] is True and a1["passing"] is False
    assert a1["git_head"] == "f" * 40


def test_dirty_tree_is_stale_and_verify(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"
    spec = root / ".slim" / "spec" / "alpha.md"
    approve_fixture(root, home, spec)
    write_evidence(root, spec, "a1", git_head_value=git_head(root), tree_dirty=True)
    (root / "src" / "dirty.py").write_text("# uncommitted\n", encoding="utf-8")

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "VERIFY"
    assert report["worktree"]["dirty"] is True
    a1 = report["checks"][0]
    assert a1["tree_dirty"] is True and a1["stale"] is True and a1["passing"] is False

    human = run(root, home, "--spec", "alpha")
    assert "Derived state (read-only, no store): VERIFY" in human.stdout


def test_legacy_evidence_without_git_head_is_stale(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    home = tmp_path / "home"
    spec = root / ".slim" / "spec" / "alpha.md"
    approve_fixture(root, home, spec)
    write_evidence(root, spec, "a1", git_head_value=None, include_git_head=False)

    report = report_of(run(root, home, "--spec", "alpha", "--json"))

    assert report["state"] == "VERIFY"  # legacy evidence can never reach DONE
    a1 = report["checks"][0]
    assert a1["git_head"] is None and a1["stale"] is True and a1["passing"] is False
