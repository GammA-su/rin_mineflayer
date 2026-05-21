"""
Manual tests for the new collectWood result shapes.

Each test feeds a synthetic JS action result into verify_action and asserts
the verifier classifies it correctly.  No live bot required.

Run:  python tests/manual_collect_wood_tests.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.schemas import ActionRequest, ActionResult
from vtuber_ai.verifier import verify_action

# Minimal before/after status dicts accepted by summarize_status.
_BASE_STATUS = {
    "inventory": [],
    "position": {"x": 0, "y": 64, "z": 0},
    "biome": "forest",
    "health": 20,
    "food": 20,
    "time": 6000,
}

BEFORE = dict(_BASE_STATUS)
AFTER = dict(_BASE_STATUS)


def _req(count: int = 4) -> ActionRequest:
    return ActionRequest(action="collect_wood", args={"count": count})


def _res(ok: bool, result_data: dict, error: str | None = None) -> ActionResult:
    return ActionResult(ok=ok, action="collect_wood", result=result_data, error=error)


# ─── 1. No logs nearby ────────────────────────────────────────────────────────
def test_no_logs_nearby() -> None:
    """preflight scan finds zero blocks → target_not_found, needs_condition_change."""
    req = _req()
    res = _res(
        ok=False,
        result_data={
            "failure_type": "target_not_found",
            "stop_reason": "no_logs_nearby",
            "repeatable_now": False,
            "needs_condition_change": True,
            "timeout_ms_used": 120,
            "diagnostics": {
                "targetCandidatesFound": 0,
                "candidatesEvaluated": 0,
                "reachableCandidatesFound": 0,
                "nearestLogDistance": None,
            },
        },
        error="No wood logs or stems found within 32 blocks.",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["success"] is False
    # target_not_found passes through unchanged (not in the nav-normalisation set).
    assert v["failure_type"] == "target_not_found", v["failure_type"]
    print("test_no_logs_nearby PASSED  failure_type:", v["failure_type"])


# ─── 2. Logs exist but no reachable stand ────────────────────────────────────
def test_logs_unreachable() -> None:
    """candidates found but none have exposed face + safe stand → target_unreachable
    (verifier normalises to navigation_failed)."""
    req = _req()
    res = _res(
        ok=False,
        result_data={
            "failure_type": "target_unreachable",
            "stop_reason": "logs_found_but_unreachable",
            "repeatable_now": False,
            "needs_condition_change": True,
            "timeout_ms_used": 290,
            "diagnostics": {
                "targetCandidatesFound": 12,
                "candidatesEvaluated": 8,
                "reachableCandidatesFound": 0,
                "nearestLogDistance": 6.2,
            },
        },
        error="Found 12 wood candidate(s) but none are safely accessible.",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["success"] is False
    # The verifier normalises target_unreachable → navigation_failed.
    assert v["failure_type"] == "navigation_failed", v["failure_type"]
    print("test_logs_unreachable PASSED  failure_type:", v["failure_type"])


# ─── 3. Reachable log — pathfinder stuck, no movement for 4 s ────────────────
def test_path_stuck() -> None:
    """per-candidate stuck detection fires → no_progress_timeout / path_no_movement."""
    req = _req()
    res = _res(
        ok=False,
        result_data={
            "failure_type": "no_progress_timeout",
            "stop_reason": "path_no_movement",
            "repeatable_now": False,
            "needs_condition_change": True,
            "diagnostics": {
                "targetCandidatesFound": 5,
                "candidatesEvaluated": 5,
                "reachableCandidatesFound": 2,
                "nearestLogDistance": 9.1,
                "selectedLogPosition": {"x": 10, "y": 64, "z": 5},
                "selectedStandPosition": {"x": 9, "y": 64, "z": 5},
                "pathAttempts": 2,
                "distance_moved": 0.2,
                "failed_because": "stuck_no_movement",
            },
        },
        error="No wood collected — 2 reachable candidate(s), 2 path attempt(s).",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["success"] is False
    # no_progress_timeout passes through unchanged.
    assert v["failure_type"] == "no_progress_timeout", v["failure_type"]
    print("test_path_stuck PASSED  failure_type:", v["failure_type"])


# ─── 4. Partial collection (1 of 4 logs mined before time ran out) ───────────
def test_partial_collection() -> None:
    """partial_progress_timeout → verifier keeps partial_success=True, repeatable_now=True."""
    req = _req()
    res = _res(
        ok=False,
        result_data={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "collect_wood_partial_progress",
            "repeatable_now": True,
            "partial_success": True,
            "continuation_relevant": True,
            "collected": 2,
            "requested": 4,
            "diagnostics": {
                "targetCandidatesFound": 4,
                "reachableCandidatesFound": 3,
                "pathAttempts": 2,
                "distance_moved": 11.3,
                "blocks_dug": 2,
                "inventory_delta": {"oak_log": 2},
            },
        },
        error="Collected 2/4 wood (partial progress).",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["success"] is False
    assert v["failure_type"] == "partial_progress_timeout", v["failure_type"]
    assert v["partial_success"] is True, v
    assert v["repeatable_now"] is True, v
    print("test_partial_collection PASSED  failure_type:", v["failure_type"],
          "partial_success:", v["partial_success"])


# ─── 5. Full collection success ──────────────────────────────────────────────
def test_full_collection() -> None:
    """ok=True with inventory gain → verifier reports success."""
    req = _req()
    res = _res(
        ok=True,
        result_data={
            "collected": 4,
            "requested": 4,
            "stop_reason": "goal_reached",
            "partial_success": False,
            "targetCandidatesFound": 6,
            "reachableCandidatesFound": 4,
            "pathAttempts": 3,
            "distance_moved": 18.7,
            "blocks_dug": 4,
            "inventory_delta": {"oak_log": 4},
        },
    )
    after_with_wood = {**AFTER, "inventory": [{"name": "oak_log", "count": 4}]}
    v = verify_action(BEFORE, after_with_wood, req, res)
    assert v["success"] is True, v
    print("test_full_collection PASSED")


# ─── 6. action_timeout with zero movement → upgraded to no_progress_timeout ──
def test_action_timeout_zero_progress_upgrade() -> None:
    """JS emits action_timeout + needs_condition_change + distance_moved < 0.5
    → verifier upgrades to no_progress_timeout and sets needs_condition_change=True."""
    req = _req()
    res = _res(
        ok=False,
        result_data={
            "failure_type": "action_timeout",
            "needs_condition_change": True,
            "diagnostics": {
                "distance_moved": 0.1,
                "inventory_delta": {},
                "currentSubstep": "pathfind",
                "timeout_classification": "timeout_path_execution_no_movement",
            },
        },
        error="Timed out after 30000ms.",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["success"] is False
    assert v["failure_type"] == "no_progress_timeout", v["failure_type"]
    assert v["needs_condition_change"] is True, v
    print("test_action_timeout_zero_progress_upgrade PASSED  failure_type:", v["failure_type"])


def main() -> None:
    test_no_logs_nearby()
    test_logs_unreachable()
    test_path_stuck()
    test_partial_collection()
    test_full_collection()
    test_action_timeout_zero_progress_upgrade()
    print("\nAll manual_collect_wood_tests PASSED.")


if __name__ == "__main__":
    main()
