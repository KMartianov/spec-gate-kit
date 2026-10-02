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
import { execFileSync, spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
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
const AUDIT_VECTORS_FILE = path.join(REPO_ROOT, "config", "tools", "gov", "audit_vectors.json")

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
const REAL_AUDIT_DIR = path.join(REAL_HOME, ".local", "share", "opencode", "audit")
const REAL_AUDIT_BEFORE = snapshotTree(REAL_AUDIT_DIR)

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

// --- fresh-process child (boot canary / legacy marker) ----------------------
//
// Boot is exactly-once-per-process, so the only honest way to exercise it under
// a temporarily set `OPENCODE_SPEC_GATE=off` (and the `chain-start` marker on a
// legacy journal) is a fresh `node` process whose `HOME` is its own temp dir.

const CHILD_SCRIPT = path.join(BASE, "audit-child.mjs")
writeFileSync(
  CHILD_SCRIPT,
  [
    'import { pathToFileURL } from "node:url"',
    "const mod = await import(pathToFileURL(process.env.CHILD_PLUGIN).href)",
    "const hooks = await mod.SpecGate({ directory: process.env.CHILD_DIR })",
    'const before = hooks["tool.execute.before"]',
    "await before(",
    '  { tool: "edit", sessionID: "ses_child", callID: "call_child" },',
    "  { args: { filePath: process.env.CHILD_TARGET } },",
    ")",
    'process.stdout.write("CHILD_OK\\n")',
    "",
  ].join("\n"),
  "utf8",
)

/** Child env with its own isolated HOME and no inherited test overrides. */
function childEnv(home: string, extra: Record<string, string> = {}): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    HOME: home,
    XDG_DATA_HOME: path.join(home, ".local", "share"),
    CHILD_PLUGIN: PLUGIN,
  }
  delete env.OPENCODE_SPEC_GATE
  delete env.OPENCODE_SPEC_GATE_AUDIT_FILE
  return { ...env, ...extra }
}

function runChild(env: NodeJS.ProcessEnv): void {
  const res = spawnSync(process.execPath, [CHILD_SCRIPT], { env, encoding: "utf8" })
  assert.equal(res.status, 0, `child failed (status ${res.status}):\n${res.stdout}\n${res.stderr}`)
}

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

// --- audit chain (§3.9) -----------------------------------------------------

test("21. every audit record carries the chain fields; the single-process chain is linear from GENESIS", () => {
  const lines = auditLines()
  assert.ok(lines.length >= 2, `expected the isolated journal to have records, got ${lines.length}`)
  const records = lines.map((line) => JSON.parse(line))

  const markerIndex = records.findIndex((r) => typeof r.entry_hash === "string" && r.entry_hash.length > 0)
  assert.ok(markerIndex >= 0, "expected a chain root (GENESIS marker) in the isolated journal")

  // Every chained record has the additive fields and replays to its entry_hash.
  let expectedPrev = "GENESIS"
  for (let i = markerIndex; i < records.length; i++) {
    const r = records[i]
    assert.equal(r.prev_hash, expectedPrev, `record ${i}: prev_hash must extend the previous entry_hash`)
    assert.match(r.entry_hash, /^[0-9a-f]{64}$/, `record ${i}: entry_hash must be 64 hex`)
    assert.equal(r.pid, process.pid, `record ${i}: pid is this process`)
    assert.equal(typeof r.seq, "number", `record ${i}: seq is a number`)
    assert.match(r.plugin, /^[0-9a-f]{16}$/, `record ${i}: plugin is 16 hex`)
    assert.equal(__test.entryHash(r.prev_hash, r), r.entry_hash, `record ${i}: entry_hash must replay`)
    expectedPrev = r.entry_hash
  }

  // Legacy lines (if any) must precede the marker and must never carry chain fields.
  for (let i = 0; i < markerIndex; i++) {
    assert.equal(records[i].entry_hash, undefined, `legacy record ${i} must not carry entry_hash`)
  }

  // Exactly one boot record per process, chaining on ordinary terms.
  const boots = records.filter((r) => typeof r.reason === "string" && r.reason.startsWith("audit:boot"))
  assert.equal(boots.length, 1, "boot must be written exactly once per process")
  assert.match(boots[0].reason, /^audit:boot kill=(on|off) plugin=[0-9a-f]{16} pid=\d+$/)
  assert.equal(boots[0].seq, 0)
  assert.deepEqual(boots[0].targets, [])
  assert.equal(boots[0].decision, "allowed")
})

test("22. canonicalization vectors parity: all canon_cases and chain_cases match TS byte-for-byte", () => {
  const vectors = JSON.parse(readFileSync(AUDIT_VECTORS_FILE, "utf8"))
  assert.equal(vectors.version, 1)
  assert.ok(Array.isArray(vectors.canon_cases) && vectors.canon_cases.length > 0)
  assert.ok(Array.isArray(vectors.chain_cases) && vectors.chain_cases.length > 0)

  const ids = new Set<string>()
  for (const c of vectors.canon_cases) {
    assert.ok(!ids.has(c.id), `duplicate vector id: ${c.id}`)
    ids.add(c.id)
    const got = __test.canon(c.entry)
    assert.equal(got, c.canon, `canon_case ${c.id}`)
    assert.equal(Buffer.byteLength(got, "utf8"), Buffer.byteLength(c.canon, "utf8"), `canon_case ${c.id}: byte length`)
  }
  for (const c of vectors.chain_cases) {
    assert.ok(!ids.has(c.id), `duplicate vector id: ${c.id}`)
    ids.add(c.id)
    assert.match(c.entry_hash, /^[0-9a-f]{64}$/)
    assert.equal(__test.entryHash(c.prev, c.entry), c.entry_hash, `chain_case ${c.id}`)
  }

  // Required pins: a Cyrillic raw-UTF-8 case and an ordered multi-target case.
  const cyrillic = vectors.canon_cases.find((c: { id: string }) => c.id === "cyrillic-utf8-raw")
  assert.ok(cyrillic, "the cyrillic-utf8-raw case must exist")
  assert.ok(cyrillic.canon.includes("Кириллица"), "Cyrillic must be pinned raw, not \\uXXXX")
  const multi = vectors.canon_cases.find((c: { entry: { targets?: unknown[] } }) => (c.entry.targets ?? []).length >= 2)
  assert.ok(multi, "an ordered multi-target case must exist")
})

test("23. boot canary is written exactly once even when OPENCODE_SPEC_GATE=off (fresh process)", () => {
  const home = mkdtempSync(path.join(tmpdir(), "spec-gate-bootoff-"))
  const proj = path.join(home, "proj")
  mkdirSync(path.join(proj, "src"), { recursive: true })
  const journal = path.join(home, ".local", "share", "opencode", "audit", "spec-gate.jsonl")
  try {
    runChild(
      childEnv(home, {
        CHILD_DIR: proj,
        CHILD_TARGET: path.join(proj, "src", "a.ts"),
        OPENCODE_SPEC_GATE: "off",
      }),
    )
    const records = readFileSync(journal, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l))
    const boots = records.filter((r) => r.reason.startsWith("audit:boot"))
    assert.equal(boots.length, 1, "boot must be written exactly once under the kill switch")
    assert.match(boots[0].reason, /^audit:boot kill=on plugin=[0-9a-f]{16} pid=\d+$/)
    assert.equal(boots[0].seq, 0)
    // Off suppresses verdicts: the journal is just the marker + boot canary.
    assert.equal(records.length, 2, "kill switch must not emit decision records")
  } finally {
    rmSync(home, { recursive: true, force: true })
  }
})

test("24. legacy preamble is never rewritten; chain-start marker anchors it (fresh process)", () => {
  const home = mkdtempSync(path.join(tmpdir(), "spec-gate-legacy-"))
  const proj = path.join(home, "proj")
  mkdirSync(path.join(proj, "src"), { recursive: true })
  const auditDir = path.join(home, ".local", "share", "opencode", "audit")
  mkdirSync(auditDir, { recursive: true })
  const journal = path.join(auditDir, "spec-gate.jsonl")

  const legacy = [
    { ts: "2026-09-30T23:59:58Z", sessionID: "ses_legacy", tool: "edit", targets: ["old/a.py"], root: "/old", decision: "allowed", reason: "allowed-via:old", spec: null },
    { ts: "2026-09-30T23:59:59Z", sessionID: "ses_legacy", tool: "write", targets: ["old/b.py"], root: "/old", decision: "blocked", reason: "deny:docs/**", spec: null },
  ]
  const legacyBytes = Buffer.from(legacy.map((l) => JSON.stringify(l)).join("\n") + "\n", "utf8")
  writeFileSync(journal, legacyBytes)
  try {
    runChild(childEnv(home, { CHILD_DIR: proj, CHILD_TARGET: path.join(proj, "src", "a.ts") }))

    const raw = readFileSync(journal)
    assert.ok(
      raw.subarray(0, legacyBytes.length).equals(legacyBytes),
      "legacy preamble bytes must be untouched",
    )

    const records = raw.toString("utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l))
    const marker = records.find((r) => typeof r.reason === "string" && r.reason.startsWith("audit:chain-start"))
    assert.ok(marker, "a chain-start marker must be appended after the legacy preamble")
    assert.equal(marker.prev_hash, "GENESIS")
    assert.equal(marker.seq, 0)
    assert.equal(marker.tool, "spec-gate")
    const tailSha = createHash("sha256").update(Buffer.from(JSON.stringify(legacy[legacy.length - 1]), "utf8")).digest("hex")
    assert.equal(
      marker.reason,
      `audit:chain-start legacy_lines=2 legacy_tail_ts=2026-09-30T23:59:59Z legacy_tail_sha256=${tailSha}`,
    )
    assert.equal(typeof marker.entry_hash, "string")
    assert.equal(__test.entryHash(marker.prev_hash, marker), marker.entry_hash)

    // The boot canary chains from the marker on ordinary terms.
    const boot = records.find((r) => typeof r.reason === "string" && r.reason.startsWith("audit:boot"))
    assert.ok(boot, "boot canary must follow the marker")
    assert.equal(boot.prev_hash, marker.entry_hash)
  } finally {
    rmSync(home, { recursive: true, force: true })
  }
})

test("25. audit-journal isolation guard: the real journal was not touched", () => {
  assert.ok(AUDIT_FILE.startsWith(FAKE_HOME + path.sep), "AUDIT_FILE must live under the redirected temp HOME")
  assert.notEqual(
    path.resolve(AUDIT_FILE),
    path.resolve(path.join(REAL_AUDIT_DIR, "spec-gate.jsonl")),
    "AUDIT_FILE must not be the real live journal",
  )
  assert.deepEqual(
    snapshotTree(REAL_AUDIT_DIR),
    REAL_AUDIT_BEFORE,
    "the real audit directory changed during this run",
  )
})
