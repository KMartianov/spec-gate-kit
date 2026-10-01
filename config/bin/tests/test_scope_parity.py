r"""Parity test for the ``scope`` glob matcher: the Python side of the TS↔Python pair.

The language-neutral vector table ``config/tools/gov/scope_vectors.json`` is the
single source of truth for the observable semantics of both matchers:

* ``spec_scope.glob_match``   ↔ ``globMatch``   in ``plugins/spec-gate.ts``
* ``spec_scope.scope_allows`` ↔ ``scopeAllows`` in ``plugins/spec-gate.ts``

Every ``pattern_cases`` entry is run through ``glob_match`` and every
``scope_cases`` entry through ``scope_allows``.  The TypeScript harness consumes
the same table, so a drift on either side turns this pair red.

Paths are resolved from this file (never from ``cwd``); stdlib + pytest only.

Invariant (spec §3.5):

$$
\operatorname{match}_{\mathrm{TS}}(r,p) = \operatorname{match}_{\mathrm{PY}}(r,p)
\quad \forall\,(r,p)\in\text{vectors}
$$
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

BIN = Path(__file__).resolve().parents[1]  # config/bin
VECTORS = BIN.parent / "tools" / "gov" / "scope_vectors.json"  # config/tools/gov/...

sys.path.insert(0, str(BIN))
import spec_scope  # noqa: E402

DATA = json.loads(VECTORS.read_text(encoding="utf-8"))
PATTERN_CASES = DATA["pattern_cases"]
SCOPE_CASES = DATA["scope_cases"]


def _ids(cases: list[dict]) -> list[str]:
    return [case["id"] for case in cases]


def test_vector_file_shape() -> None:
    """The table is well-formed and covers the mandated minimum."""
    assert DATA.get("version") == 1, "version must be 1"
    assert len(PATTERN_CASES) >= 17, "the 17 mandated pattern cases are missing"
    assert len(SCOPE_CASES) >= 4, "mandated scope cases are missing"
    ids = _ids(PATTERN_CASES) + _ids(SCOPE_CASES)
    assert len(ids) == len(set(ids)), f"duplicate vector ids: {ids}"
    for case in PATTERN_CASES:
        assert set(case) == {"id", "rel", "pattern", "match"}, case
        assert isinstance(case["match"], bool), case
    for case in SCOPE_CASES:
        assert set(case) == {"id", "rel", "allow", "deny", "allowed"}, case
        assert isinstance(case["allowed"], bool), case
        assert isinstance(case["allow"], list), case
        assert isinstance(case["deny"], list), case


@pytest.mark.parametrize("case", PATTERN_CASES, ids=_ids(PATTERN_CASES))
def test_pattern_case(case: dict) -> None:
    """``glob_match`` agrees with the frozen expectation of every vector."""
    got = spec_scope.glob_match(case["rel"], case["pattern"])
    assert got is case["match"], (
        f"pattern case {case['id']!r}: "
        f"glob_match({case['rel']!r}, {case['pattern']!r}) = {got!r}, "
        f"expected {case['match']!r}"
    )


@pytest.mark.parametrize("case", SCOPE_CASES, ids=_ids(SCOPE_CASES))
def test_scope_case(case: dict) -> None:
    """``scope_allows`` agrees with the frozen expectation of every vector."""
    scope = spec_scope.Scope(tuple(case["allow"]), tuple(case["deny"]))
    got = spec_scope.scope_allows(scope, case["rel"])
    assert got is case["allowed"], (
        f"scope case {case['id']!r}: "
        f"scope_allows(allow={case['allow']!r}, deny={case['deny']!r}, "
        f"rel={case['rel']!r}) = {got!r}, expected {case['allowed']!r}"
    )
