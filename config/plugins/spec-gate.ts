/**
 * spec-gate — soft guardrail before file writes.
 *
 * Soft guardrail. An agent with `bash` access can bypass it. Its purpose is
 * to prevent accidental spec-skipping, not to be a security boundary.
 *
 * A project is "gated" when a directory in the target's parent chain contains
 * a `.slim/spec/` directory (searched upward, stopping at a `.git` boundary or
 * `$HOME`). Inside a gated project a write is allowed only when it is covered
 * by the per-spec mandate of an active, human-approved contract (GOV-1):
 *
 *   1. `docs/**` is always refused, whatever the approvals, the scopes or the
 *      `.slim/GATE-OFF` marker say (GOV-2).
 *   2. `<root>/.slim/spec/**` is always writable (drafts, archive moves; GOV-6).
 *   3. Otherwise the target must be matched by an `allow` pattern and not by any
 *      `deny` pattern of an *active* spec (directly in `.slim/spec/`, class
 *      `spec`) with a valid approval record (sha256 of the current content).
 *      A spec without a `scope` fence grants nothing (fail-closed).
 *
 * Detection is path-based, never tool-name-based: MCP tool ids are unstable
 * across v1/v2 (namespacing), and tools such as serena's `replace_content`
 * mutate files while looking nothing like `edit`/`write`. We therefore keep an
 * exhaustive READ_ONLY allowlist (everything else is a candidate writer) and
 * decide by inspecting the call's file targets. `isWriterByName` is only a
 * fail-closed heuristic for the case where a call exposes no parseable target.
 *
 * Per-root opt-outs (a) `.slim/spec/**` (always writable), (b) `.serena/**`
 * (per-project agent cache), (c) a `.slim/GATE-OFF` marker file (never applies
 * to `docs/**`). Exempt targets (`~/.config/opencode/**`, approvals, audit,
 * `/tmp/opencode/**`) never reach the gate.
 *
 * Every terminal decision for a *gated* call is appended to
 * `~/.local/share/opencode/audit/spec-gate.jsonl` (JSONL) as
 * `{ts, sessionID, tool, targets, root, decision, reason, spec}` plus the
 * additive tamper-evident chain fields `{prev_hash, entry_hash, pid, seq,
 * plugin}`. A boot canary is written once per process (even under the kill
 * switch), so presence is distinguishable from a silent no-op. Audit failure is
 * never allowed to change the gate decision (fail-open).
 *
 * Fail-open on internal errors, fail-closed only on genuinely gated writes and
 * on writers whose file targets cannot be parsed at all.
 */

import * as fs from "node:fs"
import * as path from "node:path"
import * as os from "node:os"
import { createHash } from "node:crypto"
import { fileURLToPath } from "node:url"
import type { Plugin, Hooks } from "@opencode-ai/plugin"

const HOME = os.homedir()
const CONFIG_DIR = path.join(HOME, ".config", "opencode")
const APPROVALS_DIR = path.join(HOME, ".local", "share", "opencode", "approvals")
const AUDIT_DIR = path.join(HOME, ".local", "share", "opencode", "audit")
/**
 * Journal path. `$HOME`-relative by default (the test harness isolates by
 * redirecting `HOME`/`XDG_DATA_HOME` before import); `OPENCODE_SPEC_GATE_AUDIT_FILE`
 * overrides it explicitly (spec §3.8).
 */
const AUDIT_FILE =
  process.env.OPENCODE_SPEC_GATE_AUDIT_FILE && process.env.OPENCODE_SPEC_GATE_AUDIT_FILE.length > 0
    ? path.resolve(process.env.OPENCODE_SPEC_GATE_AUDIT_FILE)
    : path.join(AUDIT_DIR, "spec-gate.jsonl")
const TMP_DIR = "/tmp/opencode"

/**
 * First 16 hex of `sha256` over this plugin file's own bytes, computed once at
 * module load (spec §3.2 / §3.8). Written into every record as `plugin`.
 */
const PLUGIN_ID: string = (() => {
  try {
    const selfPath = fileURLToPath(import.meta.url)
    return createHash("sha256").update(fs.readFileSync(selfPath)).digest("hex").slice(0, 16)
  } catch {
    return "0000000000000000"
  }
})()
const APPROVER = path.join(CONFIG_DIR, "bin", "spec-approve")
const SPEC_REL = path.join(".slim", "spec")
const OFF_MARKER_REL = path.join(".slim", "GATE-OFF")
const SERENA_REL = ".serena"

/**
 * Exhaustive read-only allowlist. Anything not listed may be gated; the gate
 * decides from the call's file targets rather than trusting tool names, so the
 * allowlist must stay explicit (unknown tools are treated as potential writers).
 */
const READ_ONLY_TOOLS = new Set([
  "read",
  "grep",
  "glob",
  "list",
  "ls",
  "ast_grep_search",
  "search",
  "webfetch",
  "fetch",
  "websearch",
  "todowrite",
  "todoread",
  "task",
  "subagent",
  "skill",
  "question",
  "task_status",
  "task_result",
  "task_cancel",
  "task_message",
  "task_revoke",
  "task_revive",
])

/** Tools whose args carry a unified/git diff rather than a path list. */
const PATCH_TOOLS = new Set(["apply_patch", "patch"])

/** Native tools with a known single/array edit schema. */
const EDIT_TOOLS = new Set(["edit", "write", "multiedit"])

/** Path-ish arg keys for the generic (MCP / unknown) branch. */
const GENERIC_PATH_KEYS = ["path", "filePath", "file_path", "relative_path", "notebook_path", "notebookPath"]

/** Path-ish arg keys for the native edit/write/multiedit schema. */
const EDIT_PATH_KEYS = ["filePath", "path", "file_path"]

/** Array-of-targets arg keys for the generic branch. */
const GENERIC_ARRAY_KEYS = ["paths", "files", "file_paths"]

const WRITER_NAME_RE = /write|replace|insert|append|rename|delete|remove|create|patch|edit|move|mkdir|apply/i

const PATCH_PATH_PATTERNS: RegExp[] = [
  /^\+\+\+\s+b?\/(.+)$/,
  /^diff --git\s+\S+\s+(\S+)$/,
  /^\*\*\* (?:Update|Add|Delete) File:\s*(.+)$/,
]

/** Deliberate block. Never swallowed by the fail-open wrapper. */
class SpecGateError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "SpecGateError"
  }
}

// ---------------------------------------------------------------------------
// Path helpers
// ---------------------------------------------------------------------------

function expandTilde(p: string): string {
  if (p === "~") return HOME
  if (p.startsWith("~/")) return path.join(HOME, p.slice(2))
  return p
}

/** Nearest ancestor that exists on disk (the target file itself may not). */
function nearestExisting(p: string): string {
  let cur = p
  for (;;) {
    try {
      fs.lstatSync(cur)
      return cur
    } catch {
      const parent = path.dirname(cur)
      if (parent === cur) return cur
      cur = parent
    }
  }
}

/**
 * Expand `~`, resolve relative paths against `directory`, collapse `.`/`..`,
 * realpath the nearest existing ancestor, and strip any trailing slash. The
 * result is an absolute path with no `..` segments.
 */
function canonicalize(p: string, directory: string): string {
  const expanded = expandTilde(p)
  const absolute = path.isAbsolute(expanded) ? path.resolve(expanded) : path.resolve(directory, expanded)
  const anchor = nearestExisting(absolute)
  let real = anchor
  try {
    real = fs.realpathSync(anchor)
  } catch {
    real = anchor
  }
  const rest = absolute.slice(anchor.length)
  let out = rest ? path.join(real, rest) : real
  out = path.resolve(out)
  if (out.length > 1) out = out.replace(/\/+$/, "")
  return out
}

function isUnder(target: string, dir: string): boolean {
  const base = dir.endsWith(path.sep) ? dir : dir + path.sep
  return target === dir || target.startsWith(base)
}

function isDirectory(p: string): boolean {
  try {
    return fs.statSync(p).isDirectory()
  } catch {
    return false
  }
}

/** Minimal scratch/config/state exemptions, checked before any `findRoot` walk. */
function isExempt(target: string): boolean {
  return (
    isUnder(target, CONFIG_DIR) ||
    isUnder(target, APPROVALS_DIR) ||
    isUnder(target, AUDIT_DIR) ||
    isUnder(target, TMP_DIR)
  )
}

/**
 * Walk up from the target's parent. Return the first directory holding
 * `.slim/spec`. A `.git` boundary stops the walk (never inherit a parent repo's
 * gate); `$HOME` and `/` are hard stops. Returns null when the gate is inactive.
 */
function findRoot(target: string): string | null {
  let p = path.dirname(target)
  let depth = 0
  while (p !== "/" && depth < 32 && p !== HOME) {
    if (isDirectory(path.join(p, SPEC_REL))) return p
    if (fs.existsSync(path.join(p, ".git"))) return null
    const parent = path.dirname(p)
    if (parent === p) break
    p = parent
    depth += 1
  }
  return null
}

function isSpecPath(root: string, target: string): boolean {
  const specDir = path.join(root, SPEC_REL)
  return target === specDir || target.startsWith(specDir + path.sep)
}

/** True for the immutable `docs/**` subtree (equality to the base included). */
function docsBlocked(root: string, target: string): boolean {
  return isUnder(target, path.join(root, "docs"))
}

/** POSIX-relative path used as the glob-matching domain. */
function posixRelative(root: string, target: string): string {
  return path.relative(root, target).split(path.sep).join("/")
}

// ---------------------------------------------------------------------------
// Approval contract
// ---------------------------------------------------------------------------

function sha256(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex")
}

function rootHash(root: string): string {
  return sha256(root).slice(0, 16)
}

function approvalDir(root: string): string {
  return path.join(APPROVALS_DIR, rootHash(root))
}

function specSlug(specPath: string): string {
  const base = path.basename(specPath, ".md")
  const slug = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  return (slug || "spec").slice(0, 64)
}

// ---------------------------------------------------------------------------
// Fenced blocks, scope fence (GOV-1), file class (GOV-7)
// ---------------------------------------------------------------------------

interface Scope {
  allow: string[]
  deny: string[]
}

interface ScopeReport {
  present: boolean
  scope: Scope | null
  errors: string[]
  warnings: string[]
}

/** Reserved status tokens: a file declaring one is an index, not a contract. */
const INDEX_TOKENS = new Set(["roadmap", "index"])

const STATUS_RE = /^[ \t]*-[ \t]*\*\*Статус спецификации:\*\*[ \t]*(.*)$/m
const FENCE_OPEN_RE = /^[ \t]*(`{3,}|~{3,})[ \t]*(.*)$/
const FENCE_CLOSE_RE = /^[ \t]*(`{3,}|~{3,})[ \t]*$/

/** Map info string -> body for every fenced block; first occurrence wins. */
function parseFences(text: string): Map<string, string> {
  const result = new Map<string, string>()
  const lines = text.split(/\r?\n/)
  let index = 0
  while (index < lines.length) {
    const opener = FENCE_OPEN_RE.exec(lines[index])
    if (opener === null) {
      index += 1
      continue
    }
    const fence = opener[1]
    const info = opener[2].trim()
    const body: string[] = []
    let cursor = index + 1
    let closed = false
    while (cursor < lines.length) {
      const closer = FENCE_CLOSE_RE.exec(lines[cursor])
      if (closer !== null && closer[1][0] === fence[0] && closer[1].length >= fence.length) {
        closed = true
        break
      }
      body.push(lines[cursor])
      cursor += 1
    }
    if (info.length > 0 && !result.has(info)) result.set(info, body.join("\n"))
    index = closed ? cursor + 1 : cursor
  }
  return result
}

/** Status-line token (lower-cased, backticks/quotes stripped) or null. */
function declaredToken(text: string): string | null {
  const match = STATUS_RE.exec(text)
  if (match === null) return null
  const rest = match[1].trim()
  const token = /^`([^`]*)`/.exec(rest)
  let value: string
  if (token !== null) {
    value = token[1]
  } else {
    value = rest
      .split("<!--", 1)[0]
      .trim()
      .replace(/^[`'"]+/, "")
      .replace(/[`'"]+$/, "")
      .trim()
  }
  value = value.trim().toLowerCase()
  return value.length > 0 ? value : null
}

/** `spec` | `index` | `undeclared`; unknown cases fail closed. */
function specKind(text: string): "spec" | "index" | "undeclared" {
  const token = declaredToken(text)
  if (token === null) return "undeclared"
  return INDEX_TOKENS.has(token) ? "index" : "spec"
}

function patternError(pattern: unknown): string | null {
  if (typeof pattern !== "string") return "pattern is not a string"
  if (pattern === "") return "empty pattern"
  if (pattern.startsWith("/")) return `absolute pattern not allowed: ${JSON.stringify(pattern)}`
  if (pattern.includes("~")) return `pattern must not contain '~': ${JSON.stringify(pattern)}`
  if (pattern.includes("\\")) return `pattern must not contain backslashes: ${JSON.stringify(pattern)}`
  if (pattern.split("/").some((segment) => segment === "..")) {
    return `pattern must not contain '..' segments: ${JSON.stringify(pattern)}`
  }
  let inClass = false
  for (const char of pattern) {
    if (!inClass) inClass = char === "["
    else if (char === "]") inClass = false
    else if (char === "/") return `'/' is not allowed inside a character class: ${JSON.stringify(pattern)}`
  }
  return null
}

function scopeList(body: unknown, key: string): { patterns: string[]; messages: string[] } {
  if (body === undefined || body === null) {
    return { patterns: [], messages: [`missing required key '${key}' (treated as an empty list)`] }
  }
  if (!Array.isArray(body)) {
    return { patterns: [], messages: [`'${key}' must be a list of glob strings`] }
  }
  const patterns: string[] = []
  const messages: string[] = []
  for (const item of body) {
    const error = patternError(item)
    if (error !== null) messages.push(`${key}: ${error}`)
    else patterns.push(item as string)
  }
  return { patterns, messages }
}

/** Parse the first fence whose info string is exactly `scope` (fail-closed). */
function scopeReport(text: string): ScopeReport {
  const body = parseFences(text).get("scope")
  if (body === undefined) return { present: false, scope: null, errors: [], warnings: [] }
  let data: unknown
  try {
    data = JSON.parse(body)
  } catch (err) {
    return { present: true, scope: null, errors: [`invalid JSON: ${String(err)}`], warnings: [] }
  }
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    return { present: true, scope: null, errors: ["scope body must be a JSON object"], warnings: [] }
  }
  const record = data as Record<string, unknown>
  const allow = scopeList(record.allow, "allow")
  const deny = scopeList(record.deny, "deny")
  const errors: string[] = []
  const warnings: string[] = []
  for (const message of [...allow.messages, ...deny.messages]) {
    if (message.startsWith("missing required key")) warnings.push(message)
    else errors.push(message)
  }
  for (const key of Object.keys(record).sort()) {
    if (key !== "allow" && key !== "deny") warnings.push(`unknown key '${key}' is ignored`)
  }
  if (allow.patterns.length === 0 && errors.length === 0) {
    warnings.push("empty 'allow': the fence grants nothing (no mandate)")
  }
  if (errors.length > 0) return { present: true, scope: null, errors, warnings }
  return { present: true, scope: { allow: allow.patterns, deny: deny.patterns }, errors, warnings }
}

/** The validated mandate of a spec, or null when absent/invalid. */
function parseScope(text: string): Scope | null {
  const report = scopeReport(text)
  if (!report.present || report.errors.length > 0) return null
  return report.scope
}

// ---------------------------------------------------------------------------
// Glob semantics (same normative translation as bin/spec_scope.py)
// ---------------------------------------------------------------------------

const REGEX_CACHE = new Map<string, RegExp>()

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

function globSource(pattern: string): string {
  const out: string[] = []
  let i = 0
  const n = pattern.length
  while (i < n) {
    const char = pattern[i]
    if (char === "*") {
      if (pattern.startsWith("**/", i)) {
        out.push("(?:[^/]+/)*")
        i += 3
      } else if (pattern.startsWith("**", i) && i + 2 === n && i > 0 && pattern[i - 1] === "/") {
        // trailing '/**' -> optional suffix; the '/' is consumed too:
        // ``a/**`` matches ``a`` and everything under it, but not ``ax``.
        if (out.length > 0 && out[out.length - 1] === "/") out.pop()
        out.push("(?:/.*)?")
        i += 2
      } else if (pattern.startsWith("**", i)) {
        out.push(".*")
        i += 2
      } else {
        out.push("[^/]*")
        i += 1
      }
    } else if (char === "?") {
      out.push("[^/]")
      i += 1
    } else if (char === "[") {
      let start = i + 1
      let negated = false
      if (start < n && (pattern[start] === "!" || pattern[start] === "^")) {
        negated = true
        start += 1
      }
      let close = start
      while (close < n && pattern[close] !== "]") close += 1
      if (close >= n) {
        out.push(escapeRegExp(char)) // unmatched '[' is a literal
        i += 1
      } else {
        out.push(negated ? "[^" : "[")
        for (const inner of pattern.slice(start, close)) {
          out.push("\\^[]\\".includes(inner) ? "\\" + inner : inner)
        }
        out.push("]")
        i = close + 1
      }
    } else {
      out.push(escapeRegExp(char))
      i += 1
    }
  }
  return out.join("")
}

/** Full-match a POSIX-relative path against one glob pattern. */
function globMatch(rel: string, pattern: string): boolean {
  let regex = REGEX_CACHE.get(pattern)
  if (regex === undefined) {
    // Anchor to the TRUE end of input. A bare `$` is engine/flag dependent
    // (with the `m` flag it also matches before a trailing newline), whereas
    // Python's `re.fullmatch` never forgives a trailing `\n`. `(?![\s\S])`
    // asserts "no character can follow", i.e. the real end of the string.
    regex = new RegExp("^" + globSource(pattern) + "(?![\\s\\S])")
    REGEX_CACHE.set(pattern, regex)
  }
  return regex.test(rel)
}

/** True iff `rel` is matched by some allow pattern and no deny pattern. */
function scopeAllows(scope: Scope | null, rel: string): boolean {
  if (scope === null) return false
  if (!scope.allow.some((pattern) => globMatch(rel, pattern))) return false
  return !scope.deny.some((pattern) => globMatch(rel, pattern))
}

// ---------------------------------------------------------------------------
// Active approvals (GOV-1 + GOV-3 + GOV-7)
// ---------------------------------------------------------------------------

interface Approval {
  spec: string
  scope: Scope | null
  record: string
}

interface ApprovalScan {
  /** Parseable records in the approvals dir (any root-local record). */
  records: number
  /** Records bound to an active, valid contract, sorted by spec file name. */
  approvals: Approval[]
}

function approvalScan(root: string): ApprovalScan {
  const scan: ApprovalScan = { records: 0, approvals: [] }
  const dir = approvalDir(root)
  let names: string[]
  try {
    names = fs.readdirSync(dir).sort()
  } catch {
    return scan
  }
  const specDir = path.join(root, SPEC_REL)
  const seen = new Set<string>()
  for (const name of names) {
    if (!name.endsWith(".json")) continue
    let record: Record<string, unknown>
    try {
      record = JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"))
    } catch {
      continue
    }
    if (!record || typeof record.spec !== "string" || typeof record.spec_sha256 !== "string") continue
    scan.records += 1
    let specAbs: string
    try {
      specAbs = canonicalize(record.spec, root)
    } catch {
      continue
    }
    // GOV-3: active only when directly in <root>/.slim/spec (archive never).
    if (path.dirname(specAbs) !== specDir) continue
    let content: string
    try {
      content = fs.readFileSync(specAbs, "utf8")
    } catch {
      continue
    }
    if (sha256(content) !== record.spec_sha256) continue
    // GOV-7: only contracts carry a mandate.
    if (specKind(content) !== "spec") continue
    if (seen.has(specAbs)) continue
    seen.add(specAbs)
    scan.approvals.push({ spec: specAbs, scope: parseScope(content), record: path.join(dir, name) })
  }
  scan.approvals.sort((a, b) => path.basename(a.spec).localeCompare(path.basename(b.spec)))
  return scan
}

/** Compatibility predicate: at least one active valid contract approval exists. */
function hasValidApproval(root: string, _target?: string): boolean {
  return approvalScan(root).approvals.length > 0
}

// ---------------------------------------------------------------------------
// Target extraction
// ---------------------------------------------------------------------------

function pickPathByKeys(value: unknown, keys: string[]): string | undefined {
  if (!value || typeof value !== "object") return undefined
  const v = value as Record<string, unknown>
  for (const key of keys) {
    const candidate = v[key]
    if (typeof candidate === "string" && candidate.length > 0) return candidate
  }
  return undefined
}

/** Native edit/write/multiedit path key (kept for `edits[]` compatibility). */
function pickPath(value: unknown): string | undefined {
  return pickPathByKeys(value, EDIT_PATH_KEYS)
}

function stripGitPrefix(raw: string): string {
  const cleaned = raw.trim()
  if (cleaned.startsWith("a/") || cleaned.startsWith("b/")) return cleaned.slice(2)
  return cleaned
}

function extractPatchPaths(patchText: string): string[] {
  const out: string[] = []
  for (const line of patchText.split("\n")) {
    const text = line.replace(/\r$/, "")
    for (const re of PATCH_PATH_PATTERNS) {
      const m = re.exec(text)
      if (!m) continue
      const raw = m[1].trim()
      if (raw !== "/dev/null" && raw !== "dev/null") out.push(stripGitPrefix(raw))
      break
    }
  }
  return out
}

function dedupe(items: string[]): string[] {
  return [...new Set(items)]
}

/** Heuristic for calls that expose no parseable target. Fail closed for these. */
function isWriterByName(tool: string): boolean {
  return WRITER_NAME_RE.test(tool)
}

/**
 * Canonical absolute write targets for a tool call.
 *
 * - Patch tools throw (fail closed) when no path can be parsed.
 * - Native `edit`/`write`/`multiedit` use the documented `filePath` schema plus
 *   `edits[].filePath`.
 * - Every other tool (MCP / unknown) is scanned generically for path-ish keys
 *   and arrays. `relative_path` etc. are resolved against the plugin `directory`
 *   (serena's own project root is not observable from the hook).
 *
 * Never throws for non-patch tools; an empty result is handled by the caller.
 */
function extractTargets(tool: string, args: unknown, directory: string): string[] {
  if (PATCH_TOOLS.has(tool)) {
    const a = (args ?? {}) as Record<string, unknown>
    const text = a.patchText ?? a.patch ?? a.diff
    if (typeof text !== "string" || text.trim().length === 0) {
      throw new SpecGateError(blockUnparseablePatch(tool))
    }
    const raw = extractPatchPaths(text)
    if (raw.length === 0) throw new SpecGateError(blockUnparseablePatch(tool))
    return dedupe(raw.map((r) => canonicalize(r, directory)))
  }

  const raw: string[] = []

  if (EDIT_TOOLS.has(tool)) {
    const primary = pickPathByKeys(args, EDIT_PATH_KEYS)
    if (primary) raw.push(primary)
    const edits = (args as Record<string, unknown> | undefined)?.edits
    if (Array.isArray(edits)) {
      for (const edit of edits) {
        const p = pickPathByKeys(edit, EDIT_PATH_KEYS)
        if (p) raw.push(p)
      }
    }
  } else {
    const a = (args ?? {}) as Record<string, unknown>
    const primary = pickPathByKeys(args, GENERIC_PATH_KEYS)
    if (primary) raw.push(primary)
    for (const key of GENERIC_ARRAY_KEYS) {
      const arr = a[key]
      if (!Array.isArray(arr)) continue
      for (const item of arr) {
        if (typeof item === "string" && item.length > 0) {
          raw.push(item)
        } else {
          const p = pickPathByKeys(item, GENERIC_PATH_KEYS)
          if (p) raw.push(p)
        }
      }
    }
  }

  return dedupe(raw.map((r) => canonicalize(r, directory)))
}

// ---------------------------------------------------------------------------
// Decision (§3.1 of the approved spec; steps 6-10)
// ---------------------------------------------------------------------------

interface Decision {
  allow: boolean
  reason: string
  spec: string | null
}

/**
 * Decide one canonical target inside `root`. Preconditions handled by the
 * caller: kill-switch, read-only allowlist, exemptions, `findRoot`.
 *
 * Order is normative and terminal: spec dir -> docs (always) -> serena cache ->
 * GATE-OFF -> mandate of active valid contracts -> block.
 */
function decideTarget(root: string, target: string): Decision {
  if (isSpecPath(root, target)) return { allow: true, reason: "spec-dir", spec: null }
  if (docsBlocked(root, target)) return { allow: false, reason: "docs-immutable", spec: null }
  if (isUnder(target, path.join(root, SERENA_REL))) {
    return { allow: true, reason: "serena-cache", spec: null }
  }
  if (fs.existsSync(path.join(root, OFF_MARKER_REL))) {
    return { allow: true, reason: "gate-off", spec: null }
  }
  const scan = approvalScan(root)
  if (scan.approvals.length === 0) {
    return { allow: false, reason: scan.records > 0 ? "inactive-spec" : "no-approval", spec: null }
  }
  const rel = posixRelative(root, target)
  // deny has priority over any allow, across all active contracts
  for (const approval of scan.approvals) {
    if (approval.scope === null) continue
    for (const pattern of approval.scope.deny) {
      if (globMatch(rel, pattern)) {
        return { allow: false, reason: `deny:${pattern}`, spec: approval.spec }
      }
    }
  }
  for (const approval of scan.approvals) {
    if (approval.scope === null) continue
    for (const pattern of approval.scope.allow) {
      if (globMatch(rel, pattern)) {
        return { allow: true, reason: `allowed-via:${specSlug(approval.spec)}`, spec: approval.spec }
      }
    }
  }
  return { allow: false, reason: "no-mandate", spec: null }
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

function blockGated(root: string, target: string, decision: Decision): string {
  const specDir = path.join(root, SPEC_REL)
  const lines = [
    `[SPEC-GATE BLOCKED] refusing to write ${target}`,
    ``,
    `Project root:   ${root}`,
    `Spec directory: ${specDir}`,
    `Reason:         ${decision.reason}`,
    `Mandate spec:   ${decision.spec ?? "—"}`,
    ``,
  ]
  if (decision.reason === "docs-immutable") {
    lines.push(
      `docs/** is an immutable contract (GOV-2): tool-driven writes are always refused,`,
      `independently of approvals, scopes and the .slim/GATE-OFF marker.`,
      `Edit docs/** in an editor outside the tool loop, or relaunch with OPENCODE_SPEC_GATE=off.`,
      `The same applies to MCP writers (serena replace_*/insert_*/rename_symbol/...).`,
    )
    return lines.join("\n")
  }
  lines.push(
    `This project is gated per spec. A write is allowed only when it is covered by the`,
    `scope fence of an active, human-approved contract directly in the spec directory:`,
    ``,
    "```scope",
    `{"allow": ["<glob>", ...], "deny": ["<glob>", ...]}`,
    "```",
    ``,
    `A missing, empty or invalid mandate grants nothing (fail-closed); index files`,
    `(roadmap/index) and undeclared files never carry a mandate.`,
    `Ask a human to add or fix the scope fence and approve the current spec content:`,
    ``,
    `    ${APPROVER} ${path.join(specDir, "<spec>.md")}`,
    ``,
    `An approval is valid only while its recorded hash matches the spec content.`,
  )
  return lines.join("\n")
}

function blockUnparseablePatch(tool: string): string {
  return [
    `[SPEC-GATE BLOCKED] could not parse any file paths from the ${tool} patch.`,
    `Refusing to apply a patch whose targets cannot be verified against the spec gate.`,
    `Provide a standard unified/git diff (with "+++ b/<path>" headers) or an approved patch.`,
  ].join("\n")
}

function blockUnparseableWriter(tool: string): string {
  return [
    `[SPEC-GATE BLOCKED] could not parse any file targets from the ${tool} call.`,
    `Refusing a writer whose file targets cannot be parsed: the write cannot be`,
    `verified against the spec gate, so it fails closed.`,
  ].join("\n")
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

interface AuditEntry {
  ts: string
  sessionID: string
  tool: string
  targets: string[]
  root: string
  decision: "allowed" | "blocked"
  reason: string
  spec: string | null
}

/** Tail classification for `prev_hash` selection (spec §3.4). */
type TailInfo = { kind: "hash"; hash: string } | { kind: "chainless" } | { kind: "unreadable" }

const GENESIS = "GENESIS"
const DETACHED = "DETACHED"
const TAIL_CHUNK = 64 * 1024
const BOOT_REASON_PREFIX = "audit:boot"
const CHAIN_START_REASON_PREFIX = "audit:chain-start"

/** In-process cache of the last head we wrote (spec §3.4). */
let inProcessLastHash: string | null = null
/** Boot is written lazily, exactly once per process (spec §3.5). */
let bootWritten = false
/** `seq` counter for ordinary records: 0 is reserved for boot/marker. */
let chainSeq = 0

/**
 * Recursively sort object keys, preserving array order — the TS half of the
 * normative `canon` (spec §3.1). `JSON.stringify` supplies the compact,
 * whitespace-free separators; non-ASCII is emitted as raw UTF-8.
 */
function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortValue)
  if (value !== null && typeof value === "object") {
    const src = value as Record<string, unknown>
    const out: Record<string, unknown> = {}
    for (const key of Object.keys(src).sort()) out[key] = sortValue(src[key])
    return out
  }
  return value
}

/**
 * $\operatorname{canon}(e)$: compact-sorted JSON of `e` without `entry_hash`
 * (spec §3.1). `prev_hash` and the literal `ts` are included as written.
 */
function canonEntry(entry: Record<string, unknown>): string {
  const payload: Record<string, unknown> = {}
  for (const key of Object.keys(entry)) {
    if (key === "entry_hash") continue
    payload[key] = entry[key]
  }
  return JSON.stringify(sortValue(payload))
}

/**
 * $H_n = \operatorname{sha256}(\operatorname{prev}_n \Vert
 * \operatorname{canon}(\operatorname{entry}_n))$ as hex (spec §3.1).
 */
function chainEntryHash(prev: string, entry: Record<string, unknown>): string {
  return createHash("sha256").update(prev, "utf8").update(canonEntry(entry), "utf8").digest("hex")
}

/** Classify one serialized journal line as a chain tail (spec §3.4). */
function classifyTailLine(line: string): TailInfo {
  let parsed: unknown
  try {
    parsed = JSON.parse(line)
  } catch {
    return { kind: "unreadable" }
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { kind: "unreadable" }
  }
  const hash = (parsed as Record<string, unknown>).entry_hash
  if (typeof hash === "string" && hash.length > 0) return { kind: "hash", hash }
  return { kind: "chainless" }
}

/** Last non-empty line of the whole journal (fallback for huge single lines). */
function readTailHashFull(): TailInfo {
  let raw: Buffer
  try {
    raw = fs.readFileSync(AUDIT_FILE)
  } catch (err) {
    return (err as NodeJS.ErrnoException)?.code === "ENOENT" ? { kind: "chainless" } : { kind: "unreadable" }
  }
  const lines = raw.toString("utf8").split("\n")
  while (lines.length > 0 && lines[lines.length - 1] === "") lines.pop()
  if (lines.length === 0) return { kind: "chainless" }
  return classifyTailLine(lines[lines.length - 1])
}

/**
 * Read the journal tail and return the head we must chain from (spec §3.4):
 * a hash, `chainless` (no chain record: legacy or a fresh file) or `unreadable`
 * (a partial/corrupt tail must never be mistaken for a fresh file).
 */
function readTailHash(): TailInfo {
  let fd: number | null = null
  try {
    const stat = fs.statSync(AUDIT_FILE)
    if (!stat.isFile() || stat.size === 0) return { kind: "chainless" }
    const start = Math.max(0, stat.size - TAIL_CHUNK)
    const length = stat.size - start
    fd = fs.openSync(AUDIT_FILE, "r")
    const buf = Buffer.alloc(length)
    fs.readSync(fd, buf, 0, length, start)
    let text = buf.toString("utf8")
    if (start > 0) {
      const nl = text.indexOf("\n")
      if (nl === -1) {
        fs.closeSync(fd)
        fd = null
        return readTailHashFull()
      }
      text = text.slice(nl + 1)
    }
    const lines = text.split("\n")
    while (lines.length > 0 && lines[lines.length - 1] === "") lines.pop()
    if (lines.length === 0) return { kind: "chainless" }
    return classifyTailLine(lines[lines.length - 1])
  } catch (err) {
    return (err as NodeJS.ErrnoException)?.code === "ENOENT" ? { kind: "chainless" } : { kind: "unreadable" }
  } finally {
    if (fd !== null) {
      try {
        fs.closeSync(fd)
      } catch {
        /* ignore */
      }
    }
  }
}

/**
 * Legacy preamble facts for the `chain-start` marker (spec §3.3):
 * number of lines, the last line's literal `ts` and the `sha256` of its bytes
 * without the trailing newline.
 */
function legacyInfo(): { count: number; tailTs: string; tailSha256: string } {
  let raw: Buffer
  try {
    raw = fs.readFileSync(AUDIT_FILE)
  } catch {
    return { count: 0, tailTs: "-", tailSha256: "-" }
  }
  const lines = raw.toString("utf8").split("\n")
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop()
  if (lines.length === 0) return { count: 0, tailTs: "-", tailSha256: "-" }
  const last = lines[lines.length - 1]
  let tailTs = "-"
  try {
    const parsed = JSON.parse(last)
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      const ts = (parsed as Record<string, unknown>).ts
      if (typeof ts === "string") tailTs = ts
    }
  } catch {
    /* keep "-" */
  }
  const tailSha256 = createHash("sha256").update(Buffer.from(last, "utf8")).digest("hex")
  return { count: lines.length, tailTs, tailSha256 }
}

/** Append one serialized record; the caller owns the fail-open wrapper. */
function appendRecord(record: Record<string, unknown>): void {
  fs.mkdirSync(path.dirname(AUDIT_FILE), { recursive: true })
  fs.appendFileSync(AUDIT_FILE, JSON.stringify(record) + "\n", "utf8")
}

/**
 * Write the one-off `chain-start` marker that anchors the legacy preamble
 * (spec §3.3). Legacy lines are never rewritten: the marker is appended after
 * them and carries their size and tail hash.
 */
function writeChainStart(sessionID: string): void {
  const legacy = legacyInfo()
  const reason =
    `${CHAIN_START_REASON_PREFIX} legacy_lines=${legacy.count} ` +
    `legacy_tail_ts=${legacy.tailTs} legacy_tail_sha256=${legacy.tailSha256}`
  const record: Record<string, unknown> = {
    ts: new Date().toISOString(),
    sessionID,
    tool: "spec-gate",
    targets: [],
    root: "",
    decision: "allowed",
    reason,
    spec: null,
    prev_hash: GENESIS,
    entry_hash: "",
    pid: process.pid,
    seq: 0,
    plugin: PLUGIN_ID,
  }
  const hash = chainEntryHash(GENESIS, record)
  record.entry_hash = hash
  appendRecord(record)
  inProcessLastHash = hash
}

/**
 * Append one chained record (spec §3.2-§3.4). `prev = tailHash ?? inProcessLastHash
 * ?? DETACHED`; a chainless tail first gets its `chain-start` marker, whose hash
 * then becomes the in-process head.
 */
function appendChained(entry: AuditEntry, seq: number): void {
  const tail = readTailHash()
  if (tail.kind === "chainless") writeChainStart(entry.sessionID)
  const prev = tail.kind === "hash" ? tail.hash : inProcessLastHash ?? DETACHED
  const record: Record<string, unknown> = {
    ts: entry.ts,
    sessionID: entry.sessionID,
    tool: entry.tool,
    targets: entry.targets,
    root: entry.root,
    decision: entry.decision,
    reason: entry.reason,
    spec: entry.spec,
    prev_hash: prev,
    entry_hash: "",
    pid: process.pid,
    seq,
    plugin: PLUGIN_ID,
  }
  const hash = chainEntryHash(prev, record)
  record.entry_hash = hash
  appendRecord(record)
  inProcessLastHash = hash
}

/**
 * Boot canary (spec §3.5): lazily, exactly once per process, **before** the kill
 * switch is consulted. It chains on ordinary terms; `seq` 0 is reserved.
 */
function ensureBoot(sessionID: string): void {
  if (bootWritten) return
  try {
    const kill = process.env.OPENCODE_SPEC_GATE === "off" ? "on" : "off"
    appendChained(
      {
        ts: new Date().toISOString(),
        sessionID,
        tool: "spec-gate",
        targets: [],
        root: "",
        decision: "allowed",
        reason: `${BOOT_REASON_PREFIX} kill=${kill} plugin=${PLUGIN_ID} pid=${process.pid}`,
        spec: null,
      },
      0,
    )
    // Mark the canary as written ONLY after a successful append (B2/F7.2): a
    // failed write (e.g. an unwritable audit dir) must stay retryable in this
    // process instead of silently suppressing boot forever. Fail-open and the
    // exactly-once happy path are unchanged.
    bootWritten = true
  } catch (err) {
    // Fail-open: a boot write error must never change the gate verdict.
    process.stderr.write(`[spec-gate] audit boot write failed: ${String(err)}\n`)
  }
}

/**
 * Append one JSONL audit record, now as a link in the `prev_hash` chain
 * (spec §3.2-§3.5). NEVER throws and NEVER changes the gate decision: an
 * unwritable audit dir is reported on stderr and ignored (fail-open).
 */
function audit(entry: AuditEntry): void {
  try {
    ensureBoot(entry.sessionID)
    // Reserve the next seq only once the record is durably appended (B3/F7.3):
    // a failed write must not "consume" a number and leave a permanent gap in
    // the chain. Compute it, write it, and commit the counter on success.
    const nextSeq = chainSeq + 1
    appendChained(entry, nextSeq)
    chainSeq = nextSeq
  } catch (err) {
    process.stderr.write(`[spec-gate] audit write failed: ${String(err)}\n`)
  }
}

// ---------------------------------------------------------------------------
// Gate
// ---------------------------------------------------------------------------

function evaluate(input: { tool: string; sessionID: string }, output: { args: unknown }, directory: string): void {
  // 0. Boot canary: provenance of presence, written once per process BEFORE the
  //    kill switch, so a deliberate shutdown is no longer invisible (§3.5).
  ensureBoot(input.sessionID)

  // 1. Kill switch: no gating work and no verdict audit (boot already logged).
  if (process.env.OPENCODE_SPEC_GATE === "off") return

  // 2. Read-only allowlist.
  if (READ_ONLY_TOOLS.has(input.tool)) return

  // 3. Extract targets. Fail closed for a writer with no parseable target.
  const targets = extractTargets(input.tool, output.args, directory)
  if (targets.length === 0) {
    if (isWriterByName(input.tool)) throw new SpecGateError(blockUnparseableWriter(input.tool))
    return
  }

  // 4/5. Exempt targets and non-gated roots are skipped without an audit.
  // 6-11. Per-target decision; the first refusal is terminal.
  let gatedRoot: string | null = null
  let allowedReason: string | null = null
  let allowedSpec: string | null = null
  for (const target of targets) {
    if (isExempt(target)) continue
    const root = findRoot(target)
    if (root === null) continue
    if (gatedRoot === null) gatedRoot = root
    const decision = decideTarget(root, target)
    if (decision.allow) {
      if (allowedReason === null) {
        allowedReason = decision.reason
        allowedSpec = decision.spec
      }
      continue
    }

    audit({
      ts: new Date().toISOString(),
      sessionID: input.sessionID,
      tool: input.tool,
      targets,
      root,
      decision: "blocked",
      reason: decision.reason,
      spec: decision.spec,
    })
    throw new SpecGateError(blockGated(root, target, decision))
  }

  // All targets cleared. Record an allowed decision if any were gated.
  if (gatedRoot !== null) {
    audit({
      ts: new Date().toISOString(),
      sessionID: input.sessionID,
      tool: input.tool,
      targets,
      root: gatedRoot,
      decision: "allowed",
      reason: allowedReason ?? "allowed",
      spec: allowedSpec,
    })
  }
}

/** Fail-open wrapper: deliberate blocks rethrow, everything else is logged. */
async function before(
  input: { tool: string; sessionID: string; callID: string },
  output: { args: unknown },
  directory: string,
): Promise<void> {
  try {
    evaluate(input, output, directory)
  } catch (err) {
    if (err instanceof SpecGateError) throw err
    process.stderr.write(`[spec-gate] internal error, failing open: ${String(err)}\n`)
  }
}

/**
 * v2 `execute.after` observer. The block/allow decision (and its audit line)
 * is already produced by the before-hook; this hook is registered for parity
 * with the v2 hook surface and must never throw, so it is a pure no-op.
 */
async function after(_event?: unknown): Promise<void> {
  // intentionally empty
}

function pickDirectory(ctx: unknown): string {
  const c = ctx as Record<string, any> | undefined
  if (c && typeof c.directory === "string" && c.directory) return c.directory
  if (c && typeof c.location?.directory === "string" && c.location.directory) return c.location.directory
  if (c && typeof c.app?.directory === "string" && c.app.directory) return c.app.directory
  return process.cwd()
}

function buildHooks(directory: string): Hooks {
  return {
    "tool.execute.before": (input, output) => before(input, output, directory),
  }
}

/**
 * Documented plugin shape: `async ({ directory }) => Hooks`.
 */
export const SpecGate: Plugin = async ({ directory }: any) => buildHooks(directory ?? process.cwd())

/**
 * OpenCode >= v2 loads the module's *default* export and requires `{ id, setup }`.
 * We register directly on the v2 tool hook when available and otherwise fall
 * back to the documented Hooks object. Same gate logic either way.
 *
 * `toolNameToV1` in the v2 binary is identity for everything except delegation
 * (subagent <-> task), so tool names arrive unchanged.
 */
export default {
  id: "spec-gate",
  setup: async (ctx: any) => {
    const directory = pickDirectory(ctx)
    if (ctx && typeof ctx.tool?.hook === "function") {
      // Mirrors the proven v2 pattern in oh-my-opencode-slim: await the
      // registration and keep the v2 event field names ({tool, input, id}).
      await ctx.tool.hook("execute.before", (event: any) =>
        before(
          { tool: event?.tool, sessionID: event?.sessionID ?? "", callID: event?.id ?? "" },
          { args: event?.input },
          directory,
        ),
      )
      await ctx.tool.hook("execute.after", after)
      return
    }
    return buildHooks(directory)
  },
} satisfies { id: string; setup: (ctx: any) => Promise<unknown> }

/**
 * Test-only surface. Not part of the plugin contract.
 *
 * The snake_case keys are the normative extension named by the approved spec
 * (§3.2.4, invariant I-3): `parse_scope`, `active_approvals`, `scope_allows`,
 * `docs_blocked`, `decide_target`, `evaluate`, `glob_match` (plus `spec_kind`,
 * used by the vectors). The camelCase aliases are kept for convenience; the
 * pre-existing keys are unchanged.
 */
export const __test = {
  canonicalize,
  findRoot,
  isExempt,
  isSpecPath,
  docsBlocked,
  hasValidApproval,
  approvalScan,
  activeApprovals: (root: string) => approvalScan(root).approvals,
  extractTargets,
  isWriterByName,
  specSlug,
  rootHash,
  sha256,
  parseFences,
  declaredToken,
  specKind,
  parseScope,
  scopeReport,
  globMatch,
  globSource,
  scopeAllows,
  decideTarget,
  evaluate,
  blockGated,
  posixRelative,
  canon: canonEntry,
  entryHash: chainEntryHash,
  pluginId: PLUGIN_ID,
  GENESIS,
  DETACHED,
  // normative snake_case aliases (spec §3.2.4 / I-3)
  parse_fences: parseFences,
  declared_token: declaredToken,
  spec_kind: specKind,
  parse_scope: parseScope,
  scope_report: scopeReport,
  glob_match: globMatch,
  glob_source: globSource,
  scope_allows: scopeAllows,
  docs_blocked: docsBlocked,
  decide_target: decideTarget,
  active_approvals: (root: string) => approvalScan(root).approvals,
  block_gated: blockGated,
  HOME,
  CONFIG_DIR,
  APPROVALS_DIR,
  AUDIT_DIR,
  AUDIT_FILE,
  TMP_DIR,
  APPROVER,
  SPEC_REL,
  OFF_MARKER_REL,
  SERENA_REL,
  INDEX_TOKENS,
  READ_ONLY_TOOLS,
}
