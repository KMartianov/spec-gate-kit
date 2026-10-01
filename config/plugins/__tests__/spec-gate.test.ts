/**
 * Test harness for plugins/spec-gate.ts.
 *
 * Run FROM THE REPO ROOT (the file is cwd-independent):
 *
 *     node --test config/plugins/__tests__/spec-gate.test.ts
 *
 * and equally from `config/`:
 *
 *     cd config && node --test plugins/__tests__/spec-gate.test.ts
 *
 * Every path (the plugin module, the `spec-approve` CLI, the shared vector
 * file) is resolved from THIS file (`fileURLToPath(import.meta.url)`), never
 * from `process.cwd()`.
 *
 * Isolation (MANDATORY): the plugin reads `os.homedir()` at module load, so
 * `HOME` and `XDG_DATA_HOME` are redirected to a temp dir BEFORE the plugin is
 * dynamically `import()`ed; `spec-approve` additionally gets an explicit
 * `--approvals-dir` under that temp HOME. The harness therefore never creates a
 * record in the real `~/.local/share/opencode/approvals/**`; the explicit guard
 * test at the end snapshots the real store before/after and fails on any drift.
 *
 * Fixtures live under `$TMPDIR` via `mkdtempSync` and NEVER under
 * `/tmp/opencode/**` (that prefix is exempt in the gate, so block tests there
 * would be meaningless).
 */

import test, { after } from "node:test"
import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { homedir, tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

// --- cwd-independent locations ---------------------------------------------

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PLUGIN = path.resolve(HERE, "..", "spec-gate.ts")
const REPO_ROOT = path.resolve(HERE, "..", "..", "..")
const CLI = path.join(REPO_ROOT, "config", "bin", "spec-approve")
const VECTORS_FILE = path.join(REPO_ROOT, "config", "tools", "gov", "scope_vectors.json")

// --- real approvals dir snapshot (captured BEFORE the HOME redirect) -------

function snapshotTree(dir: string): string[] {
  if (!existsSync(dir)) return []
  const out: string[] = []
  const walk = (current: string, rel: string): void => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const entryRel = rel ? `${rel}/${entry.name}` : entry.name
      out.push(entry.isDirectory() ? `${entryRel}/` : entryRel)
      if (entry.isDirectory()) walk(path.join(current, entry.name), entryRel)
    }
  }
  walk(dir, "")
  return out.sort()
}

const REAL_HOME = homedir()
const REAL_APPROVALS_DIR = path.join(REAL_HOME, ".local", "share", "opencode", "approvals")
const REAL_APPROVALS_BEFORE = snapshotTree(REAL_APPROVALS_DIR)

// --- temp HOME + projects, then dynamic import of the plugin ---------------

const BASE = mkdtempSync(path.join(tmpdir(), "spec-gate-tests-"))
const FAKE_HOME = path.join(BASE, "home")
const PROJECTS = path.join(BASE, "projects")
const APPROVALS_DIR = path.join(FAKE_HOME, ".local", "share", "opencode", "approvals")
mkdirSync(FAKE_HOME, { recursive: true })
mkdirSync(PROJECTS, { recursive: true })

// The plugin computes HOME / APPROVALS_DIR / AUDIT_DIR at import time, so the
// environment must be redirected *before* the dynamic import below.
process.env.HOME = FAKE_HOME
process.env.XDG_DATA_HOME = path.join(FAKE_HOME, ".local", "share")

const mod = await import(pathToFileURL(PLUGIN).href)
const specGate = mod.default as { setup: (ctx: unknown) => Promise<unknown> }
const SpecGate = mod.SpecGate as (ctx: unknown) => Promise<Record<string, unknown>>
const __test = mod.__test as Record<string, any>

const AUDIT_FILE = __test.AUDIT_FILE as string
const APPROVER = __test.APPROVER as string

// --- fixtures ---------------------------------------------------------------

function fixtureSpec(): string {
  return [
    "# Task",
    "",
    "- **Статус спецификации:** `draft`",
    "",
    "Original spec body.",
    "",
    "```scope",
    JSON.stringify({ allow: ["src/**"], deny: ["src/secret/**"] }),
    "```",
    "",
    "```dod",
    JSON.stringify({ checks: [{ id: "noop", cmd: "true" }] }),
    "```",
    "",
  ].join("\n")
}

function makeProject(name: string, withSpec: boolean): string {
  const root = path.join(PROJECTS, name)
  mkdirSync(path.join(root, "src"), { recursive: true })
  if (withSpec) {
    mkdirSync(path.join(root, ".slim", "spec"), { recursive: true })
    writeFileSync(path.join(root, ".slim", "spec", "task.md"), fixtureSpec(), "utf8")
  }
  return root
}

/** Approve one spec against the ISOLATED store and parse the CLI's current output. */
function approve(root: string): { spec: string; sha256: string; gate: string } {
  const spec = path.join(root, ".slim", "spec", "task.md")
  const out = execFileSync(CLI, [spec, "--approvals-dir", APPROVALS_DIR], { encoding: "utf8" })
  const approved = /^approved (.+) \(sha256 ([0-9a-f]+)\)\s*$/m.exec(out)
  const unchanged = /^already approved, unchanged \(sha256 ([0-9a-f]+)\)\s*$/m.exec(out)
  assert.ok(approved || unchanged, `unexpected spec-approve output:\n${out}`)
  const gate = /^gate: allow via (\S+)/m.exec(out)
  assert.ok(gate, `missing 'gate: allow via <slug>' line in output:\n${out}`)
  const digest = (approved ?? unchanged)![2]
  assert.match(digest, /^[0-9a-f]+$/, "sha256 digest must be hex")
  return { spec, sha256: digest, gate: gate![1] }
}

const P = {
  noGate: makeProject("nogate", false),
  gated: makeProject("gated", true),
  approved: makeProject("approved", true),
  mandate: makeProject("mandate", true),
  serena: makeProject("serena", true),
  offMarker: makeProject("off-marker", true),
  offEnv: makeProject("off-env", true),
  patch: makeProject("patch", true),
  audit: makeProject("audit", true),
  invalidate: makeProject("invalidate", true),
}

async function beforeFor(directory: string) {
  const hooks = await SpecGate({ directory })
  return hooks["tool.execute.before"] as (input: unknown, output: unknown) => Promise<void>
}

function call(tool: string, args: unknown) {
  return { tool, sessionID: "ses_test", callID: "call_test" }
}

async function expectAllowed(directory: string, tool: string, args: unknown): Promise<void> {
  const hook = await beforeFor(directory)
  await hook(call(tool, args), { args })
}

async function expectBlocked(directory: string, tool: string, args: unknown): Promise<string> {
  const hook = await beforeFor(directory)
  try {
    await hook(call(tool, args), { args })
  } catch (err) {
    return (err as Error).message
  }
  throw new Error("expected the spec gate to block, but the call was allowed")
}

function auditLines(): string[] {
  try {
    return readFileSync(AUDIT_FILE, "utf8").split("\n").filter((l) => l.length > 0)
  } catch {
    return []
  }
}

after(() => {
  // The whole sandbox (temp HOME + approvals + projects) lives under BASE.
  rmSync(BASE, { recursive: true, force: true })
})

// --- 1 ---------------------------------------------------------------------
test("1. read-only tool (read) in a gated project, no approval -> allowed", async () => {
  await expectAllowed(P.gated, "read", { filePath: path.join(P.gated, "src", "a.ts") })
})

// --- 2 ---------------------------------------------------------------------
test("2. unknown tool with a path in a gated project, no approval -> BLOCKED", async () => {
  const msg = await expectBlocked(P.gated, "frobnicate", { path: path.join(P.gated, "src", "a.ts") })
  assert.match(msg, /\[SPEC-GATE BLOCKED\]/)
  assert.ok(msg.includes(APPROVER), "message names the absolute approver command")
  assert.ok(msg.includes(path.join(P.gated, ".slim", "spec")), "message names the spec directory")
})

// --- 3 ---------------------------------------------------------------------
test("3. unknown tool with a path in a gated project, after approval -> allowed", async () => {
  approve(P.approved)
  await expectAllowed(P.approved, "frobnicate", { path: path.join(P.approved, "src", "a.py") })
})

// --- 4 ---------------------------------------------------------------------
test("4. serena-shaped relative_path on an unknown tool, no approval -> BLOCKED", async () => {
  const msg = await expectBlocked(P.gated, "serena_write_like", { relative_path: "src/a.py" })
  assert.match(msg, /\[SPEC-GATE BLOCKED\]/)
})

// --- 5 ---------------------------------------------------------------------
test("5. writer-by-name (replace_content) with unparseable args -> BLOCKED (fail-closed)", async () => {
  const msg = await expectBlocked(P.noGate, "replace_content", { old_str: "x", new_str: "y" })
  assert.match(msg, /\[SPEC-GATE BLOCKED\]/)
  assert.match(msg, /could not parse/)
})

// --- 6 ---------------------------------------------------------------------
test("6. non-writer unknown tool with NO path arg -> allowed", async () => {
  await expectAllowed(P.noGate, "bash", { command: "ls" })
})

// --- 7 ---------------------------------------------------------------------
test("7. exempt path under CONFIG_DIR -> allowed", async () => {
  const target = path.join(FAKE_HOME, ".config", "opencode", "foo.ts")
  await expectAllowed("/", "edit", { filePath: target })
})

// --- 8 ---------------------------------------------------------------------
test("8. target under <root>/.serena/ -> allowed", async () => {
  const target = path.join(P.serena, ".serena", "memories", "x.md")
  await expectAllowed(P.serena, "edit", { filePath: target })
})

// --- 9 ---------------------------------------------------------------------
test("9. target in a gated project with <root>/.slim/GATE-OFF -> allowed", async () => {
  writeFileSync(path.join(P.offMarker, ".slim", "GATE-OFF"), "")
  await expectAllowed(P.offMarker, "edit", { filePath: path.join(P.offMarker, "src", "a.ts") })
})

// --- 10 --------------------------------------------------------------------
test("10. OPENCODE_SPEC_GATE=off -> allowed even for a gated write, no approval", async () => {
  const prev = process.env.OPENCODE_SPEC_GATE
  process.env.OPENCODE_SPEC_GATE = "off"
  try {
    await expectAllowed(P.offEnv, "edit", { filePath: path.join(P.offEnv, "src", "a.ts") })
  } finally {
    if (prev === undefined) delete process.env.OPENCODE_SPEC_GATE
    else process.env.OPENCODE_SPEC_GATE = prev
  }
})

// --- 11 --------------------------------------------------------------------
test("11. target outside any gated project -> allowed", async () => {
  await expectAllowed(P.noGate, "edit", { filePath: path.join(P.noGate, "src", "a.ts") })
})

// --- 12 --------------------------------------------------------------------
test("12. audit JSONL gets a decision:allowed line for a successful gated write", async () => {
  approve(P.audit)
  const before = auditLines().length
  const target = path.join(P.audit, "src", "audited.py")
  await expectAllowed(P.audit, "write", { filePath: target })
  const lines = auditLines()
  assert.ok(lines.length > before, `expected AUDIT_FILE to grow (${before} -> ${lines.length})`)
  const last = JSON.parse(lines[lines.length - 1])
  assert.equal(last.decision, "allowed")
  assert.equal(last.tool, "write")
  assert.equal(last.root, realpathSync(P.audit))
  assert.ok(last.targets.includes(__test.canonicalize(target, P.audit)))
  assert.equal(typeof last.ts, "string")
  assert.ok(existsSync(AUDIT_FILE))
})

// --- 13 --------------------------------------------------------------------
test("13. patch tool with zero parseable paths -> BLOCKED (fail-closed)", async () => {
  const msg = await expectBlocked(P.patch, "apply_patch", { patchText: "this is not a patch" })
  assert.match(msg, /\[SPEC-GATE BLOCKED\]/)
  assert.match(msg, /could not parse/)
})

// --- extras ----------------------------------------------------------------

test("14. v2 setup registers both execute.before and execute.after", async () => {
  const calls: string[] = []
  const ctx = {
    tool: {
      hook: async (name: string, _handler: unknown) => {
        calls.push(name)
      },
    },
    directory: "/",
  }
  await specGate.setup(ctx)
  assert.deepEqual(calls, ["execute.before", "execute.after"])
})

test("15. relative and ~ paths canonicalize correctly", () => {
  const root = P.noGate
  const real = realpathSync(root)
  assert.equal(__test.canonicalize("src/../src/a.ts", root), path.join(real, "src", "a.ts"))
  assert.equal(__test.canonicalize("./b.ts", root), path.join(real, "b.ts"))
  assert.equal(__test.canonicalize("a/b/../../c", root), path.join(real, "c"))
  assert.equal(__test.canonicalize("~/ml_base/x.ts", root), path.join(FAKE_HOME, "ml_base", "x.ts"))
  assert.equal(__test.isExempt(path.join("/tmp/opencode", "x.ts")), true)
  assert.equal(__test.isExempt(path.join(FAKE_HOME, ".config", "opencode", "x.ts")), true)
  assert.equal(__test.isExempt(path.join(FAKE_HOME, ".local", "share", "opencode", "audit", "x.jsonl")), true)
  assert.equal(__test.isExempt(path.join(FAKE_HOME, "ml_base", "x.ts")), false)
})

test("16. writer-by-name heuristic is case-insensitive and broad", () => {
  for (const t of ["write", "replace_content", "replace_in_files", "replace_symbol_body", "insert_before_symbol", "insert_after_symbol", "rename_symbol", "safe_delete_symbol", "multiedit", "apply_patch", "move_file"]) {
    assert.equal(__test.isWriterByName(t), true, `${t} should look like a writer`)
  }
  for (const t of ["bash", "read", "grep", "frobnicate", "list_directory"]) {
    assert.equal(__test.isWriterByName(t), false, `${t} should not look like a writer`)
  }
})

test("17. editing the spec invalidates an approval", async () => {
  approve(P.invalidate)
  await expectAllowed(P.invalidate, "edit", { filePath: path.join(P.invalidate, "src", "a.ts") })
  appendFileSync(path.join(P.invalidate, ".slim", "spec", "task.md"), "\nAdded after approval.\n")
  const msg = await expectBlocked(P.invalidate, "edit", { filePath: path.join(P.invalidate, "src", "a.ts") })
  assert.match(msg, /\[SPEC-GATE BLOCKED\]/)
})

// --- mandate path (§3.4.3) --------------------------------------------------

test("18. scope mandate: allow inside / no-mandate outside / deny wins over allow", async () => {
  approve(P.mandate)

  // inside `allow` -> permitted
  await expectAllowed(P.mandate, "edit", { filePath: path.join(P.mandate, "src", "ok.ts") })

  // outside `allow` -> BLOCKED with reason `no-mandate`
  const outside = await expectBlocked(P.mandate, "edit", { filePath: path.join(P.mandate, "test", "x.ts") })
  assert.match(outside, /\[SPEC-GATE BLOCKED\]/)
  assert.ok(outside.includes("no-mandate"), `expected reason no-mandate, got:\n${outside}`)

  // deny-matched even though `allow` covers it -> BLOCKED with the deny reason
  const denied = await expectBlocked(P.mandate, "edit", { filePath: path.join(P.mandate, "src", "secret", "x.ts") })
  assert.match(denied, /\[SPEC-GATE BLOCKED\]/)
  assert.ok(denied.includes("deny:src/secret/**"), `expected a deny reason, got:\n${denied}`)
})

// --- shared parity vectors (§3.1, §3.4.6) -----------------------------------

test("19. scope vectors parity: every pattern_case and scope_case matches TS", () => {
  const vectors = JSON.parse(readFileSync(VECTORS_FILE, "utf8"))
  assert.equal(vectors.version, 1)
  assert.ok(Array.isArray(vectors.pattern_cases) && vectors.pattern_cases.length > 0)
  assert.ok(Array.isArray(vectors.scope_cases) && vectors.scope_cases.length > 0)

  const ids = new Set<string>()
  for (const c of vectors.pattern_cases) {
    assert.ok(!ids.has(c.id), `duplicate vector id: ${c.id}`)
    ids.add(c.id)
    assert.equal(__test.globMatch(c.rel, c.pattern), c.match, `pattern_case ${c.id}`)
  }
  for (const c of vectors.scope_cases) {
    assert.ok(!ids.has(c.id), `duplicate vector id: ${c.id}`)
    ids.add(c.id)
    assert.equal(
      __test.scopeAllows({ allow: c.allow, deny: c.deny }, c.rel),
      c.allowed,
      `scope_case ${c.id}`,
    )
  }

  // The defect-17 vector must be present and must reject the trailing newline.
  const anchor = vectors.pattern_cases.find((c: { id: string }) => c.id === "anchoring-trailing-newline-rejected")
  assert.ok(anchor, "vector anchoring-trailing-newline-rejected must exist")
  assert.equal(anchor.rel, "src/app.ts\n")
  assert.equal(anchor.pattern, "src/*.ts")
  assert.equal(anchor.match, false)
  assert.equal(__test.globMatch(anchor.rel, anchor.pattern), false)
  assert.equal(__test.globMatch("src/app.ts", "src/*.ts"), true)
})

// --- isolation guard (§3.4.4) ----------------------------------------------

test("20. approval-store isolation guard: the real approvals dir was not touched", () => {
  const afterRun = snapshotTree(REAL_APPROVALS_DIR)
  assert.deepEqual(afterRun, REAL_APPROVALS_BEFORE, "the real approvals store changed during this run")

  // Non-vacuous: the harness *did* write approvals, but only under the redirected store.
  const isolated = snapshotTree(APPROVALS_DIR)
  assert.ok(isolated.some((name) => name.endsWith(".json")), "expected at least one isolated approval record")
  assert.notEqual(path.resolve(APPROVALS_DIR), path.resolve(REAL_APPROVALS_DIR))
})
