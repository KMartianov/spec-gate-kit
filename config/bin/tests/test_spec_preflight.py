"""Tests for config/bin/spec-preflight, driving the CLI as a subprocess.

Every fixture lives under ``/tmp/opencode`` (``tempfile.mkdtemp``) and the real
``~/.local/share/opencode`` store is never touched: spec-preflight is read-only
and needs no approvals at all.  Tests are stdlib-only apart from pytest.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]
CLI = BIN / "spec-preflight"

SCOPE_OK = '{"allow": ["src/**"], "deny": []}'


def dod(*checks: tuple[str, str]) -> str:
    return json.dumps({"checks": [{"id": cid, "cmd": cmd} for cid, cmd in checks]})


DOD_ONE = dod(("smoke", "true"))


@pytest.fixture
def ws() -> Path:
    """A throwaway workspace under /tmp/opencode, removed afterwards."""
    base = Path(tempfile.mkdtemp(dir="/tmp/opencode", prefix="spec-preflight-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def make_project(ws: Path) -> Path:
    """A gated project root with a git-tracked ``src/common.py``."""
    root = ws / "proj"
    (root / ".slim" / "spec").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "common.py").write_text("# common\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    return root


def write_spec(
    root: Path,
    slug: str,
    *,
    status: str = "draft",
    scope: str | None = SCOPE_OK,
    dod_body: str | None = DOD_ONE,
    extra: str = "",
) -> Path:
    lines = [f"# spec {slug}", "", f"- **Статус спецификации:** `{status}`", ""]
    if scope is not None:
        lines += ["```scope", scope, "```", ""]
    if dod_body is not None:
        lines += ["```dod", dod_body, "```", ""]
    if extra:
        lines += [extra, ""]
    path = root / ".slim" / "spec" / f"{slug}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=root,
        capture_output=True,
        text=True,
    )


def report_of(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def snapshot(root: Path) -> dict[str, bytes | str]:
    out: dict[str, bytes | str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        out[rel] = "<dir>" if path.is_dir() else path.read_bytes()
    return out


# ---------------------------------------------------------------------------
# Happy path, JSON shape, quiet mode
# ---------------------------------------------------------------------------


def test_clean_project_exit_0(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha")

    result = run(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""

    result = run(root, "--json")
    assert result.returncode == 0
    payload = report_of(result)
    assert set(payload) == {"root", "errors", "warnings", "report"}
    assert payload["root"] == str(root.resolve())
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert set(payload["report"]) == {"contracts", "owners", "heavy_duplicates"}
    assert payload["report"]["contracts"] == ["alpha"]
    assert payload["report"]["owners"] == []
    assert payload["report"]["heavy_duplicates"] == []


def test_quiet_suppresses_only_without_errors(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha")
    quiet = run(root, "--quiet")
    assert quiet.returncode == 0
    assert quiet.stdout == ""

    write_spec(root, "broken", dod_body='{"checks": []}')
    loud = run(root, "--quiet")
    assert loud.returncode == 1
    assert "ERROR:" in loud.stdout


def test_help_exit_0(ws: Path) -> None:
    result = run(ws, "--help")
    assert result.returncode == 0
    assert "spec-preflight" in result.stdout


def test_read_only_snapshot(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha")
    write_spec(root, "beta", scope=None)
    before = snapshot(root)

    for args in ((), ("--json",), ("--spec", "alpha"), ("--all-owners",)):
        run(root, *args)

    assert snapshot(root) == before


# ---------------------------------------------------------------------------
# E2 -- scope mandate: missing/empty is a WARNING, broken form is an ERROR
# ---------------------------------------------------------------------------


def test_missing_scope_is_warning_not_error(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", scope=None)

    result = run(root)
    assert result.returncode == 0, result.stdout
    assert "WARN: .slim/spec/alpha.md: [preflight-scope]" in result.stdout
    assert "ERROR:" not in result.stdout

    payload = report_of(run(root, "--json"))
    assert payload["errors"] == []
    assert [w["check"] for w in payload["warnings"]] == ["preflight-scope"]


def test_empty_scope_is_warning(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", scope='{"allow": [], "deny": []}')
    result = run(root)
    assert result.returncode == 0, result.stdout
    assert "[preflight-scope]" in result.stdout
    assert "ERROR:" not in result.stdout


@pytest.mark.parametrize(
    "scope",
    [
        "{not json",
        '["not", "an", "object"]',
        '{"allow": ["/absolute/**"], "deny": []}',
        '{"allow": ["src/**"], "deny": ["../escape"]}',
        '{"allow": "src/**", "deny": []}',
    ],
)
def test_broken_scope_form_is_error(ws: Path, scope: str) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", scope=scope)

    result = run(root)
    assert result.returncode == 1, result.stdout
    payload = report_of(run(root, "--json"))
    assert [e["check"] for e in payload["errors"]] == ["preflight-scope"]
    assert "invalid scope fence" in payload["errors"][0]["message"]


# ---------------------------------------------------------------------------
# E3 -- dod block shape and the id rule (verbatim dod-run:248)
# ---------------------------------------------------------------------------


def test_missing_dod_is_error(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=None)
    result = run(root)
    assert result.returncode == 1
    assert "[preflight-dod]" in result.stdout


@pytest.mark.parametrize(
    "dod_body",
    [
        "{broken json",
        '{"checks": {"x": 1}}',
        '{"checks": []}',
        '{"checks": ["not-an-object"]}',
        '{"checks": [{"id": 1, "cmd": "true"}]}',
        '{"checks": [{"id": "", "cmd": "true"}]}',
        '{"checks": [{"id": "x"}]}',
        '{"checks": [{"id": "x", "cmd": 3}]}',
    ],
)
def test_malformed_dod_is_error(ws: Path, dod_body: str) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=dod_body)

    result = run(root)
    assert result.returncode == 1, result.stdout
    payload = report_of(run(root, "--json"))
    assert [e["check"] for e in payload["errors"]] == ["preflight-dod"]


@pytest.mark.parametrize(
    ("check_id", "ok"),
    [
        ("smoke", True),
        ("a.b", True),  # a dot INSIDE an id is legal (dod-run:248)
        ("a-b_c.d", True),
        (".", False),
        ("..", False),
        ("a/b", False),
        ("a\\b", False),
        ("", False),
    ],
)
def test_id_rule(ws: Path, check_id: str, ok: bool) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=dod((check_id, "true")))

    result = run(root)
    if ok:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "preflight-dod" not in result.stdout
    else:
        assert result.returncode == 1, result.stdout
        assert "[preflight-dod]" in result.stdout


# ---------------------------------------------------------------------------
# E4 -- duplicate dod ids within and across contracts
# ---------------------------------------------------------------------------


def test_duplicate_id_within_contract(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=dod(("smoke", "true"), ("smoke", "false")))

    result = run(root)
    assert result.returncode == 1
    payload = report_of(run(root, "--json"))
    assert [e["check"] for e in payload["errors"]] == ["preflight-dod-duplicate"]
    assert "2 times" in payload["errors"][0]["message"]


def test_duplicate_id_across_contracts(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=dod(("shared", "true")))
    write_spec(root, "beta", dod_body=dod(("shared", "false")))

    result = run(root)
    assert result.returncode == 1
    payload = report_of(run(root, "--json"))
    assert [e["check"] for e in payload["errors"]] == ["preflight-dod-duplicate"]
    message = payload["errors"][0]["message"]
    assert "alpha.md" in message and "beta.md" in message
    assert "verify/shared.json" in message
    assert "P1-10" in message  # namespaced-migration sunset caveat


# ---------------------------------------------------------------------------
# E1 -- --spec selection, resolution and non-contracts
# ---------------------------------------------------------------------------


def test_spec_filter_isolates_contract(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha")
    write_spec(root, "beta", dod_body='{"checks": []}')

    clean = run(root, "--spec", "alpha")
    assert clean.returncode == 0, clean.stdout
    assert "beta" not in clean.stdout

    targeted = run(root, "--spec", "beta")
    assert targeted.returncode == 1
    assert "[preflight-dod]" in targeted.stdout

    by_path = run(root, "--spec", "beta.md")
    assert by_path.returncode == 1

    by_eq = run(root, "--spec=beta")
    assert by_eq.returncode == 1


def test_spec_miss_exit_2_lists_slugs(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha")
    result = run(root, "--spec", "nope")
    assert result.returncode == 2
    assert "available" in result.stderr and "alpha" in result.stderr


def test_non_contract_selection_is_error(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "ROADMAP", status="roadmap", dod_body=None)
    (root / ".slim" / "spec" / "stray.md").write_text("# no status line\n", encoding="utf-8")

    # Default mode: index/undeclared files are simply not part of C.
    default = run(root)
    assert default.returncode == 0, default.stdout

    for selector in ("ROADMAP", "stray"):
        result = run(root, "--spec", selector)
        assert result.returncode == 1, selector
        assert "[preflight-status]" in result.stdout


# ---------------------------------------------------------------------------
# W1 -- single-writer map
# ---------------------------------------------------------------------------


def test_w1_owner_intersections_only_by_default(ws: Path) -> None:
    root = make_project(ws)
    (root / "src" / "beta").mkdir()
    (root / "src" / "beta" / "only.py").write_text("# beta\n", encoding="utf-8")
    (root / "src" / "alpha_only.py").write_text("# alpha\n", encoding="utf-8")
    git(root, "add", "-A")

    write_spec(root, "alpha", scope='{"allow": ["src/**"], "deny": []}', dod_body=dod(("a1", "true")))
    write_spec(root, "beta", scope='{"allow": ["src/beta/**"], "deny": []}', dod_body=dod(("b1", "true")))

    result = run(root)
    assert result.returncode == 0, result.stdout
    assert "WARN: src/beta/only.py: [preflight-owner]" in result.stdout
    assert "src/common.py: [preflight-owner]" not in result.stdout

    payload = report_of(run(root, "--json"))
    assert payload["report"]["owners"] == [
        {"path": "src/beta/only.py", "contracts": ["alpha", "beta"]}
    ]

    everything = report_of(run(root, "--all-owners", "--json"))
    assert [row["path"] for row in everything["report"]["owners"]] == [
        "src/alpha_only.py",
        "src/beta/only.py",
        "src/common.py",
    ]
    assert everything["report"]["owners"][2]["contracts"] == ["alpha"]
    # --all-owners widens the report only; warnings still flag intersections only
    assert [w["check"] for w in everything["warnings"]] == ["preflight-owner"]


# ---------------------------------------------------------------------------
# W2 -- heavy duplicates across contracts, canon semantics
# ---------------------------------------------------------------------------


def test_w2_heavy_duplicate_across_contracts(ws: Path) -> None:
    root = make_project(ws)
    wrapped = (
        "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 nice -n 19 taskset -c 0,1 "
        "ionice -c3 python3 -m pytest tests -q"
    )
    bare = "python -m pytest tests -q"
    write_spec(root, "alpha", dod_body=dod(("a-suite", wrapped)))
    write_spec(root, "beta", dod_body=dod(("b-suite", bare)))

    result = run(root)
    assert result.returncode == 0, result.stdout
    assert "[preflight-heavy-duplicate]" in result.stdout

    payload = report_of(run(root, "--json"))
    assert payload["report"]["heavy_duplicates"] == [
        {
            "canon": "python -m pytest tests -q",
            "kind": "pytest",
            "contracts": ["alpha", "beta"],
            "suggested_owner": "alpha",
        }
    ]


def test_w2_omp_1_and_8_are_different_canons(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=dod(("a-suite", "OMP_NUM_THREADS=1 pytest tests -q")))
    write_spec(root, "beta", dod_body=dod(("b-suite", "OMP_NUM_THREADS=8 pytest tests -q")))

    payload = report_of(run(root, "--json"))
    assert payload["report"]["heavy_duplicates"] == []
    assert "[preflight-heavy-duplicate]" not in run(root).stdout


def test_w2_unknown_env_blocks_grouping(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=dod(("a-suite", "FOO=1 pytest tests -q")))
    write_spec(root, "beta", dod_body=dod(("b-suite", "pytest tests -q")))

    payload = report_of(run(root, "--json"))
    assert payload["report"]["heavy_duplicates"] == []

    # two *different* unknown prefixes are two different canons, too
    root2 = ws / "proj2"
    (root2 / ".slim" / "spec").mkdir(parents=True)
    write_spec(root2, "alpha", dod_body=dod(("a-suite", "FOO=1 pytest tests -q")))
    write_spec(root2, "beta", dod_body=dod(("b-suite", "BAR=1 pytest tests -q")))
    payload2 = report_of(run(root2, "--json"))
    assert payload2["report"]["heavy_duplicates"] == []


# ---------------------------------------------------------------------------
# W3 -- non-canonical command forms
# ---------------------------------------------------------------------------


def test_w3_runner_wrapper_warns(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha", dod_body=dod(("a-suite", "uv run python -m pytest tests -q")))
    result = run(root)
    assert result.returncode == 0, result.stdout
    assert "[preflight-canon]" in result.stdout
    payload = report_of(run(root, "--json"))
    assert [w["check"] for w in payload["warnings"]] == ["preflight-canon"]

    # the bare command is canonical: no warning
    root2 = ws / "proj2"
    (root2 / ".slim" / "spec").mkdir(parents=True)
    write_spec(root2, "alpha", dod_body=dod(("a-suite", "python -m pytest tests -q")))
    assert report_of(run(root2, "--json"))["warnings"] == []


# ---------------------------------------------------------------------------
# Output order, usage errors, snapshot of the read-only contract
# ---------------------------------------------------------------------------


def test_errors_before_warnings_and_sorted(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "b1", dod_body='{"checks": []}')
    write_spec(root, "b2", dod_body="{broken")
    write_spec(root, "c1", scope=None, dod_body=dod(("c1-check", "true")))
    write_spec(root, "c2", scope=None, dod_body=dod(("c2-check", "true")))

    result = run(root)
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    error_positions = [i for i, line in enumerate(lines) if line.startswith("ERROR:")]
    warn_positions = [i for i, line in enumerate(lines) if line.startswith("WARN:")]
    assert error_positions and warn_positions
    assert max(error_positions) < min(warn_positions)

    payload = report_of(run(root, "--json"))
    assert [e["file"] for e in payload["errors"]] == [
        ".slim/spec/b1.md",
        ".slim/spec/b2.md",
    ]
    assert [w["file"] for w in payload["warnings"]] == [
        ".slim/spec/c1.md",
        ".slim/spec/c2.md",
        "src/common.py",  # b1/b2 overlap on src/** -> W1 intersection warning
    ]


def test_usage_errors_exit_2(ws: Path) -> None:
    root = make_project(ws)
    write_spec(root, "alpha")

    assert run(root, "--unknown").returncode == 2
    assert run(root, "--spec").returncode == 2
    assert run(root, "a", "b").returncode == 2
    assert run(root, str(ws / "nowhere")).returncode == 2

    sandbox = ws / "sandbox"
    (sandbox / ".git").mkdir(parents=True)
    missing_root = run(sandbox)
    assert missing_root.returncode == 2
    assert "no project root" in missing_root.stderr
