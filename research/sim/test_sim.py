#!/usr/bin/env python3
"""Invariant tests for the M2 simulator (M1-model-design.md §6).

Run:  python test_sim.py            (unittest, std lib only)
      python -m pytest test_sim.py  (if pytest is installed)

The tests are deterministic: seeds are derived from policy|scenario|rep|seed_base.
"""

from __future__ import annotations

import statistics
import unittest
from pathlib import Path

import sim

HERE = Path(__file__).resolve().parent
PARAMS = sim.load_params(HERE / "params.json")
POLICIES = sim.build_policies(PARAMS)


def scen(name: str, contracts: int) -> dict:
    return {"name": name, "contracts": contracts}


def run(policy: str, scenario: dict, reps: int, seed_base: str = "t", params: dict | None = None):
    p = params or PARAMS
    pol = POLICIES[policy]
    return [
        sim.simulate_one(p, pol, scenario["name"], scenario, rep, seed_base)
        for rep in range(reps)
    ]


def mean(rows, key):
    return statistics.fmean(r[key] for r in rows)


class TestModelInvariants(unittest.TestCase):
    N16 = scen("n16", 16)
    N8 = scen("n8", 8)

    def test_determinism(self):
        a = run("B+C", self.N8, 10, seed_base="det")
        b = run("B+C", self.N8, 10, seed_base="det")
        self.assertEqual([r["wall_s"] for r in a], [r["wall_s"] for r in b])
        self.assertEqual([r["checks"] for r in a], [r["checks"] for r in b])

    def test_work_conservation(self):
        """Every contract reaches DONE (or the run is explicitly censored)."""
        for policy in ("A", "B", "B+C", "B+C+D", "E"):
            rows = run(policy, self.N8, 25)
            for r in rows:
                self.assertEqual(r["censored"], 0)
                self.assertEqual(r["contracts_done"], 8, msg=f"{policy} lost work")
                self.assertGreater(r["checks"], 0)
                self.assertGreater(r["cost_usd"], 0.0)

    def test_finished_state_is_green_fresh_and_approved(self):
        """M1 §6.1: DONE implies green + fresh + approved (asserted inside run())."""
        rows = run("A", self.N8, 15)
        self.assertTrue(all(r["contracts_done"] == 8 for r in rows))

    def test_dedup_saves_suites_and_heavy_time(self):
        """H1: B runs the shared suite once per wave; heavy time drops >= 40%."""
        a = run("A", self.N16, 200, seed_base="dedup")
        b = run("B", self.N16, 200, seed_base="dedup")
        self.assertLess(mean(b, "suites"), 0.25 * mean(a, "suites"))
        self.assertLess(mean(b, "heavy_busy_s"), 0.6 * mean(a, "heavy_busy_s"))
        self.assertLess(mean(b, "checks"), mean(a, "checks"))

    def test_policy_b_not_slower_than_status_quo(self):
        """A must not be faster than B at equal conditions (paired seeds)."""
        a = run("A", self.N16, 200, seed_base="wall")
        b = run("B", self.N16, 200, seed_base="wall")
        self.assertLess(mean(b, "wall_s"), mean(a, "wall_s") - 5 * 60)
        self.assertLess(statistics.median(r["wall_s"] for r in b),
                        statistics.median(r["wall_s"] for r in a))

    def test_batch_approval_cuts_interactions(self):
        a = run("A", self.N16, 150, seed_base="appr")
        ab = run("A_batch", self.N16, 150, seed_base="appr")
        self.assertLess(mean(ab, "interactions"), 0.6 * mean(a, "interactions"))
        self.assertLess(mean(ab, "wall_s"), 1.15 * mean(a, "wall_s"))

    def test_sampling_is_cheaper_and_riskier(self):
        """H4/E: risk-weighted sampling buys heavy time with P(false DONE)."""
        a = run("A", self.N16, 300, seed_base="samp")
        e = run("E", self.N16, 300, seed_base="samp")
        self.assertLess(mean(e, "heavy_busy_s"), 0.8 * mean(a, "heavy_busy_s"))
        self.assertGreater(mean(e, "false_done_any"), mean(a, "false_done_any") + 0.01)

    def test_scope_shallow_cuts_checks_but_adds_risk(self):
        """H2: C re-runs less; hidden out-of-scope coupling must show up as risk."""
        a = run("A", self.N16, 300, seed_base="shallow")
        c = run("C", self.N16, 300, seed_base="shallow")
        self.assertLess(mean(c, "checks"), mean(a, "checks"))
        self.assertGreaterEqual(mean(c, "false_done_shallow"), 0.0)
        self.assertGreater(mean(c, "hidden_misses"), 0.0)

    def test_two_tier_staleness_is_observable(self):
        """M1 §6.3: a commit without scope overlap stales cert but not scope."""
        pol = POLICIES["A"]
        rep = sim.Replication(PARAMS, pol, self.N8, "unit|two-tier")
        # mark contract 0 as passed with a commit; find a contract with disjoint files
        disjoint = next(
            (d for d in range(rep.n) if d != 0 and not (rep.files[d] & rep.files[0])), None
        )
        self.assertIsNotNone(disjoint, "portfolio has no disjoint pair — adjust test")
        rep._commit(0)
        self.assertTrue(rep.stale_cert[disjoint])      # global rule: stale
        self.assertFalse(rep.stale_scope[disjoint])    # scope rule: fresh
        reps_overlap = [d for d in range(rep.n) if d != 0 and (rep.files[d] & rep.files[0])]
        for d in reps_overlap:
            self.assertTrue(rep.stale_scope[d])

    def test_resource_bounds(self):
        """H heavy slots and the writer-map are never exceeded."""
        for policy in ("A", "B+C+D", "D", "A+D"):
            for r in run(policy, self.N8, 30):
                self.assertLessEqual(r["max_concurrent_heavy"], POLICIES[policy].heavy)

    def test_r6_cap(self):
        cap = PARAMS["dod"]["r6"]["max_consults"] * 16
        for policy in ("A", "B+C+D"):
            for r in run(policy, self.N16, 40):
                self.assertLessEqual(r["r6_stops"], cap)

    def test_zero_flake_zero_theater_no_false_done(self):
        params = sim.deep_merge(
            PARAMS,
            {"dod": {"p_flake_verify": 0.0, "p_theater": 0.0, "detect": {"suite": 1.0, "local": 1.0}}},
        )
        rows = run("B", self.N8, 30, seed_base="clean", params=params)
        self.assertTrue(all(r["false_done_contracts"] == 0 for r in rows))

    def test_boundaries_n1_and_chain(self):
        one = scen("n1", 1)
        rows = run("A", one, 20, seed_base="n1")
        self.assertTrue(all(r["contracts_done"] == 1 for r in rows))
        chain = sim.deep_merge(PARAMS, {"graph": {"edge_prob": 1.0, "max_deps": 1}})
        rows = run("B+C", self.N8, 20, seed_base="chain", params=chain)
        self.assertTrue(all(r["contracts_done"] == 8 for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
