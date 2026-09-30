#!/usr/bin/env python3
"""M2 — discrete-event + Monte-Carlo simulator of the spec-gate project factory.

Implements the DES designed in ``research/M1-model-design.md`` (std lib only):

    request -> N contracts (random DAG) -> draft lanes (light slots)
    -> human approval gate (per-contract or batch --all/--changed)
    -> implementation waves (light slots, single-writer by scope files)
    -> heavy DoD verification waves (H slots, dedup / sampling, contention)
    -> evidence v2 (git_head / tree_dirty / spec sha) -> DONE

Policy = independent axes over the space:

    dedup          DoD dedup + one shared suite run per wave (stateless wave-run)
    staleness      "global"  : any commit stales all evidence (certification rule)
                   "scope"   : only touched scopes stale (scope-shallow + --changed,
                               charged with hidden-input risk via ``shallow.*``)
    approval       "per_contract" | "batch" (--all/--changed)
    heavy          number of heavy execution slots H (laptop: 1; oclab envs: >1)
    single_writer  serialize overlapping scopes (writer-map)
    sampling       risk-weighted verification sampling (cheap + risky)

Determinism: one RNG per replication, seeded by ``policy|scenario|rep|seed_base``.
Security note: the code is a simulator; no external inputs are executed.

Run ``python sim.py --help`` for the CLI.  All parameters live in ``params.json``.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
DEFAULT_PARAMS = HERE / "params.json"
DEFAULT_OUT = HERE / "results"

# --------------------------------------------------------------------------
# policies


@dataclass(frozen=True, slots=True)
class Policy:
    """A point in the policy space (M1 §3)."""

    name: str
    label: str
    dedup: bool
    staleness: str
    approval: str
    heavy: int
    single_writer: bool
    sampling: bool

    @staticmethod
    def from_config(name: str, cfg: dict[str, Any]) -> "Policy":
        return Policy(
            name=name,
            label=str(cfg.get("label", name)),
            dedup=bool(cfg["dedup"]),
            staleness=str(cfg["staleness"]),
            approval=str(cfg["approval"]),
            heavy=int(cfg["heavy"]),
            single_writer=bool(cfg["single_writer"]),
            sampling=bool(cfg["sampling"]),
        )


def load_params(path: Path | str = DEFAULT_PARAMS) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_policies(params: dict[str, Any]) -> dict[str, Policy]:
    return {name: Policy.from_config(name, cfg) for name, cfg in params["policies"].items()}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# --------------------------------------------------------------------------
# one replication


class Replication:
    """One Monte-Carlo replication: the full pipeline until all contracts DONE."""

    def __init__(self, params: dict[str, Any], policy: Policy, scenario: dict[str, Any], seed: str):
        self.P = params
        self.pol = policy
        self.scenario = scenario
        self.name = str(scenario["name"])
        self.n = int(scenario["contracts"])
        self.rng = random.Random(seed)
        self.seed = seed
        rng = self.rng
        n = self.n

        # ---- fixed per-replication portfolio ------------------------------
        g = params["graph"]
        self.deps: list[list[int]] = []
        for i in range(n):
            cand = list(range(i))
            rng.shuffle(cand)
            deps = [j for j in cand if rng.random() < g["edge_prob"]][: g["max_deps"]]
            self.deps.append(sorted(deps))
        port = params["portfolio"]
        self.is_heavy = [rng.random() < port["heavy_fraction"] for _ in range(n)]
        pool = int(port["files"]["pool"])
        k = int(port["files"]["per_contract"])
        self.files = [frozenset(rng.sample(range(pool), min(k, pool))) for _ in range(n)]
        rk = port["risk"]
        lo, hi = rk["clip"]
        self.risk = [
            min(hi, max(lo, rk["base"] + (rk["heavy_bonus"] if self.is_heavy[i] else 0.0)
                       + rk["noise"] * rng.uniform(-1.0, 1.0)))
            for i in range(n)
        ]
        dod = params["dod"]
        self.defect = [rng.random() < dod["p_defect"] for _ in range(n)]
        self.detected = [False] * n
        self.hidden_defect = [False] * n  # injected by a missed out-of-scope coupling

        # ---- lifecycle flags ----------------------------------------------
        self.draft_started = [False] * n
        self.drafted = [False] * n
        self.impl_started = [False] * n
        self.impl_done = [False] * n
        self.approved = [False] * n
        self.approved_once = [False] * n
        self.passed = [False] * n
        self.stale_cert = [False] * n   # global rule (ev_head != HEAD)
        self.stale_scope = [False] * n  # scope-shallow rule (touched scope / hidden catch)
        self.seq_fail = [0] * n
        self.r6_consults = [0] * n
        self.flake_tries = [0] * n
        self.blocked: set[int] = set()  # awaiting an R6 human consult (stop-and-ask)

        # ---- resources ------------------------------------------------------
        self.head = 0
        self.t = 0.0
        self.light_slots: list[tuple[str, int, frozenset[int] | None] | None] = [
            None
        ] * int(params["lanes"]["light"])
        self.heavy_slots: list[tuple[int, frozenset[int]] | None] = [None] * policy.heavy
        self.events: list[tuple[float, int, str, Any]] = []
        self._seq = 0
        self.events_processed = 0
        self.censored = False

        # queues / human
        self.rework_queue: list[int] = []
        self.rework_pending: set[int] = set()
        self.verify_queue: list[int] = []
        self.pending: list[int] = []
        self.wave_open = False
        self.suite_ran = False
        self.retry_pending = 0
        self.batch_gen = 0
        self.batch_timer: float | None = None
        self.human_busy = False

        # ---- counters -------------------------------------------------------
        self.cost = 0.0
        self.approvals = 0
        self.interactions = 0
        self.spec_edits = 0
        self.rework_rounds = 0
        self.flake_retries = 0
        self.r6_stops = 0
        self.checks = 0
        self.suites = 0
        self.waves = 0
        self.heavy_busy = 0.0
        self.max_concurrent_heavy = 0
        self.t_last_draft = 0.0
        self.hidden_misses = 0
        self.verifies = 0
        self.attempts = [0] * n
        self.first_fail = [False] * n

        # cached parameter handles
        D = params["durations_s"]
        self.D = D
        self.C = params["costs_usd"]
        self.DOD = dod
        self.SH = params["shallow"]
        self.r6 = dod["r6"]
        self.n_loc = int(dod["locals_per_contract"])
        self.n_loc_sampled = int(dod["locals_sampled"])
        self.sample_threshold = float(params["sampling"]["risk_threshold"])
        self.collect = float(D["approval_collect"].get("value", D["approval_collect"]))
        self.batch_threshold = max(2, math.ceil(n / 2))
        self.contention = dod["contention"]

    # -- RNG helpers ---------------------------------------------------------

    def _dist(self, spec: dict[str, Any]) -> float:
        if spec.get("dist", "lognormal") == "lognormal":
            return math.exp(math.log(spec["median"]) + spec["sigma"] * self.rng.gauss(0.0, 1.0))
        return float(spec["value"])

    def _push(self, when: float, kind: str, arg: Any) -> None:
        self._seq += 1
        heapq.heappush(self.events, (when, self._seq, kind, arg))

    # -- resources -----------------------------------------------------------

    def _light_busy(self) -> int:
        return sum(1 for s in self.light_slots if s is not None)

    def _enqueue_rework(self, c: int) -> None:
        """A contract can only be in the rework queue once (no duplicate lanes)."""
        if c in self.rework_pending:
            return
        if any(s is not None and s[0] == "rework" and s[1] == c for s in self.light_slots):
            return
        self.rework_pending.add(c)
        self.rework_queue.append(c)

    def _heavy_busy(self) -> int:
        return sum(1 for s in self.heavy_slots if s is not None)

    def _next_light_job(self) -> tuple[str, int] | None:
        occ = [s[2] for s in self.light_slots if s is not None and s[2] is not None]

        def conflicts(c: int) -> bool:
            return self.pol.single_writer and any(self.files[c] & f for f in occ)

        for i, c in enumerate(self.rework_queue):
            if conflicts(c):
                continue
            del self.rework_queue[i]
            self.rework_pending.discard(c)
            return "rework", c
        draft_first = self.P["lanes"].get("priority", "draft_first") == "draft_first"

        def next_impl() -> int | None:
            for c in range(self.n):
                if self.impl_started[c] or self.impl_done[c]:
                    continue
                if not (self.drafted[c] and self.approved[c]):
                    continue
                if any(not self.passed[d] for d in self.deps[c]):
                    continue
                if conflicts(c):
                    continue
                return c
            return None

        def next_draft() -> int | None:
            for c in range(self.n):
                if not self.draft_started[c]:
                    return c
            return None

        if draft_first:
            c = next_draft()
            if c is not None:
                self.draft_started[c] = True
                return "draft", c
        c = next_impl()
        if c is not None:
            self.impl_started[c] = True
            return "impl", c
        if not draft_first:
            c = next_draft()
            if c is not None:
                self.draft_started[c] = True
                return "draft", c
        return None

    def _dispatch_light(self) -> None:
        D = self.D
        while True:
            slot = next((i for i, s in enumerate(self.light_slots) if s is None), None)
            if slot is None:
                return
            job = self._next_light_job()
            if job is None:
                return
            kind, c = job
            if kind == "draft":
                dur, files = self._dist(D["draft"]), None
            elif kind == "impl":
                key = "impl_heavy" if self.is_heavy[c] else "impl_light"
                dur, files = self._dist(D[key]), self.files[c]
            else:  # rework
                dur, files = self._dist(D["rework"]), self.files[c]
            self.light_slots[slot] = (kind, c, files)
            self._push(self.t + dur, kind, (c, slot))
        if self.pol.single_writer:
            busy = [s[2] for s in self.light_slots if s is not None and s[2] is not None]
            for i in range(len(busy)):
                for j in range(i + 1, len(busy)):
                    assert not (busy[i] & busy[j]), "single-writer violated in light dispatch"

    def _free_light(self, slot: int) -> None:
        self.light_slots[slot] = None

    # -- approvals (human) ---------------------------------------------------

    def _request_approval(self, c: int) -> None:
        self.pending.append(c)
        if self.pol.approval == "per_contract":
            if not self.human_busy:
                self.human_busy = True
                self._push(self.t + self._dist(self.D["approval_per_item"]), "approve_item", None)
            return
        # batch (--all / --changed): one sitting once the batch is ready
        threshold = 1 if all(self.approved_once) else self.batch_threshold
        if len(self.pending) >= threshold or all(self.drafted):
            self._schedule_batch(self._dist(self.D["approval_batch"]))
        elif self.batch_timer is None:
            self._schedule_batch(self.collect)

    def _schedule_batch(self, delay: float) -> None:
        self.batch_gen += 1
        self.batch_timer = self.t + delay
        self._push(self.batch_timer, "approve_batch", self.batch_gen)

    def _on_approve_item(self, _arg: Any) -> None:
        c = self.pending.pop(0)
        self._approve(c)
        self.interactions += 1
        if self.pending:
            self._push(self.t + self._dist(self.D["approval_per_item"]), "approve_item", None)
        else:
            self.human_busy = False
        self._dispatch_light()
        self._maybe_start_wave()

    def _on_approve_batch(self, gen: int) -> None:
        if gen != self.batch_gen:
            return  # superseded timer
        items = list(self.pending)
        self.pending.clear()
        self.batch_timer = None
        if not items:
            return
        self.interactions += 1
        for c in items:
            self._approve(c)
        self._dispatch_light()
        self._maybe_start_wave()

    def _approve(self, c: int) -> None:
        self.approved[c] = True
        self.approved_once[c] = True
        self.approvals += 1

    # -- commits & staleness --------------------------------------------------

    def _commit(self, c: int) -> None:
        """A commit by contract ``c``: HEAD++, evidence staleness per policy rule."""
        self.head += 1
        # global rule: every evidence record is at an older HEAD
        for d in range(self.n):
            self.stale_cert[d] = True
        # scope rule: touched scopes only
        for d in range(self.n):
            if self.files[d] & self.files[c]:
                self.stale_scope[d] = True
        # hidden out-of-scope coupling: only matters when the policy trusts scope-shallow
        if self.pol.staleness == "scope":
            sh = self.SH
            for d in range(self.n):
                if d == c or (self.files[d] & self.files[c]):
                    continue
                if not (self.passed[d] and self.approved[d]):
                    continue
                if self.rng.random() < sh["p_hidden_input"]:
                    if self.rng.random() < sh["p_catch"]:
                        self.stale_scope[d] = True  # tooling noticed it
                    else:
                        self.hidden_misses += 1
                        if self.rng.random() < sh["p_hidden_defect"]:
                            self.hidden_defect[d] = True  # silent input change, latent defect

    def _needs_rerun(self, c: int) -> bool:
        if c in self.blocked:
            return False
        if not (self.impl_done[c] and self.approved[c]):
            return False
        if self.passed[c] and not self._is_stale(c):
            return False
        return True

    def _is_stale(self, c: int) -> bool:
        return self.stale_cert[c] if self.pol.staleness == "global" else self.stale_scope[c]

    def _mark_pass(self, c: int) -> None:
        self.passed[c] = True
        self.stale_cert[c] = False
        self.stale_scope[c] = False
        self.seq_fail[c] = 0
        self.flake_tries[c] = 0

    # -- waves (heavy verification) -------------------------------------------

    def _maybe_start_wave(self) -> None:
        if self.wave_open or self._heavy_busy():
            return
        if self._light_busy():
            return
        needs = [c for c in range(self.n) if self._needs_rerun(c)]
        if not needs:
            return
        self.wave_open = True
        self.waves += 1
        self.cost += self.C["wave"]
        self.suite_ran = False
        self.verify_queue.extend(needs)
        self._dispatch_verify()

    def _dispatch_verify(self) -> None:
        if not self.wave_open:
            return
        H = self.pol.heavy
        while self.verify_queue and self._heavy_busy() < H:
            slot = next(i for i, s in enumerate(self.heavy_slots) if s is None)
            busy = [s[1] for s in self.heavy_slots if s is not None]
            pick = None
            for i, c in enumerate(self.verify_queue):
                if self.pol.single_writer and any(self.files[c] & f for f in busy):
                    continue
                pick = i
                break
            if pick is None:
                return
            c = self.verify_queue.pop(pick)
            sampled = self.pol.sampling and self.risk[c] < self.sample_threshold
            if self.pol.dedup:
                run_suite = (not sampled) and (not self.suite_ran)
                suite_credit = self.suite_ran or run_suite
            else:
                run_suite = not sampled
                suite_credit = not sampled
            if run_suite:
                self.suite_ran = True
                self.suites += 1
            nl = self.n_loc_sampled if sampled else self.n_loc
            dur = self._dist(self.D["suite"]) if run_suite else 0.0
            for _ in range(nl):
                dur += self._dist(self.D["local"])
            if self.pol.heavy > 1:
                dur *= self.contention["duration_mult"]
            self.heavy_slots[slot] = (c, self.files[c])
            self.heavy_busy += dur
            self.max_concurrent_heavy = max(self.max_concurrent_heavy, self._heavy_busy())
            self._push(self.t + dur, "verify", (c, slot, suite_credit, nl, run_suite))
        if self.pol.single_writer:
            busy = [s[1] for s in self.heavy_slots if s is not None]
            for i in range(len(busy)):
                for j in range(i + 1, len(busy)):
                    assert not (busy[i] & busy[j]), "single-writer violated in verify dispatch"

    def _on_verify(self, arg: tuple[int, int, bool, int, bool]) -> None:
        c, slot, suite_credit, nl, ran_suite = arg
        self.heavy_slots[slot] = None
        dod = self.DOD
        n_checks = nl + (1 if ran_suite else 0)
        self.checks += n_checks
        self.cost += self.C["check"] * n_checks

        d_suite = dod["detect"]["suite"] * (1.0 - dod["p_theater"]) if suite_credit else 0.0
        d_local = dod["detect"]["local"] * (1.0 - dod["p_theater"])
        p_det = 1.0 - (1.0 - d_suite) * (1.0 - d_local) ** nl
        defect_here = self.defect[c] or (self.hidden_defect[c] and suite_credit)
        hit = bool(defect_here and self.rng.random() < p_det)
        p_flake = dod["p_flake_verify"] * (nl / self.n_loc)
        if self.pol.heavy > 1:
            p_flake *= self.contention["flake_mult"]
        flake = bool(not hit and self.rng.random() < p_flake)
        self.verifies += 1
        if self.attempts[c] == 0:
            self.first_fail[c] = bool(hit or flake)
        self.attempts[c] += 1

        if hit:
            self.detected[c] = True
            if self.hidden_defect[c]:
                self.hidden_defect[c] = False  # the latent defect is now visible and will be fixed
            self.seq_fail[c] += 1
            if self.seq_fail[c] >= self.r6["limit"] and self.r6_consults[c] < self.r6["max_consults"]:
                self.blocked.add(c)  # stop-and-ask: no re-verification until the human answers
                self.r6_stops += 1
                self.interactions += 1
                self.cost += self.C["r6"]
                self._push(self.t + self._dist(self.D["r6_consult"]), "r6", c)
            else:
                self._enqueue_rework(c)
        elif flake:
            self.flake_retries += 1
            if self.flake_tries[c] < dod["flake_max_retries"]:
                self.flake_tries[c] += 1
                self.retry_pending += 1
                self._push(self.t + self._dist(self.D["flake_backoff"]), "retry", c)
            else:  # quarantine: accept after N re-runs (S5-F6 policy)
                self._mark_pass(c)
        else:
            if suite_credit:
                self.hidden_defect[c] = False  # the full battery covered it and found nothing
            self._mark_pass(c)

        self._dispatch_verify()
        if not self.verify_queue and not self._heavy_busy() and self.retry_pending == 0:
            self.wave_open = False
            self._dispatch_light()
            self._maybe_start_wave()

    def _on_retry(self, c: int) -> None:
        self.retry_pending -= 1
        if not self.wave_open:
            # keep a wave open for the retry; a light job may have sneaked in only if the
            # wave closed — reopen one for this contract alone (no re-run of others).
            if self._light_busy():
                self._push(self.t + 1.0, "retry", c)
                self.retry_pending += 1
                return
            self.wave_open = True
            self.waves += 1
            self.cost += self.C["wave"]
            self.suite_ran = False
        self.verify_queue.insert(0, c)
        self._dispatch_verify()
        if not self.verify_queue and not self._heavy_busy() and self.retry_pending == 0:
            self.wave_open = False
            self._dispatch_light()
            self._maybe_start_wave()

    def _on_r6(self, c: int) -> None:
        self.r6_consults[c] += 1
        self.blocked.discard(c)
        if self.r6_consults[c] >= self.r6["max_consults"] or self.rng.random() < self.r6["p_fix"]:
            self.defect[c] = False
            self.hidden_defect[c] = False
        self.seq_fail[c] = 0
        self._enqueue_rework(c)
        self._dispatch_light()

    # -- light-slot completions ------------------------------------------------

    def _on_draft(self, arg: tuple[int, int]) -> None:
        c, slot = arg
        self._free_light(slot)
        self.drafted[c] = True
        self.t_last_draft = self.t
        self.cost += self.C["draft"]
        self._request_approval(c)
        self._dispatch_light()

    def _on_impl(self, arg: tuple[int, int]) -> None:
        c, slot = arg
        self._free_light(slot)
        self.impl_done[c] = True
        self.cost += self.C["impl"]
        # writer-map violation: two concurrent impls sharing files (only when not enforced)
        if not self.pol.single_writer:
            for s in self.light_slots:
                if s is not None and s[0] in ("impl", "rework") and s[1] != c \
                        and (self.files[c] & self.files[s[1]]):
                    if self.rng.random() < self.P["rework"]["p_collision"]:
                        self._enqueue_rework(c)
                    break
        self._commit(c)
        if self.rng.random() < self.P["rework"]["p_spec_edit"]:
            self.spec_edits += 1
            self.cost += self.C["spec_edit"]
            self.approved[c] = False          # spec edit invalidates approval (hash rule)
            self.passed[c] = False            # and the evidence (spec_sha256)
            self.stale_cert[c] = True
            self.stale_scope[c] = True
            self._request_approval(c)
        self._dispatch_light()
        self._maybe_start_wave()

    def _on_rework(self, arg: tuple[int, int]) -> None:
        c, slot = arg
        self._free_light(slot)
        self.rework_rounds += 1
        self.cost += self.C["rework"]
        # the fix actually fixes the detected defect (with the usual fixer success rate)
        if self.defect[c] and self.rng.random() < self.P["rework"]["p_fix"]:
            self.defect[c] = False
        self._commit(c)
        if not self.pol.single_writer:
            for s in self.light_slots:
                if s is not None and s[0] in ("impl", "rework") and s[1] != c \
                        and (self.files[c] & self.files[s[1]]):
                    if self.rng.random() < self.P["rework"]["p_collision"]:
                        self._enqueue_rework(c)
                    break
        self._dispatch_light()
        self._maybe_start_wave()

    # -- main loop -------------------------------------------------------------

    def _finished(self) -> bool:
        if self.wave_open or self._heavy_busy() or self._light_busy() or self.retry_pending:
            return False
        if self.rework_queue or self.verify_queue:
            return False
        return all(
            self.impl_done[c] and self.passed[c] and self.approved[c] and not self._is_stale(c)
            for c in range(self.n)
        )

    def run(self) -> None:
        params = self.P
        max_wall = float(params["sim"]["max_wall_s"])
        max_events = int(params["sim"]["max_events"])
        self._dispatch_light()
        while not self._finished():
            if self.events_processed >= max_events:
                self.censored = True
                break
            if not self.events:
                raise RuntimeError(
                    f"deadlock: policy={self.pol.name} scenario={self.name} seed={self.seed}"
                )
            t, _, kind, arg = heapq.heappop(self.events)
            if t > max_wall:
                self.censored = True
                break
            self.t = t
            self.events_processed += 1
            getattr(self, f"_on_{kind}")(arg)
        self._invariant_check()

    def _invariant_check(self) -> None:
        """M1 §6: DONE implies green + fresh + approved; resource bounds hold."""
        if self.censored:
            return
        assert not self.wave_open and self._heavy_busy() == 0 and self._light_busy() == 0
        for c in range(self.n):
            assert self.impl_done[c] and self.passed[c] and self.approved[c], (self.seed, c)
            assert not self._is_stale(c), (self.seed, c)
        assert self.max_concurrent_heavy <= self.pol.heavy

    # -- metrics ---------------------------------------------------------------

    def metrics(self) -> dict[str, Any]:
        params = self.P
        peak = params["sim"]["peak"]
        cost = self.cost * (1.0 + peak["p_peak"] * (peak["mult"] - 1.0))
        wall = self.t
        done = [
            c
            for c in range(self.n)
            if self.impl_done[c] and self.passed[c] and self.approved[c] and not self._is_stale(c)
        ]
        false_detect = 0
        false_shallow = 0
        for c in done:
            if self.defect[c] and not self.detected[c]:
                false_detect += 1  # a defect the battery never caught
            elif self.hidden_defect[c]:
                false_shallow += 1  # silently stale after an out-of-scope coupling
        false_done = false_detect + false_shallow
        attempted = [c for c in range(self.n) if self.attempts[c] > 0]
        first_pass = (
            1.0 - sum(self.first_fail[c] for c in attempted) / len(attempted) if attempted else 1.0
        )
        return {
            "wall_s": wall,
            "tail_s": max(0.0, wall - self.t_last_draft),
            "cost_usd": cost,
            "approvals": self.approvals,
            "interactions": self.interactions,
            "spec_edits": self.spec_edits,
            "rework_rounds": self.rework_rounds,
            "flake_retries": self.flake_retries,
            "r6_stops": self.r6_stops,
            "checks": self.checks,
            "suites": self.suites,
            "waves": self.waves,
            "heavy_busy_s": self.heavy_busy,
            "heavy_util": self.heavy_busy / (wall * self.pol.heavy) if wall > 0 else 0.0,
            "contracts_done": len(done),
            "false_done_contracts": false_done,
            "false_done_detect": false_detect,
            "false_done_shallow": false_shallow,
            "false_done_any": 1 if false_done else 0,
            "first_pass_rate": first_pass,
            "verifies": self.verifies,
            "heavy_per_verify_s": self.heavy_busy / self.verifies if self.verifies else 0.0,
            "censored": 1 if self.censored else 0,
            "hidden_misses": self.hidden_misses,
            "events": self.events_processed,
            "max_concurrent_heavy": self.max_concurrent_heavy,
        }


def simulate_one(
    params: dict[str, Any],
    policy: Policy,
    scenario_name: str,
    scenario: dict[str, Any],
    rep: int,
    seed_base: str = "0",
) -> dict[str, Any]:
    seed = f"{policy.name}|{scenario_name}|{rep}|{seed_base}"
    rep_obj = Replication(params, policy, scenario, seed)
    rep_obj.run()
    out = rep_obj.metrics()
    out["policy"] = policy.name
    out["scenario"] = scenario_name
    out["rep"] = rep
    return out


# --------------------------------------------------------------------------
# aggregation


def _pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-replication metrics of one (scenario, policy) cell."""
    reps = len(rows)

    def vals(key: str) -> list[float]:
        return [float(r[key]) for r in rows]

    wall = vals("wall_s")
    heavy = vals("heavy_busy_s")
    out: dict[str, Any] = {
        "reps": reps,
        "wall_p50_min": _pct(wall, 0.50) / 60.0,
        "wall_p95_min": _pct(wall, 0.95) / 60.0,
        "wall_mean_min": statistics.fmean(wall) / 60.0,
        "wall_max_min": max(wall) / 60.0,
        "tail_p50_min": _pct(vals("tail_s"), 0.50) / 60.0,
        "cost_mean_usd": statistics.fmean(vals("cost_usd")),
        "cost_p95_usd": _pct(vals("cost_usd"), 0.95),
        "interactions_mean": statistics.fmean(vals("interactions")),
        "interactions_p95": _pct(vals("interactions"), 0.95),
        "approvals_mean": statistics.fmean(vals("approvals")),
        "spec_edits_mean": statistics.fmean(vals("spec_edits")),
        "rework_mean": statistics.fmean(vals("rework_rounds")),
        "flake_mean": statistics.fmean(vals("flake_retries")),
        "r6_mean": statistics.fmean(vals("r6_stops")),
        "checks_mean": statistics.fmean(vals("checks")),
        "suites_mean": statistics.fmean(vals("suites")),
        "waves_mean": statistics.fmean(vals("waves")),
        "verifies_mean": statistics.fmean(vals("verifies")),
        "heavy_per_verify_s": statistics.fmean(vals("heavy_per_verify_s")),
        "heavy_min_mean": statistics.fmean(heavy) / 60.0,
        "heavy_util_mean": statistics.fmean(vals("heavy_util")),
        "throughput_h_mean": statistics.fmean(vals("contracts_done")) / (statistics.fmean(wall) / 3600.0),
        "p_false_done": statistics.fmean(vals("false_done_any")),
        "false_done_per_contract": statistics.fmean(vals("false_done_contracts")),
        "p_false_done_detect": statistics.fmean(vals("false_done_detect")),
        "p_false_done_shallow": statistics.fmean(vals("false_done_shallow")),
        "first_pass_rate": statistics.fmean(vals("first_pass_rate")),
        "p_censored": statistics.fmean(vals("censored")),
        "hidden_misses_mean": statistics.fmean(vals("hidden_misses")),
        "events_mean": statistics.fmean(vals("events")),
    }
    return out


def run_grid(
    params: dict[str, Any],
    policies: Iterable[Policy],
    scenarios: list[dict[str, Any]],
    reps: int,
    seed_base: str = "0",
    progress: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        for policy in policies:
            per_rep = [
                simulate_one(params, policy, str(scenario["name"]), scenario, rep, seed_base)
                for rep in range(reps)
            ]
            agg = summarize(per_rep)
            agg.update({"scenario": scenario["name"], "policy": policy.name,
                        "label": policy.label, "reps": reps})
            rows.append(agg)
            if progress:
                print(
                    f"  {scenario['name']:>4} {policy.name:<10} "
                    f"wall p50={agg['wall_p50_min']:7.1f} min  "
                    f"falseDONE={agg['p_false_done']:6.3f}  "
                    f"checks={agg['checks_mean']:7.0f}",
                    flush=True,
                )
    return rows


# --------------------------------------------------------------------------
# output


CSV_FIELDS = [
    "scenario", "policy", "label", "reps",
    "wall_p50_min", "wall_p95_min", "wall_mean_min", "wall_max_min", "tail_p50_min",
    "heavy_min_mean", "heavy_util_mean", "waves_mean", "checks_mean", "suites_mean",
    "verifies_mean", "heavy_per_verify_s", "first_pass_rate",
    "cost_mean_usd", "cost_p95_usd",
    "interactions_mean", "interactions_p95", "approvals_mean",
    "spec_edits_mean", "rework_mean", "flake_mean", "r6_mean",
    "throughput_h_mean", "p_false_done", "p_false_done_detect", "p_false_done_shallow",
    "false_done_per_contract", "hidden_misses_mean", "p_censored", "events_mean",
]


def write_csv(rows: list[dict[str, Any]], path: Path, fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields or CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)


def pareto(rows: list[dict[str, Any]]) -> list[str]:
    """Pareto frontier over (wall_p50, cost_mean, p_false_done, interactions_mean)."""
    keys = ("wall_p50_min", "cost_mean_usd", "p_false_done", "interactions_mean")
    front: list[str] = []
    for row in rows:
        dominated = False
        for other in rows:
            if other is row:
                continue
            if all(other[k] <= row[k] for k in keys) and any(other[k] < row[k] for k in keys):
                dominated = True
                break
        if not dominated:
            front.append(row["policy"])
    return front


def print_tables(rows: list[dict[str, Any]]) -> None:
    scenarios = sorted({str(r["scenario"]) for r in rows})
    for scen in scenarios:
        subset = [r for r in rows if r["scenario"] == scen]
        subset.sort(key=lambda r: r["wall_p50_min"])
        print(f"\n=== scenario {scen} ({subset[0]['reps']} reps) — sorted by wall p50 ===")
        header = (f"{'policy':<10} {'wall50':>7} {'wall95':>7} {'verify':>7} {'checks':>7} "
                  f"{'waves':>6} {'$':>6} {'inter':>6} {'appr':>5} {'rework':>6} "
                  f"{'fDONE':>6} {'cens':>5}")
        print(header)
        print("-" * len(header))
        for r in subset:
            print(f"{r['policy']:<10} {r['wall_p50_min']:7.1f} {r['wall_p95_min']:7.1f} "
                  f"{r['heavy_min_mean']:7.1f} {r['checks_mean']:7.0f} {r['waves_mean']:6.1f} "
                  f"{r['cost_mean_usd']:6.2f} {r['interactions_mean']:6.1f} "
                  f"{r['approvals_mean']:5.1f} {r['rework_mean']:6.2f} "
                  f"{100*r['p_false_done']:5.1f}% {100*r['p_censored']:4.1f}%")
        print(f"pareto(wall,$,falseDONE,interactions): {', '.join(pareto(subset))}")


# --------------------------------------------------------------------------
# sensitivity


SENSITIVITY: list[dict[str, Any]] = [
    {"name": "base", "override": {}},
    {"name": "approval_fast", "override": {"durations_s": {
        "approval_per_item": {"dist": "const", "value": 60},
        "approval_batch": {"dist": "const", "value": 60}}}},
    {"name": "approval_slow", "override": {"durations_s": {
        "approval_per_item": {"dist": "const", "value": 1800},
        "approval_batch": {"dist": "const", "value": 1800}}}},
    {"name": "flake_high", "override": {"dod": {"p_flake_verify": 0.12}}},
    {"name": "flake_zero", "override": {"dod": {"p_flake_verify": 0.0}}},
    {"name": "hidden_input_high", "override": {"shallow": {"p_hidden_input": 0.02}}},
    {"name": "hidden_input_zero", "override": {"shallow": {"p_hidden_input": 0.0}}},
]


def run_sensitivity(
    params: dict[str, Any],
    policies: list[Policy],
    scenario: dict[str, Any],
    reps: int,
    seed_base: str,
    progress: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variant in SENSITIVITY:
        variant_params = deep_merge(params, variant["override"])
        name = f"{seed_base}-{variant['name']}"
        for policy in policies:
            per_rep = [
                simulate_one(variant_params, policy, str(scenario["name"]), scenario, rep, name)
                for rep in range(reps)
            ]
            agg = summarize(per_rep)
            agg.update({"variant": variant["name"], "scenario": scenario["name"],
                        "policy": policy.name, "reps": reps})
            rows.append(agg)
            if progress:
                print(f"  sens {variant['name']:<18} {policy.name:<10} "
                      f"wall50={agg['wall_p50_min']:7.1f} fDONE={agg['p_false_done']:6.3f}",
                      flush=True)
    return rows


# --------------------------------------------------------------------------
# CLI


def resolve_scenarios(params: dict[str, Any], names: list[str]) -> list[dict[str, Any]]:
    out = []
    for name in names:
        cfg = params["scenarios"][name]
        out.append({"name": name, "contracts": int(cfg["contracts"])})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--params", type=Path, default=DEFAULT_PARAMS)
    ap.add_argument("--reps", type=int, default=10000)
    ap.add_argument("--scenarios", default="n4,n8,n16",
                    help="comma-separated keys of params.scenarios")
    ap.add_argument("--policies", default="", help="comma-separated; default = all in params")
    ap.add_argument("--seed-base", default="0")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--quick", action="store_true", help="300 reps (smoke run)")
    ap.add_argument("--sensitivity", action="store_true", help="extra sensitivity sweeps")
    ap.add_argument("--sensitivity-reps", type=int, default=3000)
    ap.add_argument("--no-print", action="store_true")
    args = ap.parse_args(argv)

    params = load_params(args.params)
    policy_map = build_policies(params)
    if args.policies:
        wanted = [p.strip() for p in args.policies.split(",") if p.strip()]
        missing = [p for p in wanted if p not in policy_map]
        if missing:
            ap.error(f"unknown policies: {missing}; known: {list(policy_map)}")
        policies = [policy_map[p] for p in wanted]
    else:
        policies = list(policy_map.values())
    scenarios = resolve_scenarios(params, [s.strip() for s in args.scenarios.split(",")])
    reps = 300 if args.quick else args.reps

    print(f"policies={[p.name for p in policies]} scenarios={[s['name'] for s in scenarios]} "
          f"reps={reps} seed_base={args.seed_base}", flush=True)
    rows = run_grid(params, policies, scenarios, reps, args.seed_base)
    write_csv(rows, args.out / "summary.csv")
    write_json(rows, args.out / "summary.json")
    if not args.no_print:
        print_tables(rows)

    if args.sensitivity:
        sens_policies = [p for p in policies if p.name in ("A", "B", "B+C", "B+C+D")]
        sens = run_sensitivity(params, sens_policies, scenarios[-1], args.sensitivity_reps,
                               args.seed_base)
        write_csv(sens, args.out / "sensitivity.csv",
                  fields=["variant"] + CSV_FIELDS)
        write_json(sens, args.out / "sensitivity.json")
        if not args.no_print:
            print("\n=== sensitivity ===")
            for r in sens:
                print(f"{r['variant']:<18} {r['policy']:<10} wall50={r['wall_p50_min']:7.1f} "
                      f"fDONE={r['p_false_done']:6.3f} checks={r['checks_mean']:7.0f} "
                      f"inter={r['interactions_mean']:5.1f}")

    manifest = {
        "reps": reps,
        "seed_base": args.seed_base,
        "scenarios": [s["name"] for s in scenarios],
        "policies": [p.name for p in policies],
        "params_file": str(args.params),
        "seeds": "policy|scenario|rep|seed_base",
    }
    (args.out / "run_manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (args.out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {args.out}/summary.csv, summary.json"
          + (", sensitivity.csv" if args.sensitivity else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
