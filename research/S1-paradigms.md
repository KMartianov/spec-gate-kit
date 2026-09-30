# S1 — Paradigm Survey: Organizing Autonomous Agentic Software Development for Quality & Reliability

> Workstream S1 of the R&D plan (`research/README.md`). Owner: `@librarian` (session `ses_f0c9a0887ffecFte93HTyLHnsG`). Persisted by the orchestrator.

## 1. Framing

Our kit encodes one specific answer to the trust question: **no code before a human-approved spec; writes scoped by `scope` mandates; completion earned via `verify/<id>.json` evidence with hash-bound validity; state derived, never stored**. This survey asks whether that answer is the best-known of the paradigm space, externally validated as of 2026-09. The external literature is organized by *where trust is manufactured*: (i) in the **process topology** (plans, roles, review), (ii) in the **spec-as-contract** layer, (iii) in **mechanical verification** of outputs, (iv) in the **execution substrate** (durability, isolation), and (v) in **attestation** of artifacts. A key empirical backdrop: GitClear's 211M-line study finds refactoring share of changed lines collapsed from 25% (2021) to <10% (2024) with 8× growth in duplicated blocks [GitClear 2025](https://www.gitclear.com/ai_assistant_code_quality_2025_research); agent commits over-produce weak mock-heavy tests [arXiv:2602.00409](https://arxiv.org/abs/2602.00409); Veracode's 2026 snapshot shows only ~56% of generated code passing security checks. Throughput is no longer the bottleneck — **verifiable quality per change** is; ironically our own audit log shows review/verify time rising 91% as PR size grows [Faros analysis](https://www.faros.ai/blog/ai-software-engineering). Any "project factory" must therefore invest disproportionately in gates *after* generation, not only *before* it.

## 2. Pattern catalog

| # | Pattern | Problem solved | Evidence of effectiveness | Cost / complexity | Citation |
|---|---|---|---|---|---|
| 1 | **Orchestrator + parallel subagents (breadth fan-out)** | Context saturation on broad tasks | +90.2% over single-agent on research evals; token usage explains 80% of variance | ~15× tokens vs chat, ~4× vs single agent [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system) | [Anthropic eng. blog](https://www.anthropic.com/engineering/multi-agent-research-system) |
| 2 | **Plan→Act→Replan split (plan-then-execute)** | Drift in long-horizon tasks; cost of per-step reasoning | 57.6% WebArena-Lite / 81.4% WebVoyager; ReWOO 5× token saving, +4% acc; LLMCompiler up to 3.7× latency / 6.7× cost vs ReAct | Plan-review loop overhead; plan staleness needs re-planning triggers | [arXiv:2503.09572](https://arxiv.org/abs/2503.09572), [arXiv:2305.18323](https://arxiv.org/abs/2305.18323), [arXiv:2312.04511](https://arxiv.org/abs/2312.04511) |
| 3 | **Plan-as-artifact with least privilege (Plan-then-Act security)** | Integrity of multi-step agentic work under injection | Framework argues plan separation + task-scoped tools + sandboxing improves integrity; mostly positional evidence, no SOTA eval | Low if it reuses existing plan artifact | [arXiv:2509.08646](https://arxiv.org/abs/2509.08646) |
| 4 | **Spec-driven development (SDD): spec as executable source of truth** | Code-before-consent; doc↔code drift | Institutional momentum: [GitHub Spec Kit](https://github.com/github/spec-kit) (~129k stars, 38 agent integrations), AWS Kiro, Microsoft guidance; SDD preprint formalizes specs as validation gates | Spec authorship cost; risk of spec-as-shame (unverified spec text) | [arXiv:2602.00180](https://arxiv.org/abs/2602.00180), [Fowler analysis](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) |
| 5 | **Enforced spec-first + TDD (spec + immutable tests, live DB branches)** | Spec text alone doesn't enforce (frameworks in #4 don't execute gates deterministically) | Consort: gates in code, not prose; claims enforced immutability prevents agent test-weakening | High: DB-branch CI, additional runner | [arXiv:2609.09671](https://arxiv.org/abs/2609.09671) |
| 6 | **Role-architecture pipelines (MetaGPT/ChatDev-style SOPs)** | Naive agent chains lose information | MetaGPT: 85.9/87.7 Pass@1 on HumanEval/MBPP; but leakage and benchmark-fragile; code often short, weak cross-file logic | Low-medium; degradation at real scale | [arXiv:2308.00352](https://arxiv.org/abs/2308.00352), [arXiv:2307.07924](https://arxiv.org/abs/2307.07924) |
| 7 | **Multi-agent review (diverse reviewers + aggregation)** | Hallucinated diffs; low-recall review | LinkedIn: 63.9% acceptance, 100% on concurrency bugs; CRT architecture resists injection (1.42% attack success vs single-agent) | Medium; pseudo-review smell (human becomes rubber stamp) risk | [InfoQ LinkedIn](https://www.infoq.com/news/2026/08/linkedin-ai-code-review/), [zylos CRT study](https://zylos.ai/research/2026-04-22-autonomous-code-review-multi-agent-pr-analysis/), [arXiv:2607.13196](https://arxiv.org/abs/2607.13196) |
| 8 | **Property-based / metamorphic testing in CI** | Oracle-free verification of agent-written code; coverage of edge cases | Anthropic agent-inferred PBT found real bugs in numpy/scipy/pandas [Anthropic PBT](https://www.anthropic.com/research/property-based-testing); PBT-guided LLM generation improvement [arXiv:2506.18315](https://arxiv.org/html/2506.18315v1) | Low-medium; requires property authorship discipline | [PracticalAdvocacy](https://medium.com/@VectorWorksAcademy/property-based-testing-in-the-age-of-ai-coding-a-paradigm-shift-97b83051f8b8) |
| 9 | **Formal verification / proof-carrying code from NL specs** | Trust beyond tests (math-provable properties) | Dafny verification success 68%→96% in 1yr (per [Berkeley RDI position paper](https://rdi.berkeley.edu/assets/position-auto-sd.pdf)); niche yet maturing | High (expertise, tooling, verbose contracts) | [VeriBench](https://cs.stanford.edu/people/brando9/professional_documents/papers/NeurIPS_2026_VeriBench.pdf), [Re:Form](https://arxiv.org/html/2507.16331v4) |
| 10 | **Durable execution engine (Temporal-style)** | Recovery, replay, long-running runs surviving crash | Production agents (OpenAI, Cursor, Klarna…) on Temporal; graph-durability via plugin; checkpointing + interrupt semantics | Medium-high (host service, activity semantics, idempotency discipline) | [Temporal LangGraph plugin](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution), [LangGraph vs Temporal debate](https://www.langchain.com/resources/langgraph-vs-temporal), [Diagrid "agentic durable execution"](https://www.diagrid.io/blog/what-is-agentic-durable-execution) |
| 11 | **Supply-chain attestation (SLSA / in-toto / Sigstore)** | Provenance of artifacts: who produced what, reproducible build metadata | Mature for binaries; GitHub OIDC attestation in a YAML stanza; rekor transparency log | Low for hosted CI; draft-stage for AI-generated code provenance | [SLSA FAQ](https://slsa.dev/spec/v1.2/faq), [in-toto attestation framework](https://github.com/in-toto/attestation), [nolabs AI-provenance sketch](https://nolabs.ai/blog/sigstore-ai-agent-provenance) |
| 12 | **Sandbox / isolation of agent execution** | Escape, RCE, resource abuse | Firecracker (125 ms boot, 5 MB overhead) = gold standard for untrusted code; gVisor good middle; containers insufficient; Anthropic uses bwrap/Seatbelt | Ops burden varies; cheapest strong option = hypervisor-per-session | [northflank guide](https://northflank.com/blog/how-to-sandbox-ai-agents), [wincent gist sandbox taxonomy](https://gist.github.com/wincent/2752d8d97727577050c043e4ff9e386e), [Anthropic sandbox runtime (medium)](https://medium.com/@earlperry562/how-every-major-tech-company-is-sandboxing-ai-agents-differently-f41b65f14d8a) |
| 13 | **Ensemble / multi-model consensus on quality decisions** | Variance, hallucinated completeness | Reddit-scale anecdotes: 80%→90% SWE-bench w/ reviewer-agent; industry anecdotal, avoids Review-Buddy narrowing biases | High cost (multi-model inference); hard to integrate with deterministic evidence | [arXiv:2607.13196](https://arxiv.org/html/2607.13196v1), [r/ClaudeAI experiment](https://www.reddit.com/r/ClaudeAI/comments/1qi2gh0/i_ran_100_swebench_tests_comparing_1_agent_vs_2/) |
| 14 | **Continuous-AI / Agentic CI (GitHub Actions, safe outputs, merge gates)** | Sickness of "agent proposes, human merges" being ad-hoc | Official GitHub pattern: read-only agents + safe-output jobs + policy gates; still in preview | Low-medium; quality is gate-quality-dependent | [GitHub Agentic Workflows](https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/), [GitHub Next project](https://githubnext.com/projects/agentic-workflows/) |

### 2.a Multi-agent orchestration & roles

Verdict: heavily validated for **breadth-oriented research**, weakly validated for **depth-oriented coding**. Anthropic's 15× token multiplier is honest about when it's worth it; MetaGPT / ChatDev show stronger SOP-driven pipelines but degrade on real repos. Our current roster (explorer / librarian / oracle / fixer / cpp-expert / python-expert / math-verifier / council) is aligned to the "specialized subagents + orchestrator" convergence. Nobody replicates our council across models; this is more like a consensus pattern than an industry standard — cheap credibility but expensive runtime.

### 2.b Plan→Execute→Verify

Validated as RePlan-Loops: Plan-and-Act, ReWOO, LLMCompiler. Our `spec-new → scope-write → dod-run → DONE` is essentially Plan-then-Act with (a) an extra human gate between plan and act, (b) missing an executor/rollback primitive. **Missing**: an equivalence to "re-plan on evidence mismatch" — our staleness check invalidates, but no agent-owned loop reactively re-plans.

### 2.c Spec/contract-driven development

Spec Kit & Kiro show vocabulary convergence with ours; but both lack:
- A machine-enforced write-scope mandate (`scope` fence) — unsurpassed: nobody in the wild has path-scoped *write* gates.
- A derived-state lifecycle — both Spec Kit / Kiro track phases manually.
- Evidence v2 binding: `spec_sha256 ∧ git_head ∧ tree_dirty ∧ exit_code == 0`.
Prior work is more "spec-as-instructions," ours is "spec-as-executed-contract."

### 2.d Property/formal/metamorphic verification

Strong evidence this should be a **first-class DoD check type** in our kit (not just pytest/ctest). Our current `dod` block can trivially carry `hypothesis run py` or a bwrap-isolated metamorphic check; a first-class primitive would yield better specificity. Veracode's 56% security pass-rate and GitClear's refactoring collapse are the adverse-effect data motivating this.

### 2.e Durable execution / workflow engines

Loosely mapped in our kit (we execute doD checks synchronously, no durable plan graph). LangGraph+Temporal (or Inngest-style `step.run` boundaries) skips this problem cleanly and is production-proven. **Adopt opportunity:** treat per-contract approval → implement → dod-run as a durable stateful workflow, not a shell waterfall; benefit is crash recovery + long-running parallel lane work.

### 2.f Autonomous SWE research

SWE-bench Verified has saturating per-model numbers (mini-SWE-agent 79+ with Claude 4.5/4.6 Opus, ~$0.36-0.75/run) [swebench.com](https://www.swebench.com/), [steel.dev leaderboard](https://leaderboard.steel.dev/leaderboards/swe-bench-verified/). But real-repo success is much lower (SWE-bench Mobile: ≤12% best config; scaffolding matters more than model: a 6× gap OpenCode vs Cursor on the same model) [arXiv:2602.09540](https://arxiv.org/html/2602.09540). "One model + scaffolding" overpromises; harness engineering is the actual lever ([framing](https://www.faros.ai/blog/harness-engineering)).

### 2.g Provenance / attestation

SLSA L2-L3 is achievable in an afternoon via GitHub OIDC attestations [guide](https://aquilax.ai/blog/supply-chain-artifact-signing-slsa). For agent-generated artifacts, "what model produced this" is invisible in current SLSA; draft predicate extensions exist ([nolabs sketch](https://nolabs.ai/blog/sigstore-ai-agent-provenance)). Our `verify/<id>.json` is morally a **link** attestation (in-toto's link statement!) but lacks signature / counterparty transparency log; the biggest gap is that our approval record is forgeable by design (P0 weakness, acknowledged).

### 2.h Sandboxing

Converging on: **Firecracker/Kata microVM > gVisor > container > naive (bubblewrap-only)** for untrusted code; Anthropic's Claude Code uses bwrap/Seatbelt as a pragmatic host-local boundary. Our P0 plan (bwrap + uid-split) puts us at Level ~1.5; a robust "project factory" aiming at adversarial robustness needs microVMs or gVisor per session.

## 3. Comparison vs our spec-gate design

**Strengths we possess that the external paradigm space lacks / does poorly:**

1. **Machine-readable write mandate** (`scope` fence + glob denominator + fail-closed parse): no equivalent found in Spec Kit, Kiro, OpenSpec, BMAD; their "guardrail" is prose-in-the-prompt, not a tool-interval constraint.
2. **Derived lifecycle state** with cryptographic staleness: `DONE ⟺ validApproval ∧ ∀ᵢ verify(i).exit=0 ∧ sha(spec)=sha(spec_approved) ∧ git_head=HEAD ∧ ¬dirty`. No external framework has this invariant binding of approval/evidence/HEAD.
3. **Spec-file hash as certification subject.** Our invalidation rule ~ GitClear → not "we assume approval," we bind it.

**Weaknesses / gaps vs the strongest external patterns:**

1. **No post-generation deep verification primitive.** Our DoD checks are human-curated shell commands; no property-based / metamorphic / fuzz / contract-check classes; no "critic agent" reviewed-against-spec for semantic compliance. GitClear + Veracode data says this is the highest-leverage missing class.
2. **No durable execution.** We run checks synchronously in-process per spec; no crash-resume for long/huge check volumes; no durable wait on multi-lane work (we do have background jobs, but they're not replayable).
3. **Approval ledger is forgeable.** Directly undermines our central claim of "human-only." External pattern #11 (Sigstore/in-toto) solves this; ours is a flat assertion. Our lack of signature kills the unforgeability of "approval event happened."
4. **Verification is check-count, not risk-weighted.** We do not model the (per-check pass rate) → per-artifact reliability product; GitClear's leakage + Veracode's failure rates suggest the DoD list should be quality-weighted / coverage-aware, not just exhaustive.
5. **No attested continuous pipeline.** No release/PR attestation, no transparency log, no tamper-evident audit journal (we flag this as P0).
6. **Sandbox boundary is soft.** Acknowledged ADR-0001 "soft guardrail" honest limitation; external state-of-the-art moved past "we wrote a hooks plugin" into "we put the agent in a microVM."

**Cost / complexity positioning:** our approach is dramatically cheaper than Temporal/Firecracker stacks, and cheaper than Spec Kit (we don't require new agents / new scaffolds, just file conventions). But the pattern in the field is shifting: nobody thinks "jest as DoD" is sufficient — external verification primitives are getting *more* mechanical, not less.

## 4. Candidate target architectures for a "project factory"

| ID | Architecture | Composition | Cost | Best when |
|---|---|---|---|---|
| **A1. "Belt & Braces" (evolutionary)** | Keep spec-gate + add (i) bwrap/uid-split sandboxed DoD executor, (ii) a PBT/metamorphic check class, (iii) signed approval records (HMAC/minisign with key outside agent reach), (iv) tamper-evident audit chain | High fit with current code | Low | Slow ship-focused single-machine work |
| **A2. "Spec Factory with durable lanes"** | A1 + Temporal-wrapped per-contract workflow (`plan → implement → verify → attest` as a Temporal workflow); background lanes + durable waits on human approval | Medium | Workloads where runs exceed day-scale or multiple parallel projects |
| **A3. "MicroVM factory for untrusted agents"** | Firecracker/gVisor per session for generation; spec-gate inside the VM as friction layer, not boundary; event-streamed evidence out; attestation chain via Sigstore | Medium-high | Adversarial / multi-tenant / open-source-facing workflows |
| **A4. "Verified codegen" (formal / metamorphic-heavy)** | Diagram as: spec → proof artifacts (Dafny/Lean) → implementation → PBT/metamorphic; "clean-room" refactor pattern used by researchers, used selectively per-contract | High | High-assurance modules (math/crypto kernels, parsing, protocol codecs) |
| **A5. "Continuous-AI repo"** | GitHub Agentic Workflows style: agents as CI jobs with safe-output gates + merge-gate policy; spec-gate demoted to repo-local friction | Low | Public / OSS / CI-native projects; weaker for local-only heavy compute work |

Combinations: (A1 ⊕ A4) gives *strong local quality for key components without exploding complexity* — highest ROI for our project. (A2 ⊕ A3) is the industry consensus trajectory [Temporal LangGraph](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution) + [Firecracker sandboxing consensus](https://northflank.com/blog/how-to-sandbox-ai-agents); relevant only when the factory runs multi-project fleets.

## 5. Recommendation

**Keep and harden the paradigm; borrow three external primitives; do not replace the paradigm.**

- SDD, in our reading of the field, survives an important shift: from "spec-as-source" (which everyone claims) to **"spec-as-executed-gate"** — the direction of [arXiv:2602.00180](https://arxiv.org/abs/2602.00180), [Consort](https://arxiv.org/abs/2609.09671). We're ahead on write-scope enforcement, slightly behind on spec re-execution (our spec changes should re-run gates, not just invalidate).
- **Priority 1:** Add property-based / metamorphic / (optionally Dafny-class) checks as named DoD classes; allow spec to declare required *coverage class* so semantic regressions get caught instead of (or alongside) known case checks.
- **Priority 2:** Regenerate the approval/evidence ledger with **Sigstore-style signed attestation binding** `(human identity, spec_sha, git_head, dod timestamp)` — we're already 80% there: in-toto's *human-review* link statement is essentially our approval record.
- **Priority 3:** Wrap the per-contract cycle in a **durable workflow**; our derived state is already the right substrate for this. Cheap payoff for crash-resume + parallel-lane orchestration.
- **Not recommended (for this tool):** deep microVM infrastructure (we are not multi-tenant, single-user, low-risk boundary available via bwrap/uid-split). Formal-verification-first is high-value but only for narrow, invariant-rich modules; going full-A4 would be overkill for a Python/C++ CV/ML shop.
- Meta-lesson from 2026 SWE literature: **scaffolding, not model choice, is the quality lever** (Gemini 3.1 Pro ≈ 80.6% vs DeepSeek V4 Plus ≈ 78.8% vs Claude Opus 5 ≈ 97% — model matters; but the 6× spread from scaffolding shows the harness dominates on real repos). Our kit's harness quality metrics should therefore be tracked as a first-class output of `spec-status` and `docs-lint`, not just success rates.

## 6. Open questions

1. **What's the minimal credible "spec re-executed" gate?** (re-run lints, run `dod-run --changed`, replay-tolerance analysis vs. hard re-approval) — empirical sizing needed.
2. **How much per-check quality signal can a harness absorb before diminishing returns?** GitClear suggests coverage/diversity > volume; we can calibrate our 155-check wave against a metric like "checks passing that would fail under a 5% injected-bug corpus."
3. **Is `approval-as-in-toto-attestation` adoptable without new tooling?** We'd need a local `cosign`-equivalent signing path against a Spec-statement object; UDP/HMAC fallback discussed in ADR-0002.
4. **Sandbox selection under a laptop budget:** Firecracker is overkill for us, gVisor has a sysctl dependency not yet tested on our kernel; pragmatic middle is bwrap-with-ro-mount + uid namespace; need explicit envelope tests.
5. **Formal verification at what tier?** For our CV/ML codebase, high-value targets are dataloaders, image ops, and the spec/status invariants (e.g., $$\text{stale}(e) = (\text{ev\_head} \ne \text{HEAD}) \lor \text{tree\_dirty}$$) — but the integration cost of Dafny/Lean with Python-class code is high; sympy-based property/sanity classes might be the practical ceiling.
6. **Cost-optimal role diversity:** our roster of 10 roles vs. Anthropic's 3-role orchestrator pattern — how many specialized agents earn their 15× token multiplier in practice? Ready to re-evaluate with a `task_message`-based lane-caching experiment.

---

**Bound check:** ~200 lines, covered all 8 mandated areas (a–h), 14-row catalog with citations, verdicts per pattern in §2, explicit adopt/replace recommendations in §5.
