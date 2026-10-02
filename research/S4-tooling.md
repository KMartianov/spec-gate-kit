# S4 — Tooling & Utilities Inventory + Gap Analysis (`spec-gate-kit`)

> **Superseded (2026-10-02).** Written 2026-09-27, before the kit had a committed
> baseline, CI, `VERSION`/`install.sh`, archived DONE contracts or the 2026-10-02
> audits. Current picture: `research/SYNTHESIS.md` + `.slim/spec/notes/` (full-audit
> and decisions, 2026-10-02). Kept as history — do not treat its *State* column as current.

> Workstream S4 of the R&D plan (`research/README.md`). Owner: `@explorer` (session `ses_f0c982bd1ffeozH1E8FrnpyLHl`). Persisted by the orchestrator.

**Scope:** machinery under `config/` (drop-in mirror of `~/.config/opencode/`), plus `docs/`/`research/` context. README §5 (P0/P1/P2) and `repo-audit-2026-09-29.md` §4 are the canonical backlog; this report maps *what exists*, *what is missing*, and *what a "factory" needs*. `git log` is empty, all files untracked — no committed baseline.

## 1. Inventory (path → role → state)

| Path | Role | State |
|---|---|---|
| `plugins/spec-gate.ts` (993 L) | Zero-Code gate: target extraction, per-spec mandate, docs-immutable, audit JSONL | **Core OK**; test-only hooks D1/D2; doc-drift on `.slim/GATE-OFF` "writable" (code has no such write branch); multi-root audit records first root only (NIT) |
| `plugins/__tests__/spec-gate.test.ts` (242 L) | Gate harness (`node --test`) | **STALE/lying** — audit CRIT-1/2: parses old CLI output, fixture lacks `scope`, writes real `~/.local/share/.../approvals` |
| `bin/spec_scope.py` (713 L) | Shared governance semantics: fences, scope, globs, classify, approvals, git attestation, `atomic_write` | **OK**; declares `tools/gov/scope_vectors.json` that does not exist; ragged LaTeX (NIT) |
| `bin/spec-status` (460 L) | Read-only derived state, multi-spec, `--json` | **OK**; no tests; `APPROVED` vs guide `VERIFY` drift (MAJOR-7); local `find_root`/`now_iso` copies |
| `bin/dod-run` (455 L) | Execute `dod` checks → `verify/<id>.json` (evidence v2) | **OK**; non-atomic write (MAJOR-5); denylist theatre (MAJOR-4); flat store (README P1-6); no tests |
| `bin/docs-lint` (503 L) | Contract lint + scope validation + cross-contract dup `id` | **OK**; third fence parser (MINOR-11); arg selects root not file (E2, fixed via `--spec`); no per-file attribution |
| `bin/spec-approve` (616 L) | **Human-only** approve: flip→stamp→hash→record | **OK, hardened**; good isolated tests. Sets the bar |
| `bin/spec-revoke` (382 L) | **Human-only** revoke; flips to `draft`, deletes own records | **BUG** — `STATUS_APPROVED_RE` matches only back-ticked `` `approved` ``, bare token not reverted (MAJOR-6) |
| `bin/spec-new` (261 L) | Scaffold spec + Diátaxis/ADR tree + `git init` | **OK**; hardcoded `ml_base/.venv`, scope `<task>` placeholder, `git init` no `--initial-branch` |
| `bin/gate-off` (93 L) / `gate-on` (87 L) | Human opt-out marker `<root>/.slim/GATE-OFF` | **OK**; near-duplicate twins; `find_root` copy |
| `bin/tests/{test_spec_approve,test_spec_revoke,test_docs_lint}.py` (393/398/253 L) | pytest, isolated via `--approvals-dir`/tmpdir | **Partial** — no coverage for `dod-run`, `spec-status`, `spec_scope`, `spec-new`, gates, `oc-usage` (MAJOR-9) |
| `templates/spec-template.md` (175 L), `adr-template.md` (42 L) | Contract + Nygard ADR skeletons | **OK**; `tools/<task>/**` unrendered (MINOR-14) |
| `command/spec-approve.md` (25 L) | TUI `/spec-approve` slash-command | **OK**; hardcoded absolute path |
| `oh-my-opencode-slim/*_append.md` (9×11 L + orchestrator 60 L) | Per-role append prompts | **9 DEAD STUBS** (only LaTeX block); `orchestrator_append.md` is the real doctrine |
| `skills/verification-planning` (111 L), `skills/oh-my-opencode-slim` (326 L) | Skill payloads | **OK** |
| `opencode.json`, `oh-my-opencode-slim.json`, `cli.json`, `tui.json`, `dcp.jsonc` | Snapshots of live config | **FROZEN, machine-specific** (§4 of README) |
| `docs/adr/0001–0004`, `docs/guides/*`, `docs/notes/*`, `docs/SPEC-OpenCode-Hardening.md` | Doctrine + audit + notes | **Duplicated** from live config; ADRs drifted from code (MAJOR-10) |
| **MISSING** `bin/oc-usage` | Quota/cost telemetry from `opencode.db` | Documented in SPEC §16.1 but **absent from kit**; quotas hardcoded |
| **MISSING** `bin/preflight` | Env/port preconditions (B9) | Proposed, never built |
| **MISSING** `plugins/session-note.ts` | Session export | Referenced in orchestrator report §5.2, absent |
| **MISSING** `plugins/token-tracker.tsx` | Cost display | Referenced by `cli.json:5`, absent |
| **MISSING** `tools/gov/scope_vectors.json` | TS↔Python glob parity vectors | "single source of truth" (audit MAJOR-3) |
| `examples/` (empty), `research/` (README only) | R&D scaffolding | **Empty** |

## 2. Capability matrix & gaps

| Capability | Implemented by | I/O | State / gap (cross-ref) |
|---|---|---|---|
| Write-mandate enforcement | `spec-gate.ts` | hook in → allow/block + audit | Soft; `bash`/heredoc bypass (README P0-1) |
| Spec classification (GOV-3/6/7) | `spec_scope.py` ↔ `spec-gate.ts` | text → `spec\|index\|undeclared` | Two unverified implementations (MAJOR-3) |
| Approval lifecycle | `spec-approve`/`spec-revoke` | CLI → flipped spec + record | Forgeable by construction (README P0-2) |
| Approval store | `~/.local/share/.../approvals/<rootHash>/<16hex>-<slug>.json` | hashed record | External, human-only writer |
| DoD execution | `dod-run` | `dod` fence → `verify/<id>.json` | Non-atomic (MAJOR-5); flat namespace (P1-6) |
| Derived state | `spec-status` | artifacts → `INTAKE…DONE` | No store; staleness $\text{stale}=(\text{ev\_head}\neq\text{HEAD})\lor\text{tree\_dirty}$ |
| Docs immutability | `spec-gate.ts` step 6 | path → refuse | Files-only; `bash` bypass (README P0-3) |
| Contract/docs lint | `docs-lint` | spec → ERROR/WARN | No pre-approval consistency pass (F1) |
| Scaffold | `spec-new` | name → project tree | Hardcoded env; placeholders |
| Project opt-out | `gate-off/on`, `OPENCODE_SPEC_GATE=off` | marker → disabled | Marker write branch absent in code (doc drift) |
| Audit trail | `spec-gate.ts` → `audit/spec-gate.jsonl` | decision → JSONL | **Not tamper-evident** (P1-8) |
| Compute throttling | Policy prose only (`AGENTS.md`) | — | **No enforcing tool**; `-j$(nproc)` caused load 26.7 |
| Parallel DoD wave | — | — | **MISSING**; ~75–80 % wave time is duplicate commands (P1-5) |
| Env/port preflight | — | — | **MISSING**; re-diagnosed in 6 sessions (B9) |
| Cost/quota telemetry | `oc-usage` (absent here) | `opencode.db` → per-agent report | Missing from kit; quota matrix hardcoded |
| TS↔Py parity | — | vectors → assert equal | **MISSING harness** (MAJOR-3) |
| Versioning/install | — | — | No `VERSION`/`CHANGELOG`/`install.sh` (P2-9) |
| CI | — | — | None (P2-10) |
| Task/queue scheduling | Orchestrator prompt (prose) | — | No DAG/queue artifact (research S2) |

## 3. Proposed utilities (purpose · interface sketch · effort)

1. **`wave-runner`** — cut the dominant cost (P1-5). Reads every active contract's `dod`, de-dups identical `cmd` across specs, schedules independent checks under `nice -n 19 taskset -c 0,1 ionice -c3`, serialises port/cmake/ctest owners, writes the same v2 evidence. Interface: `bin/wave-run [--root] [--jobs N] [--lock <id>=<port>] [--changed] [--json]`. Effort **M (2–3 d)**, build on `dod-run`.
2. **`preflight`** — one-shot env/port gate (B9). `bin/preflight [--root] [--json]` → Python/git/cmake/ctest versions, port 19280/8888 occupancy, disk, required env vars; emits `.slim/preflight.json` as a dispatch fact. Effort **S (0.5 d)**.
3. **Namespaced evidence store** — `verify/<slug>/<id>.json` + fallback + **fail-loud** on foreign `spec_sha256` (P1-6, notes). Touches `dod-run`, `spec-status`, `spec-revoke::evidence_for`, and *relaxes* `docs-lint` cross-spec dup check to advisory. Effort **S–M (1–2 d)**; needs an ADR superseding 0003.
4. **`oc-usage` (port + de-hardcode)** — read-only `opencode.db` telemetry, `--json`, window `--mins`; move quota matrix to `config/quotas.json`. Effort **S (0.5–1 d)**.
5. **Installer + VERSION + CHANGELOG** — `install.sh [--target DIR]`: assert Python ≥3.11, back up existing config, `cp -a config/.`, smoke `INTAKE→DONE` in a tmp dir. Effort **S–M (1 d)** (P2-9).
6. **CI** — `.github/workflows/kit.yml`: `pytest config/bin/tests`, `node --test` gate harness, parity vectors, tmp-project smoke. Effort **M (1–2 d)** (P2-10).
7. **Shared scope-vector parity harness** — `tools/gov/scope_vectors.json` + `run_vectors.py` + TS runner; vectors for `*`,`?`,`**`,`a/**`,classes,deny-wins,`..`/absolute (MAJOR-3, P1-1). Effort **S–M (1 d)**.
8. **`spec-preflight` (pre-approval consistency)** — run before human approval (F1): unique `dod.id` across contracts, `scope` sanity, canon-command check, "file→single-writer" map. Interface: `bin/spec-preflight [--spec] --json`. Effort **S (0.5 d)**; much already exists in `docs-lint`.
9. **Tamper-evident audit** — append `prev_hash` chain to `spec-gate.jsonl` (P1-8). Effort **S (0.5 d)**.
10. **`spec-graph` / task-queue scheduler** — read `ROADMAP`+specs §6 phases + `scope` overlap → ready set + writer map. Effort **L (5–10 d), high uncertainty**; defer until research S2 decides paradigm.
11. **Watchdog/time-box for lanes** — cap turns/wall-time with interim report requirement (B11). Effort **S–M**.

## 4. Duplication / dead weight to remove

- **9 `*_append.md` stubs** — pure LaTeX blocks presented as per-role "enforcement" (audit NIT); fold into `AGENTS.md`, keep only `orchestrator_append.md`.
- **`find_root` ×5 copies** (`spec-status`, `dod-run`, `docs-lint`, `gate-off`, `gate-on`) — route through `spec_scope.find_root` (MINOR-12).
- **Third fence parser** — `docs-lint::has_dod_block` re-implements `spec_scope.parse_fences` (MINOR-11).
- **`resolve_path`/`resolve_target` twins** (`spec-approve`, `spec-revoke`) and slug resolution (`docs-lint::resolve_spec`) → one resolver.
- **`gate-off`/`gate-on`** — one binary with `--on/--off`.
- **`spec-status::now_iso`, local `find_root`** — duplicate `spec_scope`.
- **Snapshot doc duplication** — `docs/**` mirrors live config; decide generator vs frozen copy (P2-13).
- **Dead references** — `cli.json:5` `token-tracker.tsx`, `context7`/`gh_grep` MCP names (audit MAJOR-2) point at nonexistent artifacts.

## 5. Priority ranking (by leverage)

| # | Item | Why first | Effort |
|---|---|---|---|
| 1 | Parity harness (`scope_vectors.json`) + canonicalize `specDir` | Prevents silent TS/Py divergence; cheap; unblocks P1-1 | S–M |
| 2 | Fix TS test harness isolation + `scope` fixture | Tests currently lie and pollute real store (audit P0-2) | S |
| 3 | `dod-run`: `atomic_write` + fail-loud foreign evidence | Correctness of the trust anchor | S |
| 4 | Namespaced evidence `verify/<slug>/<id>.json` | Removes structural `DONE` dead-lock (P1-6) | M |
| 5 | `wave-runner` + throttling/dedup | Biggest measured win (~75–80 % of wave) | M |
| 6 | `preflight` | Eliminates repeated 6-session diagnosis | S |
| 7 | `oc-usage` port + quota config | Makes cost/context observable | S |
| 8 | Audit `prev_hash` chain | Tamper-evidence for the only trail | S |
| 9 | Installer/VERSION/CHANGELOG + CI | Kit becomes a product, not a snapshot | M |
| 10 | Dedup `find_root`/fence parser/resolvers | Reduces drift surface before CI | S |
| 11 | `spec-preflight` pre-approval pass | Kills 3 rewrite rounds + re-approvals (F1) | S |
| 12 | `examples/` population | Test fixtures for CI + docs | S |
| 13 | `spec-graph` scheduler | High value but paradigm-dependent | L |

## 6. Open questions

1. **Policy for `verify/**`** — tracked (re-run wave each commit) vs `.gitignore` vs external artifact store (P1-7)? Blocks evidence-store and CI design.
2. **Does the factory keep `spec-gate` at all**, or replace the soft guardrail with OS isolation (bwrap/uid-split, P0-1)? If replaced, most of this inventory is a reference, not a product.
3. **Where does scheduling live** — orchestrator prompt prose, `backgroundJobs` (`oh-my-opencode-slim.json:17`), or a durable external queue? Is there a stable OpenCode API to drive a queue?
4. **Single source for canon commands** — how to make `uv run` never reappear (B8) so `dod` stays reproducible?
5. **Golden CI project** — what minimal repo exercises full `INTAKE→DONE` without violating the compute fence?
6. **`gate-off` self-grant** — docs call `.slim/GATE-OFF` "writable" while `spec-gate.ts` has no write branch for it; resolve doc vs code (and the agent-cannot-self-grant claim).
7. **Snapshot strategy** — regenerate `config/` from templates, or keep the frozen `cp -a` and re-sync manually (P2-13)?
8. **Namespacing vs cross-contract `id` uniqueness** — if evidence is namespaced, should `docs-lint`'s cross-spec dup `id` ERROR become advisory?
