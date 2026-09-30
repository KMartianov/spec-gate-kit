# `research/sim/` — M2: DES + Monte-Carlo simulator

Workstream **M2** of the Ф3 modelling phase (`research/README.md`): a discrete-event
simulation of the spec-gate pipeline (request → N contracts → draft lanes → human
approval → implementation waves → heavy DoD verification → evidence v2 → DONE),
replayed `reps` times per policy/scenario to compare **organisational policies**.

The model, policy space, invariants and calibration sources are specified in
`research/M1-model-design.md`; results are in `research/M2-simulation.md`.

## Files

| file | role |
|---|---|
| `sim.py` | simulator + CLI + aggregation + Pareto + sensitivity sweeps (stdlib only) |
| `params.json` | **all** parameters: scenarios, graph, distributions, probabilities, prices, policies |
| `test_sim.py` | 13 invariant tests (determinism, work conservation, dedup, H bound, writer-map, two-tier staleness, R6 cap, boundaries) |
| `results/` | generated: `summary.csv/.json`, `sensitivity.csv/.json`, `sensitivity_pdefect.csv/.json`, `run_manifest.json` |

## Run

```bash
cd research/sim

# smoke (300 reps)
python sim.py --quick

# full grid: 12 policies x {n4,n8,n16} x 10^4 reps + sensitivity sweeps
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  nice -n 19 taskset -c 0,1 /home/asdcxfrt/ml_base/.venv/bin/python sim.py \
  --reps 10000 --sensitivity

# subset
python sim.py --reps 2000 --scenarios n16 --policies A,B,B+C,B+C+D
```

Runtime scales roughly linearly: ~0.4 ms/rep (N=4), ~1.7 ms/rep (N=16); the full
grid above takes ≈10 min on two pinned cores.

## Policy = point in an extensible space

A policy is 6 axes (`params.json → policies`), not a hardcoded branch:

```json
"B+C+D": {"dedup": true, "staleness": "scope", "approval": "batch",
          "heavy": 2, "single_writer": true, "sampling": false}
```

| axis | values | meaning |
|---|---|---|
| `dedup` | bool | shared suite executed once per wave (stateless `wave-run`) |
| `staleness` | `global` / `scope` | certification rule: any commit vs touched `scope.allow` only (`--changed`) |
| `approval` | `per_contract` / `batch` | human gate: one sitting per spec vs `--all/--changed` |
| `heavy` | int | parallel heavy execution slots `H` (1 laptop, >1 oclab envs) |
| `single_writer` | bool | serialize contracts with overlapping scope files (writer-map) |
| `sampling` | bool | risk-weighted DoD sampling (cheap, higher `P(false DONE)`) |

Add a row to `params.json → policies` — no code change. `sim.py --policies ...` selects.

## Determinism & invariants

Seed = `policy|scenario|rep|seed_base`; the same invocation reproduces metrics
bit-for-bit (`test_sim.py::test_determinism`). Every replication asserts, before
returning, that all contracts are DONE with green + fresh + approved evidence and
that `H`/writer-map limits held (`Replication._invariant_check`).

Model outputs per replication: wall-clock, tail, $ (peak-priced), human
interactions/approvals, rework rounds, spec-edit rounds, flake re-runs, R6 stops,
checks/suites executed, wave count, heavy utilisation, throughput,
`P(false DONE)` split by cause (`detect` = a defect the battery missed,
`shallow` = silently stale after an out-of-scope coupling).

## Honest limitations

- Durations and human latencies are lognormal **priors** (M1 §2), not measurements;
  M3 replaces them from `verify/*.json` + `spec-gate.jsonl`.
- Policy C implements **optimistic** scope-shallow certification (the README
  §5-P0.4 proposal). The conservative reading (`stale_cert` still gates `DONE`)
  would reduce C to an intermediate-wave optimisation; the `shallow.*` risk knobs
  and the sensitivity sweep quantify the difference.
- Checks are aggregated per contract (one verify job = full battery); failure,
  flake and theater are Bernoulli per attempt, calibrated so the first-pass DoD
  rate ≈ 79–84 % (S6 alert is “< 80 %”).
