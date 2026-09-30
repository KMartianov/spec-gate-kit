# S6 — Economics, Context Management & Observability

> Workstream S6 of the R&D plan (`research/README.md`). Owner: `@librarian` (session `ses_f0c969706ffe54YTMiZgezgcfP`). Persisted by the orchestrator.

Sources: repo docs (`README §5`, `docs/notes/2026-09-28-orchestrator-improvement-report.md` §3 = «the report», `docs/guides/repo-audit-2026-09-29.md` = «the audit»), `config/AGENTS.md`, `config/oh-my-opencode-slim.json`, live `bin/oc-usage`, plus external: [OpenCode Go pricing](https://opencode.ai/docs/go/), [Anthropic: effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [Anthropic: multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system).

---

## 1. Cost model & routing policy

**Real pricing exists (official, 2026-09).** OpenCode Go is a flat subscription ($10/mo Go, $40/mo Plus) whose *usage limits are dollar-denominated per model*, split as 5 h window = 20 % of monthly limit, week = 50 %, month = 100 %. Token prices for the models actually configured in `oh-my-opencode-slim.json` (per 1 M tokens, in/cached-read/out):

| Model (`opencode-go/…`) | in | cached read | out | monthly $ limit | req/5 h (official est.) |
|---|---|---|---|---|---|
| `deepseek-v4.1-flash` off-peak | $0.15 | **$0.003** | $0.60 | $60 | 26 000 |
| `deepseek-v4.1-flash` peak | $0.30 | $0.006 | $1.20 | $60 | 26 000 |
| `glm-5.3-flash` | $0.15 | $0.03 | $0.50 | $60 | 6 320 |
| `muse-spark-1.3-contributor` | $0.10 | $0.002 | $0.20 | $60 | 45 300 |
| `glm-5.3` (council.architect) | $1.40 | $0.26 | $4.40 | **$15** | **220** |
| `mimo-v2.6-pro` (council.reviewer) | $0.435 | $0.0036 | $0.87 | $15 | 3 250 |
| `hy3` (council.pragmatist) | $0.14 | $0.035 | $0.58 | $60 | 4 300 |

The oc-usage `QUOTA` table (26000/6320/45300/220/3250/4300 …) is **exactly the official request estimate per 5 h** — it is a dollar budget in disguise: a "request" is priced at the official typical usage (DeepSeek: 410 in + 71 300 cached + 310 out ⇒ $\$4.6\cdot10^{-4}$/req off-peak, and $26\,000 \times \$4.6\cdot10^{-4} = \$12 = 0.2\cdot\$60$). So quota pressure ≡ dollar burn at *official average context*, and agents with bloated contexts burn the window faster than oc-usage's request counts suggest.

**Cost model.** For a session (or role):
$$C = p_{\text{in}}N_{\text{in}} + p_{\text{c}}N_{\text{c}} + p_{\text{out}}(N_{\text{out}}+N_{\text{reason}})$$
with quota consumption $Q = C / (0.2\,B_{\text{month}})$ of the 5 h window. Two measured facts calibrate it:

- Orchestrator session: $N_{\text{in}}=448{,}396$, $N_{\text{c}}=4{,}708{,}096$, $C\approx\$0.17$. Off-peak prediction $= 0.15\cdot0.448 + 0.003\cdot4.71 + 0.6\,N_{\text{out}} \approx \$0.087+out$; peak prediction $\approx \$0.175$. Measured $0.17 ⇒$ the session ran at **peak pricing** (peak = 01:00–04:00 and 06:00–10:00 UTC Mon–Fri; off-peak all other hours incl. weekends — [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)).
- Cache-read dominance: subagents accumulated $N_{\text{c}}\approx60.4$ M vs $N_{\text{in}}\approx 18\times245\text{k}\approx4.4$ M ⇒ replay ratio
$$r = \frac{N_{\text{c}}}{N_{\text{in}}} \approx 13.7$$
i.e. each turn re-pays the whole context ~14×. With DeepSeek's $p_{\text{c}} = 0.02\,p_{\text{in}}$, cached tokens are nearly free ($2\cdot10^{-6}\$/\text{token off-peak}$); the *marginal* cost is reasoning/output tokens, not context length. On `glm-5.3-flash` $p_{\text{c}} = 0.2\,p_{\text{in}}$ and on `hy3` $0.25\,p_{\text{in}}$ — the same 200–290 k context costs ~10–12× more per replay there.

**Measured session economics (report §3):** 18 subagent sessions ≈ \$1.00; 6 draft-spec sessions ≈ \$0.70 ⇒ \$0.117/draft vs \$0.056/other ($\approx2\times$), with input at 200–290 k (near context limit) and 50–70 k reasoning tokens per draft session. The 6 draft sessions were template-rewriting work (report §4.3) — i.e. **~70 % of subagent spend bought re-derivation the template should have pre-packaged**.

**Routing policy (concrete):**
1. **Difficulty cascade, cheap-first with escalation** (cf. FrugalGPT pattern, [arXiv:2305.05176](https://arxiv.org/abs/2305.05176)): explorer/librarian/fixer on flash tier (`deepseek-v4.1-flash` high / `glm-5.3-flash` high) — current setup is already right. Escalate to `xhigh`/`max` variants only on failure signals (R6 trigger, oracle review request), never by default: a `max` variant multiplies reasoning tokens (50–70 k/session observed) which, at $p_{\text{out}}$-pricing, is the dominant term of $C$.
2. **Off-peak scheduling.** Since limits are dollar-based, off-peak DeepSeek lanes get the *same* request quota at half the budget burn — effectively 2× quota for heavy lanes. Schedule batch DoD waves and impl lanes outside 01:00–04:00 / 06:00–10:00 UTC workdays; weekends are always off-peak.
3. **Variant discipline (A1).** The orchestrator ran `high`, not the preset's `max`, because omos leaves the orchestrator model to the session — document this as intended, and make `max` an explicit, per-task TUI decision rather than an assumed default.
4. **Council rationing.** `glm-5.3` has a $15 monthly cap ⇒ 220 req/5 h ≈ 1/118 of a fixer's budget per request. Council must stay "high-stakes only" (as AGENTS.md says) and the orchestrator should check `oc-usage --json` before invoking it; consider `mimo-v2.6-flash` ($0.14 in / 30 100 req/5 h) as a cheaper architect substitute when the council pool is drained.
5. **Batch approvals (F2/E1).** ≥12 manual `spec-approve` rounds each followed by invalidated approvals and stale evidence ⇒ each invalidation cascades into a re-approval + re-run wave (see §1.below). The now-shipped `--all`/`--changed` plus the **pre-approval cross-spec lint** (F1) convert a 3-round approval loop into 1 round — this is the single largest human-time *and* agent-cost lever, because every approval invalidation re-opens the whole VERIFY state.
6. **Wave dedup (README P1.5).** 155 checks/wave, identical commands run 14–15×; $u\approx0.20$–$0.25$ of wave time is unique work. With owner-scoped DoD commands + wave parallelism 2–3: $T' \approx u\,T_{\text{wave}} + \text{tail}$ ⇒ 14 min → ~4–5 min, and 75–80 % of the wave's *agent supervision* disappears with it.

---

## 2. Context-management policy

The measured smoking gun: **0 `compress` calls across 18 subagent sessions at 200–290 k input** (report §3) — subagents ran to the context ceiling unsqueezed. External pattern-check agrees with the fix direction: Anthropic's guidance is that context is a finite "attention budget" subject to *context rot*, and prescribes compaction, structured note-taking, and sub-agent isolation ([effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)); tool-result clearing is called out as the cheapest, safest compaction.

**Policy:**
1. **Compaction rule applies to every role, not just the orchestrator** — close-and-compress each completed work range; never compress an empty/no-op range (B2). Add a token threshold (e.g. compress when $N_{\text{ctx}} > 150$ k) so it is mechanical, not judgmental.
2. **Subagent briefing contract** (fixes B7/B8/B11): every dispatch brief must contain — (a) *ready decision order* (the implement-G1 brief re-dumped the spec and the agent burned ~3000 lines reverse-deriving its own plan, then the export truncated); (b) the *single command canon* from exactly one source (the `uv run` vs `.venv` conflict was caused by the dispatch prompt itself and cost one extra fixer dispatch, 61 token-replacements); (c) a *known-facts list* marked "do not re-verify" (port `127.0.0.1:19280` was re-diagnosed in 6 sessions — B9; make it a `bin/preflight` fact); (d) *target-catalog contents including non-spec files* (the ROADMAP-is-an-index lesson was delivered late, in the only `task_message` of the session); (e) a *single-writer map* (file → sole owner) before any multi-lane run.
3. **Artifact handoff over telephone-game** ([multi-agent research system, appendix](https://www.anthropic.com/engineering/multi-agent-research-system)): subagents write full reports/evidence to files and pass lightweight references to the orchestrator; the orchestrator consumes digests. This directly fixes B4 (orchestrator re-read files already in subagent briefs) and B5 (same fact derived ≥3×): one `spec-status --json` run is an *artifact*, subsequent turns cite it.
4. **Delegation thresholds**: reading via `shell` banned (B3 — 17 `shell` vs 14 `read`); own writes > $N$ lines delegated (B6 — the orchestrator hand-wrote a ~400-line ROADMAP.md); one `wait_for_user` per turn (B1).
5. **Just-in-time retrieval, not pre-loading** (Anthropic pattern): keep CLAUDE/AGENTS.md lean, let agents pull file content on demand via `read`/`grep` instead of stuffing briefs — the failed G1 brief shows pre-stuffing *and* under-stuffing both fail; the durable rule is references + decision orders, not content dumps.
6. **Cross-session memory**: the `memory` MCP knowledge graph is the right place for durable facts (port state, env quirks, legacy lint noise — report §7), but its entries must carry evidence pointers, since agent-written memory is unverifiable by construction.
7. **Time-boxing long lanes**: S4 = 73 turns, G1-draft = 78, G1-impl = truncated-without-report. Briefs must demand an intermediate report every $k$ turns and declare an abort budget; the human should not be the monitor (§6.4).

---

## 3. Observability & metrics spec

**Existing instruments** (all read-only, good bones): (a) `audit/spec-gate.jsonl` — every gate decision `{ts, sessionID, tool, targets, root, decision, reason, spec}`; (b) `bin/oc-usage` — per-role request counts in a rolling 5 h window vs the §7/§1 quota matrix, observed `provider/model#variant`, **DRIFT** flag on config-vs-observed mismatch, `--json`; (c) `verify/<id>.json` evidence v2 with `spec_sha256`, `git_head`, `tree_dirty`, `duration_s`, `tail`; (d) `spec-status` derived state `INTAKE → SPEC_DESIGN → APPROVED → VERIFY → DONE`; (e) `session-note.ts` exports.

**Gaps (measured):** oc-usage is undocumented (A3) and **absent from the kit snapshot** `config/bin/` — the kit ships the doctrine but not the meter; its quotas are hardcoded (audit NIT) — now justifiable as a mirror of the official table, but it should validate against `https://opencode.ai/zen/go/v1/models` or fetch limits from console; it counts *requests, not tokens/dollars*, though `opencode.db` rows carry token data (the report derived token counts from exports, so the DB has them) — extending oc-usage with $N_{\text{in}},N_{\text{c}},N_{\text{out}}$ columns is the highest-value single change; the audit journal is not tamper-evident (README P1.8 — add `prev_hash` chain); session export loses `compress` boundaries, error outputs, and leaks tool-call fragments into user turns (D3) — **every future post-mortem is blind without fixing this first**.

**Metric spec (proposed, all derivable from existing sinks):**

| Metric | Definition | Source | Alert |
|---|---|---|---|
| quota burn rate | $C_{\text{est}}(t)/0.2B_{\text{month}}$ per model, from tokens | oc-usage+DB tokens | > 60 % before a batch ⇒ reschedule off-peak |
| DRIFT | observed model/variant ≠ preset | oc-usage | any ≠ ok ⇒ stop, reconcile |
| compress coverage | compresses / sessions with $N_{\text{in}}>100$k | DB | 0 like the measured 18 sessions ⇒ policy failure |
| replay ratio $r$ | $N_{\text{c}}/N_{\text{in}}$ per session | DB tokens | $r>15$ with no compress ⇒ runaway |
| cost per artifact | \$ per spec reaching DONE | oc-usage + spec-status | trend upward across projects ⇒ template/prompt regression |
| first-pass DoD rate | checks passing on first `dod-run` | verify/*.json | < 80 % ⇒ DoD or scope written wrong |
| approval churn | approvals invalidated by spec edits per batch (F1: 3 rounds, ≥12 approvals) | approval records mtime | > 1 per batch ⇒ pre-approval lint missing |
| extra-dispatch rate | fixer dispatches per lane not in plan (B8: 1) | audit + session logs | > 0 ⇒ canon-source conflict |
| generation drift | CJK-in-Russian prose incidents (A2: 2) | export scan | recurring ⇒ lower orchestrator $T$: $0.6\to0.4$ |
| real gate blocks | `[SPEC-GATE BLOCKED]` events (measured: **0 real**, all in prose) | audit jsonl | 0 over a full session ⇒ gate no-op'd |
| wave staleness | checks invalidated per commit (all-16 per commit today; README P1.4) | verify/*.json vs git log | full wave per commit ⇒ adopt scope-shallow staleness |
| lane discipline | turns per lane (S4:73, G1-draft:78, G1-impl: abort) | exports | > 60 or truncated ⇒ time-box breach |

**Dashboards/alerts:** a single `oc-usage --json` → jq/HTML panel is enough (per-role quota %, DRIFT, token columns, totals). Alerts worth automating: (1) window > 60 % before a planned heavy batch; (2) DRIFT ≠ ok; (3) audit-journal hash-chain break; (4) `tree_dirty=true` at `dod-run` (prevents DONE); (5) zero-compress sessions. External analogue: OpenTelemetry GenAI semantic conventions ([opentelemetry.io/docs/specs/semconv/gen-ai](https://opentelemetry.io/docs/specs/semconv/gen-ai/)) for token/usage metric names if the kit ever emits real OTel.

---

## 4. Feedback loop to improve the factory

The kit already has a working loop — measure → post-mortem → patch → (implicitly) re-measure — proven by the 2026-09-28 report (8 of its top-8 fixes shipped same-day). Formalize it into five stations:

1. **Capture:** fixed session export (D3 first — without compress boundaries and error outputs the loop's raw data is corrupt) + audit journal + oc-usage snapshots per project phase.
2. **Post-mortem:** orchestrator-led (or a dedicated read-only auditor role) report like the 2026-09-28 one: quantified findings with log line citations, ranked by leverage. Anthropic's practice matches: "start with ~20 real queries; effect sizes are large enough to see immediately" ([multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)).
3. **Patch:** edits go to prompts/templates/CLI — note the honest asymmetry: `~/.config/opencode/**` is *exempt from the gate*, so the factory improves itself **outside its own approval discipline**. Mitigation: treat the kit repo (`spec-gate-kit`) as the spec-gated home of every config change — patch the kit, sync, restart (README §3) — so factory self-improvement passes through the same gate it enforces on clients.
4. **Replay validation:** before shipping a prompt/template change, replay a small fixed eval set (the failed briefs + canonical commands from the last post-mortem) on the cheap tier; accept only if first-pass DoD rate and extra-dispatch rate improve.
5. **Re-measure:** `oc-usage --json` deltas + next post-mortem; retire fixes into AGENTS.md (the report's §2 "already fixed — do not re-recommend" pattern is exactly right; keep it).

Failure-loop protection is R6 (stop after 3 consecutive failures on one check) — with the audit journal as the counter source of truth.

---

## 5. Recommendations (ranked by leverage)

1. **Extend `oc-usage` with token/cost columns** (`opencode.db` has them) + official dollar-limit awareness, and **ship it in `config/bin/`** + document it (closes A3, audit #7/NIT). Converts the whole §1 model from theory to a running number.
2. **Fix session export fidelity first** (D3): compress boundaries, error outputs, no tool-call leakage — precondition for every metric in §3.
3. **Off-peak lane scheduling** — free 2× on DeepSeek quota/budget; encode peak hours in AGENTS.md throttling section.
4. **Subagent compaction mandate + time-box + intermediate reports in every dispatch brief** (0/18 compresses; lanes of 73–78 turns).
5. **Pre-approval cross-spec lint** (`scope`, canon commands, unique `dod.id`) — kills the approval-churn cascade (3 rounds × 6–12 approvals × full stale waves).
6. **Wave dedup + owner-scoped DoD commands** — 14 min → 4–5 min per certification wave (README P1.5, already spec'd).
7. **Hash-chain the audit journal** (`prev_hash`) — cheap, makes R6 counters and drift forensics trustworthy.
8. **Model/privacy review of `muse-spark-1.3-contributor`**: official docs state it **trains on your prompts/completions and is not ZDR** (Meta contributor tier) — oracle and math-verifier route all code and specs through it. For proprietary workloads either accept explicitly per project or swap oracle to a ZDR model (e.g. `deepseek-v4.1-flash` max, ZDR monthly-renewed; DeepSeek ZDR "valid through 2026-10-31" — needs a monthly re-check).

---

## 6. Open questions

- **No per-token receipts.** Is per-request token usage exposed in `opencode.db` rows for *both* request and *response* tokens, or only request metadata? (Determines whether oc-usage can compute $C$ exactly or must estimate from official per-request token profiles.)
- **Quota semantics drift.** "Usage limits may change as we learn" (official docs) — oc-usage's hardcoded QUOTA will silently rot; should it fetch limits from `https://opencode.ai/zen/go/v1/models` (if the API exposes them) or accept staleness with a freshness banner?
- **Peak-hour measurement.** Off-peak pricing halves budget burn — but does the *quota meter* also discount off-peak requests, or is the 5 h allowance fixed at typical-mix pricing regardless of hour? (The $12=0.2\cdot\$60$ arithmetic above used off-peak prices and matched exactly, suggesting quota already assumes off-peak — verify with one controlled window.)
- **Variant economics unquantified.** Does `high→max/xhigh` on these providers multiply only reasoning tokens, or also change cache behavior? Needs an A/B on one brief.
- **`compress` fidelity under compaction.** The export shows compression produces real summaries but empty `startId/endId` — is any evidence-grade information lost in-compression? Un-measurable until D3 is fixed.
- **Council value-per-dollar.** 220 req/5 h on the architect seat: is three-councillor consensus measurably better than one `oracle` pass on the same question? No data exists yet; design a 10-case comparison.
- **Constitutional drift.** `variant` and temperature are per-role constants in JSON, but the orchestrator's effective variant follows the session `/model` (A1) — should omos pin the orchestrator model explicitly and accept losing TUI flexibility, or keep the session override and treat DRIFT on `orchestrator` as expected-`None`?
