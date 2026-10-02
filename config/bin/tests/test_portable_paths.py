"""Portable evidence paths and dual-accept readers (contract §4, Phase 1).

Covers the ``portable-evidence-paths-p0`` contract on throwaway copies only:

(i)   new evidence records carry a root-relative POSIX ``spec`` -- both the
      per-check ``verify/<id>.json`` record and the ``--json`` payload;
(ii)  legacy absolute records are accepted by every dual-accept reader (the
      evidence overwrite guard and the approval lookup
      ``find_valid_approval`` / ``approved_scopes``) without changing the
      verdict, and a relocated clone keeps its evidence valid;
(iii) a foreign record (another ``spec_sha256`` *and* another path) is refused
      with exit 3 and left byte-identical; a non-string/missing ``spec`` with a
      foreign digest is refused the same way;
(iv)  ``spec_scope.norm_spec_path`` is total for absolute, relative, missing,
      empty and non-string values.

Fixtures live under pytest's ``tmp_path`` (throwaway git repositories with
instant ``cmd: "true"`` checks); the live ``~/.local/share/opencode`` stores and
the repository's own ``verify/`` are never touched.  Stdlib + pytest only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]  # config/bin
CLI = BIN / "dod-run"

sys.path.insert(0, str(BIN))
import spec_scope  # noqa: E402

CHECK_ID = "smoke"
REL_SPEC = ".slim/spec/alpha.md"
SCOPE_OK = '{"allow": ["src/**"], "deny": []}'
DOD_OK = '{"checks": [{"id": "smoke", "cmd": "true"}]}'


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


def read_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_evidence(root: Path, record: dict) -> bytes:
    """Plant an evidence file; return the exact bytes written."""
    out = evidence_file(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    before = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out.write_bytes(before)
    return before


def write_approval(
    approvals_dir: Path, root: Path, name: str, spec_field: object, digest: str
) -> None:
    """Write one hand-crafted approval record into an isolated store."""
    record_dir = approvals_dir / spec_scope.root_hash(root)
    record_dir.mkdir(parents=True, exist_ok=True)
    record = {"spec": spec_field, "spec_sha256": digest}
    (record_dir / name).write_text(
        json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def temp_leftovers(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if ".tmp-" in p.name)


# ---------------------------------------------------------------------------
# (i) New evidence is portable
# ---------------------------------------------------------------------------


def test_new_evidence_record_uses_root_relative_spec(project: Path) -> None:
    result = run_dod(project, "--spec", "alpha")

    assert result.returncode == 0, result.stderr
    record = read_record(evidence_file(project))
    assert record["spec"] == REL_SPEC
    assert not Path(record["spec"]).is_absolute()
    assert record["spec_sha256"] == hashlib.sha256(
        (project / REL_SPEC).read_bytes()
    ).hexdigest()


def test_json_payload_uses_root_relative_spec(project: Path) -> None:
    result = run_dod(project, "--spec", "alpha", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["spec"] == REL_SPEC


# ---------------------------------------------------------------------------
# (ii) Dual-accept: legacy absolute records and relocated clones stay valid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("legacy_field", ["abs", "rel"])
def test_stale_own_record_accepted_by_overwrite_guard(
    project: Path, legacy_field: str
) -> None:
    """A stale-digest record pointing at *our* spec -- absolute (legacy) or
    relative (new) -- is still our own evidence and may be overwritten."""
    spec = (project / REL_SPEC).resolve()
    recorded = str(spec) if legacy_field == "abs" else REL_SPEC
    write_evidence(project, {"spec": recorded, "spec_sha256": "0" * 64, "sentinel": True})

    result = run_dod(project, "--spec", "alpha")

    assert result.returncode == 0, result.stderr
    record = read_record(evidence_file(project))
    assert "sentinel" not in record
    assert record["spec"] == REL_SPEC
    assert temp_leftovers(project / "verify") == []


def test_legacy_absolute_record_with_matching_digest_accepted(project: Path) -> None:
    """Byte-identical clone case: the digest branch accepts a legacy record even
    though its absolute path belongs to the original location."""
    spec = (project / REL_SPEC).resolve()
    digest = hashlib.sha256(spec.read_bytes()).hexdigest()
    write_evidence(project, {"spec": str(spec), "spec_sha256": digest, "check": CHECK_ID})

    result = run_dod(project, "--spec", "alpha")

    assert result.returncode == 0, result.stderr
    assert temp_leftovers(project / "verify") == []


def test_relocated_clone_rerun_keeps_verdict(project: Path, tmp_path: Path) -> None:
    """After a copy the relative record anchors at the clone's own root: an
    edited spec (stale digest) is still overwritable -- the portability promise."""
    first = run_dod(project, "--spec", "alpha")
    assert first.returncode == 0, first.stderr

    clone = tmp_path / "clone"
    shutil.copytree(project, clone)
    clone_spec = clone / ".slim" / "spec" / "alpha.md"
    clone_spec.write_text(
        clone_spec.read_text(encoding="utf-8") + "\n<!-- clone edit -->\n",
        encoding="utf-8",
    )

    result = run_dod(clone, "--spec", "alpha")

    assert result.returncode == 0, result.stderr
    record = read_record(evidence_file(clone))
    assert record["spec"] == REL_SPEC
    assert temp_leftovers(clone / "verify") == []


@pytest.mark.parametrize("legacy_field", ["abs", "rel"])
def test_find_valid_approval_dual_accept(
    project: Path, tmp_path: Path, legacy_field: str
) -> None:
    spec = (project / REL_SPEC).resolve()
    digest = hashlib.sha256(spec.read_bytes()).hexdigest()
    recorded = str(spec) if legacy_field == "abs" else REL_SPEC
    store = tmp_path / f"approvals-{legacy_field}"
    write_approval(store, project, "record.json", recorded, digest)

    record_file, record = spec_scope.find_valid_approval(project, spec, store)

    assert record_file is not None
    assert record is not None
    assert record["spec"] == recorded


@pytest.mark.parametrize("legacy_field", ["abs", "rel"])
def test_approved_scopes_dual_accept(
    project: Path, tmp_path: Path, legacy_field: str
) -> None:
    spec = (project / REL_SPEC).resolve()
    digest = hashlib.sha256(spec.read_bytes()).hexdigest()
    recorded = str(spec) if legacy_field == "abs" else REL_SPEC
    store = tmp_path / f"approvals-{legacy_field}"
    write_approval(store, project, "record.json", recorded, digest)

    entries = spec_scope.approved_scopes(project, store)

    assert [entry[0].name for entry in entries] == ["alpha.md"]
    scope = entries[0][1]
    assert scope is not None
    assert scope.allow == ("src/**",)


# ---------------------------------------------------------------------------
# (iii) Foreign evidence stays refused and untouched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("foreign_field", ["abs", "rel", "nonstr", "missing"])
def test_foreign_record_refused_and_untouched(project: Path, foreign_field: str) -> None:
    make_spec(project, "beta")
    beta = (project / ".slim" / "spec" / "beta.md").resolve()
    record: dict = {
        "check": CHECK_ID,
        "cmd": "true",
        "exit_code": 0,
        "spec_sha256": "f" * 64,
    }
    if foreign_field == "abs":
        record["spec"] = str(beta)
    elif foreign_field == "rel":
        record["spec"] = ".slim/spec/beta.md"
    elif foreign_field == "nonstr":
        record["spec"] = 123
    # "missing": no ``spec`` key at all
    before = write_evidence(project, record)

    result = run_dod(project, "--spec", "alpha")

    assert result.returncode == 3, result.stderr
    assert evidence_file(project).read_bytes() == before
    assert "another spec" in result.stderr
    assert temp_leftovers(project / "verify") == []


# ---------------------------------------------------------------------------
# (iv) norm_spec_path / spec_rel are total
# ---------------------------------------------------------------------------


def test_norm_spec_path_absolute_relative_and_missing(project: Path) -> None:
    root = project.resolve()
    spec = (project / REL_SPEC).resolve()
    ghost = (root / ".slim" / "spec" / "ghost.md").resolve()

    assert spec_scope.norm_spec_path(root, str(spec)) == spec
    assert spec_scope.norm_spec_path(root, REL_SPEC) == spec
    assert spec_scope.norm_spec_path(root, str(ghost)) == ghost
    assert spec_scope.norm_spec_path(root, ".slim/spec/ghost.md") == ghost


def test_norm_spec_path_fails_closed_for_bad_values(project: Path) -> None:
    root = project.resolve()
    spec = (project / REL_SPEC).resolve()

    for bad in (None, 123, [], {}, ""):
        normalized = spec_scope.norm_spec_path(root, bad)
        assert normalized == root  # the root sentinel...
        assert normalized != spec  # ...can never equal a spec file

    # An embedded NUL raises ValueError in pathlib; the normalizer swallows it.
    assert spec_scope.norm_spec_path(root, "a\x00b") == root
    # An unresolvable ``~user`` raises RuntimeError; also swallowed.
    assert spec_scope.norm_spec_path(root, "~definitely_no_such_user_zz/x.md") == root


def test_spec_rel_relative_and_outside_fallback(project: Path) -> None:
    root = project.resolve()
    spec = (project / REL_SPEC).resolve()
    outside = Path("/somewhere/else/alpha.md")

    assert spec_scope.spec_rel(root, spec) == REL_SPEC
    assert spec_scope.spec_rel(root, outside) == str(outside)


# ---------------------------------------------------------------------------
# (v) check_portability paths: active evidence is fatal, inactive is a note
# ---------------------------------------------------------------------------

PORTABILITY = Path(__file__).resolve().parents[2] / "tools" / "gov" / "check_portability.py"
# Assembled from fragments: this test file lives under config/** and is itself
# text-scanned by the checker, so the literal must not appear verbatim.
HOME_LITERAL = "/home/asd" + "cxfrt"


def _portable_repo(tmp_path: Path) -> Path:
    """A throwaway REPO_ROOT whose own path contains the author-home literal.

    The checker derives REPO_ROOT from its ``__file__``; copying it under a
    ``home/<user>/proj/config/tools/gov/`` subtree makes every absolute spec
    path in this tree contain ``HOME_LITERAL`` naturally.
    """
    root = tmp_path / "home" / "asdcxfrt" / "proj"
    checker = root / "config" / "tools" / "gov" / "check_portability.py"
    checker.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PORTABILITY, checker)
    spec_dir = root / ".slim" / "spec"
    (spec_dir / "archive").mkdir(parents=True, exist_ok=True)
    (spec_dir / "active.md").write_text("# active\n", encoding="utf-8")
    (spec_dir / "archive" / "old.md").write_text("# old\n", encoding="utf-8")
    return root


def _run_paths(root: Path) -> subprocess.CompletedProcess[str]:
    checker = root / "config" / "tools" / "gov" / "check_portability.py"
    return subprocess.run(
        [sys.executable, str(checker), "paths"],
        capture_output=True,
        text=True,
    )


def test_paths_active_evidence_fatal_inactive_evidence_note(tmp_path: Path) -> None:
    root = _portable_repo(tmp_path)
    spec_dir = root / ".slim" / "spec"
    active_spec = str(spec_dir / "active.md")  # exists directly in .slim/spec
    old_spec = str(spec_dir / "old.md")  # archived -> no longer exists here
    assert HOME_LITERAL in active_spec
    assert HOME_LITERAL in old_spec

    verify = root / "verify"
    verify.mkdir(parents=True, exist_ok=True)
    for name, recorded in (("active-x.json", active_spec), ("old-y.json", old_spec)):
        (verify / name).write_text(
            json.dumps({"spec": recorded, "spec_sha256": "0" * 64}) + "\n",
            encoding="utf-8",
        )

    # The active record is a hard violation; the archived one is only a note.
    result = _run_paths(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "verify/active-x.json [active-evidence]" in result.stdout
    assert "note: verify/old-y.json [evidence-inactive]" in result.stdout

    # Removing the active record leaves only the archived one: rc=0, note only.
    (verify / "active-x.json").unlink()
    result = _run_paths(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "note: verify/old-y.json [evidence-inactive]" in result.stdout
    assert "[active-evidence]" not in result.stdout
