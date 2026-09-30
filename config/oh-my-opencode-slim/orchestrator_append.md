## Mathematical notation (mandatory)

- Always write mathematics in **proper LaTeX**: inline math with `$...$`, display equations with `$$...$$`.
- Never emit mathematics as ASCII or Unicode pseudo-notation. For example, write

  $$\delta_\ell = \left(W_{\ell+1}^{\top}\,\delta_{\ell+1}\right)\odot\sigma'(z_\ell), \qquad \frac{\partial L}{\partial W_\ell} = \delta_\ell\, a_{\ell-1}^{\top}$$

  and **never** the ASCII form `δ_ℓ = (W_{ℓ+1}ᵀ δ_{ℓ+1}) ⊙ σ′(z_ℓ)`.
- Use LaTeX for all mathematical expressions, derivations, proofs, and for **storing and transferring formulas** across files, artifacts, tool payloads, reports, commit messages and messages between agents (e.g. Markdown files, `.tex`, Jupyter Markdown cells, docs).
- Use standard LaTeX constructs: `\frac`, `\sum`, `\prod`, `\int`, `\partial`, `\nabla`, `\top`, `\odot`, `\mathbb{R}`, `\operatorname{}`, aligned/matrix environments (`\begin{aligned}...\end{aligned}`, `\begin{pmatrix}...\end{pmatrix}`, `\begin{cases}...\end{cases}`).
- When a target cannot render LaTeX (plain source comments, some CLIs), still keep the LaTeX source as the canonical form and only degrade for that specific surface.

## Doc-Driven Development (Spec-First) — MANDATORY

**Zero-Code Gate.** Any non-trivial task (touches more than ~3 files, or changes interfaces/contracts/schemas) MUST begin as a specification at `.slim/spec/<task_slug>.md` with status `draft`. Until the human approves it, the ONLY writable location is `.slim/spec/**`. Modifying the code base before approval is forbidden and is enforced by the `spec-gate` plugin, which raises `[SPEC-GATE BLOCKED]`. Never try to bypass it through the shell. After approval the mandate is **not** the root: only targets covered by the spec's own `scope` fence become writable (approve alone opens nothing — fail-closed).

**How the gate decides** (`plugins/spec-gate.ts`, hook `tool.execute.before`). Order is terminal: kill switch `OPENCODE_SPEC_GATE=off` → read-only allowlist (`read`, `grep`, `glob`, `list`, `ls`, `ast_grep_search`, `search`, `webfetch`, `fetch`, `websearch`, `todowrite`, `todoread`, `task`, `subagent`, `skill`, `question`, `task_status`, `task_result`, `task_cancel`, `task_message`, `task_revoke`, `task_revive`) → target extraction (a writer without parseable paths is blocked **fail-closed** — covers `edit`/`write`/`multiedit`/`apply_patch`/`patch` and serena MCP writers: `replace_content`, `replace_in_files`, `replace_symbol_body`, `insert_before_symbol`, `insert_after_symbol`, `rename_symbol`, `safe_delete_symbol`) → exempt (`~/.config/opencode/**`, approvals, audit, `/tmp/opencode/**`) → `<root>/.slim/spec/**` always writable (archive included) → **`docs/**` always refused** (GOV-2; before scopes/serena/`GATE-OFF`, so even `GATE-OFF` does not open it) → `<root>/.serena/**` cache → `<root>/.slim/GATE-OFF` → **mandate**: the target is covered by an `allow` pattern and by no `deny` pattern of an active approved **contract** (fail-closed; a spec without a `scope` fence grants nothing). Block reasons: `docs-immutable` / `no-mandate` / `deny:<pattern>` / `no-approval` / `inactive-spec`. Audit line: `{"ts","sessionID","tool","targets","root","decision","reason","spec"}` in `~/.local/share/opencode/audit/spec-gate.jsonl`.

**`scope` fence = the only mandate (GOV-1).** First fence whose info string is exactly `scope`, JSON `{"allow": [...], "deny": [...]}`; globs: `*` (no `/`), `?`, `[a-z]`/`[!abc]`, `**` as a whole component (`a/**` matches `a` too). Missing/invalid fence, unsafe patterns (absolute, `~`, `\`, `..`, empty) or empty `allow` ⇒ no mandate. Mandates of all active approved contracts union; any `deny` wins. Editing a spec (scope included) invalidates its approval.

**File classes in `.slim/spec/` (GOV-7).** Status token `roadmap`/`index` ⇒ portfolio **index**, not a contract (no mandate, no `dod`; `ROADMAP.md` is one); any other token ⇒ contract; no status line ⇒ `undeclared`, not a contract. Approvals of non-contracts grant nothing.

**Archive (GOV-6).** `.slim/spec/archive/**` is inactive: retire without delete. Gate/`spec-status`/`docs-lint` ignore it.

**Task state is DERIVED, never stored.** There is no state file and no `r6` counter. `bin/spec-status [<path>] [--spec <slug|path>] [--json]` computes the state read-only, **per active contract** (multi-spec: the default output lists every contract and prints `index:`/`undeclared:` info lines; `--json` is an array; `--spec` selects one, incl. archive/non-contract with `role`/`active`):
- `INTAKE` — no spec; `SPEC_DESIGN` — spec exists, no valid approval; `APPROVED` — valid approval, no valid evidence; `VERIFY` — valid approval + some evidence (or stale evidence); `DONE` — valid approval + every DoD check has `verify/<id>.json` with `exit_code == 0`, a matching `spec_sha256`, `git_head == HEAD` and `tree_dirty == false` (evidence v2, GOV-4). Legacy evidence without `git_head` or from another revision/dirty tree is **stale ⇒ VERIFY, never DONE** — that is the goal, not a regression.
- `DISCOVERY` and `AUTONOMOUS_EXEC` are **prose only**: they gate nothing, so they are not machine states.
- Editing the spec invalidates the approval **and** the evidence (same `sha256` rule). Never keep a second copy of the state — a store that caches a verdict is a liability, not a feature.

**DoD evidence.** The spec carries a machine-readable fenced block whose info string is exactly `dod`, body `{"checks": [{"id": "...", "cmd": "..."}]}` (JSON, not YAML). `bin/dod-run [--spec <slug|path>]` executes the checks (`--list`, `--only <id>`, `--timeout <sec>`, default 900 s) and writes the only evidence store `verify/<id>.json` = `{check, cmd, exit_code, started_at, finished_at, duration_s, spec, spec_sha256, tail, git_head, tree_dirty, scope_sha256}` (v2); destructive commands are refused before execution, and a timeout records `exit_code: 124`. Only active **contracts** have a `dod` circuit — `dod-run` refuses index (`roadmap`/`index`), `undeclared` and `archive/**` selections without writing evidence. Commit everything outside `.slim/spec/**` and `verify/**` **before** running (otherwise `tree_dirty=true` and `DONE` is unreachable). **Commit `verify/`** — it is proof, not build junk. `DONE` is earned from those artifacts, never claimed.

**R6 — stop and ask the human (a policy line, not a counter).** Break autonomy ONLY when:
1. the approved specification is internally contradictory and needs a contract/schema change;
2. an operation risks irreversible data loss outside the working tree;
3. three consecutive failed attempts at the same compile error or failing test;
4. critical environment failure (missing compiler/system library/external service down).

If you must count failures, count them from the audit journal — never from a mutable file: a counter in a file is bash-writable and resettable simply by renaming the check.

**Documentation framework.** Diátaxis quadrants — Tutorials, How-To, Reference, Explanation — plus ADRs in the Nygard format (`docs/adr/NNNN-title.md`: status, context, decision, positive/negative consequences, rejected alternatives). Reference is normative: implement exactly to it. `spec-new` scaffolds the four quadrants plus `docs/adr/{README.md,0000-template.md,0001-<slug>.md}`; `bin/docs-lint [<root>]` lints **contracts only** (status line, a real ADR reference, every referenced `docs/…` path exists, missing `dod` fence = WARNING) and validates the `scope` fence (broken = ERROR; missing/empty = WARNING); an index file gets zero ERRORs, `undeclared` exactly one, and `archive/**` is never linted.

**Spec contract** (`.slim/spec/<task_slug>.md`): header + metadata; §1 Scope and Non-goals; §2 Mini-ADR; §3 Reference (DDL / JSON-RPC / C++/Python signatures, all math in LaTeX) **plus the machine-readable `scope` fence** (the write mandate; without it an approved spec grants nothing); §4 Evidence Path (`verification-planning`); §5 Definition of Done checklist **plus the machine-readable `dod` fence**; §6 autonomous phases with the assigned subagent. Reference template: `~/.config/opencode/templates/spec-template.md`.

**Compute fence.** This is a laptop: only light builds, micro-tests and short benchmarks. Never start training, heavy GPU/large-data jobs or long profiling — emit cluster-ready SLURM scripts instead.

**Approval is human-only.** Never write an approval artifact yourself, never run the human-only CLIs below, and never attempt to switch the gate off. If the plugin blocks you, stop and ask the human.

Agents **may** run these (they only scaffold, report, or execute an already-approved DoD):
- `spec-new <name> [--base DIR] [--no-git]` — scaffold `<base>/<name>/`: `.slim/spec/<slug>.md` (from `templates/spec-template.md`), the Diátaxis tree, `docs/adr/`, `README.md`, `.gitignore`, `git init`. Writes only under `<base>/<name>/`; `--force` fills in missing files only.
- `spec-status [<path>] [--spec <slug|path>] [--json]` — read-only derived state, multi-spec; writes nothing, ever.
- `dod-run [--spec <slug|path>] [--only <id>]... [--timeout <sec>] [--list] [--json]` — run the approved DoD checks of an active contract and write `verify/<id>.json`; index/undeclared/archive are refused.

Human-only CLIs in `~/.config/opencode/bin/` (NOT on `$PATH`; an agent must not invoke them):
- `spec-approve <spec>` — **flip the spec's status line to `approved`, stamp `- **Утверждено:** <ISO8601> (human)`, then** hash the post-flip payload and write `~/.local/share/opencode/approvals/<sha256(root)[:16]>/<slug>.json`. Editing the spec afterwards changes the hash and **invalidates** the approval.
- `spec-revoke [<spec-or-project>]` — delete the approval record(s), revert the status to `draft`, drop the `Утверждено` line.
- `gate-off [<path>]` / `gate-on [<path>]` — create/remove the opt-out marker `<root>/.slim/GATE-OFF`. `gate-off` is the sanctioned trivial-work escape hatch; it can only be created **outside** `.slim/spec/**`, so an agent armed with `write`/`edit` cannot self-grant it either. The marker does **not** open `docs/**` (immutable by GOV-2); the global `OPENCODE_SPEC_GATE=off` does.

**In-session shortcut.** The human can also type `/spec-approve <spec>` in the TUI (`command/spec-approve.md`); the shell block runs in the client process, not as an agent tool.

**Honest scope.** The gate is a soft guardrail with real value (friction + audit trail), **not** a security boundary: `bash` is allowlisted for `python -m *` and `spec-new`/`dod-run` run as shell commands, so a determined agent can still write files through the shell. Kernel-level read-only isolation is deferred to the oclab stage. Design rule: anything that must hold unconditionally has to be enforced by the platform or the kernel — never by a convention, and never by a second copy of the truth.
