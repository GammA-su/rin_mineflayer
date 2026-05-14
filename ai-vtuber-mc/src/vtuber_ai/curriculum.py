from typing import Any

WOOD_LOG_SUFFIXES = ("_log", "_stem")
PLANK_SUFFIX = "_planks"


def recommend_objective(status: dict[str, Any], recent_events: list[dict[str, Any]] | None = None) -> str:
    counts = inventory_counts(status)

    logs = count_logs(counts)
    planks = count_planks(counts)
    sticks = counts.get("stick", 0)
    crafting_tables = counts.get("crafting_table", 0)
    wooden_pickaxes = counts.get("wooden_pickaxe", 0)
    cobblestone = counts.get("cobblestone", 0)
    stone_pickaxes = counts.get("stone_pickaxe", 0)
    nearby_crafting_table = has_nearby_crafting_table(status)

    if stone_pickaxes > 0:
        return "tier1_complete"

    if wooden_pickaxes > 0:
        if cobblestone < 3:
            return "mine_stone"
        if sticks < 2:
            return "craft_sticks"
        return "craft_stone_pickaxe"

    if crafting_tables > 0:
        if not nearby_crafting_table:
            return "place_crafting_table"
        if sticks < 2:
            return "craft_sticks"
        if planks < 3:
            return "craft_planks"
        return "craft_wooden_pickaxe"

    if sticks > 0:
        return "craft_crafting_table"

    if planks > 0:
        return "craft_sticks"

    if logs > 0:
        return "craft_planks"

    return "collect_wood"


def inventory_counts(status: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    inventory = status.get("inventory") or []

    if not isinstance(inventory, list):
        return counts

    for item in inventory:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        count = item.get("count", 0)
        if not isinstance(name, str) or not isinstance(count, int):
            continue

        counts[name] = counts.get(name, 0) + count

    return counts


def count_logs(counts: dict[str, int]) -> int:
    return sum(count for name, count in counts.items() if name.endswith(WOOD_LOG_SUFFIXES))


def count_planks(counts: dict[str, int]) -> int:
    return sum(count for name, count in counts.items() if name.endswith(PLANK_SUFFIX))


def objective_item_count(objective: str, status: dict[str, Any]) -> int:
    counts = inventory_counts(status)

    if objective == "collect_wood":
        return count_logs(counts)

    if objective == "craft_planks":
        return count_planks(counts)

    if objective == "craft_sticks":
        return counts.get("stick", 0)

    if objective == "craft_crafting_table":
        return counts.get("crafting_table", 0)

    if objective == "place_crafting_table":
        return 1 if has_nearby_crafting_table(status) else 0

    if objective == "craft_wooden_pickaxe":
        return counts.get("wooden_pickaxe", 0)

    if objective == "mine_stone":
        return counts.get("cobblestone", 0)

    if objective == "craft_stone_pickaxe":
        return counts.get("stone_pickaxe", 0)

    return 0


def objective_item_name(objective: str) -> str | None:
    return {
        "collect_wood": "logs",
        "craft_planks": "planks",
        "craft_sticks": "stick",
        "craft_crafting_table": "crafting_table",
        "place_crafting_table": "nearby_crafting_table",
        "craft_wooden_pickaxe": "wooden_pickaxe",
        "mine_stone": "cobblestone",
        "craft_stone_pickaxe": "stone_pickaxe",
    }.get(objective)


def has_nearby_crafting_table(status: dict[str, Any]) -> bool:
    nearby_blocks = status.get("nearbyBlocks")
    if not isinstance(nearby_blocks, dict):
        return False

    crafting_table = nearby_blocks.get("crafting_table")
    return isinstance(crafting_table, dict)
