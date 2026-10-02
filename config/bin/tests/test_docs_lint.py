"""Subprocess tests for bin/docs-lint (per-spec mode + duplicate dod ids).

Fixtures are built under ``/tmp/opencode`` (the approved scratch dir) and each
test owns a fresh directory that is removed afterwards.  Stdlib only (plus
pytest for the runner).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]  # config/bin (repo-local, never the live machine)
CLI = BIN / "docs-lint"
DOD_RUN = BIN / "dod-run"
SPEC_STATUS = BIN / "spec-status"
SCRATCH = Path("/tmp/opencode")

DIATAXIS_DIRS = (
    "docs/tutorials",
    "docs/how-to",
    "docs/reference",
    "docs/explanation",
    "docs/adr",
)

SCOPE_OK = '{"allow": ["src/**"], "deny": []}'


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def workdir():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="docs-lint-test-", dir=str(SCRATCH)))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def make_project(base: Path, name: str = "proj") -> Path:
    """A minimal valid project: the five framework dirs plus one real ADR."""
    root = base / name
    for rel in DIATAXIS_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "docs" / "adr" / "0001-test.md").write_text("# ADR 1\n", encoding="utf-8")
    return root


def add_spec(
    root: Path,
    slug: str,
    *,
    token: str = "draft",
    dod_ids: tuple[str, ...] | None = ("build",),
    adr_ref: str = "docs/adr/0001-test.md",
) -> Path:
    lines = [
        f"# {slug}",
        "",
        f"- **Статус спецификации:** `{token}`",
        "",
        f"See {adr_ref}.",
        "",
        "```scope",
        SCOPE_OK,
        "```",
        "",
    ]
    if dod_ids is not None:
        checks = ", ".join(f'{{"id": "{cid}", "cmd": "true"}}' for cid in dod_ids)
        lines += ["```dod", f'{{"checks": [{checks}]}}', "```", ""]
    spec = root / ".slim" / "spec" / f"{slug}.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("\n".join(lines), encoding="utf-8")
    return spec


def run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=project,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# 1. clean project lints clean
# ---------------------------------------------------------------------------


def test_clean_project_no_error(workdir: Path) -> None:
    root = make_project(workdir)
    add_spec(root, "alpha", dod_ids=("alpha_build",))
    add_spec(root, "beta", dod_ids=("beta_build",))

    result = run(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ERROR" not in result.stdout


# ---------------------------------------------------------------------------
# 2. two contracts sharing a check id -> ERROR naming both
# ---------------------------------------------------------------------------


def test_two_specs_share_check_id(workdir: Path) -> None:
    root = make_project(workdir)
    add_spec(root, "alpha", dod_ids=("build",))
    add_spec(root, "beta", dod_ids=("build",))

    result = run(root)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "ERROR" in result.stdout
    assert "alpha.md" in result.stdout
    assert "beta.md" in result.stdout
    assert "'build'" in result.stdout
    assert "DONE" in result.stdout  # the consequence is explained


def test_no_duplicate_is_silent(workdir: Path) -> None:
    root = make_project(workdir)
    add_spec(root, "alpha", dod_ids=("a_build",))
    add_spec(root, "beta", dod_ids=("b_build",))

    result = run(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dod-duplicate" not in result.stdout


# ---------------------------------------------------------------------------
# 3. duplicate id within one spec -> ERROR
# ---------------------------------------------------------------------------


def test_duplicate_within_one_spec(workdir: Path) -> None:
    root = make_project(workdir)
    add_spec(root, "alpha", dod_ids=("build", "build"))

    result = run(root)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "'build'" in result.stdout
    assert "2 times" in result.stdout


# ---------------------------------------------------------------------------
# 4. --spec lints only that file and reports its collisions
# ---------------------------------------------------------------------------


def test_spec_mode_only_that_file(workdir: Path) -> None:
    root = make_project(workdir)
    add_spec(root, "alpha", dod_ids=("shared",))
    add_spec(root, "beta", dod_ids=("shared",))
    # A third, broken spec: its missing-ADR error must NOT appear in --spec mode.
    add_spec(root, "broken", dod_ids=("other",), adr_ref="docs/adr/9999-missing.md")

    default = run(root)
    assert default.returncode == 1
    assert "broken.md" in default.stdout

    result = run(root, "--spec", "alpha")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "alpha.md" in result.stdout
    assert "beta.md" in result.stdout  # its collision is reported
    assert "'shared'" in result.stdout
    assert "broken.md" not in result.stdout  # not linted at all


def test_spec_mode_accepts_slug_md_and_path(workdir: Path) -> None:
    root = make_project(workdir)
    add_spec(root, "alpha", dod_ids=("alpha_build",))

    assert run(root, "--spec", "alpha").returncode == 0
    assert run(root, "--spec", "alpha.md").returncode == 0
    assert run(root, "--spec", ".slim/spec/alpha.md").returncode == 0


# ---------------------------------------------------------------------------
# 5. --spec with an unknown slug -> nonzero + available list
# ---------------------------------------------------------------------------


def test_spec_unknown_slug(workdir: Path) -> None:
    root = make_project(workdir)
    add_spec(root, "alpha", dod_ids=("alpha_build",))

    result = run(root, "--spec", "does-not-exist")

    assert result.returncode != 0
    assert "no spec matches does-not-exist" in result.stderr
    assert "available" in result.stderr
    assert "alpha" in result.stderr


# ---------------------------------------------------------------------------
# 6. an index file is never linted as a contract
# ---------------------------------------------------------------------------


def test_index_is_not_linted_as_contract(workdir: Path) -> None:
    root = make_project(workdir)
    # Point the index at a missing ADR and give it a scope fence: if it were
    # treated as a contract it would produce an ERROR, but it is an index.
    add_spec(root, "ROADMAP", token="roadmap", dod_ids=None, adr_ref="docs/adr/9999-missing.md")

    result = run(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ERROR" not in result.stdout


# ---------------------------------------------------------------------------
# 7. sibling tools still import / run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", [DOD_RUN, SPEC_STATUS])
def test_sibling_tools_import(tool: Path, workdir: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(tool), "--help"],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# 8. the changed CLIs byte-compile
# ---------------------------------------------------------------------------


def test_changed_clis_compile(tmp_path: Path) -> None:
    import py_compile

    for tool in (CLI, BIN / "spec-approve"):
        out = tmp_path / (tool.name + ".pyc")
        py_compile.compile(str(tool), cfile=str(out), doraise=True)
        assert out.is_file()
