from __future__ import annotations

import json
from typing import Any


MILESTONE_GROUPS: dict[str, tuple[str, ...]] = {
    "early": (
        "has_logs",
        "has_planks",
        "has_crafting_table",
        "has_nearby_crafting_table",
        "has_wooden_pickaxe",
        "has_stone_pickaxe",
        "has_furnace",
        "has_torches",
    ),
    "iron": (
        "has_coal",
        "has_raw_iron",
        "has_iron_ingot",
        "has_shield",
        "has_bucket",
        "has_iron_pickaxe",
        "has_iron_armor_piece",
        "has_full_iron_armor",
    ),
    "diamond_portal": (
        "has_diamond",
        "has_diamond_pickaxe",
        "has_obsidian",
        "has_flint",
        "has_flint_and_steel",
        "has_nether_portal",
        "entered_nether",
    ),
    "nether": (
        "has_gold_armor",
        "found_fortress",
        "has_blaze_rod",
        "has_blaze_powder",
        "has_ender_pearl",
        "has_eye_of_ender",
        "returned_from_nether",
    ),
    "stronghold_end": (
        "stronghold_search_started",
        "found_stronghold",
        "found_end_portal_room",
        "activated_end_portal",
        "entered_end",
    ),
    "dragon": (
        "end_safe_landing_done",
        "crystals_remaining_unknown_or_known",
        "crystals_destroyed",
        "dragon_damaged",
        "dragon_defeated",
        "returned_to_overworld_via_end_portal",
    ),
    "death_recovery": (
        "died",
        "recovered_death_items",
        "abandoned_death_recovery",
    ),
}

ALL_MILESTONES: tuple[str, ...] = tuple(
    milestone for group in MILESTONE_GROUPS.values() for milestone in group
)


def build_milestone_state(
    *,
    status: dict[str, Any] | None,
    recent_memory: list[dict[str, Any]] | None = None,
    recent_ticks: list[dict[str, Any]] | None = None,
    waypoints: list[dict[str, Any]] | None = None,
    death_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer broad Minecraft completion milestones from state and history.

    Milestones are advisory awareness for the planner. They intentionally do not
    encode a deterministic checklist or force action ordering.
    """

    status = status if isinstance(status, dict) else {}
    recent_memory = recent_memory or []
    recent_ticks = recent_ticks or []
    waypoints = waypoints or []
    death_state = death_state if isinstance(death_state, dict) else {}

    counts = _inventory_counts(status)
    dimension = str(status.get("dimension") or "")
    nearby_blocks = status.get("nearbyBlocks") if isinstance(status.get("nearbyBlocks"), dict) else {}
    nearby_counts = status.get("nearbyBlockCounts") if isinstance(status.get("nearbyBlockCounts"), dict) else {}
    action_events = _action_events(recent_memory, recent_ticks)
    waypoint_labels = {str(w.get("label")) for w in waypoints if isinstance(w, dict)}
    waypoint_kinds = {str(w.get("kind")) for w in waypoints if isinstance(w, dict)}

    completed: dict[str, bool] = {name: False for name in ALL_MILESTONES}

    completed.update(
        {
            "has_logs": _count_suffixes(counts, ("_log", "_stem")) > 0,
            "has_planks": _count_suffixes(counts, ("_planks",)) > 0,
            "has_crafting_table": counts.get("crafting_table", 0) > 0,
            "has_nearby_crafting_table": isinstance(nearby_blocks.get("crafting_table"), dict),
            "has_wooden_pickaxe": counts.get("wooden_pickaxe", 0) > 0,
            "has_stone_pickaxe": counts.get("stone_pickaxe", 0) > 0,
            "has_furnace": counts.get("furnace", 0) > 0 or nearby_counts.get("furnace", 0) > 0,
            "has_torches": counts.get("torch", 0) > 0,
            "has_coal": counts.get("coal", 0) > 0 or counts.get("charcoal", 0) > 0,
            "has_raw_iron": counts.get("raw_iron", 0) > 0,
            "has_iron_ingot": counts.get("iron_ingot", 0) > 0,
            "has_shield": counts.get("shield", 0) > 0,
            "has_bucket": _count_names(counts, ("bucket", "water_bucket", "lava_bucket", "milk_bucket")) > 0,
            "has_iron_pickaxe": counts.get("iron_pickaxe", 0) > 0,
            "has_iron_armor_piece": _iron_armor_count(counts) > 0,
            "has_full_iron_armor": _iron_armor_count(counts) >= 4,
            "has_diamond": counts.get("diamond", 0) > 0,
            "has_diamond_pickaxe": counts.get("diamond_pickaxe", 0) > 0,
            "has_obsidian": counts.get("obsidian", 0) > 0,
            "has_flint": counts.get("flint", 0) > 0,
            "has_flint_and_steel": counts.get("flint_and_steel", 0) > 0,
            "has_gold_armor": _gold_armor_count(counts) > 0,
            "has_blaze_rod": counts.get("blaze_rod", 0) > 0,
            "has_blaze_powder": counts.get("blaze_powder", 0) > 0,
            "has_ender_pearl": counts.get("ender_pearl", 0) > 0,
            "has_eye_of_ender": counts.get("ender_eye", 0) > 0,
            "entered_nether": "nether" in dimension or _action_ok(action_events, "enter_nether"),
            "entered_end": "the_end" in dimension or _action_ok(action_events, "enter_end"),
            "died": bool(death_state.get("known")) or _has_action(action_events, "death_event"),
        }
    )

    completed["has_nether_portal"] = (
        "nether_portal_overworld" in waypoint_labels
        or "nether_portal_nether" in waypoint_labels
        or nearby_counts.get("nether_portal", 0) > 0
        or _action_ok(action_events, "build_nether_portal")
        or _action_ok(action_events, "cast_nether_portal")
        or _action_ok(action_events, "light_nether_portal")
    )
    completed["found_fortress"] = (
        "fortress" in waypoint_labels
        or "fortress" in waypoint_kinds
        or _action_ok(action_events, "find_nether_fortress")
    )
    completed["returned_from_nether"] = (
        _action_ok(action_events, "leave_nether")
        or _action_ok(action_events, "return_to_portal")
        or ("nether" not in dimension and completed["entered_nether"] and completed["has_blaze_rod"])
    )
    completed["stronghold_search_started"] = _has_action(
        action_events, "throw_eye_of_ender", "locate_stronghold_step"
    )
    completed["found_stronghold"] = (
        "stronghold" in waypoint_labels
        or "stronghold" in waypoint_kinds
        or _action_ok(action_events, "locate_stronghold_step")
        or _action_ok(action_events, "dig_staircase_to_stronghold")
    )
    completed["found_end_portal_room"] = (
        "end_portal_room" in waypoint_labels
        or "end_portal_room" in waypoint_kinds
        or _action_ok(action_events, "scan_for_end_portal_room")
    )
    completed["activated_end_portal"] = (
        nearby_counts.get("end_portal", 0) > 0
        or _action_result_flag(action_events, "activate_end_portal", "portal_active")
        or _action_ok(action_events, "activate_end_portal")
    )
    completed["end_safe_landing_done"] = _action_ok(action_events, "end_safe_landing")
    completed["crystals_remaining_unknown_or_known"] = (
        completed["entered_end"]
        or _has_action(action_events, "scan_end_crystals", "fight_dragon_phase")
    )
    completed["crystals_destroyed"] = (
        _action_result_value(action_events, "destroy_nearby_end_crystals", "remaining") == 0
        or _action_result_flag(action_events, "dragon_phase_crystals", "milestone_reached")
        or _action_result_flag(action_events, "fight_dragon_phase", "milestone_reached")
    )
    completed["dragon_damaged"] = (
        _action_ok(action_events, "attack_dragon_with_bow")
        or _action_ok(action_events, "attack_perched_dragon")
        or _action_ok(action_events, "dragon_phase_circle")
        or _action_ok(action_events, "dragon_phase_perch")
    )
    completed["dragon_defeated"] = (
        _action_ok(action_events, "return_to_overworld_via_end_portal")
        or _action_result_value(action_events, "fight_dragon_phase", "phase") == "complete"
        or _action_result_flag(action_events, "attack_dragon_with_bow", "milestone_reached")
        or _action_result_flag(action_events, "attack_perched_dragon", "milestone_reached")
    )
    completed["returned_to_overworld_via_end_portal"] = _action_ok(
        action_events, "return_to_overworld_via_end_portal"
    )
    completed["recovered_death_items"] = (
        _action_result_flag(action_events, "recover_death_items", "recovered_any")
        or _has_recovered_items(action_events)
    )
    completed["abandoned_death_recovery"] = (
        bool(death_state.get("abandoned")) or _action_ok(action_events, "abandon_death_recovery")
    )

    grouped = {
        group: {name: completed[name] for name in names}
        for group, names in MILESTONE_GROUPS.items()
    }
    completed_names = [name for name in ALL_MILESTONES if completed[name]]
    next_possible = _next_possible(completed)

    return {
        "groups": grouped,
        "completed": completed,
        "completed_milestones": completed_names,
        "next_possible_milestones": next_possible,
        "counts": {
            "completed": len(completed_names),
            "total": len(ALL_MILESTONES),
        },
    }


def newly_completed(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_completed = before.get("completed") if isinstance(before.get("completed"), dict) else {}
    after_completed = after.get("completed") if isinstance(after.get("completed"), dict) else {}
    return [
        name for name in ALL_MILESTONES
        if bool(after_completed.get(name)) and not bool(before_completed.get(name))
    ]


def _next_possible(completed: dict[str, bool]) -> list[str]:
    candidates: list[str] = []
    for group_name, names in MILESTONE_GROUPS.items():
        remaining = [name for name in names if not completed[name]]
        if remaining:
            candidates.extend(remaining[:3])
        if group_name in {"early", "iron"} and remaining:
            break
    return candidates[:10]


def _inventory_counts(status: dict[str, Any]) -> dict[str, int]:
    inventory = status.get("inventory")
    if not isinstance(inventory, list):
        return {}
    counts: dict[str, int] = {}
    for item in inventory:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        count = item.get("count")
        if isinstance(name, str) and isinstance(count, int):
            counts[name] = counts.get(name, 0) + count
    return counts


def _count_suffixes(counts: dict[str, int], suffixes: tuple[str, ...]) -> int:
    return sum(count for name, count in counts.items() if name.endswith(suffixes))


def _count_names(counts: dict[str, int], names: tuple[str, ...]) -> int:
    return sum(counts.get(name, 0) for name in names)


def _iron_armor_count(counts: dict[str, int]) -> int:
    return sum(1 for name in _armor_names("iron") if counts.get(name, 0) > 0)


def _gold_armor_count(counts: dict[str, int]) -> int:
    return sum(1 for name in _armor_names("golden") if counts.get(name, 0) > 0)


def _armor_names(material: str) -> tuple[str, ...]:
    return (
        f"{material}_helmet",
        f"{material}_chestplate",
        f"{material}_leggings",
        f"{material}_boots",
    )


def _action_events(
    recent_memory: list[dict[str, Any]],
    recent_ticks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in recent_memory:
        if not isinstance(row, dict):
            continue
        events.append(
            {
                "action": row.get("action"),
                "ok": _coerce_ok(row.get("ok")),
                "result": _decode_json(row.get("result_json")),
            }
        )
    for row in recent_ticks:
        if not isinstance(row, dict):
            continue
        events.append(
            {
                "action": row.get("action"),
                "ok": _coerce_ok(row.get("ok")),
                "result": _decode_json(row.get("result_json")),
            }
        )
    return events


def _decode_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _coerce_ok(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return False


def _has_action(events: list[dict[str, Any]], *actions: str) -> bool:
    wanted = set(actions)
    return any(event.get("action") in wanted for event in events)


def _action_ok(events: list[dict[str, Any]], action: str) -> bool:
    return any(event.get("action") == action and bool(event.get("ok")) for event in events)


def _action_result_flag(events: list[dict[str, Any]], action: str, field: str) -> bool:
    for event in events:
        if event.get("action") != action:
            continue
        result = event.get("result")
        if isinstance(result, dict) and bool(result.get(field)):
            return True
    return False


def _action_result_value(events: list[dict[str, Any]], action: str, field: str) -> Any:
    for event in events:
        if event.get("action") != action:
            continue
        result = event.get("result")
        if isinstance(result, dict) and field in result:
            return result.get(field)
    return None


def _has_recovered_items(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if event.get("action") != "recover_death_items":
            continue
        result = event.get("result")
        recovered = result.get("recovered") if isinstance(result, dict) else None
        if isinstance(recovered, list) and len(recovered) > 0:
            return True
    return False
