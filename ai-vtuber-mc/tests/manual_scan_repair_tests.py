"""
Manual tests for scan_for_specific_block missing-targets repair.

Run:  python tests/manual_scan_repair_tests.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.game_brain import (
    BrainDecision,
    _repair_scan_specific_block_args,
    _WOOD_LOG_TARGETS,
    _SCAN_WOOD_TARGETS,
)


def _decision(action: str = "scan_for_specific_block", args: dict | None = None) -> BrainDecision:
    return BrainDecision(
        objective="find wood",
        action=action,
        args=args or {},
        speech="",
        mood="neutral",
        reason="test",
    )


_WOOD_LOOP_STUCK: dict = {
    "active": True,
    "kind": "underground_no_wood_no_workspace",
    "facts": {"no_logs_nearby": True},
}

_OTHER_STUCK: dict = {
    "active": True,
    "kind": "navigation_stuck",
    "facts": {},
}


# ─── 1. targets missing, in wood loop → repaired with max 6 targets ──────────
def test_repair_in_wood_loop() -> None:
    d = _decision(args={"radius": 32})
    out = _repair_scan_specific_block_args(d, _WOOD_LOOP_STUCK)
    assert isinstance(out.args.get("targets"), list), "targets should be filled"
    # Repair fills the 6 most common overworld logs (scan_for_specific_block max).
    assert len(out.args["targets"]) == len(_SCAN_WOOD_TARGETS), f"expected 6 targets, got {len(out.args['targets'])}"
    assert out.args["targets"] == list(_SCAN_WOOD_TARGETS)
    assert out.args.get("args_repaired") is True
    assert out.args.get("repair_reason") == "wood_dependency_loop_default_log_targets"
    assert out.args.get("radius") == 32, "existing args preserved"
    print("test_repair_in_wood_loop PASSED  targets:", out.args["targets"])


# ─── 2. targets missing, not in wood loop → unchanged (policy will reject) ───
def test_no_repair_outside_wood_loop() -> None:
    d = _decision(args={"radius": 32})
    out = _repair_scan_specific_block_args(d, _OTHER_STUCK)
    assert out.args.get("targets") is None, "targets should not be filled"
    assert out.args.get("args_repaired") is None
    print("test_no_repair_outside_wood_loop PASSED  (args unchanged, policy will reject)")


# ─── 3. targets missing, no stuck state → unchanged ──────────────────────────
def test_no_repair_no_stuck_state() -> None:
    d = _decision(args={})
    out = _repair_scan_specific_block_args(d, None)
    assert out.args.get("targets") is None
    print("test_no_repair_no_stuck_state PASSED")


# ─── 4. targets already valid → untouched ─────────────────────────────────────
def test_valid_targets_untouched() -> None:
    d = _decision(args={"targets": ["oak_log", "birch_log"]})
    out = _repair_scan_specific_block_args(d, _WOOD_LOOP_STUCK)
    assert out.args["targets"] == ["oak_log", "birch_log"], "should not override valid targets"
    assert out.args.get("args_repaired") is None
    print("test_valid_targets_untouched PASSED")


# ─── 5. wrong action → untouched ─────────────────────────────────────────────
def test_wrong_action_untouched() -> None:
    d = _decision(action="collect_wood", args={})
    out = _repair_scan_specific_block_args(d, _WOOD_LOOP_STUCK)
    assert out.args.get("targets") is None
    assert out.action == "collect_wood"
    print("test_wrong_action_untouched PASSED")


# ─── 6. empty list targets → treated as missing, repaired in wood loop ───────
def test_empty_targets_repaired() -> None:
    d = _decision(args={"targets": []})
    out = _repair_scan_specific_block_args(d, _WOOD_LOOP_STUCK)
    assert isinstance(out.args.get("targets"), list)
    assert len(out.args["targets"]) == 6, f"expected 6, got {len(out.args['targets'])}"
    assert out.args.get("args_repaired") is True
    print("test_empty_targets_repaired PASSED  targets count:", len(out.args["targets"]))


def main() -> None:
    test_repair_in_wood_loop()
    test_no_repair_outside_wood_loop()
    test_no_repair_no_stuck_state()
    test_valid_targets_untouched()
    test_wrong_action_untouched()
    test_empty_targets_repaired()
    print("\nAll manual_scan_repair_tests PASSED.")


if __name__ == "__main__":
    main()
