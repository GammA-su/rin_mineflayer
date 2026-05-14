import json
import os
import time
from typing import Any

import httpx

from vtuber_ai.agent_state import summarize_status
from vtuber_ai.schemas import BrainDecision

AUTONOMOUS_ALLOWED_ACTIONS = (
    "status",
    "say",
    "look_around",
    "explore_nearby",
    "acquire_blocks",
    "navigate_to_block_type",
    "collect_wood",
    "craft_planks",
    "craft_sticks",
    "craft_crafting_table",
    "place_crafting_table",
    "craft_wooden_pickaxe",
    "mine_stone",
    "craft_stone_pickaxe",
    "stop",
    "jump",
    "flee",
    "eat_food",
)

NO_ARG_ACTIONS = frozenset(
    {
        "status",
        "look_around",
        "craft_crafting_table",
        "place_crafting_table",
        "craft_wooden_pickaxe",
        "craft_stone_pickaxe",
        "stop",
        "jump",
        "flee",
        "eat_food",
    }
)

ACTION_ALLOWED_ARGS = {
    "say": frozenset({"message"}),
    "set_vtuber_mood": frozenset({"mood"}),
    "acquire_blocks": frozenset({"targets", "count", "radius", "allowExcavate", "accessMode"}),
    "navigate_to_block_type": frozenset({"targets", "radius"}),
    "collect_wood": frozenset({"count"}),
    "mine_stone": frozenset({"count"}),
    "explore_nearby": frozenset({"radius"}),
    "craft_planks": frozenset({"count"}),
    "craft_sticks": frozenset({"count"}),
}

ACTION_SPECS: dict[str, dict[str, Any]] = {
    "status": {"args": {}, "description": "Get the current bot status and observations."},
    "say": {"args": {"message": "1-240 chars, not a slash command"}, "description": "Send a short safe chat message."},
    "look_around": {"args": {}, "description": "Refresh nearby observations without moving far."},
    "explore_nearby": {"args": {"radius": "8-64"}, "description": "Cautiously scout nearby terrain."},
    "acquire_blocks": {
        "args": {
            "targets": "allowed block names",
            "count": "1-32 optional",
            "radius": "8-96 optional",
            "allowExcavate": "boolean optional",
            "accessMode": "surface_first|safe_staircase optional",
        },
        "description": "Acquire safe allowlisted blocks using surface search or limited safe staircase access.",
    },
    "navigate_to_block_type": {
        "args": {"targets": "allowed block names", "radius": "8-96 optional"},
        "description": "Move near an accessible target block type if direct acquisition fails.",
    },
    "collect_wood": {"args": {"count": "1-16"}, "description": "Collect nearby logs or stems."},
    "craft_planks": {"args": {"count": "1-64 optional"}, "description": "Craft planks from logs if materials are available."},
    "craft_sticks": {"args": {"count": "1-64 optional"}, "description": "Craft sticks from planks if materials are available."},
    "craft_crafting_table": {"args": {}, "description": "Craft one crafting table if planks are available."},
    "place_crafting_table": {
        "args": {},
        "description": "Place a crafting table from inventory nearby. Use this if you have a crafting_table item but no nearby crafting_table.",
    },
    "craft_wooden_pickaxe": {
        "args": {},
        "description": "Craft a wooden pickaxe using planks and sticks. Requires nearby crafting_table. Do not use if wooden_pickaxe already exists.",
    },
    "mine_stone": {"args": {"count": "1-16"}, "description": "Mine stone to obtain cobblestone. Requires a pickaxe."},
    "craft_stone_pickaxe": {
        "args": {},
        "description": "Craft a stone pickaxe using cobblestone and sticks. Requires nearby crafting_table. Use if cobblestone>=3, sticks>=2, and no stone_pickaxe.",
    },
    "stop": {"args": {}, "description": "Stop movement and clear controls."},
    "jump": {"args": {}, "description": "Perform one short jump."},
    "flee": {"args": {}, "description": "Move away from immediate danger if possible."},
    "eat_food": {"args": {}, "description": "Eat available food if hunger recovery is needed."},
}

BRAIN_SYSTEM_PROMPT = """You are the gameplay brain of an AI VTuber playing Minecraft.
Your mission is to beat Minecraft by playing naturally and surviving.
You receive current game state, inventory, nearby blocks/entities, available actions, and previous action result.
Current state and current_facts are authoritative. Memory may be stale. If memory conflicts with current inventory or nearby blocks, trust current_facts.
Before choosing an action, check whether the needed item already exists in current_facts. Do not craft duplicate tools if you already have them.
If you need to craft at a table and nearby crafting_table is null but inventory has crafting_table, choose place_crafting_table first.
Choose the best next action from the actual state.
Do not follow a fixed checklist.
If the last action failed because something was missing, choose an action that obtains or prepares the missing prerequisite.
If you lack materials for an item, choose a prerequisite action.
If an action is already satisfied, do not repeat it.
If uncertain, choose status or look_around.
If in danger, prioritize survival.
Return one compact JSON object only.
No markdown. No code. No comments.
Output format: {"objective":"short objective","action":"available_action_name","args":{},"speech":"short stream line","mood":"neutral|focused|happy|surprised|scared|confused","reason":"brief reason"}
Use the available_actions schemas exactly. For no-argument actions, args must be {}."""

ALLOWED_MOODS = frozenset({"neutral", "focused", "happy", "surprised", "scared", "confused"})


def choose_next_action(
    state: dict[str, Any],
    memory: list[dict[str, Any]],
    mission: str,
    allowed_actions: list[str] | tuple[str, ...],
    planner: str = "hybrid",
) -> tuple[BrainDecision, dict[str, Any]]:
    """Choose one high-level skill for the next autonomous tick."""

    allowed = tuple(action for action in allowed_actions if action in AUTONOMOUS_ALLOWED_ACTIONS)
    mode = (planner or "hybrid").strip().lower()

    if mode not in {"llm", "hybrid", "fallback"}:
        mode = "hybrid"

    if mode == "hybrid":
        reflex = _emergency_reflex(state, allowed)
        if reflex is not None:
            return reflex, {
                "planner": "hybrid",
                "source": "emergency_reflex",
                "fallback_used": False,
                "llm_latency_sec": 0.0,
                "prompt_size_chars": 0,
                "args_sanitized": False,
                "removed_arg_keys": [],
            }

    if mode in {"llm", "hybrid"}:
        llm_decision, llm_info = _llm_decision(state, memory, mission, allowed)
        if llm_decision is not None:
            llm_decision, sanitize_info = sanitize_decision_args(llm_decision)
            llm_info.update(sanitize_info)
            llm_info["planner"] = mode
            llm_info["source"] = "llm"
            llm_info["fallback_used"] = False
            return llm_decision, llm_info

        fallback = _fallback_decision(allowed, reason=llm_info.get("fallback_reason"))
        llm_info["planner"] = mode
        llm_info["source"] = "fallback"
        llm_info["fallback_used"] = True
        llm_info.setdefault("args_sanitized", False)
        llm_info.setdefault("removed_arg_keys", [])
        return fallback, llm_info

    return _fallback_decision(allowed, reason="Fallback planner selected."), {
        "planner": "fallback",
        "source": "fallback",
        "fallback_used": False,
        "llm_latency_sec": 0.0,
        "prompt_size_chars": 0,
        "args_sanitized": False,
        "removed_arg_keys": [],
    }


def build_llm_state_packet(
    status: dict[str, Any],
    recent_memory: list[dict[str, Any]],
    last_result: dict[str, Any] | None,
    bridge_actions: list[str] | tuple[str, ...],
    mission: str = "Beat Minecraft while playing naturally and surviving.",
) -> dict[str, Any]:
    """Build the compact game-state packet sent to the LLM planner."""

    summary = _summary_from_status_or_state(status)
    raw_status = status.get("bot_status") if isinstance(status.get("bot_status"), dict) else status
    time_info = summary.get("time") if isinstance(summary.get("time"), dict) else raw_status.get("time", summary.get("time"))
    current_facts = _current_facts(summary)
    filtered_memory, memory_stats = _filtered_memory(recent_memory, current_facts, limit=2)
    last_relevant_failure = _last_relevant_failure(last_result, current_facts)

    return {
        "mission": mission,
        "planner_instruction": "Current state and current_facts are authoritative. Memory may be stale. If memory conflicts with current inventory or nearby blocks, trust current_facts.",
        "health": summary.get("health"),
        "food": summary.get("food"),
        "dimension": summary.get("dimension"),
        "time": _compact_time(time_info),
        "isDay": _is_day(time_info),
        "position": summary.get("position"),
        "inventory_counts": summary.get("inventory_counts") or {},
        "current_facts": current_facts,
        "nearbyBlockCounts": _top_counts(summary.get("nearby_block_counts"), limit=20),
        "nearbyBlocks": _special_nearby_blocks(summary.get("nearby_blocks")),
        "nearbyEntities": _compact_entities(summary.get("nearby_entities"), limit=10),
        "memory": filtered_memory,
        "memory_filter": memory_stats,
        "last_relevant_failure": last_relevant_failure,
        "last_action_result": _compact_last_action_result(last_result),
        "available_actions": _available_action_specs(bridge_actions),
    }


def _emergency_reflex(state: dict[str, Any], allowed: tuple[str, ...]) -> BrainDecision | None:
    summary = _summary(state)
    movement = summary.get("movement") if isinstance(summary.get("movement"), dict) else {}
    health = summary.get("health")

    if isinstance(health, (int, float)) and health <= 6 and summary.get("hostile_nearby") and "flee" in allowed:
        return BrainDecision(
            objective="Survive immediate danger",
            action="flee",
            args={},
            speech="Too risky. I'm backing off.",
            mood="scared",
            reason="Health is dangerously low and a hostile entity is nearby.",
        )

    if movement.get("inLava") and "flee" in allowed:
        return BrainDecision(
            objective="Escape lava",
            action="flee",
            args={},
            speech="Lava. Moving now.",
            mood="scared",
            reason="The bot is in lava.",
        )

    air = summary.get("air")
    if movement.get("inWater") and isinstance(air, (int, float)) and air <= 80:
        if "flee" in allowed:
            return BrainDecision(
                objective="Get air",
                action="flee",
                args={},
                speech="I need air.",
                mood="scared",
                reason="The bot is underwater and air is low.",
            )
        if "status" in allowed:
            return BrainDecision(
                objective="Check drowning risk",
                action="status",
                args={},
                speech="I need to check my air.",
                mood="confused",
                reason="The bot is underwater and air is low.",
            )

    if not summary.get("ok") and "status" in allowed:
        return BrainDecision(
            objective="Recover observation",
            action="status",
            args={},
            speech="I need to check what is going on.",
            mood="confused",
            reason="Current status is unavailable or not ok.",
        )

    return None


def _llm_decision(
    state: dict[str, Any],
    memory: list[dict[str, Any]],
    mission: str,
    allowed: tuple[str, ...],
) -> tuple[BrainDecision | None, dict[str, Any]]:
    compact_context = build_llm_state_packet(
        status=state,
        recent_memory=memory,
        last_result=_last_action_result_from_state(state),
        bridge_actions=allowed,
        mission=mission,
    )
    user_content = json.dumps(compact_context, separators=(",", ":"))
    prompt_size_chars = len(BRAIN_SYSTEM_PROMPT) + len(user_content)
    diagnostics = {
        "llm_latency_sec": 0.0,
        "prompt_size_chars": prompt_size_chars,
        "llm_state_packet_preview": user_content[:1200],
        "last_failure_included": _last_failure_included(compact_context.get("last_action_result")),
        "last_relevant_failure_included": compact_context.get("last_relevant_failure") is not None,
        "memory_filtered_count": (compact_context.get("memory_filter") or {}).get("memory_filtered_count", 0),
        "stale_memory_removed_count": (compact_context.get("memory_filter") or {}).get("stale_memory_removed_count", 0),
        "available_actions_count": len(compact_context.get("available_actions") or {}),
    }

    base_url = (os.getenv("VTUBER_LLM_BASE_URL") or "").rstrip("/")
    if not base_url:
        return None, {
            **diagnostics,
            "fallback_reason": "VTUBER_LLM_BASE_URL is not set.",
        }

    model = os.getenv("VTUBER_LLM_MODEL") or "local-model"
    max_tokens = _int_env("VTUBER_LLM_MAX_TOKENS", 96)
    timeout_sec = _float_env("VTUBER_LLM_TIMEOUT_SEC", 120.0)
    api_key = os.getenv("VTUBER_LLM_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": BRAIN_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    started = time.perf_counter()
    raw_content: str | None = None
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_sec,
        )
        llm_latency_sec = round(time.perf_counter() - started, 3)
        response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(raw_content)
        decision = BrainDecision.model_validate(parsed)
        decision = _normalize_decision(decision)
    except Exception as exc:
        info: dict[str, Any] = {
            **diagnostics,
            "fallback_reason": f"LLM planner failed: {type(exc).__name__}.",
            "model": model,
            "llm_latency_sec": round(time.perf_counter() - started, 3),
        }
        if isinstance(exc, json.JSONDecodeError) and raw_content is not None:
            info["json_extraction_success"] = False
            info["raw_llm_text_len"] = len(raw_content)
            info["raw_llm_text_preview"] = raw_content[:1000]
            if os.getenv("VTUBER_DEBUG_LLM") == "1":
                print(f"[VTUBER_DEBUG_LLM] JSONDecodeError raw preview:\n{raw_content[:1000]}", flush=True)
        return None, info

    if decision.action not in allowed:
        return None, {
            **diagnostics,
            "fallback_reason": f"LLM chose disallowed action: {decision.action}.",
            "model": model,
            "llm_latency_sec": llm_latency_sec,
        }

    return decision, {
        **diagnostics,
        "model": model,
        "llm_latency_sec": llm_latency_sec,
    }


def _fallback_decision(allowed: tuple[str, ...], reason: str | None = None) -> BrainDecision:
    if "status" in allowed:
        return BrainDecision(
            objective="Check status safely",
            action="status",
            args={},
            speech="I'll check status.",
            mood="neutral",
            reason=reason or "Using neutral fallback because the LLM did not provide a usable action.",
        )

    action = allowed[0] if allowed else "status"
    return BrainDecision(
        objective="Stop safely",
        action=action,
        args={},
        speech="I'll pause and reassess.",
        mood="confused",
        reason=reason or "No status action was available.",
    )


def _normalize_decision(decision: BrainDecision) -> BrainDecision:
    mood = decision.mood if decision.mood in ALLOWED_MOODS else "neutral"
    args = dict(decision.args)

    if decision.action in {"collect_wood", "mine_stone"} and "count" in args:
        args["count"] = _clamp_int(args["count"], 1, 16)
    elif decision.action == "acquire_blocks":
        if "count" in args:
            args["count"] = _clamp_int(args["count"], 1, 32)
        if "radius" in args:
            args["radius"] = _clamp_int(args["radius"], 8, 96)
    elif decision.action == "navigate_to_block_type" and "radius" in args:
        args["radius"] = _clamp_int(args["radius"], 8, 96)
    elif decision.action == "explore_nearby" and "radius" in args:
        args["radius"] = _clamp_int(args["radius"], 8, 64)
    elif decision.action == "look_around" and "radius" in args:
        args["radius"] = _clamp_int(args["radius"], 8, 32)
    elif decision.action in {"craft_planks", "craft_sticks", "craft_crafting_table"} and "count" in args:
        args["count"] = _clamp_int(args["count"], 1, 64)

    return BrainDecision(
        objective=decision.objective.strip() or "Act safely",
        action=decision.action,
        args=args,
        speech=decision.speech[:160],
        mood=mood,
        reason=decision.reason.strip() or "Model selected this safe skill.",
    )


def sanitize_decision_args(decision: BrainDecision) -> tuple[BrainDecision, dict[str, Any]]:
    if decision.action not in AUTONOMOUS_ALLOWED_ACTIONS and decision.action not in ACTION_ALLOWED_ARGS:
        return decision, {
            "args_sanitized": False,
            "removed_arg_keys": [],
        }

    original_args = dict(decision.args)

    if decision.action in NO_ARG_ACTIONS:
        if original_args:
            return _decision_with_args(decision, {}), {
                "args_sanitized": True,
                "args_sanitization_reason": "no-arg action",
                "removed_arg_keys": sorted(original_args),
            }

        return decision, {
            "args_sanitized": False,
            "removed_arg_keys": [],
        }

    allowed_keys = ACTION_ALLOWED_ARGS.get(decision.action)
    if allowed_keys is None:
        return decision, {
            "args_sanitized": False,
            "removed_arg_keys": [],
        }

    sanitized_args = {key: value for key, value in original_args.items() if key in allowed_keys}
    removed_keys = sorted(set(original_args) - allowed_keys)

    return _decision_with_args(decision, sanitized_args), {
        "args_sanitized": bool(removed_keys),
        "removed_arg_keys": removed_keys,
    }


def _decision_with_args(decision: BrainDecision, args: dict[str, Any]) -> BrainDecision:
    return BrainDecision(
        objective=decision.objective,
        action=decision.action,
        args=args,
        speech=decision.speech,
        mood=decision.mood,
        reason=decision.reason,
    )


def _summary_from_status_or_state(status: dict[str, Any]) -> dict[str, Any]:
    summary = status.get("summary")
    if isinstance(summary, dict):
        return summary

    bot_status = status.get("bot_status")
    if isinstance(bot_status, dict):
        return summarize_status(bot_status)

    return summarize_status(status)


def _summary(state: dict[str, Any]) -> dict[str, Any]:
    summary = state.get("summary")
    return summary if isinstance(summary, dict) else {}


def _compact_time(time_info: Any) -> Any:
    if isinstance(time_info, dict):
        return {
            key: time_info.get(key)
            for key in ("timeOfDay", "day", "isDay")
            if key in time_info
        }
    return time_info


def _is_day(time_info: Any) -> bool | None:
    if isinstance(time_info, dict):
        value = time_info.get("isDay")
        return value if isinstance(value, bool) else None
    return None


def _available_action_specs(actions: list[str] | tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        action: ACTION_SPECS[action]
        for action in actions
        if action in AUTONOMOUS_ALLOWED_ACTIONS and action in ACTION_SPECS
    }


def _special_nearby_blocks(nearby_blocks: Any) -> dict[str, Any]:
    if not isinstance(nearby_blocks, dict):
        return {}

    special_names = ("crafting_table",)
    return {name: nearby_blocks[name] for name in special_names if name in nearby_blocks}


def _current_facts(summary: dict[str, Any]) -> dict[str, Any]:
    counts = summary.get("inventory_counts") if isinstance(summary.get("inventory_counts"), dict) else {}
    nearby_blocks = summary.get("nearby_blocks") if isinstance(summary.get("nearby_blocks"), dict) else {}
    cobblestone_count = _count_item(counts, "cobblestone")
    sticks_count = _count_item(counts, "stick")
    planks_count = _count_suffix(counts, "_planks")
    has_nearby_crafting_table = isinstance(nearby_blocks.get("crafting_table"), dict)

    return {
        "has_wooden_pickaxe": _count_item(counts, "wooden_pickaxe") > 0,
        "has_stone_pickaxe": _count_item(counts, "stone_pickaxe") > 0,
        "has_cobblestone": cobblestone_count > 0,
        "cobblestone_count": cobblestone_count,
        "has_inventory_crafting_table": _count_item(counts, "crafting_table") > 0,
        "has_nearby_crafting_table": has_nearby_crafting_table,
        "can_attempt_stone_pickaxe_materials": cobblestone_count >= 3 and sticks_count >= 2 and has_nearby_crafting_table,
        "planks_count": planks_count,
        "sticks_count": sticks_count,
    }


def _compact_last_action_result(last_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(last_result, dict):
        return None

    verifier = last_result.get("verifier") if isinstance(last_result.get("verifier"), dict) else {}
    compact = {
        "action": last_result.get("action"),
        "ok": last_result.get("ok"),
        "error": _short(last_result.get("error")),
        "verifier": {
            "failure_type": verifier.get("failure_type"),
            "recommendation": _short(verifier.get("recommendation")),
        },
    }
    flags = _result_flags(last_result.get("result"))
    if flags:
        compact["result_flags"] = flags
        compact.update(flags)
    return compact


def _last_action_result_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    last_tick = None
    recent_ticks = state.get("recent_ticks")
    if isinstance(recent_ticks, list) and recent_ticks:
        last_tick = recent_ticks[0] if isinstance(recent_ticks[0], dict) else None

    result = state.get("last_result") if isinstance(state.get("last_result"), dict) else {}
    verifier = state.get("last_verifier") if isinstance(state.get("last_verifier"), dict) else {}
    action = state.get("last_action") or (last_tick or {}).get("action")

    if not action and not result and not verifier:
        return None

    ok = (last_tick or {}).get("ok")
    if isinstance(ok, int):
        ok = bool(ok)

    return {
        "action": action,
        "ok": ok,
        "error": (last_tick or {}).get("error") or result.get("error"),
        "result": result,
        "verifier": verifier,
    }


def _result_flags(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    flag_names = (
        "alreadyPresent",
        "placed",
        "collected",
        "crafted",
        "eaten",
        "moved",
        "partial_success",
        "can_retry",
        "suggested_next_action",
        "stop_reason",
        "inventory",
    )
    flags = {name: result.get(name) for name in flag_names if name in result and name != "inventory"}

    if "inventory" in result and isinstance(result["inventory"], list):
        flags["inventoryReturned"] = True

    return flags


def _last_failure_included(last_action_result: Any) -> bool:
    if not isinstance(last_action_result, dict):
        return False

    verifier = last_action_result.get("verifier")
    failure_type = verifier.get("failure_type") if isinstance(verifier, dict) else None
    return bool(
        last_action_result.get("ok") is False
        or last_action_result.get("error")
        or (failure_type and failure_type != "none")
    )


def _last_relevant_failure(last_result: dict[str, Any] | None, current_facts: dict[str, Any]) -> dict[str, Any] | None:
    compact = _compact_last_action_result(last_result)
    if not _last_failure_included(compact):
        return None

    if _is_stale_failure(compact, current_facts):
        return None

    return compact


def _compact_memory(memory: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [_compact_memory_event(event) for event in memory[:limit]]


def _filtered_memory(
    memory: list[dict[str, Any]],
    current_facts: dict[str, Any],
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    filtered = []
    stale_removed = 0

    for event in memory:
        compact = _compact_memory_event(event)
        if _is_stale_failure(compact, current_facts):
            stale_removed += 1
            continue

        compact["historical"] = True
        filtered.append(compact)
        if len(filtered) >= limit:
            break

    return filtered, {
        "memory_filtered_count": len(filtered),
        "stale_memory_removed_count": stale_removed,
    }


def _compact_memory_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id"),
        "ts": event.get("ts"),
        "historical": True,
        "message": _short(event.get("message")),
        "action": event.get("action"),
        "ok": event.get("ok"),
        "error": _short(event.get("error")),
        "reason": _short(event.get("reason")),
    }


def _is_stale_failure(item: dict[str, Any] | None, current_facts: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False

    text = " ".join(
        str(value).lower()
        for value in (
            item.get("message"),
            item.get("error"),
            item.get("reason"),
            (item.get("verifier") or {}).get("recommendation") if isinstance(item.get("verifier"), dict) else None,
        )
        if value is not None
    )

    action = str(item.get("action") or "").lower()

    if current_facts.get("has_wooden_pickaxe") and (
        "wooden_pickaxe" in text
        or "wooden pickaxe" in text
        or "need a pickaxe" in text
        or "missing pickaxe" in text
    ):
        return True

    if current_facts.get("cobblestone_count", 0) >= 3 and (
        "cobblestone" in text
        or "missing stone" in text
        or "need stone" in text
        or action == "mine_stone"
    ):
        return True

    if current_facts.get("has_nearby_crafting_table") and (
        "no crafting table" in text
        or "missing crafting table" in text
        or "crafting table found" in text
        or action == "place_crafting_table"
    ):
        return True

    return False


def _compact_entities(entities: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(entities, list):
        return []

    compacted = []
    for entity in entities[:limit]:
        if not isinstance(entity, dict):
            continue
        compacted.append(
            {
                "name": entity.get("name"),
                "type": entity.get("type"),
                "hostile": entity.get("hostile"),
                "distance": entity.get("distance"),
            }
        )
    return compacted


def _top_counts(counts: Any, limit: int) -> dict[str, int]:
    if not isinstance(counts, dict):
        return {}

    items = sorted(
        ((name, count) for name, count in counts.items() if isinstance(name, str) and isinstance(count, int)),
        key=lambda item: item[1],
        reverse=True,
    )
    return dict(items[:limit])


def _count_item(counts: dict[str, Any], name: str) -> int:
    value = counts.get(name, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _count_suffix(counts: dict[str, Any], suffix: str) -> int:
    return sum(
        count
        for name, count in counts.items()
        if isinstance(name, str) and name.endswith(suffix) and isinstance(count, int) and not isinstance(count, bool)
    )


def _clamp_int(value: Any, low: int, high: int) -> int:
    if isinstance(value, bool):
        return low
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _short(value: Any, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."
