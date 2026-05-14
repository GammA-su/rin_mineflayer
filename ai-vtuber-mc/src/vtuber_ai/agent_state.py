import json
from typing import Any


FOOD_ITEM_NAMES = frozenset(
    {
        "apple",
        "bread",
        "cooked_beef",
        "cooked_porkchop",
        "cooked_chicken",
        "cooked_mutton",
        "cooked_rabbit",
        "baked_potato",
        "carrot",
        "beef",
        "porkchop",
        "chicken",
        "mutton",
    }
)


def summarize_status(status: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(status, dict):
        return {"ok": False, "unavailable": True}

    inventory = status.get("inventory") if isinstance(status.get("inventory"), list) else []
    nearby_entities = status.get("nearbyEntities") if isinstance(status.get("nearbyEntities"), list) else []

    return {
        "ok": status.get("ok", False),
        "connected": status.get("connected", False),
        "entityReady": status.get("entityReady", False),
        "username": status.get("username"),
        "health": status.get("health"),
        "food": status.get("food"),
        "air": status.get("air"),
        "position": status.get("position"),
        "dimension": status.get("dimension"),
        "time": status.get("time"),
        "movement": {
            "onGround": status.get("onGround"),
            "inWater": status.get("inWater"),
            "inLava": status.get("inLava"),
        },
        "inventory_counts": inventory_counts_from_items(inventory),
        "has_food": has_food(inventory),
        "nearby_players": status.get("nearbyPlayers") or [],
        "nearby_entities": nearby_entities[:12],
        "hostile_nearby": any(_is_hostile_entity(entity) for entity in nearby_entities),
        "nearby_block_counts": status.get("nearbyBlockCounts") or {},
        "nearby_blocks": status.get("nearbyBlocks") or {},
    }


def inventory_counts_from_items(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        count = item.get("count", 0)
        if isinstance(name, str) and isinstance(count, int):
            counts[name] = counts.get(name, 0) + count

    return counts


def has_food(items: list[Any]) -> bool:
    return any(isinstance(item, dict) and item.get("name") in FOOD_ITEM_NAMES for item in items)


def build_agent_state(
    *,
    bot_status: dict[str, Any] | None,
    recent_memory: list[dict[str, Any]],
    recent_ticks: list[dict[str, Any]],
) -> dict[str, Any]:
    last_tick = recent_ticks[0] if recent_ticks else None
    last_result = _decode_json_field(last_tick, "result_json") if last_tick else None
    last_verifier = _decode_json_field(last_tick, "verifier_json") if last_tick else None

    return {
        "bot_status": bot_status or {"ok": False, "unavailable": True},
        "summary": summarize_status(bot_status),
        "recent_memory": recent_memory,
        "recent_ticks": recent_ticks,
        "last_objective": last_tick.get("objective") if last_tick else None,
        "last_action": last_tick.get("action") if last_tick else None,
        "last_result": last_result,
        "last_verifier": last_verifier,
    }


def _decode_json_field(row: dict[str, Any] | None, key: str) -> Any:
    if not row:
        return None

    raw = row.get(key)
    if not isinstance(raw, str) or not raw:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _is_hostile_entity(entity: dict[str, Any]) -> bool:
    if not isinstance(entity, dict):
        return False

    if entity.get("hostile") is True:
        return True

    name = entity.get("name")
    return isinstance(name, str) and name in {
        "zombie",
        "skeleton",
        "creeper",
        "spider",
        "enderman",
        "witch",
        "drowned",
        "husk",
        "stray",
        "slime",
        "phantom",
        "pillager",
    }
