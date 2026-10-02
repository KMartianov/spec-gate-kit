r"""Behavioral tests for bin/gate-off and bin/gate-on: the project-local marker.

Both tools only create/remove ``<root>/.slim/GATE-OFF``; the *consumption* of
that marker by the plugin is covered by the TypeScript harness
(``plugins/__tests__/spec-gate.test.ts``, test 9).  Here the contract under
test is:

$$
\texttt{gate-off}:\ \text{find\_root}(p)=\varnothing \Rightarrow \text{error},
\qquad
\texttt{gate-off}(p)=\varnothing \Rightarrow
\texttt{root}/.slim/\texttt{GATE-OFF} \ni \text{``disabled by human at''}
$$

and ``gate-on`` is the exact inverse (idempotent on an already-active gate).
Every fixture lives under pytest's ``tmp_path``.  Stdlib + pytest only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]  # config/bin (repo-local, never the live machine)
GATE_OFF = BIN / "gate-off"
GATE_ON = BIN / "gate-on"


def run(tool: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tool), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def make_project(tmp_path: Path, name: str = "proj") -> Path:
    """A throwaway gated project: ``.slim/spec`` plus a real ``.git`` boundary."""
    root = tmp_path / name
    (root / ".slim" / "spec").mkdir(parents=True)
    (root / "src").mkdir()
    subprocess.run(
        ["git", "-C", str(root), "init", "-q"],
        check=True,
        capture_output=True,
        text=True,
    )
    return root


# ---------------------------------------------------------------------------
# Marker lifecycle
# ---------------------------------------------------------------------------


def test_gate_off_creates_marker_and_gate_on_removes_it(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    marker = root / ".slim" / "GATE-OFF"

    off = run(GATE_OFF, root)
    assert off.returncode == 0, off.stderr
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").startswith("disabled by human at ")
    assert "no longer gated" in off.stdout

    on = run(GATE_ON, root)
    assert on.returncode == 0, on.stderr
    assert not marker.exists()
    assert "removed" in on.stdout and str(marker) in on.stdout

    # Idempotent: an already-active gate is a no-op with exit 0.
    again = run(GATE_ON, root)
    assert again.returncode == 0, again.stderr
    assert not marker.exists()
    assert "already active" in again.stdout


def test_gate_off_from_subdirectory_finds_the_root(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    sub = root / "src"

    result = run(GATE_OFF, sub)

    assert result.returncode == 0, result.stderr
    assert (root / ".slim" / "GATE-OFF").is_file()


def test_gate_off_accepts_an_explicit_path(tmp_path: Path) -> None:
    root = make_project(tmp_path)

    result = run(GATE_OFF, tmp_path, str(root))

    assert result.returncode == 0, result.stderr
    assert (root / ".slim" / "GATE-OFF").is_file()


# ---------------------------------------------------------------------------
# Refusals outside a gated project: nothing may be created
# ---------------------------------------------------------------------------


def test_gate_off_refuses_outside_a_project(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / ".git").mkdir()  # a git boundary without .slim/spec

    result = run(GATE_OFF, sandbox)

    assert result.returncode != 0
    assert "no project root" in result.stderr
    assert not (sandbox / ".slim").exists()


def test_gate_on_refuses_outside_a_project(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / ".git").mkdir()

    result = run(GATE_ON, sandbox)

    assert result.returncode != 0
    assert "no project root" in result.stderr


def test_help_exits_0_for_both_tools(tmp_path: Path) -> None:
    for tool in (GATE_OFF, GATE_ON):
        result = run(tool, tmp_path, "--help")
        assert result.returncode == 0, tool
        assert tool.name in result.stdout
