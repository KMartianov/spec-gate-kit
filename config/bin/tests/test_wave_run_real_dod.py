r"""wave-run --execute against the REAL bin/dod-run (no stand-in on ``$PATH``).

The fake-dod-run harness (``test_wave_run.py``) covers grouping and failure
semantics; this file closes the integration gap.  A throwaway git project with
two approved contracts sharing one canonical command is executed through the
shipped ``dod-run``, which writes genuine evidence v2 for the deterministic
representative; ``wave-run`` then fans that run out to the other member with
explicit provenance.  In symbols, with $G$ one group and $r$ its representative:

$$
\text{execute}(G) \Rightarrow
\texttt{verify}/\langle r.id\rangle.json \ \text{(plain dod-run evidence)}
\;\land\;
\forall m \in G\setminus\{r\}:\ \texttt{verify}/\langle m.id\rangle.json
\ \text{(with } \texttt{via}=\text{wave-run)}
$$

The default (dry-run) invocation must write nothing at all.  ``HOME`` is
redirected to a fixture directory, so the real approvals store is never read or
written; ``$PATH`` is stripped of any stray ``dod-run`` so the sibling shipped
next to ``wave-run`` is the binary under test.  Stdlib + pytest only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]  # config/bin (repo-local, never the live machine)
WAVE = BIN / "wave-run"
sys.path.insert(0, str(BIN))
import spec_scope  # noqa: E402

STAMP = "2026-01-01T00:00:00+00:00"
SCOPE_OK = '{"allow": ["src/**"], "deny": []}'
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


def write_spec(root: Path, slug: str, check_id: str) -> Path:
    lines = [
        f"# spec {slug}",
        "",
        "- **Статус спецификации:** `draft`",
        "",
        "```scope",
        SCOPE_OK,
        "```",
        "",
        "```dod",
        json.dumps({"checks": [{"id": check_id, "cmd": "true"}]}),
        "```",
        "",
    ]
    path = root / ".slim" / "spec" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


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


def make_project(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """One committed repo, two approved contracts with one canonical command."""
    root = tmp_path / "proj"
    (root / ".slim" / "spec").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "common.py").write_text("# common\n", encoding="utf-8")
    alpha = write_spec(root, "alpha", "a1")
    beta = write_spec(root, "beta", "b1")
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
    home = tmp_path / "home"
    approve_fixture(root, home, alpha)
    approve_fixture(root, home, beta)
    return root, home, alpha, beta


def path_without_a_stray_dod_run() -> str:
    """$PATH minus any directory that would shadow the shipped sibling."""
    entries = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and (Path(entry) / "dod-run").exists():
            continue
        entries.append(entry)
    return os.pathsep.join(entries)


def run(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    home.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": path_without_a_stray_dod_run(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, str(WAVE), *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def snapshot(root: Path) -> dict[str, bytes | str]:
    """Everything under the project except git-internal state (read-only noise)."""
    out: dict[str, bytes | str] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        rel = path.relative_to(root).as_posix()
        out[rel] = "<dir>" if path.is_dir() else path.read_bytes()
    return out


# ---------------------------------------------------------------------------
# Default dry-run writes nothing
# ---------------------------------------------------------------------------


def test_default_dry_run_plans_and_writes_nothing(tmp_path: Path) -> None:
    root, home, _alpha, _beta = make_project(tmp_path)
    before = snapshot(root)

    result = run(root, home, "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert len(payload["plan"]) == 1
    group = payload["plan"][0]
    assert group["canon"] == "true"
    assert group["group_size"] == 2
    assert [member["id"] for member in group["members"]] == ["a1", "b1"]
    assert group["representative"]["id"] == "a1"  # min(slug, id): alpha wins

    assert not (root / "verify").exists()
    assert snapshot(root) == before


# ---------------------------------------------------------------------------
# --execute through the real dod-run
# ---------------------------------------------------------------------------


def test_execute_through_real_dod_run_writes_fresh_evidence(tmp_path: Path) -> None:
    root, home, alpha, beta = make_project(tmp_path)

    result = run(root, home, "--execute", "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "execute"
    assert len(payload["results"]) == 1
    outcome = payload["results"][0]
    assert outcome["representative"] == "a1"
    assert outcome["exit_code"] == 0
    assert outcome["evidence_fresh"] is True
    assert outcome["members_written"] == ["verify/b1.json"]
    assert outcome["errors"] == []

    a1 = json.loads((root / "verify" / "a1.json").read_text(encoding="utf-8"))
    b1 = json.loads((root / "verify" / "b1.json").read_text(encoding="utf-8"))

    head = git_head(root)
    # Representative: plain dod-run evidence v2, attested to the current revision.
    assert a1["check"] == "a1" and a1["exit_code"] == 0
    assert a1["git_head"] == head and a1["tree_dirty"] is False
    assert a1["spec_sha256"] == sha_file(alpha)
    assert "via" not in a1
    # Member: its own identity plus explicit provenance for the substitution.
    assert b1["check"] == "b1" and b1["exit_code"] == 0
    assert b1["spec_sha256"] == sha_file(beta)
    assert b1["via"] == "wave-run"
    assert b1["canon"] == "true"
    assert b1["executed_spec"] == str(alpha.resolve())
    assert b1["representative_id"] == "a1"
    assert b1["git_head"] == head and b1["tree_dirty"] is False
