# AGENTS.md - OpenCode Configuration (Polyglot C++ / Python, CV/ML/DS)

This is the user-level OpenCode configuration directory (`~/.config/opencode`).
It targets a **CV / ML / DS / systems-programming** workflow in **Python + C++**,
coordinated by the `oh-my-opencode-slim` orchestrator (preset `big-pickle`).

Host: **OpenCode v2.0.15** (binary `opencode`).

## Project Info

| Field | Value |
|-------|-------|
| Type | Polyglot: Python + C++ |
| Domains | Computer Vision, Machine Learning, Data Science, systems programming |
| C++ | C++17/20/23, CMake (targets, presets, FetchContent), CTest, vcpkg/Conan |
| C++ safety | ASan/UBSan/TSan, valgrind, UB/leak/race prevention |
| Python | 3.12.12 in `~/ml_base/.venv` (numpy, scipy, pandas, polars, sklearn, sympy, torch 2.13+cu130, matplotlib) |
| Math | sympy 1.14 (symbolic), numpy/scipy (numeric cross-checks) |
| Notebooks | JupyterLab 4.6.3, kernel `uv-ml-base` |
| Orchestration | oh-my-opencode-slim, preset `big-pickle` |
| **Compute policy** | **This is a laptop. Never run training / heavy GPU / large-data jobs here. User runs heavy work manually on a cluster; agents produce cluster-ready scripts.** |

## Mathematical Notation (mandatory for every agent)

All agents must write mathematics in **proper LaTeX** and use LaTeX as the
canonical form for storing and transferring formulas.

- Inline math with `$...$`; display equations with `$$...$$`.
- **Never** emit ASCII/Unicode pseudo-math. For example, write
  $$\delta_\ell = \left(W_{\ell+1}^{\top}\,\delta_{\ell+1}\right)\odot\sigma'(z_\ell), \qquad \frac{\partial L}{\partial W_\ell} = \delta_\ell\, a_{\ell-1}^{\top}$$
  and **not** `δ_ℓ = (W_{ℓ+1}ᵀ δ_{ℓ+1}) ⊙ σ′(z_ℓ)`.
- Use LaTeX for all derivations, proofs, and for formulas stored/transferred in
  files, artifacts, tool payloads, reports, commit messages, and agent-to-agent
  messages (Markdown, `.tex`, Jupyter Markdown cells, docs).
- Enforced via append prompts: `oh-my-opencode-slim/<agent>_append.md`
  (orchestrator, explorer, librarian, oracle, fixer, council, cpp-expert,
  python-expert, math-verifier, ml-expert).

## Doc-Driven Development (Zero-Code Gate) — MANDATORY

In any project that contains a `.slim/spec/` directory, every agent-tool write is
checked against the **per-spec mandate** (`plugins/spec-gate.ts`): it is allowed
only when covered by the `scope` fence of an *active, human-approved contract*,
and is **always refused** for `docs/**`.

- **Trigger:** any non-trivial task (≈ >3 files, or a change to interfaces /
  contracts / schemas) in a gated project.
- **Writable surface before approval:** `.slim/spec/**` only (drafts; the
  `archive/**` zone is part of it). Approval alone no longer unlocks the root —
  a spec without a `scope` fence grants **nothing** (fail-closed, GOV-1).
- **Gate decision order** (`tool.execute.before`; every step is terminal):
  1. kill switch `OPENCODE_SPEC_GATE=off` (global, returns before any parse; no
     audit);
  2. read-only allowlist (allowed outright): `read`, `grep`, `glob`, `list`,
     `ls`, `ast_grep_search`, `search`, `webfetch`, `fetch`, `websearch`,
     `todowrite`, `todoread`, `task`, `subagent`, `skill`, `question`,
     `task_status`, `task_result`, `task_cancel`, `task_message`, `task_revoke`,
     `task_revive`;
  3. target extraction — a writer whose paths cannot be parsed is blocked
     **fail-closed** (`apply_patch`/`patch` without paths, unknown writer without
     parseable paths);
  4. exempt paths (`~/.config/opencode/**`,
     `~/.local/share/opencode/approvals/**`,
     `~/.local/share/opencode/audit/**`, `/tmp/opencode/**`);
  5. `<root>/.slim/spec/**` — always writable, including `archive/**` (putting a
     spec into the archive needs no mandate and grants none);
  6. **`docs/**` — always refused** (GOV-2): before scopes, before the serena
     cache and before `GATE-OFF`, for `edit`/`write`/`multiedit`/`apply_patch`/
     `patch` **and** the serena MCP writers (`replace_content`,
     `replace_in_files`, `replace_symbol_body`, `insert_before_symbol`,
     `insert_after_symbol`, `rename_symbol`, `safe_delete_symbol`). Reason
     `docs-immutable`; a human edits `docs/**` in an editor or relaunches with
     the global kill switch;
  7. `<root>/.serena/**` — writable (agent cache);
  8. `<root>/.slim/GATE-OFF` — writable, but it **never** opens `docs/**`;
  9. mandate: the target is covered by some `allow` pattern and by no `deny`
     pattern of an *active approved contract* in `<root>/.slim/spec/*.md`
     (non-recursive); mandates of several contracts are unioned, `deny` wins;
 10. otherwise `[SPEC-GATE BLOCKED]` with the reason
     (`docs-immutable` / `no-mandate` / `deny:<pattern>` / `no-approval` /
     `inactive-spec`) and the human hint.
- **`scope` fence (the only mandate).** First fenced block whose info string is
  exactly `scope`, JSON body `{"allow": [...], "deny": [...]}`; glob semantics:
  `*` (any run without `/`), `?` (one non-`/` char), `[abc]`/`[a-z]`/`[!abc]`,
  `**` as a whole component (zero or more components; `a/**` also matches `a`).
  A missing or invalid fence, bad JSON/types, unsafe patterns (absolute, `~`,
  `\`, `..`, empty) or an empty `allow` grant **nothing**. Editing the spec —
  including its `scope` — changes the hash and **invalidates** the approval.
- **File classes in `.slim/spec/` (GOV-7).** The status line declares the role:
  `roadmap`/`index` token ⇒ portfolio **index** (not a contract: no mandate, no
  `dod` circuit, no lifecycle state — `ROADMAP.md` is one); any other token ⇒
  contract; no status line ⇒ `undeclared` (not a contract, fail-closed). An
  approval on an index/`undeclared` file is harmless but useless, and no
  approval can change the class. `docs-lint` gives an index zero ERRORs
  (at most a WARNING about an ignored `scope` fence).
- **Archive (GOV-6).** `.slim/spec/archive/**` is the inactive zone: moving a
  spec there = retire *without delete* (spec, `verify/*.json` and the approval
  record stay on disk; the approval simply stops granting). Gate, `spec-status`
  and `docs-lint` ignore the archive; the approval-directory records of
  archived specs are dead by location.
- **Audit trail:** every gated decision is appended to
  `~/.local/share/opencode/audit/spec-gate.jsonl` as
  `{"ts","sessionID","tool","targets","root","decision","reason","spec"}` —
  e.g. `reason: "allowed-via:<slug>"` / `"deny:<pattern>"` / `"docs-immutable"`.
- **Approval is human-only.** Never create, fake, or "self-approve" a record,
  and never run the human-only CLIs yourself. The human runs:
  `~/.config/opencode/bin/spec-approve <your-spec>`, where `<your-spec>` is a
  bare slug (resolved as `cwd/.slim/spec/<slug>`, then `<slug>.md`, then up the
  ancestor chain), a path, or a directory; **with no argument it only previews**
  (`--list`), `--all` approves every contract of the project and `--changed`
  skips the ones that are already valid. It flips the spec status line to
  `approved` and stamps
  `- **Утверждено:** <ISO8601> (human)`, **then** hashes the post-flip payload
  into `~/.local/share/opencode/approvals/<rootHash>/<16hex>-<slug>.json`. Editing
  the spec afterwards changes the hash and **invalidates** the approval; a second
  approval of an unchanged spec rewrites only the record, never the spec, so
  existing evidence stays valid (never use `--restamp` casually: it rewrites the
  stamp, changes the bytes and drops `DONE → VERIFY`).
- **An agent MAY run:** `bin/spec-new <name>` (scaffold a project: spec from
  `templates/spec-template.md`, the Diátaxis tree, `docs/adr/`, `README.md`,
  `.gitignore`, `git init`), `bin/spec-status [<path>] [--spec <slug|path>]
  [--json]` (read-only derived state; **multi-spec**: by default it reports
  every active contract and prints `index:`/`undeclared:` info lines, `--json`
  is an array, `--spec` selects one — index/undeclared/archive only that way,
  with `role`/`active`/`scope`/`worktree`), `bin/dod-run [--spec <slug|path>]`
  (execute the approved DoD checks → `verify/<id>.json`; only active contracts
  have a `dod` circuit — index/undeclared/archive are refused without writing
  evidence), `bin/docs-lint [<path>] [--spec <slug|path>] [--json] [--quiet]`
  (lints contracts only; also errors on a DoD check `id` duplicated inside one
  spec or shared by two contracts, because the flat `verify/<id>.json` store
  would be overwritten and one of them could never reach `DONE`),
  `bin/spec-preflight [<path>] [--spec <slug|path>] [--json] [--quiet]` and
  `bin/wave-run [<path>] [--spec <slug|path>]... [--dry-run] [--json]
  [--only <id>]... [--timeout <sec>]` (both read-only w.r.t. the repository:
  `spec-preflight` is the pre-approval consensus lint — it never writes and never
  executes; `wave-run` defaults to `--dry-run`, executes only with `--execute`,
  and does so exclusively by delegating to `dod-run`).
- **Human-only CLIs** (`~/.config/opencode/bin/`, not on `$PATH`): `spec-approve`
  (`<slug>|<path>|<dir>`, `--all`, `--changed`, `--list`, `--restamp`, `--strict`,
  `--approvals-dir PATH`; no argument only previews and never writes),
  `spec-revoke` (`<slug>|<path>|<dir>` or `--all`; reverts the status and deletes
  **only** the records of the specs it actually reverts — never the whole
  project's; `--list` previews, `--approvals-dir PATH` retargets the store),
  `gate-off` / `gate-on`
  (create/remove `.slim/GATE-OFF`). The human may also type
  `/spec-approve <spec>` in the TUI (`command/spec-approve.md`; the shell block
  runs in the client process, not as an agent tool).
- **Task state is derived, never stored.** There is no `.slim/state.json` and no
  `r6` counter. `bin/spec-status` computes `INTAKE → SPEC_DESIGN → APPROVED →
  VERIFY → DONE` read-only from the spec bytes, the approval records and
  `verify/*.json`; `DISCOVERY` and `AUTONOMOUS_EXEC` are prose only. Editing the
  spec invalidates the approval **and** the evidence — the same `sha256` rule.
  `DONE` requires every declared check to have `verify/<id>.json` with a matching
  `spec_sha256`, `exit_code == 0`, `git_head == HEAD` **and** `tree_dirty ==
  false` (evidence v2, GOV-4); legacy evidence without `git_head`, or evidence
  from another revision / from a dirty tree, is **stale** and yields `VERIFY`,
  never `DONE` (each check carries a `stale` flag; the report shows the current
  `worktree.head/dirty`). Templates: `templates/spec-template.md`,
  `templates/adr-template.md`; orchestrator-facing rules in
  `oh-my-opencode-slim/orchestrator_append.md`.
- **DoD block:** the spec carries a fenced block whose info string is exactly
  `dod`, with JSON body `{"checks":[{"id","cmd"}]}`. `bin/dod-run` executes it
  (destructive commands are refused before execution, default timeout 900 s,
  contract specs only) and writes `verify/<id>.json` — schema v2:
  `{check, cmd, exit_code, started_at, finished_at, duration_s, spec,
  spec_sha256, tail, git_head, tree_dirty, scope_sha256}` — which **is
  committed**: it is proof, not junk. The attestation triple is captured once
  before the first check; commit everything outside `.slim/spec/**` and
  `verify/**` **before** `dod-run`, otherwise `tree_dirty=true` and `DONE` stays
  unreachable. `bin/docs-lint` lints contracts only (index → at most a WARNING,
  undeclared → exactly one ERROR), validates the `scope` fence (broken form =
  ERROR, missing/empty = WARNING) and errors when a DoD check `id` collides
  inside one spec or across two contracts (the flat `verify/<id>.json` store
  would be overwritten, so one of them could never reach `DONE`).
- **R6 (a policy line, not a counter):** stop and ask the human after three
  consecutive failures on the same check, on a spec/contract contradiction, on a
  risk of irreversible data loss outside the worktree, or on a critical
  environment failure. Count from the audit journal if you must — a mutable
  counter file is bash-writable and resettable by renaming the check.
- **Kill switch:** start OpenCode with `OPENCODE_SPEC_GATE=off` (the global
  escape hatch, `docs/**` included). The `.slim/GATE-OFF` marker is per project
  and deliberately does **not** open `docs/**`.
- **Rollback:** `rm ~/.config/opencode/plugins/spec-gate.ts` + restart.
- **Honest limitation:** this is a **soft guardrail, not a security boundary** —
  `bash` (`python -m *` is allowlisted) plus the `spec-new`/`dod-run` shell paths
  all sit outside it. Residual risk: an MCP writer may pass a path that resolves
  from its own server root rather than the session directory (serena
  `relative_path`), so the checked path can differ from the written one.
  Kernel-level read-only mounting belongs to the deferred oclab Stage 3.

## Agents

Model IDs mirror `oh-my-opencode-slim.json` (preset `big-pickle`). `T` is the
sampling temperature fixed by the Doc-Driven spec §7 and tuned to each role's
quota pool.

| Agent | Role | Model (`opencode-go/…`) | Variant | `T` |
|-------|------|------------------------|:-------:|:---:|
| orchestrator | Planning, delegation, synthesis | `deepseek-v4.1-flash` | `max` | 0.6 |
| oracle | Architecture, risk, code review, simplification | `muse-spark-1.3-contributor` | `xhigh` | 0.6 |
| explorer | Fast codebase recon | `deepseek-v4.1-flash` | `high` | 0.2 |
| librarian | External docs / library research | `glm-5.3-flash` | `high` | 0.2 |
| fixer | Bounded implementation | `deepseek-v4.1-flash` | `high` | 0.3 |
| council | Multi-model consensus (`@council`) — synthesizer | `deepseek-v4.1-flash` | — | 0.5 |
| cpp-expert | Modern C++ / CMake implementation, memory safety, performance | `deepseek-v4.1-flash` | `max` | 0.4 |
| python-expert | Python implementation: scientific stack, notebooks, reproducibility | `deepseek-v4.1-flash` | `max` | 0.4 |
| math-verifier | Independent verification of math claims (symbolic/numeric), read-only | `muse-spark-1.3-contributor` | `xhigh` | 0.5 |
| ml-expert | ML/CV/DS methodology, experiments, evaluation, cluster-ready pipelines | `deepseek-v4.1-flash` | `high` | 0.4 |

`designer` and `observer` are globally disabled, so image attachments are not
analyzed. If you change a model or temperature, update **both** this table and
`oh-my-opencode-slim.json`.

**Variant semantics (verified live 2026-09-27).** `variant` is honoured by
OpenCode v2 and maps to the provider's reasoning-effort setting. For
**subagents** omos writes `model` + `variant` from this preset, so the table
above is what actually runs (probe: `python-expert` persisted
`variant: "max"`; `oracle` persisted `xhigh`). For the **orchestrator** omos
deliberately leaves `model` unset so the session's `/model` choice wins — the
orchestrator's effective variant therefore follows the *session model*, not the
preset's `variant: max`; pick a variant in the TUI (`/model`) if you want one.
`temperature` is applied for every agent, the orchestrator included.

### C++ agent (`@cpp-expert`)
Per-call instructions: `oh-my-opencode-slim.json` → `agents.cpp-expert.prompt`;
routing block: `agents.cpp-expert.orchestratorPrompt` (starts `@cpp-expert`).
Skills: `simplify`, `modern-cmake`, `cpp-sanitizers`, `cpp-profiling`,
`cpp-python-interop`. MCP: `serena`.

### Python agent (`@python-expert`)
The deprecated Python Expert pack (`.opencode/`) has been **removed**; global
skills live in `skills/`. Python work is owned by the `python-expert` custom
agent. Skills: `simplify`, `notebook-verify`, `sympy-verify`,
`scientific-python`. MCPs: `serena`, `jupyter`.

### Math verifier (`@math-verifier`)
Read-only (`edit: deny`, `bash: allow`). Verifies derivations/formulas/invariants
with sympy + numeric cross-checks and counterexample search. Every verdict is
labeled `verified (symbolic)` / `verified (numeric on <domain>)` / `UNVERIFIED`,
with the exact code. Use it whenever a mathematical claim must be *trusted*.

### ML agent (`@ml-expert`)
Owns experiment methodology: leakage-free splits, metrics, ablations,
determinism, training hygiene. Skills: `simplify`, `scientific-python`,
`ml-experiment`. MCP: `hf`. Output must be cluster-ready; no local training.

### Council
`@council <question>` runs three councillors in parallel and synthesizes a single
answer with a consensus confidence rating. Preset `balanced`:

| Councillor | Model (`opencode-go/…`) | Variant | `T` | Focus |
|-----------|------------------------|:-------:|:---:|-------|
| architect | `glm-5.3` | `max` | 0.6 | Architecture, boundaries, maintainability |
| reviewer | `mimo-v2.6-pro` | — | 0.5 | Correctness, bugs, edge cases |
| pragmatist | `hy3` | `high` | 0.4 | Simplicity, scope, cost/benefit |

Use it for high-stakes or ambiguous decisions, not routine work.

## MCP Servers

Registered in `opencode.json` → `mcp`; distributed per agent via `mcps` arrays in
`oh-my-opencode-slim.json`. **Restart OpenCode after changing them.**

| MCP | Type | Purpose | Assigned to |
|-----|------|---------|-------------|
| `serena` | local | Symbolic navigation/editing for large C++/Python monorepos | orchestrator, explorer, fixer, oracle, cpp-expert, python-expert |
| `jupyter` | local | Create/read/edit and **execute** notebook cells (Datalayer server) | orchestrator, python-expert |
| `hf` | remote | Hugging Face models/datasets/Spaces/papers discovery | librarian, ml-expert |
| `arxiv` | local | Literature search + LaTeX source reading | librarian |
| `memory` | local | Cross-session knowledge graph (`memory.jsonl`) | orchestrator |
| `context7`, `gh_grep` | remote (built-in) | Library docs + GitHub code search | librarian |

Prerequisites:
- **serena**: `uv tool install -p 3.13 serena-agent` (installed). Command:
  `serena start-mcp-server --context ide --project-from-cwd`.
- **jupyter**: needs a running JupyterLab with `jupyter-collaboration` +
  `ipykernel`. `JUPYTER_URL` задан в `opencode.json` литерально
  (`http://127.0.0.1:8888`) — это не секрет. `JUPYTER_TOKEN` берётся **только из
  окружения** (`{env:JUPYTER_TOKEN}`); литерального токена в `opencode.json` нет и
  быть не должно. Токен выдаёт `bash tools/jupyter_up.sh` (в проекте Diplom: при
  пустом `JUPYTER_TOKEN` генерирует `openssl rand -hex 16`, печатает
  `JUPYTER_URL`/`JUPYTER_TOKEN` и поднимает JupyterLab строго на `127.0.0.1:8888`
  из корня проекта); OpenCode нужно запускать из того же окружения. Если Jupyter
  уже был поднят со старым токеном — сменить токен (перезапуск через
  `tools/jupyter_up.sh`), старый считается скомпрометированным.
  ```bash
  # внутри проекта Diplom используется conda `optflow_env`, а не ~/ml_base/.venv
  bash tools/jupyter_up.sh
  ```
  Without a running server the `jupyter` MCP will fail to connect.
- **hf**: no token configured by default; run `opencode mcp auth hf` (or set
  `HF_TOKEN` and add an Authorization header in `opencode.json`) for gated assets.
- **arxiv** uses `uvx arxiv-mcp-server`; **memory** uses `npx -y
  @modelcontextprotocol/server-memory` (both auto-fetch on first run).

## Skills

### Local custom skills (`skills/*/SKILL.md`)

| Skill | Assigned to | Purpose |
|-------|-------------|---------|
| notebook-verify | python-expert | Deterministic `.ipynb` verification: nbconvert execute, nbval, papermill, jupytext, nbstripout |
| sympy-verify | python-expert, math-verifier | Symbolic + numeric verification of math claims via subprocess |
| scientific-python | python-expert, math-verifier, ml-expert | numpy/scipy/pandas/polars/sklearn correctness, reproducibility, performance |
| ml-experiment | ml-expert | Leakage-free splits, metrics, ablations, determinism, cluster-ready training |
| modern-cmake | cpp-expert | Target-based CMake, presets, FetchContent, CTest, export |
| cpp-sanitizers | cpp-expert | ASan/UBSan/TSan/MSan, valgrind, report triage |
| cpp-profiling | cpp-expert | perf, callgrind/cachegrind, Google Benchmark, cache-friendly layout |
| cpp-python-interop | cpp-expert | pybind11/nanobind, GIL, zero-copy numpy, scikit-build-core |

### oh-my-opencode-slim (bundled)

| Skill | Assigned to | Purpose |
|-------|-------------|---------|
| simplify | oracle, orchestrator, fixer, python-expert, ml-expert, cpp-expert | Behavior-preserving simplification |
| codemap | orchestrator, explorer | Hierarchical repository mapping |
| clonedeps | orchestrator | Local dependency source mirroring |
| deepwork | orchestrator | Heavy/complex coding-session workflow |
| verification-planning | orchestrator | Design project-specific evidence before implementation |
| reflect | orchestrator | Review repeated work, suggest reusable workflow |
| worktrees | orchestrator | Safe git-worktree lane management |
| oh-my-opencode-slim | orchestrator | Plugin configuration / self-improvement guidance |

Usage: `skill(name="notebook-verify")`

### Removed: Python Expert pack (`.opencode/`)

The deprecated, inert `.opencode/` pack was deleted; global skills live in
`skills/`. Do not recreate it.

## Subagents

| Subagent | Source | Use For |
|----------|--------|---------|
| cpp-expert | `oh-my-opencode-slim.json` | C++/CMake implementation, memory safety, performance |
| python-expert | `oh-my-opencode-slim.json` | Python/scientific implementation, notebooks |
| math-verifier | `oh-my-opencode-slim.json` | Independent math verification (read-only) |
| ml-expert | `oh-my-opencode-slim.json` | ML/CV/DS methodology and experiment design |

## Configuration Files

| File | Purpose |
|------|---------|
| `opencode.json` | Core: providers, plugin registration, **`mcp` servers**, native agent toggles, LSP |
| `oh-my-opencode-slim.json` | Plugin: preset, agent models/skills/**MCPs**, custom agents (cpp-expert, python-expert, math-verifier, ml-expert), council, backgroundJobs |
| `cli.json` | CLI v2: plugins, diffs, session, animations |
| `tui.json` | TUI plugin list |
| `memory.jsonl` | Persistent knowledge graph for the `memory` MCP |

## Resources

- Local skills: `skills/*/SKILL.md`
- Plugin source (installed): `~/.cache/opencode/packages/oh-my-opencode-slim@latest/`

## Known Caveats

- **Compute:** never launch training/heavy GPU/large-data jobs on this laptop;
  output cluster-ready scripts (SLURM/sbatch) and small smoke tests only.
- **Compute throttle (laptop, 6 cores) — обязательный троттлинг тяжёлых команд.**
  Замер 2026-09-30: `load average` до **26.68** при 6 ядрах — сборка `cmake --build build`
  (по умолчанию `-j$(nproc)`), C++-стенды `ctest` и I/O-воркеры `btrfs/zstd`+LUKS.
  Правила для агентов и фоновых лейнов:
  - сборка: **только** `cmake --build build -j2`; никогда без `-j` и никогда `-j$(nproc)`;
  - тесты: `ctest --test-dir build -j1`; узкие подмножества (`-k`, `-R`) вместо полного
    сьюта; полный `pytest tests`, `tests/e2e` и ASan-стенды — только когда это DoD-чек,
    по одному разу и под троттлингом;
  - тяжёлый шаг оборачивать: `nice -n 19 taskset -c 0,1 ionice -c3 <cmd>`;
  - перед python-прогонами: `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
    NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`;
  - **никогда** два тяжёлых прогона одновременно (в т.ч. у параллельных лейнов);
  - `dod-run` вызывать под тем же троттлингом
    (`nice -n 19 taskset -c 0,1 <BIN>/dod-run …`) — строки `cmd` в спеках не менять.
  Жёсткий предел при необходимости: `systemd-run --user --scope -p CPUQuota=150% <cmd>`
  (`cpulimit` в системе отсутствует).
- **Python env:** use `/home/asdcxfrt/ml_base/.venv` (Python 3.12). Missing there:
  `pytest`, `cv2`, `transformers`, `datasets`, `wandb`, `mlflow` — add with
  `uv pip install --python /home/asdcxfrt/ml_base/.venv/bin/python <pkg>`.
- **Python env (правило приоритета):** env выбирается по корню проекта. Внутри
  `/home/asdcxfrt/Projects/Diplom` действует только conda `optflow_env`
  (`/home/asdcxfrt/.conda/envs/optflow_env`, Python 3.12.0, kernelspec ноутбуков
  `display_name: optflow_env`) — это же окружение поднимает `tools/jupyter_up.sh`.
  `~/ml_base/.venv` (Python 3.12.12, ядро `uv-ml-base`) — глобальный дефолт вне
  проекта Diplom; в задачах по Diplom его не использовать.
- **Provider keys:** only `OPENROUTER_API_KEY` is set; the other declared
  providers (DeepSeek, Moonshot, SiliconFlow, MiniMax, ZAI, FCM*) have no keys
  and fail if selected. `opencode-go/*` models are the working default.
- **serena** — the installed **1.7.0 is MIT-licensed** (the project moved to
  GPL-3.0 only from v2/`main`); it partially duplicates built-in tools and is
  launched with `--context ide` and assigned only to the agents that benefit.
- **Built-in websearch** requires `OPENCODE_ENABLE_EXA=1` in the launch env.
- **MCP changes require an OpenCode restart.**
