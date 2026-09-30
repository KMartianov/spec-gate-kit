# S3 — Roles, Separation & Verification Independence in the "Project Factory"

> Workstream S3 of the R&D plan (`research/README.md`). Owner: `@oracle` (session `ses_f0c98fd77ffevGtAcMzh2ak905`). Persisted by the orchestrator.

## 1. Framing

The overarching R\&D question is not "does spec-gate work" but: what roster plus what information-flow rules make autonomous OpenCode output **trustworthy** without making the human the bottleneck. The kit answers one slice — *who may write what, when* — via a Zero-Code Gate (`config/plugins/spec-gate.ts`), human-only approvals, derived state, and artifact evidence. It deliberately does **not** answer *who may judge whom*: the audit (`docs/guides/repo-audit-2026-09-29.md:4-19`) shows per-agent permissions, test harnesses, and several "protections" already drifted into theater. This report models the full factory, separates creation from judgment, and names what the kit enforces mechanically vs. what survives only by prompt discipline.

Ground rule from the kit worth keeping regardless of mechanism:

$$\text{valid} \iff \operatorname{sha256}(\text{spec\_bytes}) = \text{record.spec\_sha256}, \quad \text{stale} = (\text{ev\_head} \neq \text{HEAD}) \lor \text{tree\_dirty}$$

`config/AGENTS.md:142-154`; `docs/adr/0002-external-approval-records.md:31-33`; `docs/adr/0004-dod-evidence-artifacts.md:49-59`; `README.md:81-86`.

## 2. Candidate roles & boundaries

| Role | Writes? | Receives | Must never receive/do |
|---|---|---|---|
| **Human (principal)** | `docs/**`, approvals, `GATE-OFF`, git commits | status reports, diffs, `verify/*.json` tails | never delegated: `spec-approve`, `spec-revoke`, `gate-off/on` (`config/AGENTS.md:132-141`) |
| **Orchestrator (workflow manager)** | delegates; small isolated edits itself | requirements, `spec-status --json` snapshot, digests | own >N-line artifacts; re-derive settled facts (`docs/guides/spec-driven-development.md:35-72`; notes `2026-09-28-orchestrator-improvement-report.md:106-116`) |
| **Intake/Decomposer** (today: orchestrator §1 + `spec-new`) | `.slim/spec/**` drafts only | raw request, repo map | code edits pre-approval |
| **Planner (spec author)** | draft contract incl. `scope`+`dod` fences | explorer/librarian digests, ADR refs | claim `DONE`; approve own spec |
| **Implementers: `@fixer`, `@cpp-expert`, `@python-expert`, `@ml-expert`** | only their `scope.allow minus deny` lane | spec §§1–6, file→writer map, command canon | touch `docs/**`, approvals, other lanes' files |
| **Recon: `@explorer` (`edit:deny`), `@librarian` (`edit:deny, bash:deny`)** | nothing (read-only) | question + path hints | implementation or verdicts (`config/oh-my-opencode-slim.json:49-89`) |
| **Verifiers: `@math-verifier` (`edit:deny`), `dod-run`+`spec-status` (machine), `docs-lint`** | throwaway `/tmp/opencode/**` scripts; `verify/*.json` only via `dod-run` | claim + domain + artifact paths | project source edits; grading without runnable evidence |
| **Reviewers: `@oracle` (`edit:deny`), `@council`** | review text only | diff + spec + evidence | write code under review; approve |
| **Integrator** (today: orchestrator §1 step 5) | conflict resolution, merge order | lane outputs + audit log | silently re-scope lanes |

Single-writer rule (kit gap, process fix): before parallel lanes, publish a **file → sole writer** map; cross-spec consistency (`scope`, command canon, unique `dod.id`) gets one pre-approval lint pass. Violations caused 3 rework rounds each invalidating approval (`2026-09-28-orchestrator-improvement-report.md:113-118,196-201`).

## 3. Independence mechanisms (model diversity, read-only, adversarial prompts)

1. **Read-only enforcement, two layers.** Gate read-only allowlist is exhaustive and terminal (`config/AGENTS.md:51-61`): unknown writers block fail-closed. Agent `permission` maps add a second layer: `explorer/librarian/oracle/council: edit:deny`; `math-verifier: edit:deny, bash:allow`; implementers `edit:allow, bash:allow` (`config/oh-my-opencode-slim.json:49-112,201-282`). Audit shows the second layer is **aspirational**: `fixer`/orchestrator have no block, `oracle` has no `bash:deny`, path-scoped per-agent permissions do not exist as a mechanism (`repo-audit-2026-09-29.md:43-49`).
2. **Adversarial verifier prompt.** `@math-verifier` prompt: "Your job is to falsify, not to please… Never assert without computation… `verified (symbolic)` / `verified (numeric on <domain>)` / `UNVERIFIED`" with exact code (`config/oh-my-opencode-slim.json:246-262`; `config/AGENTS.md:230-234`). Pattern to copy for all verifiers: verdict taxonomy + mandatory artifact + stated domain + counterexample duty.
3. **Model diversity (partial).** Implementers are all `opencode-go/deepseek-v4.1-flash` (collusion risk); verifiers differ: `oracle`+`math-verifier` on `muse-spark-1.3-contributor`, `librarian` on `glm-5.3-flash`, council on `glm-5.3` + `mimo-v2.6-pro` + `hy3` (`config/AGENTS.md:191-251`). Council prompt roles (architect/reviewer/pragmatist) force dissent axes, not consensus smoothing (`config/oh-my-opencode-slim.json:176-199`).
4. **Normative reference the agent cannot move.** `docs/**` refused before scopes, serena cache, and `GATE-OFF` (`config/AGENTS.md:67-73`); agent-requested doc changes go into spec/ADR, human applies them (`docs/guides/spec-driven-development.md:240-243`).
5. **Evidence the agent cannot assert.** `DONE` requires machine artifacts, never testimony:

$$ \text{DONE} \iff \text{valid approval} \land \forall c \in \text{DoD}: \exists\, \texttt{verify/}c\texttt{.json} \land \text{exit}=0 \land \text{sha-match} \land \text{fresh} $$

`config/AGENTS.md:155-168`; `docs/adr/0004-dod-evidence-artifacts.md:55-59`. `spec-status` is read-only multi-spec; `dod-run` refuses index/`undeclared`/archive without writing (`config/AGENTS.md:119-131`).
6. **No second truth.** State derived, never stored; R6 is a policy line ("stop after 3 consecutive failures…"), counted from the audit journal, never a mutable counter file (`config/AGENTS.md:142-154,169-173`; `docs/adr/0003-derived-lifecycle-state.md:45-84`). Audit trail `spec-gate.jsonl` per decision (`config/AGENTS.md:101-104`).
7. **Approval externality + flip-before-hash.** Record lives outside the worktree (`approvals/<rootHash>/<hash>-<slug>.json`); any spec edit invalidates it; status flip precedes hashing so text and record agree by construction (`docs/adr/0002-external-approval-records.md:24-49`; `docs/adr/0003-derived-lifecycle-state.md:55-66`).

## 4. Human checkpoint design

Checkpoints must sit where machines cannot bind themselves: (a) **contract approval** — `spec-approve` flips status, stamps, hashes post-flip bytes; re-approval of unchanged spec rewrites only the record (`config/AGENTS.md:105-118`); (b) **scope-bearing approval** — spec without valid `scope` approves with warning but grants nothing, fail-closed (`docs/guides/spec-driven-development.md:403-404,840-841`); (c) **pre-commit before `dod-run`** — else `tree_dirty=true` makes `DONE` unreachable (`config/AGENTS.md:155-168`); (d) **R6 stops** — contradiction, irreversible-loss risk, 3× same failure, env failure (`docs/guides/spec-driven-development.md:803-811`); (e) **revocation / opt-out** — `spec-revoke`, `gate-off/on`, global `OPENCODE_SPEC_GATE=off` are human-only (`config/AGENTS.md:132-141`). Batch ergonomics (`--all`, `--changed`, per-file report, no-stamp-rewrite without `--restamp`) exist because ≥12 manual approves per session was the measured friction (`2026-09-28-spec-approve-hardening-plan.md:26-34,66-74`; `orchestrator-improvement-report.md:164-174,196-201`). In-session `/spec-approve` runs in the client process, not as an agent tool (`config/AGENTS.md:139-141`).

## 5. Recommended roster + responsibility matrix

Keep 8 runtime roles; fold intake/decomposer/planner into orchestrator+spec-author lane and integrator into orchestrator step 5. New explicit role: **Evidence custodian** (owns `dod-run` invocation order, `verify/` hygiene, staleness triage) — currently implicit and the source of wave-cost pain.

| Function | R | A | C | I | Read-only? | Cost driver |
|---|---|---|---|---|---|---|
| Contract draft (`scope`+`dod`) | planner | human | oracle, explorer | implementers | no (`.slim/spec/**`) | dominant: ~70% of subagent spend on 6 drafts; 200–290k input + 50–70k reasoning each (`orchestrator-improvement-report.md:83-97`) |
| Approval | human | human | — | orchestrator | n/a (outside agent reach) | 1 command; batch with `--changed` |
| Implement lane | fixer/cpp/python/ml | orchestrator | oracle (design) | integrator | no (own lane) | `deepseek` implementers, $T{=}0.3$–$0.4$; throttle builds `-j2`, `ctest -j1` (`config/AGENTS.md:349-368`) |
| Math verify | math-verifier | orchestrator | — | planner | **yes** (`edit:deny`) | cheap tiny checks; laptop-only |
| Machine evidence | dod-run/spec-status | orchestrator/custodian | — | human | report yes; runner writes `verify/` | wave ~14 min/16 contracts; ~75–80% duplicate full-suite repeats (`README.md:153-166`) |
| Architecture review | oracle | orchestrator | council on high stakes | implementers | **yes** (`edit:deny`) | `xhigh` reasoning, $T{=}0.6$; call after 2+ failures |
| Consensus (high stakes) | council (3 models) | orchestrator | — | human | **yes** | ~3× single review; reserve for ambiguous/costly calls |
| Integrate + certify | orchestrator | human | oracle | all | merge writes only | pre-approval lint removes rework loops |

## 6. Anti-patterns

1. **Self-verification.** Implementer running its own `dod` reading and declaring `DONE`; fixer/cpp/python/ml share one model family, so cross-grading among them is collusion, not review. Fix: verifier must differ in model **and** write capability; `DONE` read from artifacts by a third party.
2. **Rubber-stamping.** Verdict without artifact ("looks correct"). Fix: math-verifier contract — labeled verdict + code + output + domain, else `UNVERIFIED`.
3. **Verification theater.** Documented kit cases: `dod-run` substring denylist missing `of=`, `/*`, `$HOME`, `.` forms (`repo-audit:112-117`); per-agent allowlist claimed but absent in hook (`docs/adr/0001:73-75`); `.slim/state.json`+R6 counter gameable via `bash`/check-rename (`docs/adr/0003:27-43`); stale TS harness asserting on removed CLI output and approving scopeless fixtures while polluting the real store (`repo-audit:89-102`). Fix: each guard needs a negative test or an honest "typo-guard only" label.
4. **Same-model collusion.** Draft, implement, and review all on `deepseek-v4.1-flash` collapses independence. Fix: route review/verify to `muse-spark` and council trio; track `provider/model#variant` + `DRIFT` via `oc-usage` (`orchestrator-improvement-report.md:83-97`).
5. **Second truth.** Any cached verdict/state file alongside the bytes it summarizes (status file, R6 counter, flat `verify/<id>.json` shared by two specs — the latter permanently wedges one spec in `VERIFY`, `docs/notes/dod-run-flat-store-collision.md:10-15`). Fix: derive; namespace evidence `<slug>/<id>` with fail-loud on cross-owner overwrite.
6. **Doc-fixing-to-code.** Agent "aligning" `docs/reference` to buggy code. Fix: GOV-2 immutability + human-owns-docs rule; residual `bash`/Serena-path risk acknowledged, kernel ro-mount deferred (`config/AGENTS.md:178-183`; `docs/adr/0001:69-77`).
7. **Self-approval / self-unlock.** Agent writing approval records, flipping status, creating `GATE-OFF` inside `.slim/spec/**` (blocked because marker lives outside it), or invoking human CLIs. Fix: records outside worktree + hash binding + CLIs off `$PATH` + TUI-client execution (`docs/adr/0002:39-49`; `orchestrator_append.md:46-58`).

## 7. Open questions

1. Where should **model-diversity be mandatory** (review + math-verify always non-implementer model?) vs. advisory, given quota/cost pressure and single-key (`OPENROUTER_API_KEY`) fragility (`config/AGENTS.md:378-380`)?
2. Who owns the **Evidence custodian** — orchestrator skill or separate lane — and does shallow staleness (invalidate only on `scope.allow` change) plus `dod-run --changed` preserve trust while cutting the ~14-min wave (`README.md:153-157`)?
3. Should approvals become **signed** (GPG/HMAC, UID-split) or is hash-match + external store + audit enough, given `approved_by:"human"` is an unverified string (`README.md:147-149`)?
4. Flat `verify/<id>.json` vs. namespaced `<slug>/<id>`: migration + back-compat fallback path (`dod-run-flat-store-collision.md:64-74`; `README.md:167-169`)?
5. `verify/**` policy: untracked, tracked+re-wave, or artifact-store + wave log — and who pays the recommit cost (`README.md:170-172`)?
6. Tamper-evident audit (`prev_hash` chain / append-only) — worth it before kernel isolation, or theater without it (`README.md:173-174`)?
7. Enforceable **single-writer + command-canon + port-preflight** in dispatch prompts vs. relying on orchestrator discipline (`orchestrator-improvement-report.md:118-121,217-224`)?
