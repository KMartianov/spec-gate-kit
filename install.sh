#!/usr/bin/env bash
#
# spec-gate-kit installer — portable drop-in of the spec-governance core.
#
# Usage:
#   bash install.sh --target DIR [--force]
#   bash install.sh --help
#
# Without --target the script only prints a plan and exits non-zero: it never
# guesses a destination. See README.md ("Установка") for details.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || printf 'unknown')"

TARGET=""
FORCE=0

usage() {
  cat <<'EOF'
spec-gate-kit installer

Usage:
  bash install.sh --target DIR [--force]
  bash install.sh --help

Copies the portable core into DIR:
  config/        drop-in mirror of an OpenCode configuration directory
  README.md      kit documentation
  VERSION        kit version
  .slim/spec/    created EMPTY (kit contracts are never copied)

Options:
  --target DIR   destination directory (required; created if missing)
  --force        overwrite conflicting files without keeping *.bak copies
  -h, --help     show this help and exit

Requirements checked before installing:
  - Python >= 3.11   (CLI tools use the standard library only)
  - Node   >= 22     (native TypeScript execution for the gate tests)

Idempotent: files already identical are left untouched. Conflicting files are
backed up to <file>.bak unless --force is given.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      [ "$#" -ge 2 ] || { echo "error: --target requires a directory argument" >&2; exit 2; }
      TARGET="$2"; shift 2 ;;
    --target=*)
      TARGET="${1#*=}"; shift ;;
    --force)
      FORCE=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "spec-gate-kit ${VERSION} — plan (no --target given; nothing was written)"
  echo "  source        : ${ROOT}"
  echo "  would install : config/**, README.md, VERSION"
  echo "  would create  : <target>/.slim/spec/ (empty; kit contracts are NOT copied)"
  echo
  echo "error: --target DIR is required; refusing to guess a destination" >&2
  exit 2
fi

if [ "$TARGET" = "$ROOT" ]; then
  echo "error: --target equals the kit source directory (${ROOT}); choose another DIR" >&2
  exit 2
fi

check_env() {
  command -v python3 >/dev/null 2>&1 || {
    echo "error: python3 not found (spec-gate-kit needs Python >= 3.11)" >&2; exit 1; }
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' || {
    echo "error: Python >= 3.11 required, found $(python3 -V 2>&1)" >&2; exit 1; }
  command -v node >/dev/null 2>&1 || {
    echo "error: node not found (spec-gate-kit needs Node >= 22 for native .ts)" >&2; exit 1; }
  node -e 'process.exit(process.versions.node.split(".").map(Number)[0] >= 22 ? 0 : 1)' || {
    echo "error: Node >= 22 required, found $(node -v 2>&1)" >&2; exit 1; }
}

install_file() { # src dst
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ]; then
    if cmp -s "$src" "$dst"; then
      printf '  = %s (unchanged)\n' "$dst"
      return 0
    fi
    if [ "$FORCE" -eq 1 ]; then
      cp -p "$src" "$dst"
      printf '  ! %s (overwritten, --force)\n' "$dst"
    else
      cp -p "$dst" "${dst}.bak"
      cp -p "$src" "$dst"
      printf '  ~ %s (backup: %s.bak)\n' "$dst" "$dst"
    fi
  else
    cp -p "$src" "$dst"
    printf '  + %s\n' "$dst"
  fi
}

check_env

echo "spec-gate-kit ${VERSION} -> ${TARGET}"
mkdir -p "$TARGET"

while IFS= read -r f; do
  install_file "$f" "$TARGET/${f#"$ROOT"/}"
done < <(find "$ROOT/config" -type f -not -path '*/__pycache__/*' -not -name '*.pyc')

install_file "$ROOT/README.md" "$TARGET/README.md"
install_file "$ROOT/VERSION"   "$TARGET/VERSION"

mkdir -p "$TARGET/.slim/spec"
printf '  + %s (empty; kit contracts are not copied)\n' "$TARGET/.slim/spec/"

# --- smoke ---------------------------------------------------------------
python3 -c 'import json, pathlib'
for p in config README.md VERSION .slim/spec; do
  [ -e "$TARGET/$p" ] || { echo "smoke: missing ${TARGET}/${p}" >&2; exit 1; }
done
python3 -m json.tool "$TARGET/config/opencode.json" >/dev/null
python3 -m json.tool "$TARGET/config/oh-my-opencode-slim.json" >/dev/null
echo "smoke: OK"
