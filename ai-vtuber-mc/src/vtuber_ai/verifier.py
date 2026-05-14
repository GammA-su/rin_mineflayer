from typing import Any

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
        failure_type = "bridge_error" if _is_bridge_error(action_result.error) else "no_progress"
        return {
            "success": False,
            "evidence": {
                "action": action_request.action,
                "action_error": action_result.error,
                "before": _small_evidence(before),
                "after": _small_evidence(after),
            },
            "failure_type": failure_type,
            "recommendation": "Check the bridge connection." if failure_type == "bridge_error" else "Try a different safe action or inspect status before retrying.",
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

    success = _action_made_progress(before, after, action_request, action_result)
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


def _action_made_progress(
    before: dict[str, Any],
    after: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
) -> bool:
    action = action_request.action
    before_counts = before.get("inventory_counts", {})
    after_counts = after.get("inventory_counts", {})

    if action == "collect_wood":
        return _count_logs(after_counts) > _count_logs(before_counts)

    if action == "craft_planks":
        return _count_planks(after_counts) > _count_planks(before_counts)

    if action == "craft_sticks":
        return after_counts.get("stick", 0) > before_counts.get("stick", 0)

    if action == "craft_crafting_table":
        return after_counts.get("crafting_table", 0) > before_counts.get("crafting_table", 0)

    if action == "place_crafting_table":
        before_table = bool(before.get("nearby_blocks", {}).get("crafting_table"))
        after_table = bool(after.get("nearby_blocks", {}).get("crafting_table"))
        return after_table and not before_table

    if action == "craft_wooden_pickaxe":
        return after_counts.get("wooden_pickaxe", 0) > before_counts.get("wooden_pickaxe", 0)

    if action == "mine_stone":
        return after_counts.get("cobblestone", 0) > before_counts.get("cobblestone", 0)

    if action == "craft_stone_pickaxe":
        return after_counts.get("stone_pickaxe", 0) > before_counts.get("stone_pickaxe", 0)

    if action in {"status", "say", "look_around", "explore_nearby", "stop", "jump", "flee", "eat_food"}:
        return action_result.ok

    return action_result.ok


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


def _count_logs(counts: dict[str, int]) -> int:
    return sum(count for name, count in counts.items() if name.endswith(("_log", "_stem")))


def _count_planks(counts: dict[str, int]) -> int:
    return sum(count for name, count in counts.items() if name.endswith("_planks"))
