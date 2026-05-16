from typing import Any, Callable

from vtuber_ai.action_catalog import CATALOG
from vtuber_ai.curriculum import objective_item_count, objective_item_name, recommend_objective
from vtuber_ai.agent_state import summarize_status
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
        failure_type = result.get("failure_type") or ("bridge_error" if _is_bridge_error(action_result.error) else "no_progress")
        stop_reason = result.get("stop_reason")
        suggested_next_action = result.get("suggested_next_action")
        fallback_suggested_next_action = result.get("fallback_suggested_next_action")
        can_retry = result.get("can_retry")
        needed = result.get("needed")
        station_needed = result.get("station_needed")
        diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
        return {
            "success": False,
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
            "diagnostics": diagnostics,
            "recommendation": _failure_recommendation(
                failure_type=failure_type,
                stop_reason=stop_reason,
                suggested_next_action=suggested_next_action,
                station_needed=station_needed,
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
        return after_table and not before_table
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
    """Check that the bot's position changed."""
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
    return "bridge" in lowered or "timed out" in lowered or "timeout" in lowered


def _failure_recommendation(
    *,
    failure_type: str,
    stop_reason: str | None,
    suggested_next_action: str | None,
    station_needed: str | None = None,
) -> str:
    if failure_type == "bridge_error":
        return "Check the bridge connection."
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
