"""Tests for config/bin/wave-run, driving the CLI as a subprocess.

Fixtures live under ``/tmp/opencode`` (``tempfile.mkdtemp``); each invocation
gets ``HOME`` pointed at a throwaway approvals store inside the fixture, so the
real ``~/.local/share/opencode`` is never read or written.  ``--execute`` is
exercised against a fake ``dod-run`` placed first on ``$PATH``.  Stdlib only
apart from pytest.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]
CLI = BIN / "wave-run"
sys.path.insert(0, str(BIN))
import spec_scope  # noqa: E402

SCOPE_OK = '{"allow": ["src/**"], "deny": []}'
STAMP = "2026-01-01T00:00:00+00:00"


def dod(*checks: tuple[str, str]) -> str:
    return json.dumps({"checks": [{"id": cid, "cmd": cmd} for cid, cmd in checks]})


#: A stand-in for bin/dod-run: writes evidence v2 for the requested --only id,
#: echoes the timeout into ``tail``, and honours two failure switches.
FAKE_DOD_RUN = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]


def opt(name, default=None):
    if name in args:
        return args[args.index(name) + 1]
    return default


spec = Path(opt("--spec")).resolve()
check_id = opt("--only")
timeout = opt("--timeout", "900")
root = spec.parents[2]
if os.environ.get("FAKE_DOD_FAIL") == "1":
    print("fake dod-run: injected failure", file=sys.stderr)
    sys.exit(3)
exit_code = int(os.environ.get("FAKE_DOD_EXIT", "0"))
out = root / "verify" / (check_id + ".json")
out.parent.mkdir(parents=True, exist_ok=True)
record = {
    "check": check_id,
    "cmd": "fake executed cmd",
    "exit_code": exit_code,
    "started_at": "2026-01-01T00:00:00+00:00",
    "finished_at": "2026-01-01T00:00:01+00:00",
    "duration_s": 1.234,
    "spec": str(spec),
    "spec_sha256": "f" * 64,
    "tail": "fake tail timeout=" + str(timeout),
    "git_head": None,
    "tree_dirty": False,
    "scope_sha256": "e" * 64,
}
out.write_text(json.dumps(record) + "\n", encoding="utf-8")
print(check_id + ": exit=" + str(exit_code) + " -> verify/" + check_id + ".json")
sys.exit(exit_code)
'''


@pytest.fixture
def ws() -> Path:
    base = Path(tempfile.mkdtemp(dir="/tmp/opencode", prefix="wave-run-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def make_project(ws: Path) -> Path:
    """A gated project root; ``src/common.py`` is tracked so scope digests exist."""
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
    scope: str | None = SCOPE_OK,
    dod_body: str | None = None,
) -> Path:
    lines = [f"# spec {slug}", "", "- **Статус спецификации:** `draft`", ""]
    if scope is not None:
        lines += ["```scope", scope, "```", ""]
    if dod_body is not None:
        lines += ["```dod", dod_body, "```", ""]
    path = root / ".slim" / "spec" / f"{slug}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def approve(root: Path, ws: Path, spec: Path) -> Path:
    """Flip a spec to approved and write its matching hand-crafted record."""
    text = spec.read_text(encoding="utf-8")
    text = text.replace("`draft`", "`approved`", 1)
    text = text.replace(
        "\n\n```scope", f"\n- **Утверждено:** {STAMP} (human)\n\n```scope", 1
    )
    spec.write_text(text, encoding="utf-8")

    record = {
        "root": str(root.resolve()),
        "spec": str(spec.resolve()),
        "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
        "task": spec.stem,
        "approved_by": "human",
        "approved_at": STAMP,
    }
    rec_dir = ws / "home" / ".local" / "share" / "opencode" / "approvals" / spec_scope.root_hash(root.resolve())
    rec_dir.mkdir(parents=True, exist_ok=True)
    rec_file = rec_dir / f"{spec.stem}.json"
    rec_file.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec_file


def install_fake_dod_run(ws: Path) -> Path:
    fakebin = ws / "fakebin"
    fakebin.mkdir(exist_ok=True)
    path = fakebin / "dod-run"
    path.write_text(FAKE_DOD_RUN, encoding="utf-8")
    path.chmod(0o755)
    return fakebin


def cli_env(ws: Path, fakebin: Path | None = None, **extra: str) -> dict[str, str]:
    (ws / "home").mkdir(exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(ws / "home")
    if fakebin is not None:
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
    env.update(extra)
    return env


def run(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def snapshot(root: Path) -> dict[str, bytes | str]:
    out: dict[str, bytes | str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        out[rel] = "<dir>" if path.is_dir() else path.read_bytes()
    return out


# ---------------------------------------------------------------------------
# Dry run is the default and writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_default_writes_nothing(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws, install_fake_dod_run(ws))
    alpha = write_spec(root, "alpha", dod_body=dod(("a1", "python -m pytest tests -q")))
    beta = write_spec(
        root, "beta", dod_body=dod(("b1", "nice -n 19 nice -n 5 python -m pytest tests -q"))
    )
    approve(root, ws, alpha)
    approve(root, ws, beta)
    before = snapshot(ws)

    result = run(root, env, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["warnings"] == []
    assert payload["results"] == []
    assert len(payload["plan"]) == 1
    group = payload["plan"][0]
    assert group["canon"] == "python -m pytest tests -q"
    assert group["kind"] == "pytest"
    assert group["heavy"] is True
    assert group["group_size"] == 2
    assert [member["slug"] for member in group["members"]] == ["alpha", "beta"]
    assert group["representative"]["slug"] == "alpha"
    assert group["representative"]["id"] == "a1"

    assert not (root / "verify").exists()
    assert snapshot(ws) == before


# ---------------------------------------------------------------------------
# --execute: delegation to dod-run plus evidence fan-out
# ---------------------------------------------------------------------------


def test_execute_writes_member_evidence_with_provenance(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws, install_fake_dod_run(ws))
    alpha_cmd = "OMP_NUM_THREADS=1 nice -n 19 taskset -c 0,1 ionice -c3 python3 -m pytest tests -q"
    beta_cmd = "python -m pytest tests -q"
    alpha = write_spec(root, "alpha", dod_body=dod(("a1", alpha_cmd)))
    beta = write_spec(root, "beta", dod_body=dod(("b1", beta_cmd)))
    approve(root, ws, alpha)
    approve(root, ws, beta)

    result = run(root, env, "--execute", "--json", "--timeout", "42")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "execute"
    assert payload["wave_id"].startswith("wave-")
    assert len(payload["results"]) == 1
    assert payload["results"][0]["exit_code"] == 0
    assert payload["results"][0]["evidence_fresh"] is True
    assert "verify/b1.json" in payload["results"][0]["members_written"]

    # the representative keeps the plain dod-run evidence (no provenance keys)
    representative = json.loads((root / "verify" / "a1.json").read_text(encoding="utf-8"))
    assert representative["check"] == "a1"
    assert "via" not in representative

    member = json.loads((root / "verify" / "b1.json").read_text(encoding="utf-8"))
    beta_text = beta.read_text(encoding="utf-8")
    assert member["check"] == "b1"
    assert member["cmd"] == beta_cmd
    # common fields copied verbatim from the representative's run
    assert member["exit_code"] == 0
    assert member["started_at"] == "2026-01-01T00:00:00+00:00"
    assert member["finished_at"] == "2026-01-01T00:00:01+00:00"
    assert member["duration_s"] == 1.234
    assert member["tail"] == "fake tail timeout=42"
    assert member["git_head"] is None
    assert member["tree_dirty"] is False
    # the member's own identity
    assert member["spec"] == str(beta.resolve())
    assert member["spec_sha256"] == hashlib.sha256(beta.read_bytes()).hexdigest()
    assert member["scope_sha256"] == spec_scope.scope_digest(
        root, spec_scope.parse_scope(beta_text)
    )
    # provenance is explicit about the substitution
    assert member["via"] == "wave-run"
    assert member["wave_id"] == payload["wave_id"]
    assert member["canon"] == "python -m pytest tests -q"
    assert member["executed_cmd"] == alpha_cmd
    assert member["executed_spec"] == str(alpha.resolve())
    assert member["representative_id"] == "a1"


def test_execute_injected_dod_run_failure_writes_no_member_evidence(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws, install_fake_dod_run(ws), FAKE_DOD_FAIL="1")
    alpha = write_spec(root, "alpha", dod_body=dod(("a1", "python -m pytest tests -q")))
    beta = write_spec(root, "beta", dod_body=dod(("b1", "python -m pytest tests -q")))
    approve(root, ws, alpha)
    approve(root, ws, beta)

    result = run(root, env, "--execute", "--json")
    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["results"][0]["evidence_fresh"] is False
    assert payload["results"][0]["exit_code"] is None
    assert payload["results"][0]["members_written"] == []
    assert payload["results"][0]["errors"]
    assert not (root / "verify").exists()


def test_execute_failing_check_copies_exit_code(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws, install_fake_dod_run(ws), FAKE_DOD_EXIT="1")
    alpha = write_spec(root, "alpha", dod_body=dod(("a1", "python -m pytest tests -q")))
    beta = write_spec(root, "beta", dod_body=dod(("b1", "python -m pytest tests -q")))
    approve(root, ws, alpha)
    approve(root, ws, beta)

    result = run(root, env, "--execute", "--json")
    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["results"][0]["exit_code"] == 1
    member = json.loads((root / "verify" / "b1.json").read_text(encoding="utf-8"))
    assert member["exit_code"] == 1  # the failure is copied, not laundered


# ---------------------------------------------------------------------------
# Canonical grouping
# ---------------------------------------------------------------------------


def test_grouping_canon_omp_and_unknown_env(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    specs = {
        "alpha": ("a-suite", "OMP_NUM_THREADS=1 nice -n 19 taskset -c 0,1 ionice -c3 python3 -m pytest tests -q"),
        "beta": ("b-suite", "python -m pytest tests -q"),
        "gamma": ("g-suite", "OMP_NUM_THREADS=8 python -m pytest tests -q"),
        "delta": ("d-suite", "FOO=1 python -m pytest tests -q"),
    }
    for slug, (check_id, cmd) in specs.items():
        approve(root, ws, write_spec(root, slug, dod_body=dod((check_id, cmd))))

    payload = json.loads(run(root, env, "--json").stdout)
    groups = {group["canon"]: group for group in payload["plan"]}
    assert set(groups) == {
        "python -m pytest tests -q",
        "OMP_NUM_THREADS=8 python -m pytest tests -q",
        "FOO=1 python -m pytest tests -q",
    }
    assert [member["slug"] for member in groups["python -m pytest tests -q"]["members"]] == [
        "alpha",
        "beta",
    ]
    assert groups["OMP_NUM_THREADS=8 python -m pytest tests -q"]["group_size"] == 1
    assert groups["FOO=1 python -m pytest tests -q"]["group_size"] == 1


def test_representative_is_min_slug_then_id(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    # same canonical command in two contracts: min slug wins over smaller id
    alpha = write_spec(root, "alpha", dod_body=dod(("z9", "pytest tests -q")))
    beta = write_spec(root, "beta", dod_body=dod(("a1", "pytest tests -q")))
    # same canonical command twice inside one contract: min id wins
    gamma = write_spec(
        root, "gamma", dod_body=dod(("b2", "ctest --test-dir build -j1"), ("a1", "ctest --test-dir build -j1"))
    )
    for spec in (alpha, beta, gamma):
        approve(root, ws, spec)

    payload = json.loads(run(root, env, "--json").stdout)
    groups = {group["canon"]: group for group in payload["plan"]}
    assert groups["pytest tests -q"]["representative"]["slug"] == "alpha"
    assert groups["pytest tests -q"]["representative"]["id"] == "z9"
    assert groups["ctest --test-dir build -j1"]["representative"]["id"] == "a1"
    assert groups["ctest --test-dir build -j1"]["group_size"] == 2


def test_plan_is_deterministic(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    for slug, cmd in (
        ("alpha", "pytest tests -q"),
        ("beta", "ctest --test-dir build -j1"),
        ("gamma", "ruff check ."),
    ):
        approve(root, ws, write_spec(root, slug, dod_body=dod(("run", cmd))))

    first = run(root, env, "--json")
    second = run(root, env, "--json")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


# ---------------------------------------------------------------------------
# Approval gate, --spec/--only filters, resolution and usage errors
# ---------------------------------------------------------------------------


def test_unapproved_contract_excluded_with_warning(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws, install_fake_dod_run(ws))
    alpha = write_spec(root, "alpha", dod_body=dod(("a1", "pytest tests -q")))
    write_spec(root, "beta", dod_body=dod(("b1", "pytest tests -q")))
    approve(root, ws, alpha)

    human = run(root, env)
    assert human.returncode == 0, human.stdout
    assert "WARN: .slim/spec/beta.md: [wave-unapproved]" in human.stdout
    plan_part = human.stdout.split("plan:", 1)[1]
    assert "alpha#a1" in plan_part
    assert "beta" not in plan_part

    payload = json.loads(run(root, env, "--execute", "--json").stdout)
    assert len(payload["plan"]) == 1
    assert payload["warnings"] == [
        {
            "file": ".slim/spec/beta.md",
            "check": "wave-unapproved",
            "message": payload["warnings"][0]["message"],
        }
    ]
    assert payload["results"][0]["exit_code"] == 0
    assert not (root / "verify" / "b1.json").exists()

    # explicitly selecting the unapproved contract plans nothing and runs nothing
    selected = run(root, env, "--spec", "beta", "--json")
    assert selected.returncode == 0
    selected_payload = json.loads(selected.stdout)
    assert selected_payload["plan"] == []
    assert [w["check"] for w in selected_payload["warnings"]] == ["wave-unapproved"]


def test_only_filter(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    alpha = write_spec(root, "alpha", dod_body=dod(("a1", "pytest one -q"), ("a2", "pytest two -q")))
    beta = write_spec(root, "beta", dod_body=dod(("b1", "pytest two -q")))
    approve(root, ws, alpha)
    approve(root, ws, beta)

    payload = json.loads(run(root, env, "--only", "a2", "--only=b1", "--json").stdout)
    assert len(payload["plan"]) == 1
    group = payload["plan"][0]
    assert group["canon"] == "pytest two -q"
    assert group["representative"]["slug"] == "alpha"
    assert group["representative"]["id"] == "a2"
    assert [member["id"] for member in group["members"]] == ["a2", "b1"]

    single = json.loads(run(root, env, "--only=a1", "--json").stdout)
    assert [group["group_size"] for group in single["plan"]] == [1]

    unknown = run(root, env, "--only", "nope")
    assert unknown.returncode == 2
    assert "no such check id" in unknown.stderr


def test_spec_filter_slug_and_path(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    alpha = write_spec(root, "alpha", dod_body=dod(("a1", "pytest one -q")))
    beta = write_spec(root, "beta", dod_body=dod(("b1", "pytest two -q")))
    approve(root, ws, alpha)
    approve(root, ws, beta)

    for selector in ("beta", "beta.md"):
        payload = json.loads(run(root, env, "--spec", selector, "--json").stdout)
        assert [group["representative"]["slug"] for group in payload["plan"]] == ["beta"]

    missing = run(root, env, "--spec", "nope")
    assert missing.returncode == 2
    assert "available" in missing.stderr and "alpha" in missing.stderr


def test_missing_dod_refuses_to_plan(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    alpha = write_spec(root, "alpha", dod_body=None)
    approve(root, ws, alpha)

    result = run(root, env, "--json")
    assert result.returncode == 2
    assert "dod" in result.stderr


def test_no_contracts_plan_empty(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    payload = json.loads(run(root, env, "--json").stdout)
    assert payload["plan"] == []
    assert payload["warnings"] == []


def test_usage_errors_exit_2(ws: Path) -> None:
    root = make_project(ws)
    env = cli_env(ws)
    assert run(root, env, "--unknown").returncode == 2
    assert run(root, env, "--spec").returncode == 2
    assert run(root, env, "--timeout", "abc").returncode == 2
    assert run(root, env, "--timeout", "0").returncode == 2
    assert run(root, env, "a", "b").returncode == 2

    sandbox = ws / "sandbox"
    (sandbox / ".git").mkdir(parents=True)
    missing_root = run(sandbox, env)
    assert missing_root.returncode == 2
    assert "no project root" in missing_root.stderr


def test_help_exit_0(ws: Path) -> None:
    result = run(ws, cli_env(ws), "--help")
    assert result.returncode == 0
    assert "wave-run" in result.stdout
