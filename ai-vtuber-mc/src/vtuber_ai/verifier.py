import re
from typing import Any, Callable

from vtuber_ai.action_catalog import CATALOG

# Minimum displacement (in blocks) that counts as a meaningful position change
# for resource-acquisition unblock detection. Smaller moves are treated as jitter.
POSITION_MEANINGFUL_DELTA_BLOCKS: int = 8
from vtuber_ai.curriculum import objective_item_count, objective_item_name, recommend_objective
from vtuber_ai.agent_state import summarize_status
from vtuber_ai.policy import SMELT_FUELS, SMELT_INPUTS
from vtuber_ai.requirements import (
    check_requirements,
    parse_error_to_failed_requirements,
)
from vtuber_ai.schemas import ActionRequest, ActionResult


def verify_step(
    objective: str,
    before_status: dict[str, Any],
    after_status: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> dict[str, Any]:
    expected_item = objective_item_name(objective)
    before_count = objective_item_count(objective, before_status)
    after_count = objective_item_count(objective, after_status)

    if objective == "tier1_complete":
        success = action_result.ok
    elif expected_item is None:
        success = action_result.ok
    else:
        success = action_result.ok and after_count > before_count

    return {
        "objective": objective,
        "success": success,
        "evidence": {
            "action": action_request.action,
            "action_ok": action_result.ok,
            "action_error": action_result.error,
            "expected_item": expected_item,
            "before_count": before_count,
            "after_count": after_count,
            "changed": after_count != before_count,
        },
        "next_recommended_objective": recommend_objective(after_status),
    }


def verify_action(
    before_status: dict[str, Any],
    after_status: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> dict[str, Any]:
    before = summarize_status(before_status)
    after = summarize_status(after_status)

    if not action_result.ok:
        result = action_result.result if isinstance(action_result.result, dict) else {}
        _stale_drop_failure_with_collection = (
            isinstance(result.get("stop_reason"), str)
            and result.get("stop_reason", "").startswith("drop_")
        ) or "drop collection failed" in (action_result.error or "").lower()
        if (
            action_request.action in {"collect_wood", "mine_stone", "mine_coal", "mine_iron_ore", "acquire_blocks"}
            and (
                (isinstance(result.get("targetInventoryDelta"), (int, float)) and result.get("targetInventoryDelta", 0) > 0)
                or (
                    _stale_drop_failure_with_collection
                    and isinstance(result.get("collected"), (int, float))
                    and result.get("collected", 0) > 0
                )
            )
        ):
            return {
                "success": True,
                "evidence": {
                    "action": action_request.action,
                    "result": result,
                    "before": _small_evidence(before),
                    "after": _small_evidence(after),
                },
                "failure_type": "none",
                "recommendation": "Continue adapting from the updated state.",
            }
        missing_materials = result.get("missing_materials")
        if isinstance(missing_materials, list):
            missing_materials = [
                m["name"] if isinstance(m, dict) else str(m)
                for m in missing_materials
            ]
        else:
            missing_materials = _parse_missing_materials(action_result.error)

        # Determine failure_type: navigation errors must not become bridge_error.
        raw_failure_type = result.get("failure_type")
        is_resource_acquisition = _is_resource_acquisition_error(action_request.action, action_result.error)
        is_nav = _is_navigation_error(action_result.error) or raw_failure_type in {
            "path_timeout", "target_unreachable", "navigation_failed",
        }
        if raw_failure_type:
            failure_type = raw_failure_type
        elif is_resource_acquisition:
            failure_type = "resource_acquisition_failed"
        elif _is_bridge_error(action_result.error):
            failure_type = "bridge_error"
        elif is_nav:
            failure_type = "navigation_failed"
        else:
            failure_type = "no_progress"

        # Normalise navigation failure_type to "navigation_failed".
        if failure_type in {"path_timeout", "target_unreachable"}:
            failure_type = "navigation_failed"

        if missing_materials and failure_type == "no_progress":
            failure_type = "missing_materials"
        stop_reason = result.get("stop_reason")
        if missing_materials and not stop_reason:
            stop_reason = "missing_materials"
        if (is_nav or is_resource_acquisition) and not stop_reason:
            stop_reason = result.get("stop_reason") or "path_timeout"
        suggested_next_action = result.get("suggested_next_action")
        fallback_suggested_next_action = result.get("fallback_suggested_next_action")
        can_retry = result.get("can_retry")
        needed = result.get("needed")
        station_needed = result.get("station_needed")
        nearest_station_distance = result.get("nearest_station_distance")
        usable_radius = result.get("usable_radius")
        possible_next_actions = result.get("possible_next_actions")
        if missing_materials and not possible_next_actions:
            possible_next_actions = _possible_next_actions_for_missing_materials(missing_materials, after.get("inventory_counts", {}))
        lesson = result.get("lesson")
        if missing_materials and action_request.action == "craft_torches" and not lesson:
            lesson = "Torches need sticks and coal or charcoal."
        partial_success = bool(result.get("partial_success"))
        usable_for_station = bool(result.get("usable_for_station"))
        distance_improved = bool(result.get("distance_improved"))
        diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}

        _error_lower = (action_result.error or "").lower()

        # partial_progress_timeout: bot made real physical progress before the clock expired.
        # Pass through the rich failed_because the bot already built — do not reclassify.
        # suggested_next_action is intentionally suppressed: AI should choose freely.
        if raw_failure_type == "partial_progress_timeout":
            raw_fb = result.get("failed_because")
            failed_because = raw_fb if isinstance(raw_fb, list) else []
            # Respect explicit JS opt-out of continuation (e.g. drop_deep_unreachable: mining
            # succeeded but the specific drop fell deep with no safe stand — retrying the same
            # drop is not useful, but resource_acquisition:* is NOT blocked).
            if result.get("continuation_relevant") is False:
                repeatable_now_val = False
                repeat_condition = "Drop fell deep and unreachable — mine a different block instead of retrying this drop."
            else:
                repeatable_now_val = True
                repeat_condition = "Partial progress means continuing may be reasonable, but you may choose any valid action."
            suggested_next_action = None
            possible_next_actions = None
            relevant_state = _build_navigation_relevant_state(after, action_request.args if isinstance(action_request.args, dict) else {}, result)
            # Hoist factual progress fields to top-level so they appear in the failure summary.
            partial_progress_facts = _extract_partial_progress_facts(result)
            diagnostics = {**diagnostics, **partial_progress_facts} if partial_progress_facts else diagnostics

        # Mining action timeouts → action_timeout kind (not path_timeout); position-aware.
        elif action_request.action in _MINE_TIMEOUT_ACTIONS and (
            "timed out" in _error_lower
            or "timeout" in _error_lower
            or "block acquisition failed" in _error_lower
            or raw_failure_type == "action_timeout"
        ):
            args = action_request.args if isinstance(action_request.args, dict) else {}
            failed_because, repeatable_now_val, failure_type = _build_mining_timeout_failed_because(
                action=action_request.action,
                error=action_result.error,
                before=before,
                after=after,
            )
            relevant_state = _build_navigation_relevant_state(after, args, result)
            repeat_condition = "Retry after moving to a different position or when the resource becomes accessible."
        # Navigation/resource acquisition failures get first-class embodied feedback.
        elif is_nav or is_resource_acquisition:
            args = action_request.args if isinstance(action_request.args, dict) else {}
            failed_because = _build_navigation_failed_because(
                action=action_request.action,
                error=action_result.error,
                result=result,
                args=args,
                after=after,
            )
            relevant_state = _build_navigation_relevant_state(after, args, result)
            repeatable_now_val = True  # path may open up if position or state changes
            repeat_condition = "Retry after position changes, target changes, radius changes, or exploration reveals a better path."
        elif action_request.action == "explore_nearby" and failure_type == "action_timeout":
            # Position-aware enrichment: partial_progress if bot moved, navigation_failed if not.
            position_changed, distance_moved = _compute_position_delta(before, after)
            # JS partial_success flag is an extra signal when position data is absent.
            if not position_changed and partial_success:
                position_changed = True
            explore_fb, repeatable_now_val, explore_failure_type = _build_explore_timeout_failed_because(
                action=action_request.action,
                error=action_result.error,
                result=result,
                position_changed=position_changed,
                distance_moved=distance_moved,
            )
            failure_type = explore_failure_type
            failed_because = explore_fb
            partial_success = position_changed
            relevant_state = _build_explore_timeout_relevant_state(after)
            repeat_condition = (
                "Can retry — position changed during timeout; exploring from the new position may succeed."
                if position_changed else
                "Retry after moving to a new position, reducing radius, or navigating to an open area first."
            )
        elif action_request.action == "approach_station" and failure_type == "station_not_reached":
            failed_because, repeatable_now_val, lesson_station = _build_approach_station_failed_because(result)
            if lesson_station and not lesson:
                lesson = lesson_station
            relevant_state = {k: v for k, v in {
                "station": result.get("station") or result.get("station_needed"),
                "final_distance": result.get("final_distance"),
                "target_radius": result.get("target_radius"),
                "usable_for_station": usable_for_station,
            }.items() if v is not None}
            repeat_condition = (
                "Station may be usable even if target radius not reached — check usable_for_station."
                if usable_for_station else
                "Retry after repositioning or use setup_workspace to place a station closer."
            )
        elif failure_type in {"no_safe_placement", "no_safe_workspace"} and action_request.action in {
            "place_furnace", "place_crafting_table", "place_chest", "place_block",
        }:
            raw_fb = result.get("failed_because")
            failed_because = raw_fb if isinstance(raw_fb, list) and raw_fb else []
            repeatable_now_val = True  # unblocks once position changes (find_safe_workspace)
            relevant_state = {
                k: v for k, v in {
                    "bot_position": after.get("position"),
                    "diagnostics": diagnostics if diagnostics else None,
                }.items() if v is not None
            }
            repeat_condition = "Retry after moving to a more open area with find_safe_workspace or setup_workspace."
        elif action_request.action == "smelt_item":
            failed_because, repeatable_now_val, failure_type = _build_smelt_item_failed_because(
                args=action_request.args if isinstance(action_request.args, dict) else {},
                after=after,
                failure_type=failure_type,
            )
            relevant_state = _build_smelt_item_relevant_state(after)
            repeat_condition = "Only retry after missing requirements changed." if failed_because else None
        elif action_request.action == "scan_for_specific_block":
            failed_because, repeatable_now_val, failure_type = _build_scan_specific_block_failed_because(
                args=action_request.args if isinstance(action_request.args, dict) else {},
                failure_type=failure_type,
            )
            relevant_state = None
            repeat_condition = "Only retry after providing valid targets." if failed_because else None
        else:
            # Build generic requirement failure fields once, here in the verifier.
            # These are passed through unchanged to the prompt — not re-derived later.
            facts_for_reqs = _facts_from_summary(after)
            failed_because, repeatable_now_val = _build_failed_because(
                action=action_request.action,
                error=action_result.error,
                result=result,
                missing_materials=missing_materials,
                facts=facts_for_reqs,
            )
            relevant_state = _build_relevant_state_for_failure(after, missing_materials)
            repeat_condition = "Only retry after missing requirements changed." if failed_because else None

        return {
            "success": False,
            "partial_success": partial_success,
            "usable_for_station": usable_for_station,
            "distance_improved": distance_improved,
            # Generic requirement failure fields (first-class)
            "failed_because": failed_because,
            "repeatable_now": repeatable_now_val,
            "relevant_state": relevant_state,
            "repeat_condition": repeat_condition,
            "evidence": {
                "action": action_request.action,
                "action_error": action_result.error,
                "failure_type": failure_type,
                "stop_reason": stop_reason,
                "suggested_next_action": suggested_next_action,
                "fallback_suggested_next_action": fallback_suggested_next_action,
                "can_retry": can_retry,
                "needed": needed,
                "station_needed": station_needed,
                "nearest_station_distance": nearest_station_distance,
                "usable_radius": usable_radius,
                "missing_materials": missing_materials,
                "possible_next_actions": possible_next_actions,
                "lesson": lesson,
                "partial_success": partial_success,
                "usable_for_station": usable_for_station,
                "distance_improved": distance_improved,
                "diagnostics": diagnostics,
                "before": _small_evidence(before),
                "after": _small_evidence(after),
            },
            "failure_type": failure_type,
            "stop_reason": stop_reason,
            "suggested_next_action": suggested_next_action,
            "fallback_suggested_next_action": fallback_suggested_next_action,
            "can_retry": can_retry,
            "needed": needed,
            "station_needed": station_needed,
            "nearest_station_distance": nearest_station_distance,
            "usable_radius": usable_radius,
            "missing_materials": missing_materials,
            "possible_next_actions": possible_next_actions,
            "lesson": lesson,
            "diagnostics": diagnostics,
            "recommendation": _failure_recommendation(
                failure_type=failure_type,
                stop_reason=stop_reason,
                suggested_next_action=suggested_next_action,
                station_needed=station_needed,
                missing_materials=missing_materials,
                possible_next_actions=possible_next_actions,
                partial_success=partial_success,
                usable_for_station=usable_for_station,
                distance_improved=distance_improved,
            ),
        }

    if _is_danger(after):
        return {
            "success": False,
            "evidence": {
                "action": action_request.action,
                "before": _small_evidence(before),
                "after": _small_evidence(after),
            },
            "failure_type": "danger",
            "recommendation": "Prioritize survival with flee, eat_food, stop, or status.",
        }

    if action_request.action == "approach_station":
        success = True
    else:
        # Dispatch to the verifier registered for this action's verifier_signature.
        verifier_fn = _resolve_verifier(action_request.action)
        success = verifier_fn(before, after, action_request, action_result)
    return {
        "success": success,
        "evidence": {
            "action": action_request.action,
            "result": action_result.result,
            "before": _small_evidence(before),
            "after": _small_evidence(after),
        },
        "failure_type": "none" if success else "no_progress",
        "recommendation": "Continue adapting from the updated state." if success else "Avoid repeating the same action blindly.",
    }


# ---------------------------------------------------------------------------
# Verifier function type
# ---------------------------------------------------------------------------

VerifierFn = Callable[
    [dict[str, Any], dict[str, Any], ActionRequest, ActionResult],
    bool,
]


# ---------------------------------------------------------------------------
# Individual verifier implementations
# ---------------------------------------------------------------------------

def verify_inventory_added(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Generic check: any inventory count increased after the action."""
    before_counts: dict[str, int] = before.get("inventory_counts", {})
    after_counts: dict[str, int] = after.get("inventory_counts", {})

    action = action_request.action

    # Specific per-action checks where we know the expected item.
    if action == "collect_wood":
        return _count_logs(after_counts) > _count_logs(before_counts)
    if action == "craft_planks":
        return _count_planks(after_counts) > _count_planks(before_counts)
    if action == "craft_sticks":
        return after_counts.get("stick", 0) > before_counts.get("stick", 0)
    if action == "craft_crafting_table":
        return after_counts.get("crafting_table", 0) > before_counts.get("crafting_table", 0)
    if action == "craft_wooden_pickaxe":
        return after_counts.get("wooden_pickaxe", 0) > before_counts.get("wooden_pickaxe", 0)
    if action == "mine_stone":
        return after_counts.get("cobblestone", 0) > before_counts.get("cobblestone", 0)
    if action == "craft_stone_pickaxe":
        return after_counts.get("stone_pickaxe", 0) > before_counts.get("stone_pickaxe", 0)
    if action == "craft_furnace":
        return after_counts.get("furnace", 0) > before_counts.get("furnace", 0)
    if action == "craft_torches":
        return after_counts.get("torch", 0) > before_counts.get("torch", 0)
    if action == "craft_chest":
        return after_counts.get("chest", 0) > before_counts.get("chest", 0)
    if action == "craft_shield":
        return after_counts.get("shield", 0) > before_counts.get("shield", 0)
    if action == "craft_bucket":
        return after_counts.get("bucket", 0) > before_counts.get("bucket", 0)
    if action == "craft_iron_pickaxe":
        return after_counts.get("iron_pickaxe", 0) > before_counts.get("iron_pickaxe", 0)
    if action == "craft_iron_sword":
        return after_counts.get("iron_sword", 0) > before_counts.get("iron_sword", 0)
    if action == "craft_iron_armor":
        armor = ("iron_helmet", "iron_chestplate", "iron_leggings", "iron_boots")
        return any(after_counts.get(name, 0) > before_counts.get(name, 0) for name in armor) or action_result.ok
    if action == "mine_coal":
        return after_counts.get("coal", 0) > before_counts.get("coal", 0)
    if action == "mine_iron_ore":
        return after_counts.get("raw_iron", 0) > before_counts.get("raw_iron", 0)
    if action in {"smelt_iron", "smelt_item"} and isinstance(action_result.result, dict):
        output = action_result.result.get("output") or ("iron_ingot" if action == "smelt_iron" else None)
        if isinstance(output, str):
            return after_counts.get(output, 0) > before_counts.get(output, 0) or bool(action_result.result.get("partial_success"))
    if action == "craft_item":
        item = action_request.args.get("item")
        if item == "iron_armor":
            armor = ("iron_helmet", "iron_chestplate", "iron_leggings", "iron_boots")
            return any(after_counts.get(name, 0) > before_counts.get(name, 0) for name in armor) or action_result.ok
        if isinstance(item, str):
            return after_counts.get(item, 0) > before_counts.get(item, 0)

    # Generic: any item count went up.
    for name, after_val in after_counts.items():
        if after_val > before_counts.get(name, 0):
            return True
    return False


def verify_block_placed(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check that a block appeared nearby (or the action reported placed=True)."""
    action = action_request.action

    if action == "place_crafting_table":
        before_table = bool(before.get("nearby_blocks", {}).get("crafting_table"))
        after_table = bool(after.get("nearby_blocks", {}).get("crafting_table"))
        return after_table and not before_table or action_result.ok
    if action == "place_furnace":
        before_furnace = bool(before.get("nearby_blocks", {}).get("furnace"))
        after_furnace = bool(after.get("nearby_blocks", {}).get("furnace"))
        return after_furnace and not before_furnace or action_result.ok

    # Fallback: trust the action result flag.
    if isinstance(action_result.result, dict):
        return bool(action_result.result.get("placed")) or action_result.ok
    return action_result.ok


def verify_dimension_changed(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check that the bot's dimension changed."""
    before_dim = before.get("dimension")
    after_dim = after.get("dimension")
    if before_dim and after_dim:
        return before_dim != after_dim
    return action_result.ok


def verify_entity_killed(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check entity was removed or drops appeared in inventory."""
    before_counts: dict[str, int] = before.get("inventory_counts", {})
    after_counts: dict[str, int] = after.get("inventory_counts", {})
    # Any drop increase is a proxy for a kill.
    any_drop = any(after_counts.get(n, 0) > before_counts.get(n, 0) for n in after_counts)
    return any_drop or action_result.ok


def verify_position_changed(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check that the bot's position changed, or the goal was already satisfied."""
    result = action_result.result if isinstance(action_result.result, dict) else {}
    if result.get("already_at_workspace") is True:
        return True
    before_pos = before.get("position")
    after_pos = after.get("position")
    if isinstance(before_pos, dict) and isinstance(after_pos, dict):
        for axis in ("x", "y", "z"):
            if before_pos.get(axis) != after_pos.get(axis):
                return True
        return False
    return action_result.ok


def verify_liquid_placed(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check that a water or lava source block appeared (bucket consumed)."""
    before_counts: dict[str, int] = before.get("inventory_counts", {})
    after_counts: dict[str, int] = after.get("inventory_counts", {})

    # Bucket was consumed (water/lava bucket count dropped, bucket count may have increased)
    action = action_request.action
    if action == "place_water":
        consumed = before_counts.get("water_bucket", 0) > after_counts.get("water_bucket", 0)
        return consumed or action_result.ok
    if action == "place_lava":
        consumed = before_counts.get("lava_bucket", 0) > after_counts.get("lava_bucket", 0)
        return consumed or action_result.ok
    return action_result.ok


def verify_bed_placed(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check that a bed item was consumed from inventory (placed in world)."""
    before_counts: dict[str, int] = before.get("inventory_counts", {})
    after_counts: dict[str, int] = after.get("inventory_counts", {})

    _bed_suffixes = ("_bed",)
    before_beds = sum(v for k, v in before_counts.items() if k.endswith(_bed_suffixes))
    after_beds  = sum(v for k, v in after_counts.items()  if k.endswith(_bed_suffixes))
    return (before_beds > after_beds) or action_result.ok


def verify_portal_lit(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check that a nether portal was successfully lit."""
    if isinstance(action_result.result, dict) and action_result.result.get("lit"):
        return True
    return action_result.ok


def verify_action_result_ok(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Fallback: trust the action result's ok flag."""
    return action_result.ok


def verify_equipment_changed(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check equipment-changing actions via result fields or status equipment summary."""
    if isinstance(action_result.result, dict):
        if action_result.result.get("equipped") or action_result.result.get("equippedArmor"):
            return True
    before_equipment = before.get("equipment") or before.get("equipped")
    after_equipment = after.get("equipment") or after.get("equipped")
    if before_equipment is not None and after_equipment is not None:
        return before_equipment != after_equipment
    return action_result.ok


def verify_milestone(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    """Check progress for composite/milestone actions via result flag or ok."""
    if isinstance(action_result.result, dict):
        return (
            bool(action_result.result.get("milestone_reached"))
            or bool(action_result.result.get("partial_success"))
            or action_result.ok
        )
    return action_result.ok


# ---------------------------------------------------------------------------
# Registry: verifier_signature → verifier function
# ---------------------------------------------------------------------------

VERIFIER_REGISTRY: dict[str, VerifierFn] = {
    "verify_inventory_added": verify_inventory_added,
    "verify_block_placed": verify_block_placed,
    "verify_liquid_placed": verify_liquid_placed,
    "verify_bed_placed": verify_bed_placed,
    "verify_portal_lit": verify_portal_lit,
    "verify_dimension_changed": verify_dimension_changed,
    "verify_entity_killed": verify_entity_killed,
    "verify_position_changed": verify_position_changed,
    "verify_action_result_ok": verify_action_result_ok,
    "verify_equipment_changed": verify_equipment_changed,
    "verify_milestone": verify_milestone,
}


def _resolve_verifier(action_name: str) -> VerifierFn:
    """Return the verifier function for an action, falling back to ok check."""
    spec = CATALOG.get(action_name)
    if spec is not None and spec.verifier_signature in VERIFIER_REGISTRY:
        return VERIFIER_REGISTRY[spec.verifier_signature]
    return verify_action_result_ok


# ---------------------------------------------------------------------------
# Private helpers (unchanged from v1)
# ---------------------------------------------------------------------------

def _small_evidence(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "health": summary.get("health"),
        "food": summary.get("food"),
        "position": summary.get("position"),
        "hostile_nearby": summary.get("hostile_nearby"),
        "inventory_counts": summary.get("inventory_counts", {}),
    }


def _is_danger(summary: dict[str, Any]) -> bool:
    health = summary.get("health")
    return isinstance(health, (int, float)) and health <= 6 and bool(summary.get("hostile_nearby"))


def _is_bridge_error(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    if "bridge" in lowered:
        return True
    # Navigation / pathfinding timeouts are game-world failures, not bridge crashes.
    if _is_navigation_error(error):
        return False
    if _is_resource_acquisition_error(None, error):
        return False
    return "timed out" in lowered or "timeout" in lowered


def _is_resource_acquisition_error(action: str | None, error: str | None) -> bool:
    """True when a resource-gathering action timed out in-world."""
    if not error:
        return False
    lowered = error.lower()
    if "block acquisition failed" in lowered:
        return True
    return bool(action in _RESOURCE_ACTION_TARGETS and ("timed out" in lowered or "timeout" in lowered))


def _is_navigation_error(error: str | None) -> bool:
    """True when the error describes a pathfinding / navigation failure, not a bridge crash."""
    if not error:
        return False
    lowered = error.lower()
    return (
        "navigation path failed" in lowered
        or "timed out pathing" in lowered
        or "no accessible target block" in lowered
        or "exploration path failed" in lowered
        or "flee path failed" in lowered
        or ("path" in lowered and ("timed out" in lowered or "timeout" in lowered or "failed" in lowered))
    )


def _extract_partial_progress_facts(result: dict[str, Any]) -> dict[str, Any]:
    """Pull factual progress fields from a partial_progress_timeout result for the verifier output."""
    facts: dict[str, Any] = {}
    if result.get("partial_success"):
        facts["partial_success"] = True
    failed_because = result.get("failed_because")
    _PARTIAL_PROGRESS_KINDS = {
        "partial_progress_timeout",
        "path_planning_timeout",
        "close_range_access_timeout",
        "mined_target_but_drop_not_collected",
        "drop_collection_failed",
    }
    entry = next(
        (e for e in (failed_because or []) if isinstance(e, dict) and e.get("kind") in _PARTIAL_PROGRESS_KINDS),
        None,
    )
    if entry:
        if entry.get("continuation_relevant"):
            facts["continuation_relevant"] = True
        if entry.get("localFallbackAttempted"):
            facts["localFallbackAttempted"] = True
        # Support both old nearestTargetDistance and new nearestRawTargetDistance
        near_raw = entry.get("nearestRawTargetDistance") or entry.get("nearestTargetDistance")
        if near_raw is not None:
            facts["nearestRawTargetDistance"] = near_raw
        if "selectedTargetDistance" in entry:
            facts["selectedTargetDistance"] = entry["selectedTargetDistance"]
        if "closeRangeFailureReason" in entry and entry["closeRangeFailureReason"]:
            facts["closeRangeFailureReason"] = entry["closeRangeFailureReason"]
        if entry.get("minedTargetBlocks"):
            facts["minedTargetBlocks"] = entry["minedTargetBlocks"]
            facts["progress_made"] = True
        if "nearbyDropsFound" in entry:
            facts["nearbyDropsFound"] = entry["nearbyDropsFound"]
        if "relevantDropsFound" in entry:
            facts["relevantDropsFound"] = entry["relevantDropsFound"]
        if "nearestDropDistance" in entry and entry["nearestDropDistance"] is not None:
            facts["nearestDropDistance"] = entry["nearestDropDistance"]
        if "dropPathAttempts" in entry:
            facts["dropPathAttempts"] = entry["dropPathAttempts"]
        if "drop_collection_reason" in entry and entry["drop_collection_reason"]:
            facts["dropCollectionReason"] = entry["drop_collection_reason"]
        if "pathPlannerError" in entry and entry["pathPlannerError"]:
            facts["pathPlannerError"] = entry["pathPlannerError"]
        if entry.get("recoverable"):
            facts["recoverable"] = True
        signals = entry.get("progress_signals") or {}
        if signals:
            facts["progress_made"] = True
            if "distance_moved" in signals:
                facts["distance_moved"] = signals["distance_moved"]
            if "inventory_delta" in signals:
                facts["inventory_delta"] = signals["inventory_delta"]
            if "accessCandidatesFound" in signals:
                facts["accessCandidatesFound"] = signals["accessCandidatesFound"]
            if "excavatedBlocks" in signals:
                facts["excavatedBlocks"] = signals["excavatedBlocks"]
    return facts


def _failure_recommendation(
    *,
    failure_type: str,
    stop_reason: str | None,
    suggested_next_action: str | None,
    station_needed: str | None = None,
    missing_materials: list[str] | None = None,
    possible_next_actions: list[str] | None = None,
    partial_success: bool = False,
    usable_for_station: bool = False,
    distance_improved: bool = False,
) -> str:
    if failure_type == "bridge_error":
        return "Check the bridge connection."
    if failure_type == "partial_progress_timeout":
        return "Partial progress means continuing may be reasonable, but you may choose any valid action."
    if failure_type == "partial_progress":
        return "Action made partial progress — retry or adjust approach from the new position."
    if failure_type in {"navigation_failed", "resource_acquisition_failed", "path_timeout", "target_unreachable"}:
        return "Navigation to target timed out or path was blocked. Try explore_nearby, look_around, or approach from a different direction."
    if partial_success and usable_for_station:
        choices = ", ".join(possible_next_actions or ["craft_stone_pickaxe", "look_around"])
        return f"Station approach was partial, but the station is usable; choose one of: {choices}."
    if partial_success or distance_improved:
        choices = ", ".join(possible_next_actions or ["approach_station", "look_around"])
        return f"Station approach made progress but did not reach the requested radius; choose one of: {choices}."
    if stop_reason == "station_visible_but_too_far":
        choices = ", ".join(possible_next_actions or ["approach_station", "return_to_workspace", "setup_workspace"])
        return f"{station_needed or 'Station'} is visible but outside usable range - choose one of: {choices}."
    if failure_type == "missing_materials" and missing_materials:
        choices = ", ".join(possible_next_actions or ["look_around"])
        missing = ", ".join(missing_materials)
        return f"Missing materials: {missing}. Possible next actions: {choices}."
    if failure_type == "missing_station" or stop_reason in {"no_crafting_table_nearby", "no_furnace_nearby"}:
        station = station_needed or ("crafting_table" if stop_reason == "no_crafting_table_nearby" else "furnace" if stop_reason == "no_furnace_nearby" else "station")
        next_action = suggested_next_action or "return_to_workspace"
        return f"No {station} nearby — choose {next_action} or setup_workspace before retrying."
    if suggested_next_action:
        return f"Consider {suggested_next_action} before retrying."
    if failure_type == "no_safe_workspace" or stop_reason == "area_cramped":
        return "Move to or find a safer open workspace before retrying placement."
    return "Try a different safe action or inspect status before retrying."


def _count_logs(counts: dict[str, int]) -> int:
    return sum(count for name, count in counts.items() if name.endswith(("_log", "_stem")))


def _count_planks(counts: dict[str, int]) -> int:
    return sum(count for name, count in counts.items() if name.endswith("_planks"))


_PARSE_STOPWORDS = frozenset({"have", "need", "missing", "materials", "material", "and", "the", "a", "or"})
_PARSE_SKIP_RE = re.compile(r"^\d+$")  # skip bare numbers
_LOG_STEM_ITEMS = [
    "oak_log", "spruce_log", "birch_log", "jungle_log", "acacia_log",
    "dark_oak_log", "mangrove_log", "cherry_log", "crimson_stem", "warped_stem",
]
_RESOURCE_ACTION_TARGETS = {
    "collect_wood": _LOG_STEM_ITEMS,
}

# Mining actions that produce action_timeout failed_because entries (not path_timeout).
_MINE_TIMEOUT_ACTIONS = frozenset({"mine_iron_ore", "mine_coal", "mine_stone"})


def _parse_missing_materials(error: str | None) -> list[str]:
    """Return a flat list of material name strings from an error message.

    Handles formats:
    - "stick x1"                    → ["stick"]
    - "need 2 planks, have 1"       → ["planks"]
    - "coal_or_charcoal x1"         → ["coal_or_charcoal"]
    - "no logs or stems found..."   → ["coal_or_charcoal"] (handled elsewhere; logs skipped here)
    """
    if not isinstance(error, str) or "missing material" not in error.lower():
        return []
    _, _, tail = error.partition(":")
    text = tail or error
    low_text = text.lower()
    if ("log" in low_text or "stem" in low_text) and ("no " in low_text or "not found" in low_text or "found" in low_text):
        return ["log_or_stem"]
    materials: list[str] = []
    for part in text.split(","):
        part = part.strip().rstrip(".").lower()
        # Handle "need N name" pattern — extract just the name.
        m_need = re.match(r"need\s+\d+\s+([a-z_]+)", part)
        if m_need:
            token = m_need.group(1)
        else:
            token = re.sub(r"\bx\d+\b|\b\d+\b", "", part)
            token = re.sub(r"\b(?:need|have|missing|materials?|and|the|a)\b", "", token)
            # Collapse "coal or charcoal" → "coal_or_charcoal"
            token = re.sub(r"\s+or\s+", "_or_", token)
            token = token.strip(" .:_").replace(" ", "_").replace("-", "_")
        if not token or _PARSE_SKIP_RE.match(token) or token in _PARSE_STOPWORDS:
            continue
        materials.append(token)
    return _unique(materials)


def _possible_next_actions_for_missing_materials(missing_materials: list[str], counts: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    planks_count = _count_planks({k: v for k, v in counts.items() if isinstance(v, int)})
    has_pickaxe = any(counts.get(name, 0) > 0 for name in ("wooden_pickaxe", "stone_pickaxe", "iron_pickaxe", "diamond_pickaxe"))

    for material in missing_materials:
        if material == "stick":
            if planks_count > 0:
                actions.append("craft_sticks")
            else:
                actions.extend(["collect_wood", "craft_planks"])
        elif material == "coal_or_charcoal":
            if has_pickaxe:
                actions.append("mine_coal")
            actions.append("collect_wood")
        elif material == "cobblestone":
            actions.append("mine_stone")
        elif material == "iron_ingot":
            actions.extend(["mine_iron_ore", "smelt_iron"])
        elif material in ("log_or_stem", "logs_or_stems"):
            actions.append("collect_wood")
        elif material == "crafting_table":
            actions.extend(["craft_crafting_table", "place_crafting_table", "setup_workspace"])
        elif material == "furnace":
            actions.extend(["craft_furnace", "place_furnace", "setup_workspace"])

    actions.append("look_around")
    return _unique(actions)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


# ---------------------------------------------------------------------------
# smelt_item failure helpers
# ---------------------------------------------------------------------------

def _build_smelt_item_failed_because(
    args: dict[str, Any],
    after: dict[str, Any],
    failure_type: str,
) -> tuple[list[dict[str, Any]], bool, str]:
    """Return (failed_because, repeatable_now, failure_type) for smelt_item failures.

    Detects three cases from args + after-inventory, regardless of error string source:
    1. Missing input arg        → invalid_args
    2. Invalid input (not in allowlist) → invalid_enum_value / invalid_args
    3. Valid input but not in inventory → missing_materials / inventory_item
    """
    input_name = args.get("input")
    counts: dict[str, int] = after.get("inventory_counts") or {}

    if not isinstance(input_name, str) or not input_name.strip():
        return (
            [{"kind": "invalid_args", "action": "smelt_item", "missing_arg": "input",
              "expected": "one of allowed smeltable item ids"}],
            False,
            "invalid_args",
        )

    if input_name not in SMELT_INPUTS:
        return (
            [{"kind": "invalid_enum_value", "action": "smelt_item", "arg": "input",
              "received": input_name, "allowed_values": sorted(SMELT_INPUTS)}],
            False,
            "invalid_args",
        )

    # Valid input — check inventory
    have = counts.get(input_name, 0)
    return (
        [{"kind": "inventory_item", "item": input_name, "need": 1, "have": have}],
        False,
        "missing_materials",
    )


def _build_smelt_item_relevant_state(after: dict[str, Any]) -> dict[str, Any]:
    """Compact relevant state for smelt_item failures."""
    counts: dict[str, int] = after.get("inventory_counts") or {}
    nearby: dict[str, Any] = after.get("nearby_blocks") or {}
    smeltable = {k: v for k, v in counts.items() if k in SMELT_INPUTS and v > 0}
    fuel = {k: v for k, v in counts.items() if k in SMELT_FUELS and v > 0}
    furnace_block = nearby.get("furnace")
    furnace_usable = isinstance(furnace_block, dict) and (
        furnace_block.get("distance") is None or furnace_block.get("distance") <= 6.0
    )
    return {
        "inventory_counts": {k: v for k, v in counts.items() if v > 0},
        "has_smeltable_items": bool(smeltable),
        "smeltable_items": smeltable,
        "furnace_usable_nearby": furnace_usable,
        "fuel_items": fuel,
        "item_affordances": {
            "has_smeltable_items": bool(smeltable),
            "smeltable_items": smeltable,
            "has_fuel": bool(fuel),
            "fuel_items": fuel,
        },
    }


def _build_scan_specific_block_failed_because(
    args: dict[str, Any],
    failure_type: str,
) -> tuple[list[dict[str, Any]], bool, str]:
    targets = args.get("targets")
    if not isinstance(targets, list) or len(targets) == 0:
        return (
            [{
                "kind": "invalid_args",
                "action": "scan_for_specific_block",
                "missing_arg": "targets",
                "expected": "non-empty list of block names to scan for",
            }],
            False,
            "invalid_args",
        )
    for t in targets:
        if not isinstance(t, str) or not t.strip():
            return (
                [{
                    "kind": "invalid_args",
                    "action": "scan_for_specific_block",
                    "missing_arg": "targets",
                    "expected": "all targets must be non-empty strings",
                }],
                False,
                "invalid_args",
            )
    return [], True, failure_type


# ---------------------------------------------------------------------------
# Explore-nearby action-timeout helpers
# ---------------------------------------------------------------------------

def _compute_position_delta(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, float]:
    """Return (moved_meaningfully, distance_moved). Threshold for 'meaningful' is > 2 blocks."""
    before_pos = before.get("position")
    after_pos = after.get("position")
    if not isinstance(before_pos, dict) or not isinstance(after_pos, dict):
        return False, 0.0
    try:
        dx = float(after_pos.get("x", 0)) - float(before_pos.get("x", 0))
        dy = float(after_pos.get("y", 0)) - float(before_pos.get("y", 0))
        dz = float(after_pos.get("z", 0)) - float(before_pos.get("z", 0))
        dist = round((dx * dx + dy * dy + dz * dz) ** 0.5, 1)
        return dist > 2.0, dist
    except (TypeError, ValueError):
        return False, 0.0


def _build_explore_timeout_failed_because(
    action: str,
    error: str | None,
    result: dict[str, Any],
    position_changed: bool,
    distance_moved: float,
) -> tuple[list[dict[str, Any]], bool, str]:
    """Return (failed_because, repeatable_now, failure_type).

    Enriches the JS-side action_timeout entry with position delta facts and
    determines the Python-level failure_type:
    - "partial_progress" when the bot moved meaningfully (repeatable_now=True)
    - "navigation_failed" when the bot stayed put (repeatable_now=False)
    """
    m = re.search(r"(\d+)\s*ms", error or "")
    timeout_ms: int | None = int(m.group(1)) if m else None
    if timeout_ms is None:
        timeout_ms = (result.get("diagnostics") or {}).get("timeout_ms")

    js_fb = result.get("failed_because")
    if isinstance(js_fb, list) and js_fb and isinstance(js_fb[0], dict):
        entry: dict[str, Any] = dict(js_fb[0])
    else:
        entry = {"kind": "action_timeout", "action": action}

    if timeout_ms is not None:
        entry["timeout_ms"] = timeout_ms
    entry["position_changed"] = position_changed
    entry["distance_moved"] = distance_moved
    entry["recoverable"] = True

    if position_changed:
        return [entry], True, "partial_progress"
    return [entry], False, "navigation_failed"


def _build_explore_timeout_relevant_state(after: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    pos = after.get("position")
    if pos:
        state["position"] = pos
    block_counts = after.get("nearby_block_counts") or {}
    if block_counts:
        state["nearbyBlockCounts"] = dict(list(block_counts.items())[:12])
    return state


def _build_mining_timeout_failed_because(
    action: str,
    error: str | None,
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool, str]:
    """Return (failed_because, repeatable_now, failure_type) for mine_* action timeouts.

    Produces kind=action_timeout (not path_timeout) plus an optional
    resource_acquisition_attempt entry with position change diagnostics.
    position_changed_since_last_attempt is True only when movement exceeds
    POSITION_MEANINGFUL_DELTA_BLOCKS — path jitter below the threshold keeps
    repeatable_now=False so the family stays blocked.
    failure_type is always resource_acquisition_failed so _navigation_stall still counts it.
    """
    m = re.search(r"(\d+)\s*ms", error or "")
    timeout_ms: int | None = int(m.group(1)) if m else None

    resource_family: str | None = action[len("mine_"):] if action.startswith("mine_") else None

    entry: dict[str, Any] = {"kind": "action_timeout", "action": action, "recoverable": True}
    if timeout_ms is not None:
        entry["timeout_ms"] = timeout_ms

    entries: list[dict[str, Any]] = [entry]

    repeatable_now = True
    if resource_family is not None:
        _, distance = _compute_position_delta(before, after)
        position_change_meaningful = distance >= POSITION_MEANINGFUL_DELTA_BLOCKS
        entries.append({
            "kind": "resource_acquisition_attempt",
            "resource_family": resource_family,
            "position_changed_since_last_attempt": position_change_meaningful,
            "distance_moved_since_last_attempt": distance,
            "position_change_meaningful": position_change_meaningful,
        })
        repeatable_now = position_change_meaningful

    return entries, repeatable_now, "resource_acquisition_failed"


# ---------------------------------------------------------------------------
# Navigation failure helpers
# ---------------------------------------------------------------------------

def _build_navigation_failed_because(
    action: str,
    error: str | None,
    result: dict[str, Any],
    args: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build failed_because entries for navigation/pathfinding failures."""
    targets: list[str] = []
    raw_targets = args.get("targets") or result.get("targets")
    if isinstance(raw_targets, list):
        targets = [t for t in raw_targets if isinstance(t, str)]
    if not targets and action in _RESOURCE_ACTION_TARGETS:
        targets = list(_RESOURCE_ACTION_TARGETS[action])
    radius = args.get("radius") or result.get("radius")
    error_lower = (error or "").lower()

    entries: list[dict[str, Any]] = []

    # Path timed out — a candidate was found but navigation didn't finish.
    if "timed out" in error_lower or "timeout" in error_lower or "timed out pathing" in error_lower:
        entry: dict[str, Any] = {"kind": "path_timeout", "action": action}
        if targets:
            entry["target"] = targets[0] if len(targets) == 1 else targets
        if radius is not None:
            entry["radius"] = radius
        m = re.search(r"(\d+)\s*ms", error or "")
        if m:
            entry["timeout_ms"] = int(m.group(1))
        entries.append(entry)

        # If we know the target block position from result, add accessibility info.
        target_block = result.get("target")
        if isinstance(target_block, dict):
            dist = target_block.get("distance")
            acc_entry: dict[str, Any] = {
                "kind": "accessible_block",
                "accessible": False,
            }
            if targets:
                acc_entry["block"] = targets[0] if len(targets) == 1 else targets
            if dist is not None:
                acc_entry["nearest_distance"] = dist
                acc_entry["visible"] = True
            entries.append(acc_entry)

    # No target block found in the search radius.
    elif "no accessible target block" in error_lower or result.get("targetCandidatesFound") == 0:
        for target in (targets or ["unknown"]):
            entry = {
                "kind": "nearby_block",
                "block": target,
                "found": False,
            }
            if radius is not None:
                entry["radius"] = radius
            entries.append(entry)

    # Generic unreachable fallback.
    elif "unreachable" in error_lower or result.get("failure_type") == "target_unreachable":
        for target in (targets or ["unknown"]):
            entries.append({
                "kind": "accessible_block",
                "block": target,
                "visible": bool(result.get("target")),
                "accessible": False,
            })

    return entries


def _build_navigation_relevant_state(
    after: dict[str, Any],
    args: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Relevant world-state snapshot for a navigation failure."""
    state: dict[str, Any] = {}
    pos = after.get("position")
    if pos:
        state["position"] = pos
    block_counts = after.get("nearby_block_counts") or {}
    if block_counts:
        state["nearbyBlockCounts"] = dict(list(block_counts.items())[:12])
    nearby = after.get("nearby_blocks") or {}
    if nearby:
        state["nearbyBlocks"] = {k: {"distance": v.get("distance")} for k, v in nearby.items() if isinstance(v, dict)}
    targets = args.get("targets") or result.get("targets")
    if targets:
        state["target"] = targets[0] if isinstance(targets, list) and len(targets) == 1 else targets
    return state


def _build_approach_station_failed_because(
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Build failed_because for approach_station station_not_reached.

    Returns (failed_because, repeatable_now, lesson).
    """
    station = result.get("station") or result.get("station_needed") or "station"
    final_distance = result.get("final_distance")
    target_radius = result.get("target_radius")
    usable_for_station = bool(result.get("usable_for_station"))
    distance_improved = bool(result.get("distance_improved"))

    entry: dict[str, Any] = {
        "kind": "station_usable",
        "station": station,
        "reached": False,
        "usable_for_station": usable_for_station,
    }
    if target_radius is not None:
        entry["target_radius"] = target_radius
    if final_distance is not None:
        entry["final_distance"] = final_distance

    lesson: str | None = None
    if usable_for_station:
        repeatable_now = True
        lesson = "The station may be usable even if the exact requested radius was not reached."
    elif distance_improved:
        repeatable_now = True
    else:
        repeatable_now = False

    return [entry], repeatable_now, lesson


# ---------------------------------------------------------------------------
# Generic requirement failure helpers (used only by verify_action)
# ---------------------------------------------------------------------------

def _facts_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal facts dict from a verifier summary for requirement checking."""
    counts: dict[str, int] = summary.get("inventory_counts") or {}
    nearby = summary.get("nearby_blocks") or {}
    crafting_table = nearby.get("crafting_table")
    furnace = nearby.get("furnace")

    def _dist(block: Any) -> float | None:
        if not isinstance(block, dict):
            return None
        d = block.get("distance")
        return float(d) if isinstance(d, (int, float)) else None

    ct_dist = _dist(crafting_table)
    fn_dist = _dist(furnace)
    ct_usable = isinstance(crafting_table, dict) and (ct_dist is None or ct_dist <= 6.0)
    fn_usable = isinstance(furnace, dict) and (fn_dist is None or fn_dist <= 6.0)

    return {
        "inventory_counts": counts,
        "has_nearby_crafting_table_usable": ct_usable,
        "has_visible_crafting_table": isinstance(crafting_table, dict),
        "nearest_crafting_table_distance": ct_dist,
        "has_nearby_furnace_usable": fn_usable,
        "has_visible_furnace": isinstance(furnace, dict),
        "nearest_furnace_distance": fn_dist,
        "dimension": summary.get("dimension"),
        "health": summary.get("health"),
        "food": summary.get("food"),
    }


def _build_failed_because(
    action: str,
    error: str | None,
    result: dict[str, Any],
    missing_materials: list[str] | None,
    facts: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    """Return (failed_because list, repeatable_now).

    Priority:
    1. Exact bridge "need N item, have M" errors.
    2. Catalog typed requirements.
    3. Structured missing_materials list.
    4. Error string parsing.
    """
    # 1. Exact bridge quantity errors are the most specific source.
    exact_need_have = _parse_need_have_missing_material(error)
    if exact_need_have:
        return [exact_need_have], False

    # 2. Catalog typed requirements
    spec = CATALOG.get(action)
    if spec and spec.requirements:
        report = check_requirements(spec.requirements, facts)
        if not report.ok:
            return [fr.to_dict() for fr in report.failed_requirements], report.repeatable_now

    # 3. Structured missing_materials already parsed by verifier
    if missing_materials:
        frs = []
        counts: dict[str, int] = facts.get("inventory_counts") or {}
        for mat in missing_materials:
            if mat in ("coal_or_charcoal",):
                have = counts.get("coal", 0) + counts.get("charcoal", 0)
                frs.append({"kind": "inventory_any", "items": ["coal", "charcoal"], "need": 1, "have": have})
            elif mat in ("log_or_stem", "logs_or_stems", "no_logs_or_stems_found_in_inventory"):
                have = sum(counts.get(it, 0) for it in _LOG_STEM_ITEMS)
                frs.append({"kind": "inventory_any", "items": list(_LOG_STEM_ITEMS), "need": 1, "have": have})
            else:
                frs.append({"kind": "inventory_item", "item": mat, "need": 1, "have": counts.get(mat, 0)})
        return frs, False

    # 4. Error string fallback
    parsed = parse_error_to_failed_requirements(
        error=error,
        action=action,
        result=result,
        facts=facts,
    )
    if parsed:
        return [fr.to_dict() for fr in parsed], False

    return [], True  # no requirements identified → conservatively retryable


def _parse_need_have_missing_material(error: str | None) -> dict[str, Any] | None:
    """Parse exact "Missing materials: need N item, have M." bridge errors."""
    if not isinstance(error, str):
        return None
    match = re.search(
        r"missing\s+materials?\s*:\s*need\s+(\d+)\s+([a-zA-Z0-9_]+)\s*,\s*have\s+(\d+)\s*\.?\s*$",
        error,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return {
        "kind": "inventory_item",
        "item": match.group(2).lower(),
        "need": int(match.group(1)),
        "have": int(match.group(3)),
    }


def _build_relevant_state_for_failure(
    summary: dict[str, Any],
    missing_materials: list[str] | None,
) -> dict[str, Any]:
    """Compact relevant state snapshot for a failure."""
    counts: dict[str, int] = summary.get("inventory_counts") or {}
    relevant: dict[str, Any] = {}
    if missing_materials:
        for mat in missing_materials:
            if mat == "coal_or_charcoal":
                relevant["inv_coal"] = counts.get("coal", 0)
                relevant["inv_charcoal"] = counts.get("charcoal", 0)
            elif mat in ("log_or_stem", "logs_or_stems", "no_logs_or_stems_found_in_inventory"):
                relevant["inv_logs_or_stems"] = sum(counts.get(it, 0) for it in _LOG_STEM_ITEMS)
            else:
                relevant[f"inv_{mat}"] = counts.get(mat, 0)
    return relevant
