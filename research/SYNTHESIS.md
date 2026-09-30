# SYNTHESIS — Target 'Project Factory' Architecture & Roadmap

> Workstream Ф2 of the R&D plan (`research/README.md`). Owner: `@oracle` (sessions `ses_f0c93ea2dffe2oT9fltTQsCrI6` + continuation `ses_f0c927096ffe9YpV39HmFgwK9N`). Persisted by the orchestrator.

> **Executive summary (5 lines).** Keep spec-gate and harden it — it is the only surveyed paradigm with a machine-enforced write mandate and hash-bound derived state. Borrow exactly three primitives: property-based DoD class, signed/hash-chained attestation, wave-level dedup runner. No daemon, no microVMs, no durable engine at current scale — triggers defined below. P0 = trust-anchor correctness (parity, atomic evidence, revoke fix, audit chain, agent-reach closure); P1 = cost killers (wave dedup, shallow scheduling, HMAC approvals, telemetry). Everything else is YAGNI until measured thresholds trip.

## 1. Verdict on the paradigm

**KEEP + HARDEN; borrow three primitives; do NOT replace.** S1 (§5, `research/S1-paradigms.md:95-104`) finds no external framework with our two load-bearing invariants — path-scoped write mandate (`config/plugins/spec-gate.ts:676-708`) and derived lifecycle with `DONE ⟺ validApproval ∧ ∀checks(exit=0 ∧ sha-match ∧ fresh)` (`README.md:81-86`) — and recommends keeping the paradigm plus (i) property-based/metamorphic DoD class, (ii) Sigstore-style signed attestation, (iii) durable-workflow wrapping. S5 (`research/S5-reliability.md:5,33-37`) constrains *how* to keep it: the gate is honestly SOFT (`docs/adr/0001-gate-as-soft-guardrail.md`), so anything the enforcer cannot see (`bash`, `python -m *`, serena `relative_path`) must be labeled SOFT until it is closed by privilege level (Stage 1 userspace) or kernel (oclab Stage 3, deferred). S3 (`research/S3-roles.md:31-43,64-72`) adds the independence proviso the paradigm alone does not supply: implementers share one model family (`config/oh-my-opencode-slim.json:49-112`), review without a distinct model + distinct write capability is collusion, and `DONE`-by-testimony is forbidden — verdicts require runnable artifacts read by a third party. So: the contract math stays; the trust story is completed by attestation + role separation, not by a new paradigm.

## 2. Target architecture (composition: S1-A1 ⊕ selective A4, A2/A3/A5 deferred)

**IN (committed):**
- Hardened Zero-Code Gate + `scope` mandate + GOV-2 `docs/**` immutability for file tools, with honest SOFT labeling where `bash` bypasses (`README.md:§5-P0.1/P0.3`; S5 §3).
- Stage-1 userspace closure: approvals/audit/config out of agent `external_directory`, object-form `bash` maps only, human CLIs off allowlist (S5 §5-Stage 1).
- Derived state only, R6 as policy line counted from audit journal, never a counter file (`docs/adr/0003-derived-lifecycle-state.md`; S3 §3.6).
- Evidence v2, atomic + readback-verified, namespaced (see §3a), fail-loud on foreign-`spec_sha256` overwrite (S4 §3.3; S5 §4.3).
- Pre-approval consistency lint (`scope` validity, canon commands, unique `dod.id`, file→single-writer map) before any human approve — kills the observed 3-round invalidate cycle (`docs/notes/2026-09-28-orchestrator-improvement-report.md:113-118`; S2 §2.3).
- Orchestrator-prose scheduling + stateless `wave-run`/`dod-run --changed` CLI under one-heavy-token discipline ($H=1$), `preflight` facts, Evidence-custodian function (S2 §6; S3 §5).
- PBT/metamorphic named DoD check class as convention + template (S1 §5-P1).
- Hash-chained audit now, HMAC-signed approvals P1, GPG/kernel later (see §3c–d).
- Telemetry: `oc-usage` ported with token/cost columns + fixed session export as precondition for all metrics (S6 §5.1–2).
- Kit productization: parity vectors, fixed TS harness isolation, installer/VERSION/CHANGELOG, CI smoke `INTAKE→DONE` (S4 §5; audit §4).

**OUT (explicitly, with trigger to re-admit):** Temporal/durable engine (OUT: no crash-resume need at ≤20 contracts; IN when multi-day runs or multi-project fleets — S1-A2); Firecracker/gVisor per-session microVMs (OUT: single-user laptop; IN on untrusted-prompt-on-write-lane or observed exfil/heredoc exploit — S1 §2.h, S5 §5); formal-verification-first pipeline (OUT except invariant-rich modules: dataloaders, image ops, spec/status invariants per S1 §6.5); persistent queue/priority scheduler daemon + `spec-graph` L-effort build (OUT until >20 active contracts or multi-machine — S2 §6, S4 §3.10); Sigstore/rekor transparency + PKI (OUT: one human key per machine suffices — S5 §4.4); OTel pipeline (OUT: `oc-usage --json` panel suffices — S6 §3).

**Genuine contradictions resolved:** (i) S1-A2 "wrap in durable workflow" vs S2 "no new daemon" → resolved as stateless CLI now, durable engine only at trigger; (ii) global-staleness invariant vs scope-shallow optimization → two-tier ruling (§3b); (iii) `docs-lint` cross-spec dup-`id` ERROR vs namespaced relaxation → ERROR stays until migration lands, then advisory cross-spec + ERROR on flat-path collision; (iv) "verify tracked" (commit-then-`dod-run` flow) vs untracked policy → untracked evidence + committed wave log (§3a); (v) orchestrator `max` (preset) vs `high` (observed 51/51 turns, report A1) → document `high` as intended, `max` explicit per-task TUI choice (S6 §5-A1); (vi) council kept vs value unproven → ration to high-stakes + 10-case value test (S6 §6).

## 3. Contested questions — rulings

- **(a) `verify/**` policy: UNTRACKED + `.gitignore` (default), wave log committed.** Rationale: global staleness makes tracked+re-wave ~14 min/commit for 16 contracts (`README.md:155-166`); evidence is reproducible via `dod-run`, the committed artifact is the wave manifest (`wave_id`, `git_head`, per-check exit). **Namespaced `verify/<slug>/<id>.json`, write-namespaced / read-namespaced-first-flat-fallback, fail-loud on foreign `spec_sha256`.** Rationale: flat store structurally wedges one contract in `VERIFY` (`docs/notes/dod-run-flat-store-collision.md:8-15`); fallback preserves readers during migration.
- **(b) Two-tier staleness + `dod-run --changed`: ADOPT as scheduling optimization, NOT as certification change.** `stale_scope` (did `scope.allow` inputs change?) drives what to re-run; `stale_cert` (global `ev_head≠HEAD ∨ dirty`, `README.md:85`) still gates `DONE`. Rationale: keeps the one-mental-model invariant (audit §5) while cutting the 14-min wave to ~4–5 min via dedup + `--changed` (S6 §1.6).
- **(c) Signed approvals: HMAC in P1, GPG later. Custody: human-only `0600` keyfile under `~/.local/share/opencode/.approvals.key` (outside agent `external_directory`, never in repo/env).** Rationale: `approved_by:"human"` is an unverified string today (`README.md:147-149`); HMAC is S-effort and closes casual forgery, while without UID-split it still moves trust to key custody (S5-F2 residual) — hence P1 not P0; GPG/multi-machine only when fleet trigger trips.
- **(d) Hash-chained audit (`prev_hash`, $H_n=\operatorname{sha256}(H_{n-1}\Vert \mathrm{canon}(entry_n))$): NOW (P0).** Rationale: S-effort (S4 §3.9), makes R6 counters and drift forensics trustworthy; labeled tamper-*evident*, never tamper-proof without external anchor (S5-F3).
- **(e) Scheduling: orchestrator-prose checklist + stateless wave CLI now; NO queue daemon, NO durable engine.** Change trigger: >20 active contracts, multi-machine, or runs exceeding day-scale → then admit `wave-run` daemon/Temporal-style wrapper (S2 §6; S4 §3.10).
- **(f) Sandbox: Stage-1 userspace hardening now; oclab kernel (bwrap-ro + uid-split) DEFERRED.** Forcing trigger: untrusted content touching write lanes, observed `bash`-heredoc/`relative_path` bypass exploit, or multi-tenant use (S5 §5; S1 §2.h).
- **(g) PBT/metamorphic DoD class: ADOPT NOW as named convention** (hypothesis profile + metamorphic script template + one worked example), not as framework. Full A4 formal only for narrow invariant-rich modules later (S1 §5-P1, §6.5).
- **(h) Orchestrator own-writes threshold: $N=30$ lines, single file, `.slim/spec/**` drafts only — else delegate.** Rationale: the 400-line `ROADMAP.md` hand-write (report B6) is the failure to prohibit; 30 lines keeps manager-vs-maker separation with a mechanical tripwire.

## 4. Prioritized roadmap (metric per item from S6 §3)

**P0 — trust anchor (correctness before speed).**
1. Parity harness `config/tools/gov/scope_vectors.json` + TS↔Py CI assert [audit-P1.1; README implicit] (S, metric: extra-dispatch rate → 0).
2. Fix TS harness isolation (`--approvals-dir` tmp, `scope` fixture, parse new output) [audit-P0-2] (S, metric: real gate blocks >0/canary green).
3. `dod-run`: `atomic_write` + readback + fail-loud foreign evidence [audit-P1-2] (S, metric: first-pass DoD rate).
4. `spec-revoke` bare-token fix (`STATUS_RE` parity with `mark_approved`) [audit §2-MAJOR-6] (S, metric: approval churn).
5. Audit `prev_hash` chain + boot canary + `OPENCODE_SPEC_GATE` provenance alert (S, metric: audit-chain break alerts).
6. Stage-1 reach closure: approvals/audit/config out of agent dirs; object-form `bash` maps (S–M, metric: real gate blocks / 0 self-grants).
7. `bin/preflight` + dispatch-fact wiring [report-B9] (S, metric: lane discipline turns, port re-diagnoses → 0).
8. Template fix: `tools/<task_slug>/**`, `dod.id` = slug-prefix rule, R6/evidence-v2 section, canon commands + port precondition [report-C1] (S, metric: cost per artifact, approval churn).
9. `spec-preflight` pre-approval pass (unique `dod.id`, scope sanity, canon, writer map) [report-F1] (S, metric: approval churn 3 rounds → 1).

**P1 — cost & assurance.**
10. Namespaced evidence migration + `docs-lint` rule relaxation [README-P1.6] (M, metric: wave staleness/commit).
11. Scope-shallow scheduling + `dod-run --changed` + `--fail-fast` [README-P1.4] (M, metric: wave staleness).
12. `wave-run` stateless dedup CLI (union `dod`, one owner per full suite, $H=1$ throttle, port/build locks) [README-P1.5] (M, metric: quota burn rate, 14 min → ~4–5 min).
13. `oc-usage` port + token/cost columns + quota config + docs [report-A3] (S, metric: quota burn, DRIFT).
14. Session-export fidelity fix (compress boundaries, error outputs, no tool-call leakage) (S–M, metric: compress coverage measurable).
15. HMAC-signed approvals + `approvalScan` verify (S–M, metric: approval churn/forgery probes).
16. PBT/metamorphic check class + example (S, metric: first-pass DoD rate on edge cases).
17. Denylist relabeled typo-guard + `of=`/`/*`/`$HOME` forms [audit-MAJOR-4] (S, metric: refused-command log clarity).

**P2 — productization.**
18. Installer + VERSION + CHANGELOG + CI (`pytest`, `node --test`, parity, tmp-project smoke) [README-P2.9/10] (M, metric: cost per artifact trend).
19. `.gitignore` (`verify/`, `__pycache__/`, `.venv/`) + `examples/` population [README-P2.11/12] (S, metric: first-pass DoD rate for newcomers).
20. Dedup `find_root`/fence-parser/resolvers into `spec_scope` [audit-MINOR-11/12] (S, metric: extra-dispatch rate).
21. ADR/guide sync pass (0001/0002/0004, APPROVED-vs-VERIFY, `opencode-go` source, `explore/general`) [audit-P1-3] (S, metric: generation drift incidents).

**Do NOT build (YAGNI):** durable-engine wrapper, microVM-per-session fleet, persistent priority queue / `spec-graph` scheduler, Sigstore/rekor provenance, OTel metrics pipeline, second-truth state files or R6 counters, full-suite-per-contract DoD (keep one owner), `uv run` canon dualism (ban the form).

## 5. First implementation increment — draft spec skeleton (P0 trust anchor)

````markdown
# Trust Anchor P0 — gate is friction, not a security boundary

**Status:** draft

| Field | Value |
|---|---|
| Slug | `trust-anchor-p0` |
| Owner | human (approve/revoke only) |
| Date | 2026-09-30 |
| Area | P0 trust boundaries (§5.1–5.3 of kit README) |
| Class | contract (grants mandate via `scope` only) |

## 1. Scope and Non-goals

Scope (P0 only):

- Remove `~/.config/opencode/**` and `~/.local/share/opencode/**` from agent-writable `external_directory` in `config/opencode.json`.
- Replace string-form `bash: "allow"` with object-form per-command maps in `config/oh-my-opencode-slim.json`; never grant agents `edit: {"*": "allow"}`.
- Document residual bypasses in gate (`bash`/heredoc/`python -c`, `approvals/`/`audit/` writability, `opencode.db` always-allow) and declare OS-isolation (`bwrap`/uid-split/ro-mount for `docs/**`) explicitly out of scope for this increment.
- Harden approval-record path handling shared by `spec_scope.py` consumers (no new crypto in P0).

Non-goals: GPG/HMAC approval signing, `prev_hash` audit chaining, per-scope staleness, `verify/<id>` namespacing, CI/packaging, `examples/` fill — all deferred to P1/P2.

## 2. Mini-ADR

Context: the gate intercepts file-tool targets only; `bash` has no file-targets and agents retain write access to the artifacts that constrain them (plugin source, approvals, audit, `permission` table). Decision: shrink the agent-writable surface by configuration (deny-by-default maps, minimal `external_directory`) and document the residual as untrusted-by-design, pushing real containment to the OS layer. Consequence: short-term friction (some agent workflows need explicit human steps); the gate remains a soft guardrail with audit value, not a boundary. Alternative rejected: extending the plugin to parse `bash` bodies — fragile, bypass-trivial, high false-positive cost.

## 3. Reference

Authoritative files: `config/plugins/spec-gate.ts` (decision order, exempt list), `config/opencode.json` (`permission.external_directory`), `config/oh-my-opencode-slim.json` (agent `permission` maps), `config/bin/spec_scope.py` (shared matcher), `config/AGENTS.md` (doctrine mirror of the same rules).

```scope
{"allow": ["config/plugins/spec-gate.ts", "config/plugins/__tests__/spec-gate.test.ts", "config/opencode.json", "config/oh-my-opencode-slim.json", "config/bin/spec_scope.py", "config/AGENTS.md"], "deny": ["docs/**", "config/command/**", "**/*.db", "**/approvals/**", "**/audit/**"]}
```

## 4. Evidence Path

`bin/dod-run --spec trust-anchor-p0` writes `verify/<id>.json` (evidence v2: `spec_sha256`, `git_head`, `tree_dirty`). `DONE` requires per check: `exit_code == 0`, matching `spec_sha256`, `git_head == HEAD`, `tree_dirty == false`. Commit everything outside `.slim/spec/**` and `verify/**` before `dod-run`; run under the compute fence (`nice -n 19 taskset -c 0,1 ionice -c3`, single-threaded vars, one heavy job at a time).

## 5. Definition of Done checklist

- [ ] `external_directory` no longer contains agent-writable config/approval/audit paths.
- [ ] No string-form `bash: "allow"`; no agent holds `edit {"*": "allow"}`.
- [ ] Gate fail-closed probes (unparseable writer targets, `docs/**` write) still blocked.
- [ ] Residual-bypass note committed in covered files (not in `docs/**`).
- [ ] `spec-status --spec trust-anchor-p0` reaches `DONE` on a clean tree.

```dod
{"checks": [{"id": "trust-anchor-p0-pytests", "cmd": "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 nice -n 19 taskset -c 0,1 ionice -c3 python3 -m pytest config/bin/tests -q"}, {"id": "trust-anchor-p0-docs-lint", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 config/bin/docs-lint --spec .slim/spec/trust-anchor-p0.md"}, {"id": "trust-anchor-p0-spec-status", "cmd": "config/bin/spec-status --spec .slim/spec/trust-anchor-p0.md"}]}
```

## 6. Autonomous phases

1. **Recon (explorer):** map current `external_directory` + agent `permission` maps; list string-form `bash` grants. 2. **Config shrink (fixer):** apply minimal `opencode.json` / `oh-my-opencode-slim.json` edits; mirror doctrine in `config/AGENTS.md`. 3. **Gate probes (cpp-expert):** extend `spec-gate.test.ts` fail-closed cases if behavior changed. 4. **Verify (python-expert):** `dod-run` once under throttle, then `spec-status`; stop after 3 consecutive failures on one check (R6) and ask the human.
````

## 6. Risks & unknowns

- Residual `bash`/heredoc bypass persists by design — this increment only shrinks surface, fixes nothing at OS level.
- `opencode.db` saved always-allow entries may silently override new config `deny` — needs human DB audit.
- Approval records stay forgeable (`sha256` match only); signing deferred, window remains open.
- Tightening `external_directory` may break legitimate agent workflows (approval/audit reads) — allowlist may need a human second pass.
- `spec_scope.py` shared matcher vs `spec-gate.ts` matcher drift could cause allow/deny divergence.
- Single `dod-run` wave on a dirty tree yields `tree_dirty=true` and blocks `DONE` — commit discipline required.
- Plugin/MCP changes need an OpenCode restart; stale-process evidence is a false-negative trap.

---

# Ф3 — Эмпирическая проверка организации работы (M1–M4)

**Зачем.** Ф1/Ф2 дали архитектуру из литературы и аудита. Ф3 проверяет *политики организации* численно: discrete-event симуляция + калибровка по реальной эвиденции kit + независимый враждебный аудит. Артефакты: `research/M1-model.md` (пространство политик/гипотезы H1–H7), `research/sim/` (`sim.py`, `params.json`, `test_sim.py` 13 инвариантов, `results/*`), `research/M2-simulation.md`, `research/M3-calibration.md`, `research/M4-review.md`.

**Модель.** Волна $T_{\text{wave}}\approx\frac1H\sum_{c\in\text{heavy}}T_c+\max_{l\in\text{light}}T_l$; двухуровневая свежесть
$$\text{stale}_{cert}=( \hat G_i \neq G(t))\lor d(t),\qquad \text{stale}_{scope}(i)=(\text{scope.allow}(i)\cap\Delta F\neq\emptyset);$$
$$\text{DONE}\iff a_i=1\ \land\ \forall j\big(e_{ij}=0\ \land\ \hat h_{ij}=h_i\ \land\ \text{fresh}_{ij}\big).$$
12 политик = точки в 6-осном пространстве (dedup, staleness∈{global,scope}, approval∈{per_contract,batch}, heavy, single_writer, sampling). Калибровка M3 сошлась: $\text{dedup}\ \approx-63\%$ heavy (реально) против $-65\%$ (модель); аналитическая волна $16\times53.4=854$ с $=14.2$ мин против измеренных $\approx14$ мин; first-pass $78.9\%$ против порога «$<80\%$».

**Итог M2 (до аудита):** лучший — **B+C**: wall $250.2\to203.4$ мин ($-19\%$), human approvals $19.3\to5.9$, цена $2.2\%$ ложных DONE. Консервативный — **B** (дедуп без shallow): $1.1\%$ риска, $-17\%$ wall.

**Поправки M4 (враждебный аудит; все ключевые числа воспроизведены, 17/17 ячеек CSV сошлись).**

| Гипотеза | Вердикт M4 |
|---|---|
| H1 дедуп | **держится**: suites $73.6\to6.5$, heavy $-65.2\%$, ранжирование устойчиво во всех свипах |
| H2 scope-shallow (C) | **отвергнута как сформулирована**: $+1.1$ п.п. риска (из них $0.44$ п.п. — потеря детекта), выигрыш всего $\sim3.4$ мин; допустима лишь как платная опция «$3$ мин за $+1$–$2$ п.п.» при неизвестном $p_{hidden}$ |
| H3 параллелизм (D, $H{=}2$) | **условна**: проигрыш — артефакт приоров контеншна; без контеншна B+D выигрывает. **B+C+D («фабрика») не выигрывает ни в одной из 5 ячеек** |
| H4 агрессивный сэмплинг (E) | **отвергнута**: $P(\text{false DONE})\le10^{-3}$ недостижим при полезных сбережениях; $10.4\%$ риска в базе |
| H5 батч-approve + pre-lint | **держится и единственный устойчив ко всем свипам**: $19.3\to5.9$ при том же wall; при медленном человеке A $622\to$ B $233$ мин |
| H6 изоляция (oclab) | **вне модели**, честно; симулятор о ней ничего не говорит |
| H7 экономика ($) | **отвергнута как метрика**: `$` не различает политики (все $\$5.2$–$\$5.9$, движимы реворком) и награждает пропуск дефектов |

**Итоговая рекомендация Ф3 (исправляет Ф2 в частях, не в основе).**

1. **Берём B (дедуп DoD) и H5 (pre-lint + `--all/--changed`)** — два выигрыша, устойчивых ко всем свипам и не покупаемых риском.
2. **C (scope-shallow staleness) — опция, не бесплатный выигрыш**: включать только когда человек дорог и есть бюджет риска; по умолчанию остаётся **двухуровневая модель** (scope → *что перезапускать*, cert → *что гейтит DONE*), но `DONE` по-прежнему гейтится глобальным `stale_cert`.
3. **$H{=}2$ (параллелизм) — отложить до измерения контеншна**; при тяжёлом asan-профиле и отсутствии контеншна он окупается, иначе — нет. «Фабрика» B+C+D сейчас не оправдана.
4. **Агрессивный сэмплинг и ранжирование по `$` — запрещены**; решения принимать по wall / human-interactions / риск.
5. **Абсолютные минуты — сравнительные, не прогноз**: они структурно завышены (verify не перекрывается с draft/impl) и приоры draft/impl/rework не измерены.
6. **$P(\text{false DONE})$ $1$–$2\%$ — нижняя граница** (занижение `false_detect` при незафикшенном дефекте + допущение идеального переноса детекта из общего suite + $p_{hidden}$ без данных).

**Что сильнее всего снимет оставшуюся неопределённость (следующие измерения, не симуляции):** распределение латентности одобрения человеком $S_a$ и эффект `--all` (в модели это главный рычаг: $622\to233$ мин); вторым — $p_{hidden}$ (границы $0\to2\%$ двигают ложно-DONE B+C $1.9\%\to4.0\%$). Это аргумент за P1-пункты roadmap `oc-usage` (телеметрия) и `spec-preflight` (pre-approval lint).

**Связь с oclab.** HARD-субстрат (bwrap/EROFS/seccomp) не проверяется этой моделью, но и не противоречит ей: он снимает H6-неопределённость, а не меняет ранжирование H1/H5. Запрос фич к oclab — `research/OCLAB-REQUEST.md` (черновик).
