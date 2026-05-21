from pathlib import Path
import asyncio
import os
import tempfile
import sys
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.agent import plan_objective_action
from vtuber_ai.autonomy import _is_stale_workspace_loop, run_agent_live, run_agent_tick
from vtuber_ai.curriculum import inventory_counts, recommend_objective
from vtuber_ai.game_brain import (
    AUTONOMOUS_ALLOWED_ACTIONS,
    find_blocked_family,
    _rts_position_stuck_from_ticks,
    _workspace_navigation_stuck_state,
)
from vtuber_ai.memory import is_low_information_action, is_observation_action
from vtuber_ai.schemas import ActionRequest, ActionResult, AgentLiveRequest
from vtuber_ai.verifier import verify_action, verify_step
from vtuber_ai.world_memory import (
    STALE_WORKSPACE_CONFIDENCE_THRESHOLD,
    mark_workspace_unreachable,
    nearest_workspace,
    remember_workspace,
)


def status_with_inventory(items: list[dict]) -> dict:
    return {
        "ok": True,
        "connected": True,
        "entityReady": True,
        "inventory": items,
        "nearbyBlocks": {},
    }


def with_nearby_crafting_table(status: dict) -> dict:
    status = dict(status)
    status["nearbyBlocks"] = {
        "crafting_table": {
            "name": "crafting_table",
            "position": {"x": 1, "y": 64, "z": 1},
            "distance": 2,
        }
    }
    return status


def main() -> None:
    empty = status_with_inventory([])
    assert recommend_objective(empty) == "collect_wood"

    logs = status_with_inventory([{"name": "oak_log", "count": 1}])
    assert recommend_objective(logs) == "craft_planks"

    planks = status_with_inventory([{"name": "oak_planks", "count": 4}])
    assert recommend_objective(planks) == "craft_sticks"

    sticks = status_with_inventory(
        [
            {"name": "oak_planks", "count": 4},
            {"name": "stick", "count": 2},
        ]
    )
    assert recommend_objective(sticks) == "craft_crafting_table"

    table = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "oak_planks", "count": 3},
        ]
    )
    assert recommend_objective(table) == "place_crafting_table"
    assert recommend_objective(with_nearby_crafting_table(table)) == "craft_wooden_pickaxe"

    wooden_pick = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "wooden_pickaxe", "count": 1},
        ]
    )
    assert recommend_objective(wooden_pick) == "mine_stone"

    stone_ready = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "wooden_pickaxe", "count": 1},
            {"name": "cobblestone", "count": 3},
        ]
    )
    assert recommend_objective(stone_ready) == "craft_stone_pickaxe"

    complete = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "wooden_pickaxe", "count": 1},
            {"name": "cobblestone", "count": 3},
            {"name": "stone_pickaxe", "count": 1},
        ]
    )
    assert recommend_objective(complete) == "tier1_complete"

    assert inventory_counts(status_with_inventory([{"name": "stick", "count": 1}, {"name": "stick", "count": 2}]))[
        "stick"
    ] == 3

    action = plan_objective_action("collect_wood", "test mission", "agent")
    assert action.action == "collect_wood"
    assert plan_objective_action("place_crafting_table", "test mission", "agent").action == "place_crafting_table"

    verification = verify_step(
        objective="collect_wood",
        before_status=empty,
        after_status=logs,
        action_request=action,
        action_result=ActionResult(ok=True, action="collect_wood"),
    )
    assert verification["success"] is True
    assert verification["next_recommended_objective"] == "craft_planks"

    failed = verify_step(
        objective="collect_wood",
        before_status=empty,
        after_status=empty,
        action_request=action,
        action_result=ActionResult(ok=False, action="collect_wood", error="not implemented"),
    )
    assert failed["success"] is False

    assert is_observation_action("status") is True
    assert is_observation_action("check_inventory") is True
    assert is_observation_action("look_around") is True
    assert is_observation_action("scan_for_hostiles") is True
    assert is_observation_action("scan_anything_new") is True
    assert is_observation_action("craft_torches") is False
    assert is_low_information_action("status") is True
    assert is_low_information_action("scan_anything_new") is True
    assert is_low_information_action("mine_stone") is False

    # --- VERIFIER: navigation failure → navigation_failed, not bridge_error ---
    empty_status = {"inventory_counts": {}, "nearby_blocks": {}, "nearby_entities": [], "health": 20, "food": 20}

    nav_req = ActionRequest(action="navigate_to_block_type", args={"targets": ["spruce_log"], "radius": 32}, speech="", reason="")
    nav_res = ActionResult(
        ok=False,
        action="navigate_to_block_type",
        error="Navigation path failed: Timed out pathing to target block after 15000ms.",
        result={"targets": ["spruce_log"], "radius": 32, "target": {"name": "spruce_log", "distance": 28}},
    )
    v_nav = verify_action(empty_status, empty_status, nav_req, nav_res)
    assert v_nav["failure_type"] == "navigation_failed", \
        f"navigation timeout must be navigation_failed, not {v_nav['failure_type']}"
    assert v_nav["failure_type"] != "bridge_error", "navigation timeout must never become bridge_error"
    fb = v_nav.get("failed_because")
    assert isinstance(fb, list) and fb, f"navigation failure must produce failed_because, got: {fb}"
    assert any(e.get("kind") == "path_timeout" for e in fb), \
        f"expected path_timeout in failed_because, got: {fb}"
    pt = next(e for e in fb if e.get("kind") == "path_timeout")
    assert pt.get("target") == "spruce_log", f"path_timeout must name the target, got: {pt}"
    assert pt.get("timeout_ms") == 15000, f"timeout_ms must be extracted from error, got: {pt}"
    assert v_nav.get("repeatable_now") is True, "navigation failure is repeatable if position changes"
    assert v_nav.get("repeat_condition") is not None
    rs = v_nav.get("relevant_state")
    assert isinstance(rs, dict) and "target" in rs, f"relevant_state must include target, got: {rs}"

    # --- VERIFIER: no accessible target → nearby_block failed_because ---
    nav_nf_res = ActionResult(
        ok=False,
        action="navigate_to_block_type",
        error="No accessible target block found. Try explore_nearby or choose a different target.",
        result={"targets": ["spruce_log"], "radius": 32, "targetCandidatesFound": 0},
    )
    v_nf = verify_action(empty_status, empty_status, nav_req, nav_nf_res)
    assert v_nf["failure_type"] == "navigation_failed"
    fb_nf = v_nf.get("failed_because") or []
    assert any(e.get("kind") == "nearby_block" for e in fb_nf), \
        f"no-target failure must produce nearby_block, got: {fb_nf}"

    # --- VERIFIER: actual bridge crash stays bridge_error ---
    bridge_req = ActionRequest(action="status", args={}, speech="", reason="")
    bridge_res = ActionResult(
        ok=False,
        action="status",
        error="Mineflayer bridge request failed.",
    )
    v_bridge = verify_action(empty_status, empty_status, bridge_req, bridge_res)
    assert v_bridge["failure_type"] == "bridge_error", \
        f"bridge crash must stay bridge_error, got: {v_bridge['failure_type']}"

    # --- VERIFIER: result-level failure_type=path_timeout from bot → normalized to navigation_failed ---
    nav_res2 = ActionResult(
        ok=False,
        action="navigate_to_block_type",
        error="Navigation path failed: Timed out pathing to target block after 15000ms.",
        result={"targets": ["oak_log"], "radius": 24, "failure_type": "path_timeout"},
    )
    v_nav2 = verify_action(empty_status, empty_status, nav_req, nav_res2)
    assert v_nav2["failure_type"] == "navigation_failed", \
        f"path_timeout from bot must normalise to navigation_failed, got: {v_nav2['failure_type']}"

    # --- VERIFIER: collect_wood acquisition timeout is recoverable, not bridge_error ---
    wood_timeout_status = {
        "ok": True,
        "inventory": [],
        "nearbyBlocks": {},
        "nearbyBlockCounts": {"oak_log": 3, "spruce_log": 2, "dirt": 10},
        "nearbyEntities": [],
        "position": {"x": 10, "y": 64, "z": -4},
        "health": 20,
        "food": 20,
    }
    wood_req = ActionRequest(action="collect_wood", args={}, speech="", reason="")
    wood_res = ActionResult(
        ok=False,
        action="collect_wood",
        error="Block acquisition failed: Timed out collect_wood after 60000ms.",
    )
    v_wood = verify_action(wood_timeout_status, wood_timeout_status, wood_req, wood_res)
    assert v_wood["failure_type"] == "resource_acquisition_failed", \
        f"collect_wood timeout must be resource_acquisition_failed, got: {v_wood['failure_type']}"
    assert v_wood["failure_type"] != "bridge_error", "collect_wood timeout must never become bridge_error"
    assert v_wood.get("repeatable_now") is True
    fb_wood = v_wood.get("failed_because") or []
    pt_wood = next((e for e in fb_wood if e.get("kind") == "path_timeout"), None)
    assert pt_wood is not None, f"collect_wood timeout must produce path_timeout, got: {fb_wood}"
    assert pt_wood.get("action") == "collect_wood"
    assert pt_wood.get("target") == [
        "oak_log", "spruce_log", "birch_log", "jungle_log", "acacia_log",
        "dark_oak_log", "mangrove_log", "cherry_log", "crimson_stem", "warped_stem",
    ]
    assert pt_wood.get("timeout_ms") == 60000
    wood_state = v_wood.get("relevant_state")
    assert isinstance(wood_state, dict) and wood_state.get("position") == {"x": 10, "y": 64, "z": -4}
    assert "nearbyBlockCounts" in wood_state and wood_state["nearbyBlockCounts"]["oak_log"] == 3

    # --- VERIFIER: exact "need N item, have M" missing-material errors preserve quantities ---
    def assert_need_have_error(error: str, item: str, need: int, have: int) -> None:
        result = verify_action(
            empty_status,
            empty_status,
            ActionRequest(action="craft_sticks", args={}, speech="", reason=""),
            ActionResult(ok=False, action="craft_sticks", error=error),
        )
        expected = {"kind": "inventory_item", "item": item, "need": need, "have": have}
        assert expected in (result.get("failed_because") or []), \
            f"expected exact failed_because {expected}, got: {result.get('failed_because')}"

    assert_need_have_error("Missing materials: need 2 planks, have 1.", "planks", 2, 1)
    assert_need_have_error("Missing materials: need 3 cobblestone, have 0.", "cobblestone", 3, 0)
    assert_need_have_error("Missing materials: need 8 cobblestone, have 4.", "cobblestone", 8, 4)

    # --- VERIFIER: smelt_item missing input arg ---
    smelt_base_status = {
        "ok": True, "health": 20, "food": 20,
        "inventory": [{"name": "coal", "count": 10}],
        "nearbyBlocks": {"furnace": {"name": "furnace", "distance": 2.0}},
        "nearbyEntities": [],
    }
    v_smelt_no_input = verify_action(
        smelt_base_status, smelt_base_status,
        ActionRequest(action="smelt_item", args={"count": 64}, speech="", reason=""),
        ActionResult(ok=False, action="smelt_item", error="Action 'smelt_item' requires args.input as a non-empty string."),
    )
    assert v_smelt_no_input["failure_type"] == "invalid_args", \
        f"missing input must be invalid_args, got {v_smelt_no_input['failure_type']}"
    assert v_smelt_no_input["repeatable_now"] is False
    fb_no_input = v_smelt_no_input.get("failed_because") or []
    assert len(fb_no_input) == 1, fb_no_input
    assert fb_no_input[0]["kind"] == "invalid_args", fb_no_input[0]
    assert fb_no_input[0]["action"] == "smelt_item", fb_no_input[0]
    assert fb_no_input[0]["missing_arg"] == "input", fb_no_input[0]
    rs_no_input = v_smelt_no_input.get("relevant_state") or {}
    assert "has_smeltable_items" in rs_no_input, rs_no_input
    assert "furnace_usable_nearby" in rs_no_input, rs_no_input
    assert rs_no_input["furnace_usable_nearby"] is True
    ia_no_input = rs_no_input.get("item_affordances") or {}
    assert "has_smeltable_items" in ia_no_input, ia_no_input
    assert "has_fuel" in ia_no_input, ia_no_input

    # --- VERIFIER: smelt_item invalid input (cobblestone not smeltable) ---
    v_smelt_bad_input = verify_action(
        smelt_base_status, smelt_base_status,
        ActionRequest(action="smelt_item", args={"input": "cobblestone"}, speech="", reason=""),
        ActionResult(ok=False, action="smelt_item", error="Action 'smelt_item' args.input must be one of: ..."),
    )
    assert v_smelt_bad_input["failure_type"] == "invalid_args", \
        f"invalid input must be invalid_args, got {v_smelt_bad_input['failure_type']}"
    assert v_smelt_bad_input["repeatable_now"] is False
    fb_bad = v_smelt_bad_input.get("failed_because") or []
    assert len(fb_bad) == 1, fb_bad
    assert fb_bad[0]["kind"] == "invalid_enum_value", fb_bad[0]
    assert fb_bad[0]["action"] == "smelt_item", fb_bad[0]
    assert fb_bad[0]["arg"] == "input", fb_bad[0]
    assert fb_bad[0]["received"] == "cobblestone", fb_bad[0]
    allowed_vals = fb_bad[0].get("allowed_values") or []
    assert "raw_iron" in allowed_vals, allowed_vals
    assert "cobblestone" not in allowed_vals, allowed_vals
    rs_bad = v_smelt_bad_input.get("relevant_state") or {}
    assert "smeltable_items" in rs_bad, rs_bad
    assert "fuel_items" in rs_bad, rs_bad

    # --- VERIFIER: smelt_item valid input but not in inventory ---
    smelt_no_iron_status = {
        "ok": True, "health": 20, "food": 20,
        "inventory": [{"name": "coal", "count": 5}],  # raw_iron consumed / never had it
        "nearbyBlocks": {"furnace": {"name": "furnace", "distance": 2.0}},
        "nearbyEntities": [],
    }
    v_smelt_no_iron = verify_action(
        smelt_no_iron_status, smelt_no_iron_status,
        ActionRequest(action="smelt_item", args={"input": "raw_iron"}, speech="", reason=""),
        ActionResult(ok=False, action="smelt_item", error="Missing materials: need 1 raw_iron, have 0."),
    )
    assert v_smelt_no_iron["failure_type"] == "missing_materials", \
        f"missing raw_iron must be missing_materials, got {v_smelt_no_iron['failure_type']}"
    assert v_smelt_no_iron["repeatable_now"] is False
    fb_iron = v_smelt_no_iron.get("failed_because") or []
    assert len(fb_iron) == 1, fb_iron
    assert fb_iron[0]["kind"] == "inventory_item", fb_iron[0]
    assert fb_iron[0]["item"] == "raw_iron", fb_iron[0]
    assert fb_iron[0]["need"] == 1, fb_iron[0]
    assert fb_iron[0]["have"] == 0, fb_iron[0]
    rs_iron = v_smelt_no_iron.get("relevant_state") or {}
    assert "has_smeltable_items" in rs_iron, rs_iron
    assert rs_iron["has_smeltable_items"] is False  # no raw_iron, no other smeltables
    assert "fuel_items" in rs_iron, rs_iron
    assert rs_iron["fuel_items"].get("coal") == 5
    ia_iron = rs_iron.get("item_affordances") or {}
    assert ia_iron.get("has_smeltable_items") is False, ia_iron
    assert ia_iron.get("has_fuel") is True, ia_iron
    assert ia_iron.get("fuel_items", {}).get("coal") == 5, ia_iron

    # --- VERIFIER: scan_for_specific_block missing targets → invalid_args ---
    v_scan_no_targets = verify_action(
        empty_status, empty_status,
        ActionRequest(action="scan_for_specific_block", args={}, speech="", reason=""),
        ActionResult(
            ok=False, action="scan_for_specific_block",
            error="Action 'scan_for_specific_block' requires args.targets as a non-empty list of block names.",
        ),
    )
    assert v_scan_no_targets["failure_type"] == "invalid_args", \
        f"missing targets must be invalid_args, got {v_scan_no_targets['failure_type']}"
    assert v_scan_no_targets["repeatable_now"] is False
    fb_scan = v_scan_no_targets.get("failed_because") or []
    assert len(fb_scan) == 1, fb_scan
    assert fb_scan[0]["kind"] == "invalid_args", fb_scan[0]
    assert fb_scan[0]["action"] == "scan_for_specific_block", fb_scan[0]
    assert fb_scan[0]["missing_arg"] == "targets", fb_scan[0]
    assert "non-empty" in fb_scan[0].get("expected", ""), fb_scan[0]

    # --- VERIFIER: scan_for_specific_block empty targets list → invalid_args ---
    v_scan_empty = verify_action(
        empty_status, empty_status,
        ActionRequest(action="scan_for_specific_block", args={"targets": []}, speech="", reason=""),
        ActionResult(
            ok=False, action="scan_for_specific_block",
            error="Action 'scan_for_specific_block' requires args.targets as a non-empty list of block names.",
        ),
    )
    assert v_scan_empty["failure_type"] == "invalid_args"
    assert v_scan_empty["repeatable_now"] is False
    fb_empty = v_scan_empty.get("failed_because") or []
    assert fb_empty[0]["missing_arg"] == "targets", fb_empty[0]

    # --- VERIFIER: scan_for_specific_block with valid targets → generic path (not invalid_args) ---
    v_scan_valid = verify_action(
        empty_status, empty_status,
        ActionRequest(action="scan_for_specific_block", args={"targets": ["iron_ore"]}, speech="", reason=""),
        ActionResult(
            ok=False, action="scan_for_specific_block",
            error="Mineflayer bridge request failed.",
        ),
    )
    assert v_scan_valid["failure_type"] != "invalid_args", \
        "valid targets must not produce invalid_args"

    # --- VERIFIER: mine_iron_ore timeout → kind:action_timeout failed_because, resource_acquisition_attempt ---
    _mine_pos_before = {"inventory_counts": {}, "nearby_blocks": {}, "health": 20, "food": 20,
                        "position": {"x": 10, "y": 60, "z": 10}}
    _mine_pos_same = {"inventory_counts": {}, "nearby_blocks": {}, "health": 20, "food": 20,
                      "position": {"x": 10, "y": 60, "z": 10}}
    v_iron_timeout = verify_action(
        _mine_pos_before, _mine_pos_same,
        ActionRequest(action="mine_iron_ore", args={}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_iron_ore",
            error="Block acquisition failed: timed out after 12000ms.",
            result={"failure_type": "action_timeout"},
        ),
    )
    assert v_iron_timeout["failure_type"] == "resource_acquisition_failed", \
        f"mine_iron_ore timeout must give resource_acquisition_failed, got {v_iron_timeout['failure_type']}"
    fb_iron = v_iron_timeout.get("failed_because") or []
    assert any(e.get("kind") == "action_timeout" for e in fb_iron), \
        f"failed_because must have action_timeout entry: {fb_iron}"
    at_iron = next(e for e in fb_iron if e.get("kind") == "action_timeout")
    assert at_iron["action"] == "mine_iron_ore", at_iron
    assert at_iron["timeout_ms"] == 12000, at_iron
    assert at_iron["recoverable"] is True, at_iron
    ra_iron = next((e for e in fb_iron if e.get("kind") == "resource_acquisition_attempt"), None)
    assert ra_iron is not None, f"must include resource_acquisition_attempt entry: {fb_iron}"
    assert ra_iron["resource_family"] == "iron_ore", ra_iron
    # same position → below POSITION_MEANINGFUL_DELTA_BLOCKS (8) → not meaningful
    assert ra_iron["position_changed_since_last_attempt"] is False, ra_iron
    assert ra_iron["distance_moved_since_last_attempt"] == 0.0, ra_iron
    assert ra_iron["position_change_meaningful"] is False, ra_iron
    # no meaningful movement → repeatable_now=False; family stays blocked
    assert v_iron_timeout.get("repeatable_now") is False, \
        "same-position timeout must not be repeatable (jitter guard)"

    # --- VERIFIER: mine_coal timeout, small jitter (5 blocks < threshold 8) ---
    _mine_coal_before = {"inventory_counts": {"coal": 2}, "nearby_blocks": {}, "health": 20, "food": 20,
                         "position": {"x": 20, "y": 60, "z": 20}}
    _mine_coal_after_jitter = {"inventory_counts": {"coal": 2}, "nearby_blocks": {}, "health": 20, "food": 20,
                               "position": {"x": 25, "y": 60, "z": 20}}
    v_coal_jitter = verify_action(
        _mine_coal_before, _mine_coal_after_jitter,
        ActionRequest(action="mine_coal", args={}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="timed out after 10000ms",
            result={"failure_type": "action_timeout"},
        ),
    )
    assert v_coal_jitter["failure_type"] == "resource_acquisition_failed", \
        f"mine_coal timeout must give resource_acquisition_failed, got {v_coal_jitter['failure_type']}"
    fb_coal = v_coal_jitter.get("failed_because") or []
    assert any(e.get("kind") == "action_timeout" for e in fb_coal), \
        f"failed_because must have action_timeout: {fb_coal}"
    at_coal = next(e for e in fb_coal if e.get("kind") == "action_timeout")
    assert at_coal["action"] == "mine_coal", at_coal
    assert at_coal["timeout_ms"] == 10000, at_coal
    ra_coal = next((e for e in fb_coal if e.get("kind") == "resource_acquisition_attempt"), None)
    assert ra_coal is not None, f"must include resource_acquisition_attempt: {fb_coal}"
    assert ra_coal["resource_family"] == "coal", ra_coal
    # 5-block jitter is below POSITION_MEANINGFUL_DELTA_BLOCKS=8 → not meaningful
    assert ra_coal["position_changed_since_last_attempt"] is False, ra_coal
    assert ra_coal["distance_moved_since_last_attempt"] == 5.0, ra_coal
    assert ra_coal["position_change_meaningful"] is False, ra_coal
    assert v_coal_jitter.get("repeatable_now") is False, "jitter must not unblock"

    # --- VERIFIER: mine_iron_ore timeout, meaningful move (>= 8 blocks) → repeatable_now=True ---
    _mine_pos_far = {"inventory_counts": {}, "nearby_blocks": {}, "health": 20, "food": 20,
                     "position": {"x": 20, "y": 60, "z": 10}}
    v_iron_far = verify_action(
        _mine_pos_before, _mine_pos_far,
        ActionRequest(action="mine_iron_ore", args={}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_iron_ore",
            error="Block acquisition failed: timed out after 12000ms.",
            result={"failure_type": "action_timeout"},
        ),
    )
    fb_far = v_iron_far.get("failed_because") or []
    ra_far = next((e for e in fb_far if e.get("kind") == "resource_acquisition_attempt"), None)
    assert ra_far is not None, fb_far
    assert ra_far["position_changed_since_last_attempt"] is True, ra_far
    assert ra_far["position_change_meaningful"] is True, ra_far
    assert ra_far["distance_moved_since_last_attempt"] >= 8.0, ra_far
    assert v_iron_far.get("repeatable_now") is True, "meaningful move must allow retry"

    # mine_iron_ore without ms number in error → action_timeout entry but no timeout_ms
    v_no_ms = verify_action(
        _mine_pos_before, _mine_pos_same,
        ActionRequest(action="mine_iron_ore", args={}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_iron_ore",
            error="Block acquisition failed: timed out.",
            result={"failure_type": "action_timeout"},
        ),
    )
    fb_no_ms = v_no_ms.get("failed_because") or []
    assert any(e.get("kind") == "action_timeout" for e in fb_no_ms), fb_no_ms
    at_no_ms = next(e for e in fb_no_ms if e.get("kind") == "action_timeout")
    assert "timeout_ms" not in at_no_ms or at_no_ms["timeout_ms"] is None, at_no_ms

    # --- mine_coal: resource_buried failure type passthrough ---
    # Simulates what mineCoal wrapper returns when all candidates are buried.
    _coal_buried_before = {"inventory_counts": {"coal": 0}, "nearby_blocks": {}, "health": 20, "food": 20,
                           "position": {"x": 43, "y": 56, "z": 43}}
    _coal_buried_after = {"inventory_counts": {"coal": 0}, "nearby_blocks": {}, "health": 20, "food": 20,
                          "position": {"x": 43, "y": 56, "z": 43}}
    v_coal_buried = verify_action(
        _coal_buried_before, _coal_buried_after,
        ActionRequest(action="mine_coal", args={"radius": 32}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="No accessible coal_ore found.",
            result={
                "failure_type": "resource_buried",
                "targetCandidatesFound": 18,
                "exposedCandidatesFound": 0,
                "accessCandidatesFound": 0,
                "failed_because": [{
                    "kind": "resource_target_buried",
                    "block": "coal_ore",
                    "candidates_found": 18,
                    "nearest_distance": 14.2,
                    "exposed_faces": 0,
                    "safe_stand_candidate": False,
                }],
            },
        ),
    )
    # Verifier should treat this as a resource acquisition failure, not a timeout.
    assert v_coal_buried["failure_type"] in {"resource_buried", "resource_acquisition_failed"}, \
        f"resource_buried mine_coal must stay classified as resource failure: {v_coal_buried}"
    # repeatable_now=True because position did not change (no movement happened).
    # The verifier applies the timeout position check only for action_timeout errors.
    assert "repeatable_now" in v_coal_buried, v_coal_buried

    # --- mine_coal: partial_progress_timeout passthrough ---
    # The bot made real progress (moved + collected 1 coal) before timeout.
    # Verifier must NOT reclassify this as resource_acquisition_failed via the
    # mine timeout path — the richer bot diagnostics must be preserved.
    _coal_partial_before = {"inventory_counts": {"coal": 0, "wooden_pickaxe": 1}, "nearby_blocks": {}, "health": 20, "food": 20,
                            "position": {"x": 43, "y": 56, "z": 43}}
    _coal_partial_after = {"inventory_counts": {"coal": 1, "wooden_pickaxe": 1}, "nearby_blocks": {}, "health": 20, "food": 20,
                           "position": {"x": 50, "y": 53, "z": 43}}
    v_coal_partial = verify_action(
        _coal_partial_before, _coal_partial_after,
        ActionRequest(action="mine_coal", args={"radius": 32}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="Block acquisition timed out.",
            result={
                "failure_type": "partial_progress_timeout",
                "partial_success": True,
                "collected": 1,
                "inventory_delta": {"coal": 1},
                "failed_because": [{
                    "kind": "partial_progress_timeout",
                    "action": "mine_coal",
                    "timeout_ms": 60000,
                    "progress_signals": ["excavated_blocks:3", "inventory_gain"],
                    "excavated_blocks": 3,
                    "mined_target_blocks": 1,
                    "distance_moved": 4.5,
                    "continuation_relevant": True,
                }],
            },
        ),
    )
    # Must not be overridden to resource_acquisition_failed (that's the hard-timeout path).
    assert v_coal_partial.get("failure_type") == "partial_progress_timeout", (
        f"partial_progress_timeout must be preserved, got {v_coal_partial.get('failure_type')}: {v_coal_partial}"
    )
    assert v_coal_partial.get("repeatable_now") is True, (
        f"partial_progress_timeout must be repeatable: {v_coal_partial}"
    )
    # Confirm continuation_relevant survives passthrough
    _ppt_fb = v_coal_partial.get("failed_because") or []
    _ppt_entry = next((e for e in _ppt_fb if isinstance(e, dict) and e.get("kind") == "partial_progress_timeout"), None)
    assert _ppt_entry is not None, f"failed_because must contain partial_progress_timeout entry: {_ppt_fb}"
    assert _ppt_entry.get("continuation_relevant") is True, f"continuation_relevant must be True: {_ppt_entry}"
    # suggested_next_action and possible_next_actions must be suppressed in verifier output
    assert v_coal_partial.get("suggested_next_action") is None, (
        f"suggested_next_action must not appear in verifier output for partial_progress_timeout: {v_coal_partial}"
    )
    assert v_coal_partial.get("possible_next_actions") is None, (
        f"possible_next_actions must not appear in verifier output for partial_progress_timeout: {v_coal_partial}"
    )
    # Recommendation must match the prescribed text
    _ppt_rec = v_coal_partial.get("recommendation") or ""
    assert "partial progress" in _ppt_rec.lower() and "any valid action" in _ppt_rec.lower(), (
        f"recommendation must be the partial-progress autonomy message: {_ppt_rec!r}"
    )

    # --- mine_coal: pure action_timeout (no progress) still uses mining timeout path ---
    _coal_pure_to_before = {"inventory_counts": {"coal": 0, "wooden_pickaxe": 1}, "nearby_blocks": {}, "health": 20, "food": 20,
                             "position": {"x": 0, "y": 64, "z": 0}}
    _coal_pure_to_after = {"inventory_counts": {"coal": 0, "wooden_pickaxe": 1}, "nearby_blocks": {}, "health": 20, "food": 20,
                            "position": {"x": 0, "y": 64, "z": 0}}
    v_coal_pure = verify_action(
        _coal_pure_to_before, _coal_pure_to_after,
        ActionRequest(action="mine_coal", args={"radius": 32}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="Block acquisition timed out after 60000ms.",
            result={"failure_type": "action_timeout"},
        ),
    )
    assert v_coal_pure.get("failure_type") in {"resource_acquisition_failed", "action_timeout"}, (
        f"pure action_timeout must use mine-timeout path, got {v_coal_pure.get('failure_type')}"
    )
    assert any(
        isinstance(e, dict) and e.get("kind") == "action_timeout" for e in (v_coal_pure.get("failed_because") or [])
    ), f"pure action_timeout failed_because must contain action_timeout entry: {v_coal_pure}"

    # --- path_timeout_before_target with excavation progress → partial_progress_timeout ---
    _ptt_base = {"inventory_counts": {"wooden_pickaxe": 1}, "nearby_blocks": {}, "health": 20, "food": 20,
                 "position": {"x": 10, "y": 60, "z": 10}}
    _ptt_after = {"inventory_counts": {"wooden_pickaxe": 1}, "nearby_blocks": {}, "health": 20, "food": 20,
                  "position": {"x": 14, "y": 59, "z": 10}}

    # excavatedBlocks=1 → must promote to partial_progress_timeout
    v_ptt_excav = verify_action(
        _ptt_base, _ptt_after,
        ActionRequest(action="mine_coal", args={"radius": 32}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="Navigation path failed.",
            result={
                "failure_type": "partial_progress_timeout",
                "stop_reason": "path_timeout_after_progress",
                "partial_success": True,
                "excavatedBlocks": 1,
                "nearestTargetDistance": 9.1,
                "nearestTargetDistanceEnd": 6.9,
                "inventory_delta": {"dirt": -1},
                "accessCandidatesFound": 1,
                "pathAttempts": 1,
                "failed_because": [{
                    "kind": "partial_progress_timeout",
                    "action": "mine_coal",
                    "stop_reason": "path_timeout_before_target",
                    "progress_signals": {
                        "excavatedBlocks": 1,
                        "nearestTargetDistance": 9.1,
                        "nearestTargetDistanceEnd": 6.9,
                        "inventory_delta": {"dirt": -1},
                        "accessCandidatesFound": 1,
                        "pathAttempts": 1,
                    },
                    "continuation_relevant": True,
                }],
            },
        ),
    )
    assert v_ptt_excav.get("failure_type") == "partial_progress_timeout", (
        f"path_timeout with excavation must become partial_progress_timeout, got: {v_ptt_excav.get('failure_type')}"
    )
    assert v_ptt_excav.get("repeatable_now") is True, (
        f"partial_progress_timeout must be repeatable: {v_ptt_excav}"
    )
    _ptt_fb = v_ptt_excav.get("failed_because") or []
    _ptt_e = next((e for e in _ptt_fb if isinstance(e, dict) and e.get("kind") == "partial_progress_timeout"), None)
    assert _ptt_e is not None, f"failed_because must contain partial_progress_timeout: {_ptt_fb}"
    assert _ptt_e.get("continuation_relevant") is True, f"continuation_relevant must be True: {_ptt_e}"

    # nearestTargetDistanceEnd < nearestTargetDistance alone → partial_progress_timeout
    v_ptt_closer = verify_action(
        _ptt_base, _ptt_after,
        ActionRequest(action="mine_coal", args={"radius": 32}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="Navigation path failed.",
            result={
                "failure_type": "partial_progress_timeout",
                "stop_reason": "path_timeout_after_progress",
                "partial_success": True,
                "nearestTargetDistance": 15.0,
                "nearestTargetDistanceEnd": 10.0,
                "failed_because": [{
                    "kind": "partial_progress_timeout",
                    "action": "mine_coal",
                    "stop_reason": "path_timeout_before_target",
                    "progress_signals": {"nearestTargetDistance": 15.0, "nearestTargetDistanceEnd": 10.0},
                    "continuation_relevant": True,
                }],
            },
        ),
    )
    assert v_ptt_closer.get("failure_type") == "partial_progress_timeout", (
        f"approaching target must become partial_progress_timeout: {v_ptt_closer.get('failure_type')}"
    )

    # inventory_delta alone → partial_progress_timeout
    v_ptt_inv = verify_action(
        _ptt_base, _ptt_after,
        ActionRequest(action="mine_coal", args={"radius": 32}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="Navigation path failed.",
            result={
                "failure_type": "partial_progress_timeout",
                "stop_reason": "path_timeout_after_progress",
                "partial_success": True,
                "failed_because": [{
                    "kind": "partial_progress_timeout",
                    "action": "mine_coal",
                    "stop_reason": "path_timeout_before_target",
                    "progress_signals": {"inventory_delta": {"dirt": -1}},
                    "continuation_relevant": True,
                }],
            },
        ),
    )
    assert v_ptt_inv.get("failure_type") == "partial_progress_timeout", (
        f"inventory change must become partial_progress_timeout: {v_ptt_inv.get('failure_type')}"
    )

    # No progress → stays navigation_failed
    v_ptt_none = verify_action(
        _ptt_base, _ptt_base,
        ActionRequest(action="mine_coal", args={"radius": 32}, speech="", reason=""),
        ActionResult(
            ok=False, action="mine_coal",
            error="Navigation path failed.",
            result={
                "failure_type": "navigation_failed",
                "stop_reason": "path_timeout_before_target",
                "partial_success": False,
            },
        ),
    )
    assert v_ptt_none.get("failure_type") in {"navigation_failed", "resource_acquisition_failed"}, (
        f"no-progress path timeout must stay navigation_failed: {v_ptt_none.get('failure_type')}"
    )
    assert v_ptt_none.get("failure_type") != "partial_progress_timeout", (
        f"no-progress must NOT be partial_progress_timeout: {v_ptt_none}"
    )

    # --- mine_coal policy: radius and accessMode args accepted ---
    from vtuber_ai.policy import validate_action as _va
    from vtuber_ai.schemas import ActionRequest as _AR
    _mc_full = _va(_AR(action="mine_coal", args={"count": 2, "radius": 32, "allowExcavate": True, "accessMode": "safe_staircase"}))
    assert _mc_full.args["radius"] == 32, _mc_full.args
    assert _mc_full.args["allowExcavate"] is True, _mc_full.args
    assert _mc_full.args["accessMode"] == "safe_staircase", _mc_full.args
    _mc_exposed = _va(_AR(action="mine_coal", args={"accessMode": "exposed"}))
    assert _mc_exposed.args["accessMode"] == "exposed", _mc_exposed.args

    # --- close_range_access_timeout with progress: classified as partial_progress_timeout ---
    _status_cr = status_with_inventory([{"name": "wooden_pickaxe", "count": 1}])
    _cr_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "close_range_access_timeout",
            "partial_success": True,
            "continuation_relevant": True,
            "progress_made": True,
            "nearestTargetDistance": 3.3,
            "nearestRawTargetDistance": 3.3,
            "nearestTargetDistanceEnd": 3.3,
            "selectedTargetDistance": 3.3,
            "accessCandidatesFound": 1,
            "closeRangeFallbackAttempted": 1,
            "directDigAttempted": 1,
            "localStandAdjustmentAttempted": True,
            "localExcavationSteps": 2,
            "closeRangeFailureReason": "excavated_but_target_still_blocked",
            "failed_because": [
                {
                    "kind": "close_range_access_timeout",
                    "action": "mine_coal",
                    "stop_reason": "close_range_access_timeout",
                    "progress_signals": {"excavatedBlocks": 2},
                    "continuation_relevant": True,
                    "nearestRawTargetDistance": 3.3,
                    "selectedTargetDistance": 3.3,
                    "localFallbackAttempted": True,
                    "localExcavationSteps": 2,
                    "closeRangeFailureReason": "excavated_but_target_still_blocked",
                }
            ],
        },
        error="Close-range access failed",
    )
    _v_cr = verify_action(
        _status_cr,
        _status_cr,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _cr_result,
    )
    assert _v_cr.get("failure_type") == "partial_progress_timeout", (
        f"close_range_access_timeout with progress must be partial_progress_timeout: {_v_cr.get('failure_type')}"
    )
    assert _v_cr.get("repeatable_now") is True, f"close_range must be repeatable: {_v_cr}"
    assert "suggested_next_action" not in _v_cr or _v_cr.get("suggested_next_action") is None, (
        f"suggested_next_action must not be exposed to LLM: {_v_cr}"
    )
    _cr_diag = _v_cr.get("diagnostics") or {}
    assert _cr_diag.get("localFallbackAttempted") is True, (
        f"localFallbackAttempted must appear in diagnostics: {_cr_diag}"
    )
    assert _cr_diag.get("nearestRawTargetDistance") == 3.3, (
        f"nearestRawTargetDistance must appear in diagnostics: {_cr_diag}"
    )
    assert _cr_diag.get("continuation_relevant") is True, (
        f"continuation_relevant must be in diagnostics: {_cr_diag}"
    )

    # --- close_range_access_failed: no progress → failure_type stays close_range_access_failed ---
    _cr_noprogress = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "close_range_access_failed",
            "stop_reason": "close_range_access_timeout",
            "partial_success": False,
            "nearestTargetDistance": 3.3,
            "nearestRawTargetDistance": 3.3,
            "closeRangeFallbackAttempted": 1,
            "directDigAttempted": 1,
            "localExcavationSteps": 0,
            "closeRangeFailureReason": "target_unreachable_close_range",
            "failed_because": [
                {
                    "kind": "close_range_access_timeout",
                    "action": "mine_coal",
                    "stop_reason": "close_range_access_timeout",
                    "progress_signals": {},
                    "continuation_relevant": False,
                    "nearestRawTargetDistance": 3.3,
                    "selectedTargetDistance": 3.3,
                    "localFallbackAttempted": True,
                    "localExcavationSteps": 0,
                    "closeRangeFailureReason": "target_unreachable_close_range",
                }
            ],
        },
        error="Close-range access failed",
    )
    _v_crfail = verify_action(
        _status_cr,
        _status_cr,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _cr_noprogress,
    )
    # close_range_access_failed is still a resource acquisition failure that the verifier handles
    assert _v_crfail.get("failure_type") in {"close_range_access_failed", "partial_progress_timeout", "resource_acquisition_failed"}, (
        f"close_range_access_failed must be recognized: {_v_crfail.get('failure_type')}"
    )

    # --- target reuse: reusedLastTarget flag, nearestRawTargetDistance from cache distance ---
    _status_reuse = status_with_inventory([{"name": "wooden_pickaxe", "count": 1}])
    _reuse_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "close_range_access_timeout",
            "partial_success": True,
            "continuation_relevant": True,
            "progress_made": True,
            "reusedLastTarget": True,
            "lastTargetStillExists": True,
            "distanceToLastTarget": 3.3,
            "nearestTargetDistance": 3.3,
            "nearestRawTargetDistance": 3.3,
            "selectedTargetDistance": 3.3,
            "closeRangeFallbackAttempted": 1,
            "directDigAttempted": 1,
            "localStandAdjustmentAttempted": True,
            "localExcavationSteps": 1,
            "failed_because": [
                {
                    "kind": "close_range_access_timeout",
                    "action": "mine_coal",
                    "stop_reason": "close_range_access_timeout",
                    "progress_signals": {"excavatedBlocks": 1},
                    "continuation_relevant": True,
                    "nearestRawTargetDistance": 3.3,
                    "selectedTargetDistance": 3.3,
                    "localFallbackAttempted": True,
                    "localExcavationSteps": 1,
                }
            ],
        },
        error="Close-range access failed",
    )
    _v_reuse = verify_action(
        _status_reuse,
        _status_reuse,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _reuse_result,
    )
    assert _v_reuse.get("failure_type") == "partial_progress_timeout", (
        f"target-reuse result must be partial_progress_timeout: {_v_reuse.get('failure_type')}"
    )
    assert _v_reuse.get("repeatable_now") is True, f"target-reuse result must be repeatable: {_v_reuse}"
    _reuse_diag = _v_reuse.get("diagnostics") or {}
    assert _reuse_diag.get("nearestRawTargetDistance") == 3.3, (
        f"nearestRawTargetDistance must be 3.3 from cache: {_reuse_diag}"
    )

    # --- selectedTargetMode: when nearest raw=3.3 is chosen over far access candidate=21.9 ---
    # This is the key scenario: scanner sees nearby coal (buried) + far exposed coal.
    # Must select close_raw_target and NOT pathfind to 21.9.
    _status_mode = status_with_inventory([{"name": "wooden_pickaxe", "count": 1}])
    _mode_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "close_range_access_timeout",
            "partial_success": True,
            "nearestTargetDistance": 3.3,
            "nearestRawTargetDistance": 3.3,
            "selectedTargetDistance": 3.3,
            "selectedTargetMode": "close_raw_target",
            "selectedCloseRangeTargetPosition": {"x": 10, "y": 63, "z": 5},
            "selectedAccessTargetDistance": 21.9,
            "currentSubstep": "close_range_access",
            "closeRangeFallbackAttempted": 1,
            "directDigAttempted": 1,
            "localStandAdjustmentAttempted": True,
            "localExcavationSteps": 3,
            "closeRangeFailureReason": "excavated_but_target_still_blocked",
            "failed_because": [
                {
                    "kind": "close_range_access_timeout",
                    "action": "mine_coal",
                    "stop_reason": "close_range_access_timeout",
                    "progress_signals": {"excavatedBlocks": 3},
                    "continuation_relevant": True,
                    "nearestRawTargetDistance": 3.3,
                    "selectedTargetDistance": 3.3,
                    "selectedAccessTargetDistance": 21.9,
                    "localFallbackAttempted": True,
                    "localExcavationSteps": 3,
                    "closeRangeFailureReason": "excavated_but_target_still_blocked",
                }
            ],
        },
        error="Close-range access partial progress",
    )
    _v_mode = verify_action(
        _status_mode,
        _status_mode,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _mode_result,
    )
    assert _v_mode.get("failure_type") == "partial_progress_timeout", (
        f"close_raw_target mode with excavation must be partial_progress_timeout: {_v_mode.get('failure_type')}"
    )
    assert _v_mode.get("repeatable_now") is True, f"close raw target result must be repeatable: {_v_mode}"
    _mode_diag = _v_mode.get("diagnostics") or {}
    assert _mode_diag.get("nearestRawTargetDistance") == 3.3, (
        f"nearestRawTargetDistance must be 3.3: {_mode_diag}"
    )
    assert _mode_diag.get("continuation_relevant") is True, f"must be continuation_relevant: {_mode_diag}"

    # --- path_planning_timeout (no progress): failed_because must not be null, must expose path facts ---
    _status_path = status_with_inventory([{"name": "wooden_pickaxe", "count": 1}])
    _path_timeout_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "navigation_failed",
            "stop_reason": "path_planning_timeout",
            "partial_success": False,
            "currentSubstep": "path_to_access",
            "minedTargetBlocks": 0,
            "dropCollectionAttempted": False,
            "closeRangeFallbackAttempted": 0,
            "targetCandidatesFound": 2,
            "accessCandidatesFound": 1,
            "nearestRawTargetDistance": 5.2,
            "nearestRawTargetPosition": {"x": 10, "y": 60, "z": 5},
            "selectedTargetMode": "access_candidate",
            "selectedTargetDistance": 18.4,
            "selectedTargetPosition": {"x": 15, "y": 58, "z": 12},
            "selectedAccessTargetDistance": 18.4,
            "selectedAccessTargetPosition": {"x": 15, "y": 58, "z": 12},
            "pathPlannerError": "Took too long to decide path to goal!",
            "failed_because": [
                {
                    "kind": "path_planning_timeout",
                    "action": "mine_coal",
                    "currentSubstep": "path_to_access",
                    "selectedTargetPosition": {"x": 15, "y": 58, "z": 12},
                    "selectedTargetDistance": 18.4,
                    "selectedAccessTargetPosition": {"x": 15, "y": 58, "z": 12},
                    "selectedAccessTargetDistance": 18.4,
                    "nearestRawTargetPosition": {"x": 10, "y": 60, "z": 5},
                    "nearestRawTargetDistance": 5.2,
                    "accessCandidatesFound": 1,
                    "closeRangeFallbackAttempted": 0,
                    "pathAttempts": 1,
                    "pathPlannerError": "Took too long to decide path to goal!",
                    "recoverable": True,
                }
            ],
        },
        error="Took too long to decide path to goal!",
    )
    _v_path_timeout = verify_action(
        _status_path,
        _status_path,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _path_timeout_result,
    )
    assert _path_timeout_result.result.get("failed_because") is not None, (
        "path_planning_timeout must never return failed_because=null"
    )
    assert len(_path_timeout_result.result["failed_because"]) == 1, (
        f"failed_because must have one entry: {_path_timeout_result.result['failed_because']}"
    )
    _ptfb = _path_timeout_result.result["failed_because"][0]
    assert _ptfb.get("kind") == "path_planning_timeout", f"kind must be path_planning_timeout: {_ptfb}"
    assert _ptfb.get("selectedTargetDistance") == 18.4, f"selectedTargetDistance must be exposed: {_ptfb}"
    assert _ptfb.get("nearestRawTargetDistance") == 5.2, f"nearestRawTargetDistance must be exposed: {_ptfb}"
    assert _ptfb.get("pathPlannerError") == "Took too long to decide path to goal!", (
        f"pathPlannerError must be exposed: {_ptfb}"
    )
    assert _ptfb.get("recoverable") is True, f"recoverable must be True: {_ptfb}"

    # --- path_planning_timeout: close raw target within threshold must trigger close_range_access ---
    # (this is a structural requirement; the bot should redirect to close-range before path_to_access)
    # Verify that a result with closeRangeFallbackAttempted=1 and selectedTargetMode=close_raw_target
    # is correctly classified even when stop_reason=path_planning_timeout
    _path_with_cr_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "path_planning_timeout",
            "partial_success": True,
            "currentSubstep": "path_to_access",
            "minedTargetBlocks": 0,
            "closeRangeFallbackAttempted": 1,
            "directDigAttempted": 1,
            "nearestRawTargetDistance": 3.3,
            "nearestRawTargetPosition": {"x": 10, "y": 63, "z": 5},
            "selectedTargetMode": "close_raw_target",
            "selectedTargetDistance": 3.3,
            "selectedAccessTargetDistance": 21.9,
            "pathPlannerError": "Took too long to decide path to goal!",
            "failed_because": [
                {
                    "kind": "path_planning_timeout",
                    "action": "mine_coal",
                    "currentSubstep": "path_to_access",
                    "selectedTargetDistance": 21.9,
                    "selectedAccessTargetDistance": 21.9,
                    "nearestRawTargetDistance": 3.3,
                    "closeRangeFallbackAttempted": 1,
                    "pathPlannerError": "Took too long to decide path to goal!",
                    "recoverable": True,
                }
            ],
        },
        error="Took too long to decide path to goal!",
    )
    _v_path_cr = verify_action(
        _status_path,
        _status_path,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _path_with_cr_result,
    )
    # path_planning_timeout is in game_brain's not-a-hard-block list
    assert _path_with_cr_result.result.get("closeRangeFallbackAttempted") == 1, (
        "close_range must have been attempted before path_to_access"
    )
    assert _path_with_cr_result.result.get("selectedTargetMode") == "close_raw_target", (
        "selectedTargetMode must be close_raw_target when close-range was tried"
    )

    # --- mined_target_but_drop_not_collected: classified as partial_progress_timeout ---
    _status_drop = status_with_inventory([{"name": "wooden_pickaxe", "count": 1}])
    _drop_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "mined_target_but_drop_not_collected",
            "partial_success": True,
            "continuation_relevant": True,
            "progress_made": True,
            "nearestTargetDistance": 3.3,
            "nearestRawTargetDistance": 3.3,
            "selectedTargetDistance": 3.3,
            "selectedTargetMode": "close_raw_target",
            "minedTargetBlocks": 1,
            "collected": 0,
            "dropCollectionAttempted": True,
            "nearbyDropsFound": 0,
            "dropCollectionSucceeded": False,
            "inventoryDeltaAfterDig": 0,
            "targetBlockStillExists": False,
            "failed_because": [
                {
                    "kind": "mined_target_but_drop_not_collected",
                    "action": "mine_coal",
                    "stop_reason": "mined_target_but_drop_not_collected",
                    "minedTargetBlocks": 1,
                    "nearbyDropsFound": 0,
                    "nearestRawTargetDistance": 3.3,
                    "selectedTargetDistance": 3.3,
                    "continuation_relevant": True,
                }
            ],
        },
        error="Mined coal_ore but drop was not collected",
    )
    _v_drop = verify_action(
        _status_drop,
        _status_drop,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _drop_result,
    )
    assert _v_drop.get("failure_type") == "partial_progress_timeout", (
        f"mined_target_but_drop_not_collected must be partial_progress_timeout: {_v_drop.get('failure_type')}"
    )
    assert _v_drop.get("repeatable_now") is True, f"drop-not-collected must be repeatable: {_v_drop}"
    assert "suggested_next_action" not in _v_drop or _v_drop.get("suggested_next_action") is None, (
        f"suggested_next_action must not be in LLM output: {_v_drop}"
    )
    _drop_diag = _v_drop.get("diagnostics") or {}
    assert _drop_diag.get("minedTargetBlocks") == 1, (
        f"minedTargetBlocks must be in diagnostics: {_drop_diag}"
    )
    assert _drop_diag.get("continuation_relevant") is True, (
        f"continuation_relevant must be in diagnostics: {_drop_diag}"
    )
    assert _drop_diag.get("progress_made") is True, (
        f"progress_made must be true when block was mined: {_drop_diag}"
    )

    # --- drop_unreachable: stop_reason maps to drop_unreachable, kind=drop_collection_failed ---
    _drop_unreachable_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "drop_unreachable",
            "partial_success": True,
            "continuation_relevant": True,
            "progress_made": True,
            "nearestRawTargetDistance": 2.1,
            "selectedTargetMode": "close_raw_target",
            "minedTargetBlocks": 1,
            "collected": 0,
            "dropCollectionAttempted": True,
            "nearbyDropsFound": 1,
            "relevantDropsFound": 1,
            "nearestDropDistance": 3.5,
            "dropPathAttempts": 1,
            "dropCollectionSucceeded": False,
            "inventoryDeltaAfterDig": 0,
            "inventoryDeltaAfterDropCollection": 0,
            "failed_because": [
                {
                    "kind": "drop_collection_failed",
                    "action": "mine_coal",
                    "stop_reason": "drop_unreachable",
                    "drop_collection_reason": "drop_unreachable",
                    "minedTargetBlocks": 1,
                    "nearbyDropsFound": 1,
                    "relevantDropsFound": 1,
                    "nearestDropDistance": 3.5,
                    "dropPathAttempts": 1,
                    "nearestRawTargetDistance": 2.1,
                    "selectedTargetDistance": 2.1,
                    "continuation_relevant": True,
                }
            ],
        },
        error="Mined coal_ore but drop collection failed: drop_unreachable",
    )
    _v_unreachable = verify_action(
        _status_drop,
        _status_drop,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _drop_unreachable_result,
    )
    assert _v_unreachable.get("failure_type") == "partial_progress_timeout", (
        f"drop_unreachable must be partial_progress_timeout: {_v_unreachable.get('failure_type')}"
    )
    assert _v_unreachable.get("repeatable_now") is True, f"drop_unreachable must be repeatable: {_v_unreachable}"
    _unr_diag = _v_unreachable.get("diagnostics") or {}
    assert _unr_diag.get("minedTargetBlocks") == 1, f"minedTargetBlocks must be 1: {_unr_diag}"
    assert _unr_diag.get("nearestDropDistance") == 3.5, f"nearestDropDistance must be 3.5: {_unr_diag}"
    assert _unr_diag.get("dropPathAttempts") == 1, f"dropPathAttempts must be 1: {_unr_diag}"
    assert _unr_diag.get("dropCollectionReason") == "drop_unreachable", (
        f"dropCollectionReason must be drop_unreachable: {_unr_diag}"
    )

    # --- drop_disappeared_without_inventory_delta ---
    _drop_disappeared_result = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "drop_disappeared_without_inventory_delta",
            "partial_success": True,
            "continuation_relevant": True,
            "progress_made": True,
            "nearestRawTargetDistance": 2.1,
            "selectedTargetMode": "close_raw_target",
            "minedTargetBlocks": 1,
            "collected": 0,
            "dropCollectionAttempted": True,
            "nearbyDropsFound": 1,
            "relevantDropsFound": 1,
            "nearestDropDistance": 4.0,
            "dropPathAttempts": 1,
            "dropCollectionSucceeded": False,
            "inventoryDeltaAfterDig": 0,
            "inventoryDeltaAfterDropCollection": 0,
            "failed_because": [
                {
                    "kind": "drop_collection_failed",
                    "action": "mine_coal",
                    "stop_reason": "drop_disappeared_without_inventory_delta",
                    "drop_collection_reason": "drop_disappeared_without_inventory_delta",
                    "minedTargetBlocks": 1,
                    "nearbyDropsFound": 1,
                    "relevantDropsFound": 1,
                    "nearestDropDistance": 4.0,
                    "dropPathAttempts": 1,
                    "nearestRawTargetDistance": 2.1,
                    "selectedTargetDistance": 2.1,
                    "continuation_relevant": True,
                }
            ],
        },
        error="Mined coal_ore but drop collection failed: drop_disappeared_without_inventory_delta",
    )
    _v_disappeared = verify_action(
        _status_drop,
        _status_drop,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _drop_disappeared_result,
    )
    assert _v_disappeared.get("failure_type") == "partial_progress_timeout", (
        f"drop_disappeared must be partial_progress_timeout: {_v_disappeared.get('failure_type')}"
    )
    assert _v_disappeared.get("repeatable_now") is True, (
        f"drop_disappeared must be repeatable: {_v_disappeared}"
    )
    _dis_diag = _v_disappeared.get("diagnostics") or {}
    assert _dis_diag.get("minedTargetBlocks") == 1, f"minedTargetBlocks must be 1: {_dis_diag}"
    assert _dis_diag.get("dropCollectionReason") == "drop_disappeared_without_inventory_delta", (
        f"dropCollectionReason must be drop_disappeared_without_inventory_delta: {_dis_diag}"
    )

    # --- collected resource delta wins over stale drop collection failure ---
    _status_before_coal_delta = status_with_inventory([{"name": "wooden_pickaxe", "count": 1}])
    _status_after_coal_delta = status_with_inventory([
        {"name": "wooden_pickaxe", "count": 1},
        {"name": "coal", "count": 2},
    ])
    _drop_disappeared_with_delta = ActionResult(
        ok=False,
        action="mine_coal",
        result={
            "failure_type": "partial_progress_timeout",
            "stop_reason": "drop_disappeared_without_inventory_delta",
            "partial_success": True,
            "targetInventoryDelta": 2,
            "collected": 2,
            "dropEntityDisappeared": True,
            "dropCollectionSucceeded": False,
            "failed_because": [
                {
                    "kind": "drop_collection_failed",
                    "action": "mine_coal",
                    "drop_collection_reason": "drop_disappeared_without_inventory_delta",
                }
            ],
        },
        error="Mined coal_ore but drop collection failed: drop_disappeared_without_inventory_delta",
    )
    _v_delta = verify_action(
        _status_before_coal_delta,
        _status_after_coal_delta,
        ActionRequest(action="mine_coal", args={"targets": ["coal_ore"], "count": 1}),
        _drop_disappeared_with_delta,
    )
    assert _v_delta.get("success") is True, f"collected=2 must verify as success: {_v_delta}"
    assert _v_delta.get("failure_type") == "none", f"collected=2 must not be drop failure: {_v_delta}"

    # --- WS-WORLD-1: mark_workspace_unreachable lowers confidence ---
    with tempfile.TemporaryDirectory() as _tmpdir:
        _wm_db = str(Path(_tmpdir) / "test.sqlite")
        remember_workspace(
            {"x": 10, "y": 64, "z": 10},
            "overworld",
            has_crafting_table=True,
            safe=True,
            db_path=_wm_db,
        )
        _ws_before = nearest_workspace({"x": 0, "y": 64, "z": 0}, "overworld", db_path=_wm_db)
        assert _ws_before is not None, "WS-WORLD-1: workspace must exist before mark"
        _conf_before = float(_ws_before.get("confidence") or 0)
        assert _conf_before >= STALE_WORKSPACE_CONFIDENCE_THRESHOLD, (
            f"WS-WORLD-1: fresh workspace must be above threshold; got confidence={_conf_before}"
        )

        # First mark — lowers confidence
        _updated = mark_workspace_unreachable({"x": 0, "y": 64, "z": 0}, "overworld", db_path=_wm_db)
        assert _updated is True, "WS-WORLD-1: mark_workspace_unreachable must return True when workspace found"
        _ws_after1 = nearest_workspace({"x": 0, "y": 64, "z": 0}, "overworld", db_path=_wm_db)
        _conf_after1 = float(_ws_after1.get("confidence") or 0) if _ws_after1 else None
        assert _conf_after1 is not None and _conf_after1 < _conf_before, (
            f"WS-WORLD-1: confidence must decrease after mark; before={_conf_before}, after={_conf_after1}"
        )

        # Mark again until below threshold — workspace disappears from nearest_workspace
        mark_workspace_unreachable({"x": 0, "y": 64, "z": 0}, "overworld", db_path=_wm_db)
        mark_workspace_unreachable({"x": 0, "y": 64, "z": 0}, "overworld", db_path=_wm_db)
        _ws_filtered = nearest_workspace({"x": 0, "y": 64, "z": 0}, "overworld", db_path=_wm_db)
        assert _ws_filtered is None, (
            f"WS-WORLD-1: workspace below confidence threshold must be filtered from nearest_workspace; "
            f"got: {_ws_filtered}"
        )

        # With min_confidence=0.0, the stale workspace is still visible
        _ws_stale = nearest_workspace({"x": 0, "y": 64, "z": 0}, "overworld", min_confidence=0.0, db_path=_wm_db)
        assert _ws_stale is not None, "WS-WORLD-1: stale workspace must be findable with min_confidence=0"

    # --- SWL-1: _is_stale_workspace_loop detects repeated path_timeout failures ---
    def _make_live_ws_tick(ok_val=False, ft="path_timeout"):
        class _FakeResult:
            def __init__(self):
                self.result = {"failure_type": ft, "stop_reason": ft}
        class _FakeAction:
            action = "return_to_workspace"
        return {
            "ok": ok_val,
            "action": _FakeAction(),
            "result": _FakeResult() if not ok_val else type("R", (), {"result": {}})(),
            "verifier": {"failure_type": "navigation_failed" if not ok_val else "none"},
        }

    _swl_no_failures = [_make_live_ws_tick(ok_val=True), _make_live_ws_tick(ok_val=True)]
    assert not _is_stale_workspace_loop(_swl_no_failures), (
        "SWL-1a: no failures must not trigger stale workspace loop"
    )

    _swl_one_failure = [_make_live_ws_tick(ok_val=False), _make_live_ws_tick(ok_val=True)]
    assert not _is_stale_workspace_loop(_swl_one_failure), (
        "SWL-1b: single failure must not trigger stale workspace loop"
    )

    _swl_two_failures = [_make_live_ws_tick(ok_val=False), _make_live_ws_tick(ok_val=False)]
    assert _is_stale_workspace_loop(_swl_two_failures), (
        "SWL-1c: two consecutive path_timeout failures must trigger stale workspace loop"
    )

    _swl_reset = [
        _make_live_ws_tick(ok_val=False),
        _make_live_ws_tick(ok_val=True),
        _make_live_ws_tick(ok_val=False),
    ]
    assert not _is_stale_workspace_loop(_swl_reset), (
        "SWL-1d: success between failures must reset streak"
    )

    # --- AAW-1: verify_position_changed returns True for already_at_workspace ---
    _pos = {"x": 10, "y": 64, "z": 10}
    _status_at_ws = status_with_inventory([])
    _status_at_ws["position"] = _pos

    _already_at_result = ActionResult(
        ok=True,
        action="return_to_workspace",
        result={
            "already_at_workspace": True,
            "reached": True,
            "distance_to_workspace": 2.5,
            "workspace_name": "workspace:overworld:0:64:0",
        },
    )
    _v_already = verify_action(
        _status_at_ws,
        _status_at_ws,  # same before/after (no movement)
        ActionRequest(action="return_to_workspace", args={}),
        _already_at_result,
    )
    assert _v_already.get("success") is True, (
        f"AAW-1: already_at_workspace must verify as success even with no position change; got: {_v_already}"
    )
    assert _v_already.get("failure_type") == "none", (
        f"AAW-1: failure_type must be 'none'; got: {_v_already.get('failure_type')}"
    )

    # AAW-2: without already_at_workspace, same position → verifier failure
    _no_already_at_result = ActionResult(
        ok=True,
        action="return_to_workspace",
        result={"reached": True, "workspace_name": "workspace:overworld:0:64:0"},
    )
    _v_no_already = verify_action(
        _status_at_ws,
        _status_at_ws,
        ActionRequest(action="return_to_workspace", args={}),
        _no_already_at_result,
    )
    assert _v_no_already.get("success") is False, (
        f"AAW-2: without already_at_workspace, no position change must be failure; got: {_v_no_already}"
    )

    # --- Live loop integration tests (monkeypatched run_agent_tick) ---

    def _make_tick_result(ok: bool, action: str = "collect_wood", failure_type: str = "no_progress") -> dict:
        return {
            "ok": ok,
            "action": action,
            "args": {},
            "result": {"ok": ok, **({"failure_type": failure_type} if not ok else {})},
            "verifier": {"ok": ok, **({"failure_type": failure_type} if not ok else {})},
            "after_status": {"health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}, "dimension": "overworld"},
            "speech": "",
            "mood": "neutral",
        }

    def _run_live(request: AgentLiveRequest, tick_results: list[dict]) -> dict:
        call_count = 0

        async def _fake_tick(_tick_req):
            nonlocal call_count
            idx = min(call_count, len(tick_results) - 1)
            call_count += 1
            return tick_results[idx]

        async def _inner():
            with patch("vtuber_ai.autonomy.run_agent_tick", new=_fake_tick):
                return await run_agent_live(request)

        return asyncio.run(_inner())

    # LIVE-1: 5 consecutive failures + stop_on_failure=False → ticks_run == max_ticks
    _live_req_cont = AgentLiveRequest(
        mission="test",
        max_ticks=5,
        tick_delay_sec=0.0,
        stop_on_failure=False,
    )
    _live_failed_ticks = [_make_tick_result(ok=False) for _ in range(5)]
    _live1 = _run_live(_live_req_cont, _live_failed_ticks)
    assert _live1.get("ticks_run") == 5, (
        f"LIVE-1: 5 consecutive failures with stop_on_failure=False must run all ticks; got ticks_run={_live1.get('ticks_run')}"
    )
    assert _live1.get("stopped_reason") == "max_ticks_reached", (
        f"LIVE-1: stopped_reason must be max_ticks_reached; got {_live1.get('stopped_reason')}"
    )
    assert _live1.get("early_stop_disabled") is True, (
        f"LIVE-1: early_stop_disabled must be True; got {_live1.get('early_stop_disabled')}"
    )

    # LIVE-2: would_have_stopped=True when streak exceeds max_consecutive
    assert _live1.get("would_have_stopped") is True, (
        f"LIVE-2: would_have_stopped must be True when failures >= max_consecutive; got {_live1}"
    )
    assert _live1.get("would_have_stopped_reason") is not None, (
        f"LIVE-2: would_have_stopped_reason must be set; got {_live1}"
    )

    # LIVE-3: blocked_repetition failure does not terminate live loop
    _live_blocked_ticks = [_make_tick_result(ok=False, failure_type="blocked_repetition") for _ in range(5)]
    _live3 = _run_live(_live_req_cont, _live_blocked_ticks)
    assert _live3.get("ticks_run") == 5, (
        f"LIVE-3: blocked_repetition must not terminate live loop; got ticks_run={_live3.get('ticks_run')}"
    )

    # LIVE-4: invalid action failure does not terminate live loop
    _live_invalid_ticks = [_make_tick_result(ok=False, failure_type="invalid_action") for _ in range(5)]
    _live4 = _run_live(_live_req_cont, _live_invalid_ticks)
    assert _live4.get("ticks_run") == 5, (
        f"LIVE-4: invalid_action must not terminate live loop; got ticks_run={_live4.get('ticks_run')}"
    )

    # LIVE-5: max_ticks respected even with continuous mode
    _live_req_short = AgentLiveRequest(
        mission="test",
        max_ticks=3,
        tick_delay_sec=0.0,
        stop_on_failure=False,
    )
    _live5 = _run_live(_live_req_short, _live_failed_ticks)
    assert _live5.get("ticks_run") == 3, (
        f"LIVE-5: max_ticks=3 must cap run at 3 ticks; got ticks_run={_live5.get('ticks_run')}"
    )

    # LIVE-6: legacy stop_on_failure=True still stops early
    _live_req_legacy = AgentLiveRequest(
        mission="test",
        max_ticks=10,
        tick_delay_sec=0.0,
        stop_on_failure=True,
    )
    import os as _os
    _orig_max = _os.environ.get("VTUBER_LIVE_MAX_CONSECUTIVE_FAILURES")
    _os.environ["VTUBER_LIVE_MAX_CONSECUTIVE_FAILURES"] = "3"
    _live_legacy_ticks = [_make_tick_result(ok=False) for _ in range(10)]
    _live6 = _run_live(_live_req_legacy, _live_legacy_ticks)
    if _orig_max is None:
        _os.environ.pop("VTUBER_LIVE_MAX_CONSECUTIVE_FAILURES", None)
    else:
        _os.environ["VTUBER_LIVE_MAX_CONSECUTIVE_FAILURES"] = _orig_max
    assert _live6.get("ticks_run", 0) < 10, (
        f"LIVE-6: stop_on_failure=True must stop early; got ticks_run={_live6.get('ticks_run')}"
    )
    assert _live6.get("early_stop_disabled") is False, (
        f"LIVE-6: early_stop_disabled must be False in legacy mode; got {_live6.get('early_stop_disabled')}"
    )

    # --- PLACE-1: place_furnace station_already_available verifies as success ---
    _furnace_before = {
        "ok": True, "position": {"x": 0, "y": 64, "z": 0},
        "nearbyBlocks": {"furnace": {"distance": 2.0}},
        "inventory": [],
    }
    _place_already_result = ActionResult(
        ok=True,
        action="place_furnace",
        result={
            "alreadyPresent": True,
            "already_satisfied": True,
            "stop_reason": "station_already_available",
            "has_furnace": True,
            "furnace_position": {"x": 1, "y": 64, "z": 0},
        },
    )
    _v_already_furnace = verify_action(
        _furnace_before,
        _furnace_before,
        ActionRequest(action="place_furnace", args={}),
        _place_already_result,
    )
    assert _v_already_furnace.get("success") is True, (
        f"PLACE-1: place_furnace with station_already_available must verify as success; got {_v_already_furnace}"
    )

    # PLACE-2: place_crafting_table already_satisfied verifies as success
    _ct_before = {
        "ok": True, "position": {"x": 0, "y": 64, "z": 0},
        "nearbyBlocks": {"crafting_table": {"distance": 3.0}},
        "inventory": [],
    }
    _place_ct_result = ActionResult(
        ok=True,
        action="place_crafting_table",
        result={
            "alreadyPresent": True,
            "already_satisfied": True,
            "stop_reason": "station_already_available",
            "has_crafting_table": True,
        },
    )
    _v_ct = verify_action(
        _ct_before,
        _ct_before,
        ActionRequest(action="place_crafting_table", args={}),
        _place_ct_result,
    )
    assert _v_ct.get("success") is True, (
        f"PLACE-2: place_crafting_table already_satisfied must verify as success; got {_v_ct}"
    )

    # PLACE-3: no_safe_placement failure passes through failed_because and repeatable_now=True
    _no_place_result = ActionResult(
        ok=False,
        action="place_furnace",
        result={
            "failure_type": "no_safe_placement",
            "stop_reason": "no_station_placement_candidate",
            "area_cramped": True,
            "failed_because": [{"kind": "no_safe_placement", "station": "furnace", "candidate_positions_found": 0, "area_cramped": True}],
        },
        error="No safe placement position found nearby.",
    )
    _base_status = status_with_inventory([])
    _base_status["position"] = {"x": 0, "y": 64, "z": 0}
    _v_no_place = verify_action(
        _base_status,
        _base_status,
        ActionRequest(action="place_furnace", args={}),
        _no_place_result,
    )
    assert _v_no_place.get("success") is False, "PLACE-3: no_safe_placement must fail verification"
    assert _v_no_place.get("failure_type") == "no_safe_placement", (
        f"PLACE-3: failure_type must be no_safe_placement; got {_v_no_place.get('failure_type')}"
    )
    assert _v_no_place.get("repeatable_now") is True, (
        f"PLACE-3: repeatable_now must be True (unblocks when position changes); got {_v_no_place}"
    )
    assert isinstance(_v_no_place.get("failed_because"), list) and _v_no_place["failed_because"], (
        f"PLACE-3: failed_because must be passed through from JS result; got {_v_no_place.get('failed_because')}"
    )

    # --- ADVISORY MODE: run_agent_tick does not skip execution for blocked family ---
    def _make_iron_fail_tick_for_agent(pos: dict) -> dict:
        return {
            "action": "mine_iron_ore",
            "ok": 0,
            "args": {},
            "error": "Block acquisition failed: timed out after 12000ms.",
            "result": {"failure_type": "resource_acquisition_failed"},
            "verifier": {
                "failure_type": "resource_acquisition_failed",
                "failed_because": [
                    {"kind": "action_timeout", "action": "mine_iron_ore", "timeout_ms": 12000, "recoverable": True},
                    {"kind": "resource_acquisition_attempt", "resource_family": "iron_ore",
                     "position_changed_since_last_attempt": False, "distance_moved_since_last_attempt": 0.0,
                     "position_change_meaningful": False},
                ],
            },
            "before_state": {"position": pos, "inventory_counts": {}},
            "after_state": {"position": pos, "inventory_counts": {}},
        }

    _pos = {"x": 10, "y": 60, "z": 10}
    _iron_fail_ticks = [_make_iron_fail_tick_for_agent(_pos), _make_iron_fail_tick_for_agent(_pos)]
    _iron_summary = {
        "ok": True, "health": 20, "food": 20, "dimension": "overworld",
        "position": _pos, "inventory_counts": {}, "nearby_blocks": {},
    }

    # Verify find_blocked_family detects the block first
    _fbf = find_blocked_family("mine_iron_ore", {}, _iron_fail_ticks, _iron_summary)
    assert _fbf is not None, "find_blocked_family must detect repeated mine_iron_ore failures"
    assert "iron_ore" in _fbf.get("family", ""), _fbf

    # Advisory mode: run_agent_tick should NOT skip execution even when family is blocked
    _bot_status = {
        "ok": True, "connected": True, "entityReady": True,
        "health": 20, "food": 20, "dimension": "overworld",
        "position": _pos, "inventory": [], "nearbyBlocks": {},
    }
    _mine_action_result = ActionResult(ok=False, action="mine_iron_ore",
                                       error="Block acquisition failed: timed out after 12000ms.",
                                       result={"failure_type": "action_timeout"})
    _tick_request = type("AgentTickRequest", (), {
        "mission": "get iron",
        "planner": "hybrid",
        "tick_delay_sec": 0,
        "max_ticks": 1,
    })()

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as _tf:
        _db_path = _tf.name

    with (
        patch("vtuber_ai.autonomy.get_bot_status", new=AsyncMock(return_value=_bot_status)),
        patch("vtuber_ai.autonomy.get_bridge_actions", new=AsyncMock(return_value=list(AUTONOMOUS_ALLOWED_ACTIONS))),
        patch("vtuber_ai.autonomy.get_recent_agent_ticks", return_value=_iron_fail_ticks),
        patch("vtuber_ai.autonomy.get_recent_events", return_value=[]),
        patch("vtuber_ai.autonomy.log_agent_tick"),
        patch("vtuber_ai.autonomy.log_event"),
        patch("vtuber_ai.autonomy.emit_speech_text"),
        patch("vtuber_ai.autonomy._execute_action", new=AsyncMock(return_value=_mine_action_result)),
        patch("vtuber_ai.autonomy.choose_next_action", return_value=(
            type("D", (), {"action": "mine_iron_ore", "args": {}, "speech": "", "reason": "", "objective": "get iron", "mood": "focused"})(),
            {"source": "llm", "planner": "hybrid", "fallback_used": False, "llm_latency_sec": 0.01,
             "prompt_size_chars": 100, "blocked_action_families_count": 0, "blocked_action_families": [],
             "chose_blocked_action_family": False, "blocked_action_family_name": None, "unblock_condition": None},
        )),
    ):
        os.environ.pop("VTUBER_HARD_BLOCK_REPETITIONS", None)  # advisory mode
        from vtuber_ai.schemas import AgentTickRequest
        _tick_req = AgentTickRequest(mission="get iron", planner="hybrid")
        _tick_result = asyncio.run(run_agent_tick(_tick_req))

    # In advisory mode, execution must NOT be skipped for a blocked family
    _tick_action = _tick_result.get("action")
    _tick_action_name = _tick_action.action if hasattr(_tick_action, "action") else str(_tick_action)
    assert _tick_action_name == "mine_iron_ore", (
        f"advisory mode must not skip mine_iron_ore; got action={_tick_action_name}"
    )
    _tick_planner_info = _tick_result.get("planner") or {}
    assert _tick_planner_info.get("action_execution_skipped") is not True, (
        f"advisory mode must not skip execution; planner={_tick_planner_info}"
    )
    assert _tick_planner_info.get("repetition_warning") is True, (
        f"advisory mode must set repetition_warning in planner; got {_tick_planner_info}"
    )
    _tick_action_result = _tick_result.get("result")
    result_ft = (getattr(_tick_action_result, "result", None) or {}).get("failure_type")
    assert result_ft != "blocked_repetition", (
        f"advisory mode must not return blocked_repetition; got failure_type={result_ft}"
    )

    # Hard-block mode: execution IS skipped
    with (
        patch("vtuber_ai.autonomy.get_bot_status", new=AsyncMock(return_value=_bot_status)),
        patch("vtuber_ai.autonomy.get_bridge_actions", new=AsyncMock(return_value=list(AUTONOMOUS_ALLOWED_ACTIONS))),
        patch("vtuber_ai.autonomy.get_recent_agent_ticks", return_value=_iron_fail_ticks),
        patch("vtuber_ai.autonomy.get_recent_events", return_value=[]),
        patch("vtuber_ai.autonomy.log_agent_tick"),
        patch("vtuber_ai.autonomy.log_event"),
        patch("vtuber_ai.autonomy.emit_speech_text"),
        patch("vtuber_ai.autonomy._execute_action", new=AsyncMock(return_value=_mine_action_result)),
        patch("vtuber_ai.autonomy.choose_next_action", return_value=(
            type("D", (), {"action": "mine_iron_ore", "args": {}, "speech": "", "reason": "", "objective": "get iron", "mood": "focused"})(),
            {"source": "llm", "planner": "hybrid", "fallback_used": False, "llm_latency_sec": 0.01,
             "prompt_size_chars": 100, "blocked_action_families_count": 1,
             "blocked_action_families": [{"family": "resource_acquisition:iron_ore", "blocked": True}],
             "chose_blocked_action_family": True, "blocked_action_family_name": "resource_acquisition:iron_ore",
             "unblock_condition": "Move ≥8 blocks."},
        )),
    ):
        os.environ["VTUBER_HARD_BLOCK_REPETITIONS"] = "1"
        _hard_tick_result = asyncio.run(run_agent_tick(_tick_req))
        os.environ.pop("VTUBER_HARD_BLOCK_REPETITIONS", None)

    assert _hard_tick_result.get("ok") is False, _hard_tick_result
    _hard_action_result = _hard_tick_result.get("result")
    _hard_result_dict = getattr(_hard_action_result, "result", None) or {}
    assert _hard_result_dict.get("failure_type") == "blocked_repetition", (
        f"hard-block mode must return blocked_repetition; got {_hard_result_dict.get('failure_type')}"
    )
    _hard_planner = _hard_tick_result.get("planner") or {}
    assert _hard_planner.get("action_execution_skipped") is True, (
        f"hard-block mode must mark action_execution_skipped; got {_hard_planner}"
    )

    # --- VERIFIER: unstuck_escape no_progress → failed_because with kind=no_progress ---
    unstuck_req = ActionRequest(action="unstuck_escape", args={"radius": 8, "mode": "any"}, speech="", reason="")
    unstuck_no_progress = ActionResult(
        ok=False,
        action="unstuck_escape",
        error="No position change and no terrain modification.",
        result={
            "failure_type": "no_progress",
            "stop_reason": "no_progress",
            "distance_moved": 0.1,
            "y_delta": 0.0,
            "blocks_dug": 0,
            "clearance_created": False,
            "local_space_before": 4,
            "local_space_after": 4,
            "escape_strategy_used": None,
            "progress_made": False,
        },
    )
    v_unstuck = verify_action(empty_status, empty_status, unstuck_req, unstuck_no_progress)
    assert v_unstuck["failure_type"] == "no_progress", \
        f"unstuck_escape no_progress must be no_progress, got {v_unstuck['failure_type']}"
    fb_unstuck = v_unstuck.get("failed_because") or []
    assert isinstance(fb_unstuck, list) and len(fb_unstuck) == 1, \
        f"unstuck_escape must produce one failed_because entry, got: {fb_unstuck}"
    assert fb_unstuck[0]["kind"] == "no_progress", fb_unstuck[0]
    assert fb_unstuck[0]["action"] == "unstuck_escape", fb_unstuck[0]
    assert v_unstuck.get("repeatable_now") is True

    # --- POLICY: unstuck_escape validates radius and mode ---
    from vtuber_ai.policy import validate_action, PolicyError

    valid_unstuck = validate_action(
        ActionRequest(action="unstuck_escape", args={"radius": 10, "mode": "dig_clearance"}, speech="", reason="")
    )
    assert valid_unstuck.action == "unstuck_escape"
    assert valid_unstuck.args["radius"] == 10
    assert valid_unstuck.args["mode"] == "dig_clearance"

    import pytest
    with pytest.raises(PolicyError):
        validate_action(ActionRequest(action="unstuck_escape", args={"mode": "fly"}, speech="", reason=""))

    # --- GAME BRAIN: unstuck_escape in AUTONOMOUS_ALLOWED_ACTIONS ---
    assert "unstuck_escape" in AUTONOMOUS_ALLOWED_ACTIONS, \
        "unstuck_escape must be in AUTONOMOUS_ALLOWED_ACTIONS"

    # --- GAME BRAIN: _rts_position_stuck_from_ticks ---
    def _rts_tick(ft: str, x: float, z: float, ok: bool = False) -> dict:
        return {
            "action": "return_to_surface",
            "ok": ok,
            "result": {
                "failure_type": ft,
                "start_position": {"x": x, "y": 30.0, "z": z},
                "end_position": {"x": x, "y": 30.0, "z": z},
            },
            "verifier": {"failure_type": ft},
        }

    # Two no_progress ticks at same position → stuck
    assert _rts_position_stuck_from_ticks([
        _rts_tick("no_progress", 10.0, 10.0),
        _rts_tick("no_progress", 10.5, 10.5),
    ]), "two no_progress at same position must trigger stuck"

    # Two no_progress ticks far apart → not stuck
    assert not _rts_position_stuck_from_ticks([
        _rts_tick("no_progress", 10.0, 10.0),
        _rts_tick("no_progress", 50.0, 50.0),
    ]), "no_progress at different positions must not trigger stuck"

    # One no_progress tick → not stuck (need 2)
    assert not _rts_position_stuck_from_ticks([
        _rts_tick("no_progress", 10.0, 10.0),
    ]), "single no_progress must not trigger stuck"

    # partial_progress then no_progress → chain broken, not stuck
    assert not _rts_position_stuck_from_ticks([
        _rts_tick("no_progress", 10.0, 10.0),
        _rts_tick("partial_progress_timeout", 10.0, 10.0),
    ]), "partial_progress between failures must break chain"

    # No_progress, then observation action, then no_progress → still stuck (observation doesn't break chain)
    stuck_with_obs = [
        _rts_tick("no_progress", 10.0, 10.0),
        {"action": "status", "ok": True, "result": {}, "verifier": {}},
        _rts_tick("no_progress", 10.2, 10.2),
    ]
    assert _rts_position_stuck_from_ticks(stuck_with_obs), \
        "observation tick between no_progress failures must not break chain"

    # --- CATALOG: unstuck_escape has category=recovery and structured args_schema ---
    from vtuber_ai.action_catalog import CATALOG
    _ue = CATALOG["unstuck_escape"]
    assert _ue.category == "recovery", f"unstuck_escape category must be 'recovery'; got {_ue.category}"
    assert isinstance(_ue.args_schema.get("mode"), dict), \
        f"unstuck_escape args_schema.mode must be a structured dict; got {_ue.args_schema}"
    assert _ue.args_schema["mode"]["enum"] == ["safe_random_walk", "dig_clearance", "upward_step", "any"], \
        f"unstuck_escape mode enum mismatch; got {_ue.args_schema['mode']}"

    # --- _workspace_navigation_stuck_state fires on stream-like stuck loop ---
    _bare = {"inventory_counts": {}, "nearby_blocks": {}}
    _stream_ticks = [
        {"action": "approach_station", "ok": 0, "args": {"station": "crafting_table"},
         "result": {"failure_type": "station_not_reached"}, "verifier": {"failure_type": "station_not_reached"},
         "before_state": {"position": {"x": 0, "y": 30, "z": 0}},
         "after_state": {"position": {"x": 0, "y": 30, "z": 0}}},
        {"action": "setup_workspace", "ok": 0, "args": {},
         "result": {"failure_type": "no_safe_workspace"}, "verifier": {"failure_type": "no_safe_workspace"},
         "before_state": {"position": {"x": 0, "y": 30, "z": 0}},
         "after_state": {"position": {"x": 0, "y": 30, "z": 0}}},
        {"action": "return_to_surface", "ok": 0, "args": {},
         "result": {"failure_type": "no_progress"}, "verifier": {"failure_type": "no_progress"},
         "before_state": {"position": {"x": 0, "y": 30, "z": 0}},
         "after_state": {"position": {"x": 0, "y": 30, "z": 0}}},
        {"action": "find_safe_workspace", "ok": 0, "args": {},
         "result": {"failure_type": "no_safe_workspace"}, "verifier": {"failure_type": "no_safe_workspace"},
         "before_state": {"position": {"x": 0, "y": 30, "z": 0}},
         "after_state": {"position": {"x": 0, "y": 30, "z": 0}}},
    ]
    _ws_stuck = _workspace_navigation_stuck_state(_stream_ticks, _bare)
    assert _ws_stuck is not None and _ws_stuck["active"] is True, \
        f"stream-like stuck loop must trigger workspace_navigation_stuck; got {_ws_stuck}"

    print("manual agent tests passed")


if __name__ == "__main__":
    main()
