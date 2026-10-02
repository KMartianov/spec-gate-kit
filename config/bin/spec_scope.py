#!/usr/bin/env python3
"""Shared scope/classification semantics for the Doc-Driven governance tools.

Single source of truth for the governance primitives used by ``bin/spec-status``,
``bin/dod-run`` and ``bin/docs-lint``.  The TypeScript mirror of the hot path
lives in ``plugins/spec-gate.ts``; both implementations are pinned to the common
vectors in ``config/tools/gov/scope_vectors.json`` (glob semantics, scope composition,
file classification).

Public surface (see the approved spec §3.8):

    parse_fences      -- fenced block bodies keyed by info string
    parse_scope       -- the ``scope`` fence (GOV-1), fail-closed
    glob_match        -- normative glob semantics (§3.2.2)
    scope_allows      -- allow/deny composition for one relative path
    active_specs      -- contracts directly in ``<root>/.slim/spec`` (GOV-3/7)
    is_active_spec    -- strict location predicate (GOV-3)
    INDEX_TOKENS      -- reserved status tokens ``{roadmap, index}`` (GOV-7)
    declared_token    -- status-line token or ``None``
    classify          -- ``spec`` | ``index`` | ``undeclared`` (fail-closed)
    specs_and_indexes -- (contracts, indexes, undeclared) split
    tracked_files     -- ``git ls-files`` relative POSIX paths
    scope_digest      -- digest of tracked files covered by a scope (GOV-4)
    approved_scopes   -- active valid contracts with their mandate (GOV-1/3/7)

Extra helpers used by the tools and the harness: ``scope_report``,
``find_valid_approval``, ``git_head``, ``tree_dirty``, ``worktree_snapshot``,
``dod_check_ids`` (tolerant ``dod`` id parser), ``norm_spec_path`` and
``spec_rel`` (portable, dual-accept spec-path provenance), ``canon_command``
(shell-string canonicalisation for duplicate detection), ``command_kind`` and
``is_heavy_command`` (command classification for the preflight/wave tools).

Filesystem helpers shared by the CLI writers: ``find_root`` (nearest project
root), ``slugify`` (a spec's stable slug) and ``atomic_write`` (same-directory
temp + ``os.replace``).

READ-ONLY by default: no governance *reader* writes to disk.  ``atomic_write`` is
the only writer in this module and it touches the filesystem only when a caller
explicitly invokes it.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
APPROVALS_DIR = HOME / ".local" / "share" / "opencode" / "approvals"
SPEC_REL = Path(".slim") / "spec"
VERIFY_REL = Path("verify")

#: Reserved status tokens: a file declaring one of these is an index, not a
#: contract (GOV-7).  The set is closed; it grows only with a new spec.
INDEX_TOKENS = frozenset({"roadmap", "index"})

#: The status line is the class marker (the same line spec-approve relies on).
STATUS_RE = re.compile(
    r"^[ \t]*-[ \t]*\*\*Статус спецификации:\*\*[ \t]*(.*)$",
    re.MULTILINE,
)

_FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*(.*)$")
_FENCE_CLOSE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*$")


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def root_hash(root: Path) -> str:
    """Approval-directory key for a project root (same rule as the plugin)."""
    return sha256_hex(str(root).encode("utf-8"))[:16]


def now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Root discovery, slugs, atomic writes (shared by the CLI writers)
# ---------------------------------------------------------------------------


def find_root(start: Path) -> Path | None:
    """Nearest ancestor holding ``.slim/spec``; bounded by .git, $HOME and /.

    The walk starts at ``start`` itself when it is an existing directory (else
    at its parent), stops at a ``.git`` boundary, at ``$HOME`` and at the
    filesystem root.  Returns ``None`` when no bounded ancestor holds
    ``.slim/spec``.
    """
    directory = start if start.is_dir() else start.parent
    while True:
        if (directory / SPEC_REL).is_dir():
            return directory
        if (directory / ".git").exists():
            return None
        if directory == HOME or directory == directory.parent:
            return None
        directory = directory.parent


def slugify(spec: Path) -> str:
    """Stable slug for a spec path: lower ASCII alnum, runs collapse to ``-``.

    The stem is lower-cased; ASCII alphanumeric characters are kept, every other
    run becomes a single ``-``; leading/trailing dashes are stripped and the
    result is truncated to 64 characters.  Falls back to ``"spec"`` when empty.
    """
    base = spec.stem  # basename without the ".md" suffix
    out: list[str] = []
    prev_dash = False
    for ch in base.lower():
        if ch.isascii() and ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif out and not prev_dash:
            out.append("-")
            prev_dash = True
    slug = "".join(out).strip("-")[:64]
    return slug or "spec"


def atomic_write(target: Path, payload: bytes) -> None:
    """Write ``payload`` to ``target`` via a same-directory temp + os.replace.

    ``<name>.tmp-<pid>`` lives next to ``target`` so the replace is atomic on the
    same filesystem.  On any failure the temp file is removed and the original
    ``OSError`` propagates -- the caller decides how to report it.
    """
    tmp = target.with_name(target.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Portable spec paths (dual-accept evidence/approval provenance)
# ---------------------------------------------------------------------------


def norm_spec_path(root: Path, recorded: object) -> Path:
    """Resolve a recorded spec path: legacy absolute or root-relative.

    A relative ``recorded`` path is anchored at ``root``, so a cloned tree
    resolves its recorded ``.slim/spec/<name>.md`` against its own root.  The
    input may be any JSON value: a non-string, empty or unresolvable value
    normalizes to the resolved ``root`` directory, which can never equal a spec
    *file*, so callers fail closed instead of raising.
    """
    if isinstance(recorded, str) and recorded:
        try:
            candidate = Path(recorded).expanduser()
            if not candidate.is_absolute():
                candidate = root / candidate
            return candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            pass
    try:
        return root.resolve()
    except (OSError, RuntimeError):
        return root


def spec_rel(root: Path, spec: Path) -> str:
    """Root-relative POSIX path of a spec (e.g. ``.slim/spec/<name>.md``).

    ``root`` and ``spec`` are expected to be resolved paths (all callers pass
    resolved values); a spec outside ``root`` falls back to its absolute string
    so the helper stays total.
    """
    try:
        return spec.relative_to(root).as_posix()
    except ValueError:
        return str(spec)


# ---------------------------------------------------------------------------
# Fenced blocks
# ---------------------------------------------------------------------------


def parse_fences(text: str) -> dict[str, str]:
    """Map info string -> body for every fenced block; first occurrence wins.

    The algorithm matches the existing ``dod`` extraction: an opener is
    ``{3,}``/``~{3,}``, the info string is compared after ``strip()`` and the
    closer must use the same fence character and be at least as long.
    """
    result: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opener = _FENCE_OPEN_RE.match(lines[index])
        if not opener:
            index += 1
            continue
        fence = opener.group(1)
        info = opener.group(2).strip()
        body: list[str] = []
        cursor = index + 1
        closed = False
        while cursor < len(lines):
            closer = _FENCE_CLOSE_RE.match(lines[cursor])
            if closer and closer.group(1)[0] == fence[0] and len(closer.group(1)) >= len(fence):
                closed = True
                break
            body.append(lines[cursor])
            cursor += 1
        if info and info not in result:
            result[info] = "\n".join(body)
        index = cursor + 1 if closed else cursor
    return result


# ---------------------------------------------------------------------------
# scope fence (GOV-1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """Validated write-mandate: allow/deny glob patterns, both may be empty."""

    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeReport:
    """Parsing outcome of the ``scope`` fence, for the gate and for docs-lint."""

    present: bool = False
    scope: Scope | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _pattern_error(pattern: object) -> str | None:
    """Return a validation error for one glob pattern, else None."""
    if not isinstance(pattern, str):
        return "pattern is not a string"
    if pattern == "":
        return "empty pattern"
    if pattern.startswith("/"):
        return f"absolute pattern not allowed: {pattern!r}"
    if "~" in pattern:
        return f"pattern must not contain '~': {pattern!r}"
    if "\\" in pattern:
        return f"pattern must not contain backslashes: {pattern!r}"
    if any(segment == ".." for segment in pattern.split("/")):
        return f"pattern must not contain '..' segments: {pattern!r}"
    # A character class must not contain the path separator (the domain of the
    # match is a POSIX-relative path; a class spanning '/' is ambiguous).
    in_class = False
    for char in pattern:
        if not in_class:
            in_class = char == "["
        elif char == "]":
            in_class = False
        elif char == "/":
            return f"'/' is not allowed inside a character class: {pattern!r}"
    return None


def _scope_list(body: object, key: str) -> tuple[list[str], list[str]]:
    """Validate one allow/deny list; return (patterns, messages)."""
    if body is None:
        return [], [f"missing required key {key!r} (treated as an empty list)"]
    if not isinstance(body, list):
        return [], [f"{key!r} must be a list of glob strings"]
    patterns: list[str] = []
    messages: list[str] = []
    for item in body:
        error = _pattern_error(item)
        if error is not None:
            messages.append(f"{key}: {error}")
        else:
            patterns.append(item)
    return patterns, messages


def scope_report(text: str) -> ScopeReport:
    """Parse the first fence whose info string is exactly ``scope``.

    Fail-closed: any JSON/type/pattern problem makes the mandate absent
    (``scope is None``) while the problems are reported for ``docs-lint``.
    A missing key or an empty ``allow`` is a warning, not an error.
    """
    body = parse_fences(text).get("scope")
    if body is None:
        return ScopeReport(present=False)
    warnings: list[str] = []
    errors: list[str] = []
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        return ScopeReport(present=True, scope=None, errors=(f"invalid JSON: {exc}",))
    if not isinstance(data, dict):
        return ScopeReport(present=True, scope=None, errors=("scope body must be a JSON object",))
    allow, allow_messages = _scope_list(data.get("allow"), "allow")
    deny, deny_messages = _scope_list(data.get("deny"), "deny")
    for message in allow_messages + deny_messages:
        if message.startswith("missing required key"):
            warnings.append(message)
        else:
            errors.append(message)
    for key in sorted(data):
        if key not in ("allow", "deny"):
            warnings.append(f"unknown key {key!r} is ignored")
    if not allow and not errors:
        warnings.append("empty 'allow': the fence grants nothing (no mandate)")
    if errors:
        return ScopeReport(present=True, scope=None, errors=tuple(errors), warnings=tuple(warnings))
    return ScopeReport(present=True, scope=Scope(tuple(allow), tuple(deny)), warnings=tuple(warnings))


def parse_scope(text: str) -> Scope | None:
    """The validated ``scope`` mandate of a spec, or None when absent/invalid."""
    report = scope_report(text)
    if not report.present or report.errors:
        return None
    return report.scope


# ---------------------------------------------------------------------------
# Glob semantics (§3.2.2, normative translation)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1024)
def glob_regex(pattern: str) -> str:
    """Translate a glob pattern to a regex source (spec §3.2.2, verbatim rules)."""
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        char = pattern[i]
        if char == "*":
            if pattern.startswith("**/", i):
                out.append("(?:[^/]+/)*")
                i += 3
            elif pattern.startswith("**", i) and i + 2 == n and i > 0 and pattern[i - 1] == "/":
                # trailing '/**' -> optional suffix; the '/' is consumed too:
                # ``a/**`` matches ``a`` and everything under it, but not ``ax``.
                if out and out[-1] == "/":
                    out.pop()
                out.append("(?:/.*)?")
                i += 2
            elif pattern.startswith("**", i):
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        elif char == "[":
            start = i + 1
            negated = False
            if start < n and pattern[start] in "!^":
                negated = True
                start += 1
            close = start
            while close < n and pattern[close] != "]":
                close += 1
            if close >= n:
                out.append(re.escape(char))  # unmatched '[' is a literal
                i += 1
            else:
                out.append("[^" if negated else "[")
                for inner in pattern[start:close]:
                    out.append("\\" + inner if inner in "\\^[]" else inner)
                out.append("]")
                i = close + 1
        else:
            out.append(re.escape(char))
            i += 1
    return "".join(out)


@functools.lru_cache(maxsize=1024)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(glob_regex(pattern))


def glob_match(rel: str, pattern: str) -> bool:
    """Full-match a POSIX-relative path against one glob pattern."""
    return _compiled(pattern).fullmatch(rel) is not None


def scope_allows(scope: Scope | None, rel: str) -> bool:
    """True iff ``rel`` is matched by some allow pattern and no deny pattern."""
    if scope is None:
        return False
    if not any(glob_match(rel, pattern) for pattern in scope.allow):
        return False
    return not any(glob_match(rel, pattern) for pattern in scope.deny)


# ---------------------------------------------------------------------------
# File classification (GOV-7) and activity (GOV-3)
# ---------------------------------------------------------------------------


def declared_token(text: str) -> str | None:
    """Status-line token (lower-cased, backticks/quotes stripped) or None."""
    match = STATUS_RE.search(text)
    if match is None:
        return None
    rest = match.group(1).strip()
    token = re.match(r"^`([^`]*)`", rest)
    if token is not None:
        value = token.group(1)
    else:
        value = rest.split("<!--", 1)[0].strip().strip("`'\"").strip()
    value = value.strip().lower()
    return value or None


def classify(text: str) -> str:
    """``spec`` | ``index`` | ``undeclared``; unknown cases fail closed."""
    token = declared_token(text)
    if token is None:
        return "undeclared"
    return "index" if token in INDEX_TOKENS else "spec"


def spec_dir(root: Path) -> Path:
    return root / SPEC_REL


def spec_files(root: Path) -> list[Path]:
    """``*.md`` files directly in ``<root>/.slim/spec`` (non-recursive, sorted).

    The explicit ``parent == spec_dir`` filter is the documented archive rule
    (GOV-6): ``archive/**`` is never touched by the governance tools.
    """
    directory = spec_dir(root)
    if not directory.is_dir():
        return []
    # `parent == directory` is explicit and normative: archive/** (a
    # subdirectory) is never returned, and the scan is strictly non-recursive.
    return sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix == ".md" and p.parent == directory),
        key=lambda p: p.name,
    )


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def is_active_spec(root: Path, spec: Path) -> bool:
    """Strict location predicate: the spec lies directly in ``.slim/spec``.

    Recursive subdirectories (in particular ``archive/**``) are inactive,
    whatever the file's class (GOV-3).
    """
    try:
        return spec.resolve().parent == spec_dir(root).resolve()
    except OSError:
        return False


def specs_and_indexes(root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Split the active spec directory into (contracts, indexes, undeclared)."""
    contracts: list[Path] = []
    indexes: list[Path] = []
    undeclared: list[Path] = []
    for path in spec_files(root):
        text = read_text(path)
        kind = "undeclared" if text is None else classify(text)
        if kind == "spec":
            contracts.append(path)
        elif kind == "index":
            indexes.append(path)
        else:
            undeclared.append(path)
    return contracts, indexes, undeclared


def active_specs(root: Path) -> list[Path]:
    """The active contracts: class ``spec``, directly in ``.slim/spec``."""
    return specs_and_indexes(root)[0]


# ---------------------------------------------------------------------------
# Git state (GOV-4)
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def git_head(root: Path) -> str | None:
    """``git rev-parse --verify HEAD`` or None (not a repo / no commits)."""
    proc = _git(root, "rev-parse", "--verify", "HEAD")
    if proc is None or proc.returncode != 0:
        return None
    head = proc.stdout.strip()
    return head or None


def tree_dirty(root: Path) -> bool:
    """True when tracked/untracked changes exist outside ``.slim/spec``/``verify``.

    ``.slim/spec/**`` (drafts are the lifecycle input) and ``verify/**``
    (artifacts of the run itself) are excluded, exactly as in the spec.
    Unavailable git or a missing HEAD means "not dirty" (the field is then
    meaningless; staleness is decided by the missing ``git_head`` anyway).
    """
    if git_head(root) is None:
        return False
    proc = _git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=normal",
        "--",
        ".",
        ":!.slim/spec",
        ":!verify",
    )
    if proc is None or proc.returncode != 0:
        return False
    return bool(proc.stdout.strip())


def tracked_files(root: Path) -> list[str]:
    """Git-tracked files as POSIX-relative paths ([] when git is unavailable)."""
    proc = _git(root, "ls-files", "-z")
    if proc is None or proc.returncode != 0:
        return []
    return [name for name in proc.stdout.split("\0") if name]


def scope_digest(root: Path, scope: Scope | None) -> str | None:
    """``scope_sha256``: digest of tracked files covered by ``scope`` (GOV-4).

    $$

    \\operatorname{scope\\_sha256} = \\operatorname{SHA256}\\Bigl(
        \\operatorname{concat}_{p \\in S}
        \\bigl[\\ \\operatorname{SHA256}(\\operatorname{bytes}(p))
        \\;\\|\\; \\texttt{0x00} \\;\\|\\; p \\;\\|\\; \\texttt{0x0A}\\ \\bigr]\\Bigr)

    with $S = \\operatorname{sort}(\\operatorname{tracked}(r) \\cap
    \\operatorname{scope})$; ``None`` when git is unavailable.  A ``None`` scope
    means "all tracked files".
    """
    files = tracked_files(root)
    if not files:
        # Distinguish "no git" from "empty repository": an empty repo still
        # yields a valid (empty) digest of a digest over nothing.
        if git_head(root) is None:
            return None
    if scope is not None:
        files = [name for name in files if scope_allows(scope, name)]
    files.sort()
    digest = hashlib.sha256()
    for name in files:
        try:
            content = (root / name).read_bytes()
        except OSError:
            content = b""
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\x00")
        digest.update(name.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def worktree_snapshot(root: Path, scope: Scope | None) -> dict[str, object]:
    """Attestation triple captured once before a dod-run (GOV-4)."""
    return {
        "git_head": git_head(root),
        "tree_dirty": tree_dirty(root),
        "scope_sha256": scope_digest(root, scope),
    }


# ---------------------------------------------------------------------------
# Approvals (GOV-1/3/7)
# ---------------------------------------------------------------------------


def _load_records(record_dir: Path) -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    if not record_dir.is_dir():
        return out
    for record_file in sorted(record_dir.glob("*.json")):
        try:
            record = json.loads(record_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            out.append((record_file, record))
    return out


def find_valid_approval(
    root: Path,
    spec: Path | None,
    approvals_dir: Path | None = None,
) -> tuple[Path | None, dict | None]:
    """Approval record bound to this spec, or (None, None).

    Requires the spec to be *active* (directly in ``.slim/spec``, GOV-3) and of
    class ``spec`` (GOV-7); the recorded sha256 must equal the current content.
    Archive and non-contract files never have an approval (retire без delete).
    The recorded ``spec`` is accepted both as a legacy absolute path and as a
    root-relative one (dual-accept, spec §3).
    """
    if spec is None:
        return None, None
    if not is_active_spec(root, spec):
        return None, None
    content = None
    try:
        content = spec.read_bytes()
    except OSError:
        return None, None
    text = None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    if classify(text) != "spec":
        return None, None
    digest = sha256_hex(content)
    base = Path(approvals_dir) if approvals_dir is not None else APPROVALS_DIR
    for record_file, record in _load_records(base / root_hash(root)):
        spec_raw = record.get("spec")
        record_digest = record.get("spec_sha256")
        if not isinstance(spec_raw, str) or not isinstance(record_digest, str):
            continue
        # Dual-accept (spec §3.1): a legacy absolute record resolves as-is, a
        # root-relative one is anchored at ``root`` (portable across clones).
        if norm_spec_path(root, spec_raw) != spec.resolve():
            continue
        if record_digest == digest:
            return record_file, record
    return None, None


def approved_scopes(
    root: Path,
    approvals_dir: Path | None = None,
) -> list[tuple[Path, Scope | None]]:
    """Active valid contracts with their mandate, sorted by file name.

    One entry per spec: the first valid record wins.  A contract without a
    ``scope`` fence (or with an invalid one) is still listed with ``scope=None``
    — it simply grants nothing (fail-closed).  Index/undeclared files and
    ``archive/**`` are filtered out by class and by location (GOV-3/GOV-7).
    Records bind to a spec by digest; the recorded ``spec`` accepts both the
    legacy absolute and the root-relative form (dual-accept, spec §3).
    """
    base = Path(approvals_dir) if approvals_dir is not None else APPROVALS_DIR
    out: dict[str, tuple[Path, Scope | None]] = {}
    for record_file, record in _load_records(base / root_hash(root)):
        del record_file  # deterministic order comes from the sorted spec list
        spec_raw = record.get("spec")
        record_digest = record.get("spec_sha256")
        if not isinstance(spec_raw, str) or not isinstance(record_digest, str):
            continue
        # Dual-accept (spec §3.1): drop the legacy try/resolve in favour of the
        # total normalizer; an unresolvable record just leaves ``root`` and is
        # filtered out below.
        spec = norm_spec_path(root, spec_raw)
        if not is_active_spec(root, spec):
            continue
        try:
            content = spec.read_bytes()
        except OSError:
            continue
        if sha256_hex(content) != record_digest:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if classify(text) != "spec":
            continue
        key = str(spec)
        if key in out:
            continue
        out[key] = (spec, parse_scope(text))
    return sorted(out.values(), key=lambda item: item[0].name)


# ---------------------------------------------------------------------------
# dod parsing and command canonicalisation (SPEC §3.3)
# ---------------------------------------------------------------------------


def dod_check_ids(text: str) -> list[str]:
    """All non-empty string ids of the ``dod`` fence, in declaration order.

    Tolerant by construction: a missing block, broken JSON, a non-dict root, a
    non-list ``checks`` or a malformed entry yields ``[]``/skips the entry
    instead of failing (``bin/dod-run`` is the strict parser of this block).
    """
    body = parse_fences(text).get("dod")
    if body is None:
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    checks = data.get("checks")
    if not isinstance(checks, list):
        return []
    ids: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        cid = check.get("id")
        if isinstance(cid, str) and cid:
            ids.append(cid)
    return ids


#: The exhaustive set of ENV prefixes ``canon_command`` may normalise away --
#: exactly the single-thread throttling variables of the compute policy
#: (config/AGENTS.md).  Any other ``VAR=value`` prefix is opaque and blocks
#: grouping: it stays verbatim in the canonical string.
CANON_ENV = frozenset(
    {
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "PYTHONDONTWRITEBYTECODE",
    }
)

_ENV_ASSIGN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\S*)(?=[ \t]|$)")
_WRAPPER_RES = (
    re.compile(r"nice[ \t]+-n[ \t]*\d+(?=[ \t]|$)"),
    re.compile(r"taskset[ \t]+-c[ \t]*[0-9,\-]+(?=[ \t]|$)"),
    re.compile(r"ionice[ \t]+-c[ \t]*\d+(?=[ \t]|$)"),
)


def canon_command(cmd: str) -> str:
    r"""Canonical form of a DoD command for duplicate detection (SPEC §3.3).

    The transformation is deliberately narrow so that only provably equivalent
    shells collapse into one group:

    * whitespace runs are normalised to single spaces;
    * the throttle wrappers ``nice -n N``, ``taskset -c <list>`` and
      ``ionice -cN`` are removed from the command head, in any order and
      repeatedly (they change resources, not what is being run);
    * leading ENV assignments are recognised only for the exhaustive
      :data:`CANON_ENV` set: their policy value ``1`` is dropped, while any
      other value is preserved in sorted head position, so
      ``OMP_NUM_THREADS=1 ...`` and ``OMP_NUM_THREADS=8 ...`` stay distinct
      canons;
    * an unknown ``VAR=...`` prefix is **not** removed and stops the
      normalisation at that point, so it blocks grouping (two different
      unknown prefixes are two different canonical commands);
    * ``python3 -m`` at the head becomes ``python -m``.

    Keyword case is never changed.
    """
    text = " ".join(cmd.split())
    if not text:
        return text
    kept_env: list[str] = []
    while text:
        match = _ENV_ASSIGN_RE.match(text)
        if match is not None:
            name, value = match.group(1), match.group(2)
            if name not in CANON_ENV:
                break  # unknown prefix: opaque from here on, blocks grouping
            if value != "1":
                kept_env.append(f"{name}={value}")
            text = text[match.end() :].lstrip()
            continue
        wrapper_end: int | None = None
        for pattern in _WRAPPER_RES:
            wrapped = pattern.match(text)
            if wrapped is not None:
                wrapper_end = wrapped.end()
                break
        if wrapper_end is None:
            break
        text = text[wrapper_end:].lstrip()
    if text.startswith("python3 -m "):
        text = "python -m " + text[len("python3 -m ") :]
    if kept_env:
        text = " ".join(sorted(kept_env)) + (" " + text if text else "")
    return text


def command_kind(cmd: str) -> str:
    """Class of the canonical command: pytest/ctest/cmake/ruff/build/other."""
    tokens = canon_command(cmd).split()
    if not tokens:
        return "other"
    if "pytest" in tokens or "py.test" in tokens:
        return "pytest"
    if "ctest" in tokens:
        return "ctest"
    if "ruff" in tokens:
        return "ruff"
    if "cmake" in tokens:
        index = tokens.index("cmake")
        if "--build" in tokens or tokens[index + 1 : index + 2] == ["build"]:
            return "build"
        return "cmake"
    if tokens[0] in ("make", "ninja", "bazel", "meson"):
        return "build"
    if "cargo" in tokens and "build" in tokens:
        return "build"
    return "other"


def is_heavy_command(cmd: str) -> bool:
    """True for runs that must not overlap on this laptop (SPEC §3.3).

    Heavy classes are ``pytest``, ``ctest``, ``ruff``, ``build`` (cmake
    ``--build``/make/ninja/...) -- the commands the compute policy throttles.
    A plain ``cmake`` configure is classified ``cmake`` and stays light.
    """
    kind = command_kind(cmd)
    if kind in ("pytest", "ctest", "ruff", "build"):
        return True
    return False


__all__ = [
    "APPROVALS_DIR",
    "CANON_ENV",
    "HOME",
    "INDEX_TOKENS",
    "SPEC_REL",
    "VERIFY_REL",
    "Scope",
    "ScopeReport",
    "active_specs",
    "approved_scopes",
    "atomic_write",
    "canon_command",
    "classify",
    "command_kind",
    "declared_token",
    "dod_check_ids",
    "find_root",
    "find_valid_approval",
    "git_head",
    "glob_match",
    "glob_regex",
    "is_active_spec",
    "is_heavy_command",
    "norm_spec_path",
    "now_iso",
    "parse_fences",
    "parse_scope",
    "read_text",
    "root_hash",
    "scope_allows",
    "scope_digest",
    "scope_report",
    "sha256_hex",
    "slugify",
    "spec_dir",
    "spec_files",
    "spec_rel",
    "specs_and_indexes",
    "tracked_files",
    "tree_dirty",
    "worktree_snapshot",
]
