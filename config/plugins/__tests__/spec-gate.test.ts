/**
 * Test harness for plugins/spec-gate.ts.
 *
 * Run:  node --test plugins/__tests__/spec-gate.test.ts
 *
 * NOTE: projects live in a temp dir directly under `$TMPDIR` (NOT under
 * /tmp/opencode), because /tmp/opencode is itself an exempt prefix in the
 * gate's `isExempt` set. Placing gated projects there would make every write
 * trivially allowed and the block tests meaningless.
 */

import test, { after } from "node:test"
import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import specGate, { SpecGate, __test } from "../spec-gate.ts"

const HOME = __test.HOME
const CLI = __test.APPROVER
const AUDIT_FILE = __test.AUDIT_FILE
const TEST_ROOT = mkdtempSync(path.join(tmpdir(), "spec-gate-tests-"))
const approvalDirs = new Set<string>()

function makeProject(name: string, withSpec: boolean): string {
  const root = path.join(TEST_ROOT, name)
  mkdirSync(path.join(root, "src"), { recursive: true })
  if (withSpec) {
    mkdirSync(path.join(root, ".slim", "spec"), { recursive: true })
    writeFileSync(
      path.join(root, ".slim", "spec", "task.md"),
      [
        "# Task",
        "",
        "- **Статус спецификации:** `draft`",
        "",
        "Original spec body.",
        "",
      ].join("\n"),
    )
  }
  return root
}

function approve(root: string): void {
  const spec = path.join(root, ".slim", "spec", "task.md")
  const out = execFileSync(CLI, [spec], { encoding: "utf8" }).trim()
  assert.ok(out.endsWith(".json"), `CLI printed an approval path, got: ${out}`)
  approvalDirs.add(path.dirname(out))
}

const P = {
  noGate: makeProject("nogate", false),
  gated: makeProject("gated", true),
  approved: makeProject("approved", true),
  serena: makeProject("serena", true),
  offMarker: makeProject("off-marker", true),
  offEnv: makeProject("off-env", true),
  patch: makeProject("patch", true),
  audit: makeProject("audit", true),
  invalidate: makeProject("invalidate", true),
}

async function beforeFor(directory: string) {
  const hooks = await SpecGate({ directory } as any)
  return hooks["tool.execute.before"]!
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
  for (const dir of approvalDirs) rmSync(dir, { recursive: true, force: true })
  rmSync(TEST_ROOT, { recursive: true, force: true })
})

// --- 1 ---------------------------------------------------------------------
test("1. read-only tool (read) in a gated project, no approval -> allowed", async () => {
  await expectAllowed(P.gated, "read", { filePath: path.join(P.gated, "src", "a.ts") })
})

// --- 2 ---------------------------------------------------------------------
test("2. unknown tool with a path in a gated project, no approval -> BLOCKED", async () => {
  const msg = await expectBlocked(P.gated, "frobnicate", { path: path.join(P.gated, "src", "a.ts") })
  assert.match(msg, /\[SPEC-GATE BLOCKED\]/)
  assert.ok(msg.includes(CLI), "message names the absolute approver command")
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
  const target = path.join(HOME, ".config", "opencode", "foo.ts")
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
  assert.equal(__test.canonicalize("~/ml_base/x.ts", root), path.join(HOME, "ml_base", "x.ts"))
  assert.equal(__test.isExempt(path.join("/tmp/opencode", "x.ts")), true)
  assert.equal(__test.isExempt(path.join(HOME, ".config", "opencode", "x.ts")), true)
  assert.equal(__test.isExempt(path.join(HOME, ".local", "share", "opencode", "audit", "x.jsonl")), true)
  assert.equal(__test.isExempt(path.join(HOME, "ml_base", "x.ts")), false)
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
