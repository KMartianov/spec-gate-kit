r"""Behavioral tests for bin/spec-new: scaffolding into a throwaway base dir.

Every fixture lives under pytest's ``tmp_path`` and the scaffold runs with
``--no-git``, so the tests are free of git side effects and never touch
``$HOME/Projects``.  The emitted skeleton is checked against the documented
layout:

$$
\text{target} = \langle\text{base}\rangle/\langle\text{name}\rangle \;\supset\;
\{\texttt{.slim/spec/<slug>.md},\ \texttt{docs/\{tutorials,how-to,reference,explanation,adr\}/},\
\texttt{README.md},\ \texttt{.gitignore}\}
$$

Stdlib + pytest only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]  # config/bin (repo-local, never the live machine)
CLI = BIN / "spec-new"

PLACEHOLDERS = ("<Название задачи>", "<branch-or-path>", "<task_slug>", "YYYY-MM-DD")
DIATAXIS_DIRS = ("docs/tutorials", "docs/how-to", "docs/reference", "docs/explanation")


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_scaffold_creates_the_documented_tree(tmp_path: Path) -> None:
    base = tmp_path / "out"
    result = run(tmp_path, "demo-proj", "--base", str(base), "--no-git")

    assert result.returncode == 0, result.stdout + result.stderr
    target = base / "demo-proj"
    assert target.is_dir()

    spec = target / ".slim" / "spec" / "demo-proj.md"
    assert spec.is_file()
    spec_text = spec.read_text(encoding="utf-8")
    assert "demo-proj" in spec_text
    for placeholder in PLACEHOLDERS:
        assert placeholder not in spec_text, f"unrendered placeholder {placeholder!r}"

    assert (target / "docs" / "adr" / "0000-template.md").is_file()
    assert (target / "docs" / "adr" / "0001-demo-proj.md").is_file()
    for rel in DIATAXIS_DIRS:
        assert (target / rel / "README.md").is_file(), rel

    readme = target / "README.md"
    assert readme.is_file()
    assert ".slim/spec/demo-proj.md" in readme.read_text(encoding="utf-8")
    assert (target / ".gitignore").is_file()
    assert (target / "src").exists() is False  # spec-first: no code is emitted

    # --no-git must leave the scaffold without a repository (the tests never
    # invoke `git init` themselves, so this is a real absence, not a mock).
    assert not (target / ".git").exists()


def test_slug_is_normalized_for_the_spec_name(tmp_path: Path) -> None:
    base = tmp_path / "out"
    result = run(tmp_path, "My_Proj.v1", "--base", str(base), "--no-git")

    assert result.returncode == 0, result.stdout + result.stderr
    # '_' and '.' become '-', the letters are lower-cased; the directory keeps
    # the user-provided name.
    assert (base / "My_Proj.v1" / ".slim" / "spec" / "my-proj-v1.md").is_file()


def test_nonempty_target_is_refused(tmp_path: Path) -> None:
    base = tmp_path / "out"
    target = base / "demo"
    target.mkdir(parents=True)
    (target / "keep.txt").write_text("keep\n", encoding="utf-8")

    result = run(tmp_path, "demo", "--base", str(base), "--no-git")

    assert result.returncode != 0
    assert "not empty" in result.stderr
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (target / ".slim").exists()


def test_help_exits_0(tmp_path: Path) -> None:
    result = run(tmp_path, "--help")

    assert result.returncode == 0
    assert "spec-new" in result.stdout
