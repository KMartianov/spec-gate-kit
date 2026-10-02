#!/usr/bin/env python3
r"""Portability checker for the spec-gate kit.

Usage:
    python3 config/tools/gov/check_portability.py {paths|config|install}
    python3 config/tools/gov/check_portability.py <mode> --help
    python3 config/tools/gov/check_portability.py --help

Exit status: 0 -- clean; 1 -- a violation was found (details on stdout);
2 -- usage error / environment error.

Modes
-----

``paths``
    Hard check: fail (exit 1) when any shipped source file contains the
    author's machine-specific absolute-home literal.  The second, doctrinal
    clause of contract §3.2 (``~/.config/opencode`` "outside a doctrinal
    explanation") is operationalised as an *informational* scan: every
    occurrence is printed as ``note: file:line [kind]`` with a coarse kind
    (``code`` | ``data`` | ``doctrine`` | ``other``) and never affects the
    exit code -- all such occurrences in the kit are legitimate (the
    canonical exempt-path in ``spec-gate.ts``, the canonical install target
    in ``spec-new``/``install.sh``, doctrine prose and ``skills/**``).  The
    scanned set is ``config/**`` plus ``README.md``, ``install.sh`` and
    ``VERSION`` (absent optional files are not an error); generated caches
    and undecodable binaries are skipped, and the checker skips itself as a
    note target because it holds the pattern as a checked sample.

``config``
    Validates the shipped JSON snapshots (contract §3.2/§3.3):

    * ``config/opencode.json``: ``permission.external_directory`` must not
      mention ``~/.config/opencode/**`` or ``~/.local/share/opencode/**``,
      neither as a key nor as a value (the live configuration of the author
      must not appear in the shipped snapshot at all);
    * ``config/oh-my-opencode-slim.json``: every agent's ``permission.bash``
      (under ``presets.*`` and under ``agents.*``) must be an object map,
      never a ``"allow"``/``"deny"`` string, and must not contain the
      human-only CLIs ``spec-approve``, ``spec-revoke``, ``gate-off``,
      ``gate-on`` as keys.

    Model names, prompts and MCP lists are deliberately not checked.

``install``
    Runs ``bash install.sh --target <mktemp -d>`` (cwd = kit root) and
    requires rc=0 plus: ``config/`` (directory), ``README.md``, ``VERSION``
    (byte-identical to the kit's), ``.slim/spec/`` (directory).  Additional
    invariant (deliberately stricter than the letter of contract §3.2, an
    orchestrator decision): ``.slim/spec/`` must be **empty** -- the kit's
    contracts and approvals must never leak into the receiving project,
    otherwise the installer would silently impose the author's write
    mandates on it.  The temporary target is always removed.

Only the Python standard library is used.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Repository layout
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]  # <repo>/config/tools/gov/check_portability.py
CONFIG_DIR = REPO_ROOT / "config"

#: Root-level files of the shipped kit that are not under ``config/**``.
PATHS_ROOT_FILES = ("README.md", "install.sh", "VERSION")

#: Generated/binary artifacts excluded from the text scan.
SKIP_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache", ".git"})
SKIP_SUFFIXES = frozenset({".pyc", ".pyo", ".so", ".o", ".a"})

# --- config mode ------------------------------------------------------------

OPENCODE_JSON = CONFIG_DIR / "opencode.json"
SLIM_JSON = CONFIG_DIR / "oh-my-opencode-slim.json"

#: Must NOT appear (as a key or as a value) in ``permission.external_directory``.
FORBIDDEN_EXTERNAL_DIRS = ("~/.config/opencode/**", "~/.local/share/opencode/**")

#: Human-only CLIs that must never appear as keys of an agent's ``bash`` map.
HUMAN_ONLY_CLIS = ("spec-approve", "spec-revoke", "gate-off", "gate-on")

# --- install mode -----------------------------------------------------------

INSTALL_SH = REPO_ROOT / "install.sh"
VERSION_FILE = REPO_ROOT / "VERSION"

#: Entries that must exist in a fresh ``install.sh --target DIR`` installation.
INSTALL_EXPECTED = ("config", "README.md", "VERSION", ".slim/spec")
#: Which of them must be directories (the rest must be files).
INSTALL_DIRS = ("config", ".slim/spec")

# --- exit codes (normative, contract §3.2) ---------------------------------

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ENV_ERROR = 2

# --- needles and note classification ----------------------------------------

#: The forbidden author-home literal, assembled from fragments so this file --
#: which is scanned by its own ``paths`` mode -- does not contain it verbatim.
FORBIDDEN_HOME = "/home/asd" + "cxfrt"

#: Doctrinal-clause pattern: reported as an informational note, never fatal.
NOTE_NEEDLE = "~/.config/opencode"

CODE_SUFFIXES = frozenset({".py", ".ts", ".sh", ".bash", ".js", ".mjs", ".cjs"})
DATA_SUFFIXES = frozenset({".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini"})
DOCTRINE_SUFFIXES = frozenset({".md", ".mdx", ".txt", ".rst"})

# ---------------------------------------------------------------------------
# Help texts
# ---------------------------------------------------------------------------

USAGE = """Usage:
    python3 config/tools/gov/check_portability.py {paths|config|install}
    python3 config/tools/gov/check_portability.py <mode> --help
    python3 config/tools/gov/check_portability.py --help

Modes (all read-only; the kit itself is never modified):

  paths    Hard-fail (exit 1) on the author-specific absolute-home literal in
           config/**, README.md, install.sh, VERSION.  The doctrinal clause of
           contract §3.2 (~/.config/opencode "outside a doctrinal
           explanation") is executed as an INFORMATIONAL scan: such
           occurrences are printed as 'note: file:line [kind]' lines with a
           coarse kind (code|data|doctrine|other) and never affect the exit
           code.  Only the machine-specific literal is hard.
  config   Validate the shipped opencode.json / oh-my-opencode-slim.json
           snapshots (external_directory hardening; agent bash maps).
  install  Install into a temp target with install.sh and smoke-check it,
           including the invariant that the target's .slim/spec/ is EMPTY.

Exit status: 0 clean, 1 violation, 2 usage/environment error.
"""

PATHS_HELP = """Mode paths:
    python3 config/tools/gov/check_portability.py paths

  Hard failure (exit 1): the author's absolute-home literal in any scanned
  source file.  This is machine-specific and can never be portable.

  Doctrinal clause of contract §3.2, as interpreted: occurrences of
  '~/.config/opencode' are printed as informational
      note: <file>:<line> [kind]
  lines (kind: code | data | doctrine | other) and NEVER influence the exit
  code.  Rationale: every occurrence found in the kit is legitimate -- the
  canonical exempt path in spec-gate.ts, the canonical install target in
  spec-new/install.sh, doctrine prose and skills/**.  The checker skips
  itself as a note target (it holds the pattern as a checked sample).

  Scanned: config/** recursively plus README.md, install.sh, VERSION (absent
  optional files are not an error).  __pycache__/.pytest_cache/.git and
  undecodable binaries are skipped.
"""

CONFIG_HELP = """Mode config:
    python3 config/tools/gov/check_portability.py config

  Checks the shipped JSON snapshots (exit 1 on any violation, 'file: reason'
  lines on stdout):

    config/opencode.json
        permission.external_directory must not mention
        '~/.config/opencode/**' or '~/.local/share/opencode/**', neither as a
        key nor as a value.
    config/oh-my-opencode-slim.json
        every agent's permission.bash (under presets.* and under agents.*)
        must be an object map, never a "allow"/"deny" string, and must not
        contain the human-only CLIs spec-approve, spec-revoke, gate-off,
        gate-on as keys.

  Model names, prompts and MCP lists are not checked.
"""

INSTALL_HELP = """Mode install:
    python3 config/tools/gov/check_portability.py install

  Runs 'bash install.sh --target <mktemp -d>' (cwd = kit root) and requires:

    * install.sh exits 0;
    * the target contains config/ (dir), README.md, VERSION, .slim/spec/
      (dir);
    * the target's VERSION is byte-identical to the kit's VERSION;
    * .slim/spec/ in the target is EMPTY.

  The empty-.slim/spec/ invariant is deliberately stricter than the letter
  of contract §3.2 (which requires only existence): the kit's contracts and
  approvals must never leak into the receiving project, otherwise the
  installer would silently impose the author's write mandates on it.

  The temporary target is always removed (success or failure).
"""

MODE_USAGE = {
    "paths": PATHS_HELP,
    "config": CONFIG_HELP,
    "install": INSTALL_HELP,
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> object | None:
    """Parse a JSON file; ``None`` on any read/parse failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _is_skipped(path: Path) -> bool:
    if path.suffix in SKIP_SUFFIXES:
        return True
    return any(part in SKIP_DIR_NAMES for part in path.relative_to(REPO_ROOT).parts)


def iter_scan_targets() -> list[Path]:
    """Every source file ``paths`` must scan: ``config/**`` + optional root files."""
    targets: list[Path] = []
    if CONFIG_DIR.is_dir():
        targets.extend(
            path
            for path in sorted(CONFIG_DIR.rglob("*"))
            if path.is_file() and not _is_skipped(path)
        )
    for name in PATHS_ROOT_FILES:
        path = REPO_ROOT / name
        if path.is_file() and not _is_skipped(path):
            targets.append(path)
    return targets


def _lines_of(path: Path) -> list[str] | None:
    """Source lines of a text file; ``None`` for unreadable/binary files."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None


def find_needle(path: Path, needle: str) -> list[int]:
    """1-based line numbers containing ``needle``; [] for binaries."""
    lines = _lines_of(path)
    if lines is None:
        return []
    return [number for number, line in enumerate(lines, 1) if needle in line]


def classify_note(path: Path) -> str:
    """Coarse artifact kind for an informational ``~/.config/opencode`` note."""
    if path.suffix in CODE_SUFFIXES:
        return "code"
    if path.suffix in DATA_SUFFIXES:
        return "data"
    if path.suffix in DOCTRINE_SUFFIXES:
        return "doctrine"
    if path.parent == CONFIG_DIR / "bin":  # extensionless CLI scripts
        return "code"
    return "other"


def _string_values(node: object) -> list[str]:
    """Every string reachable from ``node`` through dict values / lists."""
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            out.extend(_string_values(item))
    elif isinstance(node, dict):
        for item in node.values():
            out.extend(_string_values(item))
    return out


# ---------------------------------------------------------------------------
# Mode: paths
# ---------------------------------------------------------------------------


def mode_paths() -> int:
    """Hard-scan for the author-home literal; note-scan the doctrinal pattern."""
    checker = Path(__file__).resolve()
    violations: list[str] = []
    notes: list[str] = []
    for path in iter_scan_targets():
        rel = path.relative_to(REPO_ROOT).as_posix()
        violations.extend(f"{rel}:{number}" for number in find_needle(path, FORBIDDEN_HOME))
        if path.resolve() == checker:
            continue  # this file holds NOTE_NEEDLE as a checked sample
        notes.extend(
            f"note: {rel}:{number} [{classify_note(path)}]"
            for number in find_needle(path, NOTE_NEEDLE)
        )
    for violation in violations:
        print(violation)
    for note in notes:
        print(note)
    if violations:
        print(
            f"check_portability: paths: FAIL ({len(violations)} occurrence(s) of the "
            f"author-specific absolute-home literal; the kit must not reference the "
            f"author's machine; {len(notes)} '{NOTE_NEEDLE}' note(s) are informational)"
        )
        return EXIT_VIOLATION
    print(
        f"check_portability: paths: clean ({len(notes)} informational "
        f"'{NOTE_NEEDLE}' occurrence(s))"
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Mode: config
# ---------------------------------------------------------------------------


def _check_opencode(doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return ["top-level JSON value is not an object"]
    permission = doc.get("permission")
    if not isinstance(permission, dict):
        return ["'permission' is missing or not an object"]
    external = permission.get("external_directory")
    if not isinstance(external, dict):
        return ["permission.external_directory is missing or not an object"]
    problems: list[str] = []
    for key, value in external.items():
        if key in FORBIDDEN_EXTERNAL_DIRS:
            problems.append(
                f"permission.external_directory contains the live-config directory "
                f"{key!r} as a key"
            )
        for found in _string_values(value):
            if found in FORBIDDEN_EXTERNAL_DIRS:
                problems.append(
                    f"permission.external_directory[{key!r}] contains the live-config "
                    f"directory {found!r} as a value (it must not appear at all)"
                )
    return problems


def _human_cli_in_key(key: str) -> str | None:
    """A human-only CLI name mentioned by a bash-map key (token/basename wise)."""
    tokens = key.replace("/", " ").split()
    for name in HUMAN_ONLY_CLIS:
        if name in tokens:
            return name
    return None


def _check_bash_map(json_path: str, bash: object) -> list[str]:
    if not isinstance(bash, dict):
        return [
            f"{json_path}.permission.bash is {type(bash).__name__} ({bash!r}); "
            f"an object map is required (a bare \"allow\"/\"deny\" string would "
            f"erase the global denies)"
        ]
    problems: list[str] = []
    for key in bash:
        name = _human_cli_in_key(str(key))
        if name is not None:
            problems.append(
                f"{json_path}.permission.bash grants the human-only CLI {name!r} "
                f"(key {key!r})"
            )
    return problems


def _check_agent(json_path: str, node: object) -> list[str]:
    """Bash-shape checks for one agent-shaped node; [] when nothing is set."""
    if not isinstance(node, dict):
        return []
    permission = node.get("permission")
    if permission is None:
        return []
    if not isinstance(permission, dict):
        return [f"{json_path}.permission is {type(permission).__name__}; an object is required"]
    if "bash" not in permission:
        return []
    return _check_bash_map(json_path, permission["bash"])


def _check_slim(doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return ["top-level JSON value is not an object"]
    problems: list[str] = []
    # Both spellings are accepted defensively: `presets` (plural container)
    # and a future object-shaped `preset`.
    for container_name in ("presets", "preset"):
        container = doc.get(container_name)
        if container is None:
            continue
        if not isinstance(container, dict):
            if container_name == "preset":
                continue  # `preset` is a selector string in the shipped schema
            problems.append(
                f"{container_name} is {type(container).__name__}; an object of agents is expected"
            )
            continue
        for preset_name, preset in container.items():
            if not isinstance(preset, dict):
                continue
            # A preset may carry a preset-wide permission.bash of its own ...
            problems.extend(_check_agent(f"{container_name}.{preset_name}", preset))
            # ... and every agent entry inside it is checked separately.
            for agent_name, agent in preset.items():
                problems.extend(
                    _check_agent(f"{container_name}.{preset_name}.{agent_name}", agent)
                )
    agents = doc.get("agents")
    if agents is not None:
        if not isinstance(agents, dict):
            problems.append(
                f"agents is {type(agents).__name__}; an object of agents is expected"
            )
        else:
            for agent_name, agent in agents.items():
                problems.extend(_check_agent(f"agents.{agent_name}", agent))
    return problems


def mode_config() -> int:
    """Validate the hardened shipped JSON snapshots (contract §3.2/§3.3)."""
    problems: list[str] = []
    for path, checker in ((OPENCODE_JSON, _check_opencode), (SLIM_JSON, _check_slim)):
        rel = path.relative_to(REPO_ROOT).as_posix()
        doc = load_json(path)
        if doc is None:
            problems.append(f"{rel}: cannot read or parse the shipped JSON snapshot")
            continue
        problems.extend(f"{rel}: {reason}" for reason in checker(doc))
    for problem in problems:
        print(problem)
    if problems:
        print(f"check_portability: config: FAIL ({len(problems)} violation(s))")
        return EXIT_VIOLATION
    print("check_portability: config: clean")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Mode: install
# ---------------------------------------------------------------------------


def _tail(text: str, limit: int = 1500) -> str:
    stripped = (text or "").strip()
    return stripped[-limit:]


def _run_installer(target: Path) -> tuple[int | None, str]:
    """Run ``bash install.sh --target target``; rc=None on an OSError."""
    try:
        proc = subprocess.run(
            ["bash", str(INSTALL_SH), "--target", str(target)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return None, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def mode_install() -> int:
    """Install into a temp target and smoke-check the result (contract §3.2/§3.4)."""
    if not INSTALL_SH.is_file():
        print(f"install: {INSTALL_SH} not found; nothing to execute")
        print("check_portability: install: FAIL (1 violation(s))")
        return EXIT_VIOLATION

    try:
        target = Path(tempfile.mkdtemp(prefix="spec-gate-kit-install-"))
    except OSError as exc:
        print(
            f"check_portability: install: environment error: cannot create a temp "
            f"target: {exc}",
            file=sys.stderr,
        )
        return EXIT_ENV_ERROR

    problems: list[str] = []
    try:
        returncode, output = _run_installer(target)
        if returncode is None:
            print(
                f"check_portability: install: environment error: cannot run "
                f"'bash {INSTALL_SH}': {output}",
                file=sys.stderr,
            )
            return EXIT_ENV_ERROR
        if returncode != 0:
            problems.append(f"install.sh exited {returncode}; output tail: {_tail(output)!r}")

        for rel in INSTALL_EXPECTED:
            entry = target / rel
            if rel in INSTALL_DIRS:
                if not entry.is_dir():
                    problems.append(f"missing directory {rel}/")
            elif not entry.is_file():
                problems.append(f"missing file {rel}")

        installed_version = target / "VERSION"
        if installed_version.is_file():
            if not VERSION_FILE.is_file():
                problems.append("the kit's VERSION is missing; cannot compare bytes")
            elif installed_version.read_bytes() != VERSION_FILE.read_bytes():
                problems.append("VERSION is not byte-identical to the kit's VERSION")

        spec_dir = target / ".slim" / "spec"
        if spec_dir.is_dir():
            entries = sorted(path.name for path in spec_dir.iterdir())
            if entries:
                shown = ", ".join(entries[:10])
                problems.append(
                    f".slim/spec/ is not empty ({len(entries)} entry(ies): {shown}); "
                    f"the installer must not leak the kit's contracts/approvals into "
                    f"the receiving project"
                )
    finally:
        shutil.rmtree(target, ignore_errors=True)

    for problem in problems:
        print(f"install: {problem}")
    if problems:
        print(f"check_portability: install: FAIL ({len(problems)} violation(s))")
        return EXIT_VIOLATION
    print("check_portability: install: clean (temp target removed)")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

MODES = {
    "paths": mode_paths,
    "config": mode_config,
    "install": mode_install,
}


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(USAGE, end="")
        return EXIT_OK
    if len(args) == 1 and args[0] in MODES:
        return MODES[args[0]]()
    if len(args) == 2 and args[0] in MODES and args[1] in ("-h", "--help"):
        print(MODE_USAGE[args[0]], end="")
        return EXIT_OK
    print(USAGE, end="", file=sys.stderr)
    return EXIT_ENV_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv))
