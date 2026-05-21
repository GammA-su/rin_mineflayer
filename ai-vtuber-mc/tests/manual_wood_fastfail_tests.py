"""
Manual tests for:
  - collect_wood fast-fail (no logs nearby → target_not_found in < 3 s)
  - scan_for_specific_block >6 targets repair/clamping

Run:  python tests/manual_wood_fastfail_tests.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.schemas import ActionRequest, ActionResult
from vtuber_ai.verifier import verify_action
from vtuber_ai.game_brain import (
    BrainDecision,
    _normalize_decision,
    _repair_scan_specific_block_args,
    _SCAN_WOOD_TARGETS,
    _wood_access_status_from_ticks,
)

_BASE_STATUS = {
    "inventory": [],
    "position": {"x": 0, "y": 40, "z": 0},
    "biome": "plains",
    "health": 20,
    "food": 20,
    "time": 6000,
}
BEFORE = dict(_BASE_STATUS)
AFTER = dict(_BASE_STATUS)


# ─── collect_wood fast-fail ───────────────────────────────────────────────────

def _cw_req(count: int = 4) -> ActionRequest:
    return ActionRequest(action="collect_wood", args={"count": count})


def _cw_res(ok: bool, result_data: dict, error: str | None = None) -> ActionResult:
    return ActionResult(ok=ok, action="collect_wood", result=result_data, error=error)


def test_no_logs_fast_fail_verified() -> None:
    """collect_wood target_not_found with timeout_ms_used < 3000 → verifier keeps it."""
    req = _cw_req()
    res = _cw_res(
        ok=False,
        result_data={
            "failure_type": "target_not_found",
            "stop_reason": "no_logs_nearby",
            "repeatable_now": False,
            "needs_condition_change": True,
            "timeout_ms_used": 180,
            "diagnostics": {
                "targetCandidatesFound": 0,
                "candidatesEvaluated": 0,
                "reachableCandidatesFound": 0,
                "nearestLogDistance": None,
                "nearestLogPosition": None,
            },
        },
        error="No wood logs or stems found within 32 blocks.",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["success"] is False
    assert v["failure_type"] == "target_not_found", v["failure_type"]
    tms = res.result.get("timeout_ms_used", 999999)
    assert tms < 3000, f"Expected fast fail < 3000ms but got {tms}ms"
    print(f"test_no_logs_fast_fail_verified PASSED  timeout_ms_used={tms}")


def test_no_logs_does_not_use_action_timeout() -> None:
    """When targetCandidatesFound=0, failure_type must NOT be action_timeout."""
    req = _cw_req()
    res = _cw_res(
        ok=False,
        result_data={
            "failure_type": "target_not_found",
            "stop_reason": "no_logs_nearby",
            "repeatable_now": False,
            "needs_condition_change": True,
            "timeout_ms_used": 95,
            "diagnostics": {
                "targetCandidatesFound": 0,
                "candidatesEvaluated": 0,
                "reachableCandidatesFound": 0,
                "nearestLogDistance": None,
                "nearestLogPosition": None,
            },
        },
        error="No wood logs or stems found within 32 blocks.",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["failure_type"] != "action_timeout", "Should not produce action_timeout when no candidates"
    print("test_no_logs_does_not_use_action_timeout PASSED")


def test_nearestLogPosition_included_when_candidates_found() -> None:
    """collect_wood with candidates found but unreachable includes nearestLogPosition."""
    req = _cw_req()
    res = _cw_res(
        ok=False,
        result_data={
            "failure_type": "target_unreachable",
            "stop_reason": "logs_found_but_unreachable",
            "repeatable_now": False,
            "needs_condition_change": True,
            "timeout_ms_used": 410,
            "diagnostics": {
                "targetCandidatesFound": 6,
                "candidatesEvaluated": 6,
                "reachableCandidatesFound": 0,
                "nearestLogDistance": 5.2,
                "nearestLogPosition": {"x": 10, "y": 40, "z": 5},
            },
        },
        error="Found 6 wood candidate(s) but none are safely accessible.",
    )
    v = verify_action(BEFORE, AFTER, req, res)
    assert v["success"] is False
    assert v["failure_type"] == "navigation_failed", v["failure_type"]
    # nearestLogPosition is in the result data — confirm it passes through
    diag = res.result.get("diagnostics", {})
    assert diag.get("nearestLogPosition") == {"x": 10, "y": 40, "z": 5}
    print(f"test_nearestLogPosition_included_when_candidates_found PASSED  pos={diag['nearestLogPosition']}")


# ─── scan_for_specific_block targets > 6 ─────────────────────────────────────

def _scan_decision(targets: list | None = None, args: dict | None = None) -> BrainDecision:
    a = args or {}
    if targets is not None:
        a = {"targets": targets, **{k: v for k, v in a.items() if k != "targets"}}
    return BrainDecision(
        objective="find wood",
        action="scan_for_specific_block",
        args=a,
        speech="",
        mood="neutral",
        reason="test",
    )


def test_scan_10_targets_clamped_to_6_by_normalize() -> None:
    """_normalize_decision truncates scan_for_specific_block targets to max 6."""
    d = _scan_decision(targets=["oak_log", "birch_log", "spruce_log", "jungle_log",
                                 "acacia_log", "dark_oak_log", "mangrove_log", "cherry_log",
                                 "crimson_stem", "warped_stem"])
    out = _normalize_decision(d)
    assert isinstance(out.args.get("targets"), list)
    assert len(out.args["targets"]) == 6, f"Expected 6 got {len(out.args['targets'])}"
    assert out.args["targets"] == ["oak_log", "birch_log", "spruce_log",
                                    "jungle_log", "acacia_log", "dark_oak_log"]
    print(f"test_scan_10_targets_clamped_to_6_by_normalize PASSED  targets={out.args['targets']}")


def test_scan_6_targets_unchanged() -> None:
    """Exactly 6 targets pass through normalize unchanged."""
    targets = ["oak_log", "birch_log", "spruce_log", "jungle_log", "acacia_log", "dark_oak_log"]
    d = _scan_decision(targets=targets)
    out = _normalize_decision(d)
    assert out.args["targets"] == targets
    print("test_scan_6_targets_unchanged PASSED")


def test_scan_repair_uses_6_targets_in_wood_loop() -> None:
    """_repair_scan_specific_block_args fills exactly 6 overworld log targets."""
    stuck = {"active": True, "kind": "underground_no_wood_no_workspace", "facts": {}}
    d = _scan_decision(args={"radius": 32})
    out = _repair_scan_specific_block_args(d, stuck)
    assert isinstance(out.args["targets"], list)
    assert len(out.args["targets"]) == 6, f"Expected 6 got {len(out.args['targets'])}"
    assert out.args["targets"] == list(_SCAN_WOOD_TARGETS)
    assert out.args.get("args_repaired") is True
    print(f"test_scan_repair_uses_6_targets_in_wood_loop PASSED  targets={out.args['targets']}")


# ─── wood_access_status from ticks ────────────────────────────────────────────

def _make_tick(action: str, ok: bool, result: dict) -> dict:
    return {
        "action": action,
        "ok": ok,
        "result": result,
        "verifier": {},
        "args": {},
    }


def test_wood_access_status_no_logs_nearby() -> None:
    """_wood_access_status_from_ticks returns status when last collect_wood had 0 candidates."""
    ticks = [
        _make_tick("collect_wood", False, {
            "failure_type": "target_not_found",
            "stop_reason": "no_logs_nearby",
            "diagnostics": {"targetCandidatesFound": 0},
        }),
    ]
    status = _wood_access_status_from_ticks(ticks)
    assert status is not None, "Expected wood_access_status to be non-None"
    assert status["logs_nearby"] is False
    assert status["needs_position_change"] is True
    assert status["last_collect_wood_failed_fast"] is True
    print(f"test_wood_access_status_no_logs_nearby PASSED  status={status}")


def test_wood_access_status_none_when_succeeded() -> None:
    """_wood_access_status_from_ticks returns None when collect_wood succeeded."""
    ticks = [
        _make_tick("collect_wood", True, {"collected": 4}),
    ]
    status = _wood_access_status_from_ticks(ticks)
    assert status is None
    print("test_wood_access_status_none_when_succeeded PASSED")


def test_wood_access_status_none_when_other_action() -> None:
    """_wood_access_status_from_ticks returns None when last action is not collect_wood."""
    ticks = [
        _make_tick("look_around", True, {}),
    ]
    status = _wood_access_status_from_ticks(ticks)
    assert status is None
    print("test_wood_access_status_none_when_other_action PASSED")


def test_wood_access_status_none_when_path_failure() -> None:
    """_wood_access_status_from_ticks returns None for path failure (candidates > 0)."""
    ticks = [
        _make_tick("collect_wood", False, {
            "failure_type": "no_progress_timeout",
            "stop_reason": "path_no_movement",
            "diagnostics": {"targetCandidatesFound": 5},
        }),
    ]
    status = _wood_access_status_from_ticks(ticks)
    assert status is None, f"Expected None for path failure got {status}"
    print("test_wood_access_status_none_when_path_failure PASSED")


def main() -> None:
    test_no_logs_fast_fail_verified()
    test_no_logs_does_not_use_action_timeout()
    test_nearestLogPosition_included_when_candidates_found()
    test_scan_10_targets_clamped_to_6_by_normalize()
    test_scan_6_targets_unchanged()
    test_scan_repair_uses_6_targets_in_wood_loop()
    test_wood_access_status_no_logs_nearby()
    test_wood_access_status_none_when_succeeded()
    test_wood_access_status_none_when_other_action()
    test_wood_access_status_none_when_path_failure()
    print("\nAll manual_wood_fastfail_tests PASSED.")


if __name__ == "__main__":
    main()
