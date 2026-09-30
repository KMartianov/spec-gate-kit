# S2 — Work Decomposition, Queues, Scheduling & Concurrency

> Workstream S2 of the R&D plan (`research/README.md`). Owner: `@oracle` (session `ses_f0c9a0885ffeUnYtO3z74Oectj`). Persisted by the orchestrator.

## 1. Problem framing

Autonomous agentic coding must convert an open-ended human request into verifiable work without exploding cost, contention, or untrusted `DONE` claims. The kit solves a slice: **admission control** (Zero-Code Gate, `config/plugins/spec-gate.ts:676-708`), **contract identity** (`scope` fence, `config/AGENTS.md`), **derived state** (`INTAKE\to SPEC\_DESIGN\to APPROVED\to VERIFY\to DONE`, `config/bin/spec-status`), **evidence** (`verify/<id>.json` v2, `config/bin/dod-run`). It deliberately does **not** solve scheduling: there is no queue, no DAG executor, no worktree allocator, no single-writer enforcer, no retry policy. Orchestration is prose in `docs/guides/spec-driven-development.md:§1` ("Plan & Parallelize", "Delegation Check") plus `backgroundJobs` limits in `config/oh-my-opencode-slim.json:17-25`. Observed failure modes from `docs/notes/2026-09-28-orchestrator-improvement-report.md` and `docs/guides/repo-audit-2026-09-29.md`: 3 rounds of batch rework each invalidating approvals (§F1); file-ownership collision (`install.sh`, G2 vs S4); canon divergence (`uv run` vs `.venv`); 200–290k input per draft session with 0 `compress`; port `:19280` rediagnosed in 6 sessions; flat-store collision making `DONE` unreachable for 2 contracts; global staleness forcing a ~14 min full wave on 16 contracts (`README.md:§5-P1.4/5`).

Scheduling must therefore be designed around three hard facts: (a) gate is **per-path, soft, bypassable via `bash`** (`docs/adr/0001-gate-as-soft-guardrail.md:51-53,69-77`); (b) laptop has 6 cores with measured `loadavg` 26.68 (`config/AGENTS.md:Known Caveats`); (c) evidence validity is global and brittle:

$$\text{stale} = (\text{ev\_head}\neq\text{HEAD})\lor\text{tree\_dirty},\quad \text{valid}\iff \operatorname{sha256}(\text{spec})=\text{record.spec\_sha256}$$

## 2. Decomposition model: request $\to$ DAG of bounded contracts

Recommended pipeline: `request → recon → contract set → human approve → wave execution → verify`.

1. **Recon (read-only, parallel, cheap).** `@explorer` codemap + `@librarian` docs. No writes; never gated (`spec-gate.ts:63-86`). Output: file list, interfaces, risks.
2. **Contracting.** Orchestrator drafts one `.slim/spec/<slug>.md` per bounded unit (6 sections + `scope` + `dod`, `spec-driven-development.md:§7`). Index `ROADMAP.md` is portfolio, never a contract (`spec-gate.ts:264-328`).
3. **Pre-approval consistency gate (missing today, highest leverage).** Before any human approve: cross-spec lint — `scope` validity, canon commands, unique `dod.id`, file$\to$writer map, port precondition. This eliminates the observed 3-round invalidate cycle.
4. **Approval (human-only).** `config/bin/spec-approve` flip-then-hash; any edit invalidates (`spec-gate.ts:502-546`).
5. **Execution DAG.** Nodes = approved contracts; edges = dependencies (interface/data/migration order). `spec-status --json` is the snapshot artifact; no `state.json` (`docs/adr/0003-*`).
6. **Verification.** Commit-then-`dod-run` per contract; `DONE` requires $\text{exit\_code}=0\land\neg\text{stale}$ on every check.

**Granularity heuristics.** Trigger for a contract: $>3$ files or interface/schema change (`config/AGENTS.md`). One contract should be: one owner, one `dod` signal, reviewable in $<30$ min, `scope.allow` covering $1$–$8$ paths. Split when: two writers need the same file; `dod` exceeds ~5 min; readiness conditions differ (C++ build vs Python notebook vs docs). Merge when: shared migration/IDL; change is a mechanical rename across many files (give to `@fixer` alone). Anti-pattern proven in audit: 400-line `ROADMAP.md` written by orchestrator itself — delegate writes $>N$ lines. Template today forces rework (headers mismatch, no `dod.id` rule, C++/Jupyter checklist, `orchestrator-improvement-report.md:§4.3`); fix template before scaling contract count.

**File $\to$ single-writer map.** Mandatory pre-dispatch artifact (lesson B7/B14). Intersect all `scope.allow` sets; any overlap is either a split, an explicit handoff order, or a `deny` carve-out. `deny` wins across contracts (`spec-gate.ts:689-707`), so overlapping `allow` without coordination serializes implicitly and confusingly — make it explicit in the DAG.

## 3. Queue / lane / scheduling model

**Lane types (from `spec-driven-development.md:§1.3` + `oh-my-opencode-slim.json`).** Read-only lanes: `explorer` (`edit:deny`), `librarian` (`edit,bash:deny`), `oracle`/`council`/`math-verifier` (review/verify, no project writes). Write lanes: `fixer` (bounded mechanical), `cpp-expert`, `python-expert`, `ml-expert` (all `edit,bash:allow`). Orchestrator is workflow-manager, small isolated step inline, else delegate (§1.2).

**States.** Keep lifecycle derived (`spec-status`), add scheduler-only ephemeral states never stored in repo: `QUEUED \to READY \to RUNNING \to EVIDENCE \to DONE/FAILED/BLOCKED$. `READY` means approved + dependencies `DONE` + worktree free + writer-map clear. Do not add a second source of truth: scheduler state lives in Job Board / `task_status`, never in a file counter (R6 explicitly forbids file counters, `spec-driven-development.md:§16`).

**Policies.**

- Dependency gating: dependent lane starts only when upstream is `DONE` (merge + evidence), not on prose "ready".
- Wave execution: independent contracts in one wave; dependents in next wave. Batch approval via `--all/--changed`; re-approve only changed specs (finding F2/E1).
- Assignment: capability match (C++ $\to$ `cpp-expert`, notebook $\to$ `python-expert`, research $\to$ `librarian`, trust-needing math $\to$ `math-verifier`), plus owner = single writer per path.
- Backpressure: bounded queue per write lane (depth 1–2); if `verify/` or approval invalidation churn rises, stop dispatching new waves and run consistency lint.
- Batch vs incremental: batch drafts for portfolio coherence, then **incremental approve+execute**; never batch-execute 16 contracts then discover a canon error. Cost data supports this: 6 draft sessions $\approx 70\%$ of subagent spend, 200k+ tokens each (`orchestrator-improvement-report.md:A3`).

**Retries.** `fallback.maxRetries:3`, `initialRetryDelayMs:2000` (`oh-my-opencode-slim.json:10-15`) covers model failover, not task semantics. Task retry: at most 3 attempts on same check then R6 stop-and-ask human (`spec-driven-development.md:§16`). Exponential backoff with jitter for transient infra (port, OOM, timeout 900s $\to$ `exit 124`):

$$d_k = \min(d_{\max},\, d_0\cdot 2^{k}) + U(0,j),\quad k=0,1,2$$

Spec/contract contradiction, irreversible-loss risk, or critical env failure stops immediately regardless of $k$.

## 4. Concurrency & throttling policy for a 6-core laptop

Current config allows `backgroundJobs.concurrency.defaultConcurrency:2`, `maxSessionsPerAgent:2` (`oh-my-opencode-slim.json:17-25`). That is a **concurrency of reasoning**, not of heavy execution, and it already overloads the box when builds overlap. Normative laptop policy (`config/AGENTS.md:Known Caveats`, `README.md:§5`):

- Build only `cmake --build build -j2`; tests `ctest -j1`; narrow subsets (`-R`, `-k`) over full suites.
- Wrap heavy steps: `nice -n 19 taskset -c 0,1 ionice -c3 <cmd>`; Python env `OMP_NUM_THREADS=1`, `OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`.
- **Never two heavy runs at once**, including parallel lanes; `dod-run` under same throttle without editing spec `cmd` strings.
- Compute fence: no training/heavy GPU/large-data locally; cluster-ready SLURM scripts only.

Scheduling consequence: model the machine as having **one heavy-execution token** ($H=1$) plus $N=2$ light-reasoning slots. Read-only recon, lint, `spec-status --json`, drafting can parallelize. Any `cmake/ctest/pytest-full/e2e/ASan/notebook-execute` consumes $H$ exclusively (file/port lock for `:19280`, `build/` dir lock). Expected wave time with deduped checks:

$$T_{\text{wave}} \approx \frac{1}{H}\sum_{c\in\text{heavy}}T_c + \max_{l\in\text{light}}T_l,\quad H=1$$

Measured duplication (~75–80% wave = repeated full `pytest` 14$\times$, `ruff` 15$\times$, `ctest` 3–5$\times$) means first optimization is semantic (one owner per full suite, others check own surface), not parallel (`README.md:P1.5`). Proposed 2–3-contract parallelism without dedup $\approx 2\times$ faster but same peak risk; prefer dedup then $H=1$.

## 5. Failure isolation & recovery

- **Blast radius = one contract + its `scope`.** Worktree per write lane (`worktrees` skill): one branch/worktree per contract; shared `build/` never shared across concurrent heavies. Port precondition (`preflight`: stop `oclab-daemon`) passed as ready-fact, not rediscovered.
- **Evidence isolation.** Flat `verify/<id>.json` is the known cross-contract clobber (`docs/notes/dod-run-flat-store-collision.md:8-15,36-44`); `docs-lint` duplicate-`id` ERROR is load-bearing until namespaced `verify/<slug>/<id>.json` + fail-loud on foreign `spec_sha256` lands. Convention until then: `id = <slug>_<check>`.
- **Staleness isolation.** Global `git_head/tree_dirty` invalidation means one commit poisons all evidence. Recovery today: commit-then-verify per contract, full wave only for final certification; roadmap item: shallow staleness keyed on `scope.allow` + `dod-run --changed` (`README.md:P1.4`).
- **Gate failure modes.** Fail-open on internal error, fail-closed on unparseable writers (`spec-gate.ts:862-874,597-600`); audit is fail-open JSONL (`spec-gate.ts:788-795`), not tamper-evident (`README.md:P1.8`). Recovery: re-derive via `spec-status`, never trust prose; recount R6 from audit journal.
- **Session hygiene.** Reuse live sessions when context overlaps; `task_status` for live, `task_result` only for final; never `subagent(sessionID=)` as poll; cancel only obsolete/conflicting (`spec-driven-development.md:§1.5-1.6`). Time-box long lanes (observed 73–78 turns, one impl session died without report).

## 6. Recommended operational model (concrete)

**Queues:** `Q_{\text{recon}}$ (unbounded light), $Q_{\text{write}}$ (per-lane depth $\le 2$), $Q_{\text{heavy}}$ (single token $H=1$, FIFO with port/build locks), $Q_{\text{verify}}$ (per-contract `dod-run`, consumes $H$). Orchestrator dispatches recon immediately, write lanes when `READY`, heavy strictly serialized.

**Lane table:** keep roster; add explicit `preflight` + `verify-owner` roles. Full-suite owners: exactly one contract owns `pytest-full/e2e/ctest-full`; others assert own paths. `math-verifier` gates any LaTeX invariant before merge.

**Required artifacts per dispatch:** owner, `scope` paths, `dod.id` list (prefixed), canon commands digest, worktree/branch, dependency set, validation owner. Missing artifact $\to$ not `READY`.

**Wave loop:** `lint-cross → approve-changed → dispatch READY (light parallel, heavy serialized) → commit → dod-run --spec → spec-status --json → promote dependents`. One `spec-status --json` snapshot per wave reused by all lanes (stops triple re-derivation).

**Minimal new mechanism (no new daemon):** orchestrator prompt checklist + `docs-lint --spec` + namespaced ids + $H$-token discipline + `preflight` script. Anything heavier (persistent scheduler, priority queues) is YAGNI until contract count $>20$ or multi-machine.

## 7. Open questions

1. Shallow staleness: is `scope.allow`-diff sufficient, or must `dod` inputs (fixtures, toolchain) join the hash? Who owns `scope_sha256` evolution?
2. Namespaced evidence layout vs flat compat: keep `verify/<id>.json` fallback forever or migrate once with a batch re-approve?
3. Where should $H$-token live — orchestrator prose, `dod-run --lock`, or `oclab` Stage 3 (`bwrap`, uid-split)? Gate cannot see `bash` anyway (ADR-0001).
4. Per-agent path scoping does not exist (`repo-audit:§1-MAJOR-3`); is OS isolation required before untrusted prompts touch write lanes?
5. Cost telemetry (`oc-usage`) and `compress` discipline for subagents: enforce in prompt or in hook? 0 compresses at 200k+ inputs suggests prompt alone failed.
6. Human bandwidth: $\ge 12$ approves/session observed; does `--changed` + pre-lint reduce to 1–2, or does contract granularity need coarsening?
7. Multi-root audit gap (`spec-gate.ts:817-858` logs first root only): does wave scheduling need cross-root atomicity, or is single-root-per-wave enough?
