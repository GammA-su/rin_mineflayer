import json
import os
import time
from typing import Any

import httpx

from vtuber_ai.action_catalog import (
    CATALOG,
    get_compact_action_list,
    get_detailed_action_docs,
    get_llm_action_specs_for_prompt,
    llm_exposed_count,
)
from vtuber_ai.agent_state import summarize_status
from vtuber_ai.milestones import build_milestone_state
from vtuber_ai.world_memory import get_death_state as _wm_death_state
from vtuber_ai.world_memory import get_relevant_known_places as _wm_relevant_known_places
from vtuber_ai.world_memory import list_waypoints as _wm_list_waypoints
from vtuber_ai.schemas import BrainDecision

# Actions the brain may choose. Must all be implemented/partial in Node and catalog.
# Derived from catalog: only implemented/partial + exposes_to_llm, restricted to
# the subset the autonomous brain currently knows how to handle.
AUTONOMOUS_ALLOWED_ACTIONS = tuple(
    name for name in (
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
        "craft_item",
        "craft_furnace",
        "craft_torches",
        "craft_chest",
        "craft_shield",
        "craft_bucket",
        "craft_iron_pickaxe",
        "craft_iron_sword",
        "craft_iron_armor",
        "craft_wooden_pickaxe",
        "mine_stone",
        "mine_coal",
        "mine_iron_ore",
        "craft_stone_pickaxe",
        "place_furnace",
        "smelt_item",
        "smelt_iron",
        "stop",
        "jump",
        "flee",
        "eat_food",
    )
    if name in CATALOG and CATALOG[name].exposes_to_llm
)

# Actions promoted to implemented since v1 - appended here to keep diff readable.
AUTONOMOUS_ALLOWED_ACTIONS = AUTONOMOUS_ALLOWED_ACTIONS + tuple(
    name for name in (
        "craft_blaze_powder",
        "craft_diamond_pickaxe",
        "craft_diamond_sword",
        "craft_diamond_armor",
        "craft_bed",
        "craft_flint_and_steel",
        "craft_eyes_of_ender",
        "place_chest",
        "place_torch",
        "place_block",
        "place_water",
        "place_lava",
        "place_bed",
        "place_boat",
        "check_inventory",
        "check_time_of_day",
        "check_light_level",
        "check_biome",
        "scan_for_hostiles",
        "scan_for_passive_mobs",
        "scan_for_chests",
        "scan_for_specific_block",
        "scan_for_liquids",
        "scan_for_structures",
        "scan_workspace",
        "drop_item",
        "equip_armor",
        "equip_tool",
        "select_hotbar_slot",
        "open_chest",
        "loot_chest",
        "deposit_items",
        "withdraw_items",
        "equip_best_armor",
        "equip_best_tool",
        "equip_best_weapon",
        "equip_gold_armor",
        "mark_waypoint",
        "list_waypoints",
        "return_to_waypoint",
        "recover_death_items",
        "abandon_death_recovery",
        "return_to_spawn_or_home",
        "recover_position",
        "find_safe_workspace",
        "setup_workspace",
        "return_to_workspace",
        "return_to_known_position",
        "set_home_position",
        "dig_staircase",
        "return_to_surface",
        "pillar_up",
        "bridge_gap",
        "place_block_in_direction",
        "mlg_water_bucket",
        "enter_boat",
        "exit_boat",
        "set_sneak",
        "set_sprint",
        "attack_mob",
        "attack_nearest_hostile",
        "retreat_from_combat",
        "block_with_shield",
        "shoot_bow",
        "charge_bow",
        "deflect_ghast_fireball",
        "kite_mob",
        "throw_ender_pearl",
        "kill_passive_mob",
        "kill_blaze",
        "kill_enderman",
        "sleep_if_possible",
        "set_spawn_with_bed",
        "use_bed_bomb",
        "avoid_bed_explosion",
        "find_lava_pool",
        "collect_water",
        "collect_lava",
        "collect_obsidian",
        "build_nether_portal",
        "cast_nether_portal",
        "light_nether_portal",
        "enter_nether",
        "return_to_portal",
        "barter_with_piglins",
        "avoid_opening_chests_near_piglins",
        "find_nether_fortress",
        "navigate_nether_safely",
        "collect_blaze_rods",
        "retreat_from_nether_danger",
        "leave_nether",
        "throw_eye_of_ender",
        "locate_stronghold_step",
        "dig_staircase_to_stronghold",
        "scan_for_end_portal_room",
        "activate_end_portal",
        "enter_end",
        "end_safe_landing",
        "equip_pumpkin_head",
        "look_down_around_endermen",
        "scan_end_crystals",
        "destroy_end_crystal",
        "destroy_caged_end_crystal",
        "destroy_nearby_end_crystals",
        "attack_perched_dragon",
        "attack_dragon_with_bow",
        "dragon_phase_crystals",
        "dragon_phase_circle",
        "dragon_phase_perch",
        "fight_dragon_phase",
        "return_to_overworld_via_end_portal",
        "describe_actions",
    )
    if name in CATALOG and CATALOG[name].exposes_to_llm
)

NO_ARG_ACTIONS = frozenset(
    name for name, spec in CATALOG.items()
    if not spec.args_schema
)

# Keep runtime LLM arg sanitization in lockstep with action_catalog.py.  This
# prevents restored/stale hand-written schemas from stripping valid args such
# as scan_for_specific_block.targets, equip_armor.mode, or set_sneak.enabled.
ACTION_ALLOWED_ARGS: dict[str, frozenset[str]] = {
    name: frozenset(spec.args_schema.keys())
    for name, spec in CATALOG.items()
    if spec.args_schema
}

# Maps semantically obvious LLM hallucinations to canonical action names.
# Applied BEFORE policy validation in _llm_decision. Policy stays strict.
ACTION_ALIASES: dict[str, str] = {
    # obsidian collection
    "mine_obsidian": "collect_obsidian",
    "collect_obsidian_blocks": "collect_obsidian",
    "gather_obsidian": "collect_obsidian",
    # furnace
    "make_furnace": "craft_furnace",
    "build_furnace": "craft_furnace",
    "create_furnace": "craft_furnace",
    # crafting table
    "make_crafting_table": "craft_crafting_table",
    "build_crafting_table": "craft_crafting_table",
    "create_crafting_table": "craft_crafting_table",
    # wood / logs
    "collect_logs": "collect_wood",
    "gather_wood": "collect_wood",
    "chop_wood": "collect_wood",
    "chop_tree": "collect_wood",
    # iron mining
    "mine_iron": "mine_iron_ore",
    "collect_iron": "mine_iron_ore",
    "gather_iron": "mine_iron_ore",
    # smelting
    "smelt_ore": "smelt_iron",
    "smelt_iron_ore": "smelt_iron",
    # navigation
    "walk_to": "navigate_to_block_type",
    "go_to": "navigate_to_block_type",
    # coal
    "mine_coal_ore": "mine_coal",
    "collect_coal": "mine_coal",
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
If previous result has suggested_next_action, choose it unless current_facts show it is obsolete.
If the last failure is no_safe_workspace or area_cramped, choose setup_workspace, find_safe_workspace, or return_to_surface before retrying placement.
If the last failure has stop_reason no_crafting_table_nearby: if current_facts.known_workspace_has_crafting_table is true, choose return_to_workspace; otherwise choose setup_workspace, or place_crafting_table if has_inventory_crafting_table is true.
If the last failure has stop_reason no_furnace_nearby: if current_facts.known_workspace_has_furnace is true, choose return_to_workspace; otherwise choose setup_workspace, or place_furnace if inventory has furnace.
If you need a crafting table or furnace and known_places.nearest_workspace has one within a reasonable distance, choose return_to_workspace instead of placing a new station.
Do not place new stations when a good workspace already exists nearby - return_to_workspace first.
Use return_to_known_position to navigate to a persistent home or workspace by label (or omit label for nearest).
If you lack materials for an item, choose a prerequisite action.
If an action is already satisfied, do not repeat it.
If uncertain or a previous action failed because environment information was missing, choose a sensing action (check_time_of_day, check_light_level, check_biome, scan_for_hostiles, scan_for_specific_block, etc.) to gather information before acting.
If in The End during the dragon fight, prefer bounded phase actions: end_safe_landing first after entering, then fight_dragon_phase, and return_to_overworld_via_end_portal only after the dragon is gone.
If recently died, decide whether to recover items or restart progression. Prefer recover_death_items only when the death location is recent and not repeatedly lethal; after two recovery failures, choose abandon_death_recovery or return_to_spawn_or_home.
Milestones are awareness, not a deterministic checklist. Use them to understand progress and prerequisites, but choose actions from the actual current state.
If in danger, prioritize survival.
You may choose any action from full_action_list. detailed_action_docs provides arg schemas and descriptions for the most relevant actions. For actions not in detailed_action_docs, use {} for no-argument actions or the arg names shown in the compact signature. Use describe_actions({actions:[...]}) if you need the full schema for an unlisted action. Use canonical action names from full_action_list. Common aliases (e.g. mine_obsidian→collect_obsidian) may be corrected automatically, but do not invent action names.
Return one compact JSON object only.
No markdown. No code. No comments.
Output format: {"objective":"short objective","action":"action_name_from_full_action_list","args":{},"speech":"short stream line","mood":"neutral|focused|happy|surprised|scared|confused","reason":"brief reason"}
For no-argument actions, args must be {}. Follow detailed_action_docs schemas exactly for documented actions."""

COMPACT_BRAIN_SYSTEM_PROMPT = """You are the gameplay action selector for a Minecraft AI VTuber.
Choose exactly one Minecraft action from full_action_list.
Return compact JSON only. No markdown. No explanation. No speech. No mood. No objective.
Format: {"a":"action_name","args":{}}
Optional why field (8 words max): {"a":"action_name","args":{},"why":"brief reason"}
Keep args minimal. If unsure, choose status.

Trust current_facts over memory. If memory conflicts with current_facts, trust current_facts.
Before crafting: check if item already exists in current_facts. Do not craft duplicates.
If crafting_table needed but not nearby: if inventory has it, choose place_crafting_table; if current_facts.known_workspace_has_crafting_table, choose return_to_workspace; else setup_workspace.
If furnace needed but not nearby: same pattern with known_workspace_has_furnace.
If last failure is no_safe_workspace or area_cramped: choose setup_workspace, find_safe_workspace, or return_to_surface.
If previous result has suggested_next_action, prefer it unless current_facts show it obsolete.
If health is low and hostiles nearby: choose flee.
If in lava: choose flee.
If uncertain or environment info missing: choose a sensing action (check_time_of_day, check_light_level, check_biome, scan_for_hostiles, scan_for_specific_block).
If recently died: prefer recover_death_items; after two failures choose abandon_death_recovery.
Milestones are awareness only. Choose actions from current state, not a fixed checklist.
Use canonical action names from full_action_list. Common aliases (e.g. mine_obsidian→collect_obsidian) corrected automatically.
Use describe_actions({"actions":[...]}) to get full schema for any unlisted action."""

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
    death_state = _wm_death_state()
    waypoints = _wm_list_waypoints()
    known_places = _wm_relevant_known_places(raw_status)
    current_facts = _current_facts(summary, nearest_workspace=known_places.get("nearest_workspace") if isinstance(known_places, dict) else None)
    filtered_memory, memory_stats = _filtered_memory(recent_memory, current_facts, limit=2)
    last_relevant_failure = _last_relevant_failure(last_result, current_facts)
    milestone_state = build_milestone_state(
        status=raw_status,
        recent_memory=recent_memory,
        recent_ticks=[],
        waypoints=waypoints,
        death_state=death_state,
    )
    recent_death = _compact_death(death_state.get("last_death")) if death_state.get("recent") else None

    max_compact_chars = _int_env("VTUBER_MAX_COMPACT_ACTION_CHARS", 4000)
    max_detailed = _int_env("VTUBER_MAX_DETAILED_ACTION_DOCS", 12)
    bridge_set = set(bridge_actions)
    compact_action_set = bridge_set & set(AUTONOMOUS_ALLOWED_ACTIONS)
    full_action_list = get_compact_action_list(compact_action_set, max_chars=max_compact_chars)
    relevant_names = _select_relevant_actions(
        last_result=last_result,
        current_facts=current_facts,
        dimension=summary.get("dimension"),
        bridge_actions=bridge_actions,
        max_count=max_detailed,
    )
    detailed_action_docs = get_detailed_action_docs(relevant_names)

    return {
        "mission": mission,
        "planner_instruction": "Current state and current_facts are authoritative. Memory may be stale. If memory conflicts with current inventory or nearby blocks, trust current_facts.",
        "last_failure_summary": _compact_failure_summary(last_result),
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
        "full_action_list": full_action_list,
        "detailed_action_docs": detailed_action_docs,
        "known_waypoints": _compact_waypoints(waypoints),
        "known_places": known_places,
        "last_death": recent_death,
        "death_state": _compact_death_state(death_state),
        "milestones": _compact_milestone_state(milestone_state),
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
    output_mode = os.getenv("VTUBER_PLANNER_OUTPUT_MODE", "compact").strip().lower()
    if output_mode not in {"compact", "full"}:
        output_mode = "compact"
    system_prompt = COMPACT_BRAIN_SYSTEM_PROMPT if output_mode == "compact" else BRAIN_SYSTEM_PROMPT

    compact_context = build_llm_state_packet(
        status=state,
        recent_memory=memory,
        last_result=_last_action_result_from_state(state),
        bridge_actions=allowed,
        mission=mission,
    )
    user_content = json.dumps(compact_context, separators=(",", ":"))
    prompt_size_chars = len(system_prompt) + len(user_content)
    max_prompt_chars = _int_env("VTUBER_MAX_PROMPT_CHARS", 9000)
    _full_action_list = compact_context.get("full_action_list") or ""
    _detailed_docs = compact_context.get("detailed_action_docs") or {}
    _compact_action_set = set(allowed) & set(AUTONOMOUS_ALLOWED_ACTIONS)
    diagnostics = {
        "llm_latency_sec": 0.0,
        "prompt_size_chars": prompt_size_chars,
        "prompt_budget_exceeded": prompt_size_chars > max_prompt_chars,
        "planner_output_mode": output_mode,
        "llm_state_packet_preview": user_content[:1200],
        "last_failure_included": _last_failure_included(compact_context.get("last_action_result")),
        "last_relevant_failure_included": compact_context.get("last_relevant_failure") is not None,
        "memory_filtered_count": (compact_context.get("memory_filter") or {}).get("memory_filtered_count", 0),
        "stale_memory_removed_count": (compact_context.get("memory_filter") or {}).get("stale_memory_removed_count", 0),
        "full_catalog_count": llm_exposed_count(),
        "compact_action_count": len(_compact_action_set),
        "compact_action_chars": len(_full_action_list),
        "detailed_action_docs_count": len(_detailed_docs),
        "detailed_action_names": list(_detailed_docs.keys()),
        "available_actions_count": len(_compact_action_set),
        "raw_llm_output_chars": 0,
        "parsed_compact_output": False,
        "completion_tokens": None,
    }

    base_url = (os.getenv("VTUBER_LLM_BASE_URL") or "").rstrip("/")
    if not base_url:
        return None, {
            **diagnostics,
            "fallback_reason": "VTUBER_LLM_BASE_URL is not set.",
        }

    model = os.getenv("VTUBER_LLM_MODEL") or "local-model"
    default_max_tokens = 48 if output_mode == "compact" else 96
    max_tokens = _int_env("VTUBER_LLM_MAX_TOKENS", default_max_tokens)
    timeout_sec = _float_env("VTUBER_LLM_TIMEOUT_SEC", 120.0)
    api_key = os.getenv("VTUBER_LLM_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    alias_info: dict[str, Any] = {}
    parsed_compact_output = False
    completion_tokens: int | None = None
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
        resp_json = response.json()
        completion_tokens = (resp_json.get("usage") or {}).get("completion_tokens")
        raw_content = resp_json["choices"][0]["message"]["content"]
        parsed = json.loads(raw_content)
        decision, parsed_compact_output = _parse_llm_raw(parsed)
        canonical = ACTION_ALIASES.get(decision.action)
        if canonical is not None:
            alias_info = {
                "action_alias_applied": True,
                "original_action": decision.action,
                "canonical_action": canonical,
            }
            decision = BrainDecision(
                objective=decision.objective,
                action=canonical,
                args=decision.args,
                speech=decision.speech,
                mood=decision.mood,
                reason=decision.reason,
            )
        decision = _normalize_decision(decision)
    except Exception as exc:
        info: dict[str, Any] = {
            **diagnostics,
            **alias_info,
            "fallback_reason": f"LLM planner failed: {type(exc).__name__}.",
            "model": model,
            "llm_latency_sec": round(time.perf_counter() - started, 3),
            "raw_llm_output_chars": len(raw_content) if raw_content is not None else 0,
            "parsed_compact_output": parsed_compact_output,
            "completion_tokens": completion_tokens,
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
            **alias_info,
            "fallback_reason": f"LLM chose disallowed action: {decision.action}.",
            "model": model,
            "llm_latency_sec": llm_latency_sec,
            "raw_llm_output_chars": len(raw_content) if raw_content is not None else 0,
            "parsed_compact_output": parsed_compact_output,
            "completion_tokens": completion_tokens,
        }

    return decision, {
        **diagnostics,
        **alias_info,
        "model": model,
        "llm_latency_sec": llm_latency_sec,
        "raw_llm_output_chars": len(raw_content) if raw_content is not None else 0,
        "parsed_compact_output": parsed_compact_output,
        "completion_tokens": completion_tokens,
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


def _parse_llm_raw(parsed: dict[str, Any]) -> tuple[BrainDecision, bool]:
    """Parse LLM JSON dict to BrainDecision.

    Handles both compact {"a":...,"args":{},"why":...} and full {"action":...} schemas.
    Returns (decision, parsed_compact_output).
    """
    if "a" in parsed:
        action = str(parsed.get("a") or "status").strip()
        args = parsed.get("args")
        why = str(parsed.get("why") or "").strip()
        return BrainDecision(
            objective=action,
            action=action,
            args=args if isinstance(args, dict) else {},
            speech="",
            mood="focused",
            reason=why or "compact planner",
        ), True
    return BrainDecision.model_validate(parsed), False


def _normalize_decision(decision: BrainDecision) -> BrainDecision:
    mood = decision.mood if decision.mood in ALLOWED_MOODS else "neutral"
    args = dict(decision.args)

    if decision.action in {"collect_wood", "mine_stone", "mine_coal", "mine_iron_ore"} and "count" in args:
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
    elif decision.action in {"craft_planks", "craft_sticks", "craft_torches", "craft_eyes_of_ender"} and "count" in args:
        args["count"] = _clamp_int(args["count"], 1, 64)
    elif decision.action in {"smelt_item", "smelt_iron", "barter_with_piglins", "collect_blaze_rods"} and "count" in args:
        args["count"] = _clamp_int(args["count"], 1, 64)
    elif decision.action == "craft_item":
        if "count" in args:
            args["count"] = _clamp_int(args["count"], 1, 64)
    elif decision.action == "find_safe_workspace":
        if "radius" in args:
            args["radius"] = _clamp_int(args["radius"], 8, 64)
        if "purpose" in args and args["purpose"] not in {"crafting", "smelting", "storage", "general"}:
            args.pop("purpose")
    elif decision.action == "setup_workspace":
        if "radius" in args:
            args["radius"] = _clamp_int(args["radius"], 8, 64)
        for flag in ("need_crafting_table", "need_furnace", "need_chest"):
            if flag in args and not isinstance(args[flag], bool):
                args.pop(flag)
    elif decision.action == "return_to_workspace":
        if "purpose" in args and args["purpose"] not in {"crafting", "smelting", "storage", "general"}:
            args.pop("purpose")
    elif decision.action == "return_to_known_position":
        label = args.get("label")
        if label is not None and (not isinstance(label, str) or not label.strip()):
            args.pop("label")
    elif decision.action == "mark_waypoint":
        label = args.get("label")
        if label is not None and (not isinstance(label, str) or not label.strip()):
            args.pop("label")
    elif decision.action == "return_to_waypoint":
        label = args.get("label")
        if label is not None and (not isinstance(label, str) or not label.strip()):
            args.pop("label")
    elif decision.action == "dig_staircase":
        if "max_steps" in args:
            args["max_steps"] = _clamp_int(args["max_steps"], 1, 32)

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


def _select_relevant_actions(
    last_result: dict[str, Any] | None,
    current_facts: dict[str, Any],
    dimension: str | None,
    bridge_actions: list[str] | tuple[str, ...],
    max_count: int = 12,
) -> list[str]:
    """Select which actions receive full detailed docs in the prompt."""
    bridge_set = set(bridge_actions)
    priority: list[str] = []

    # Emergency actions always come first
    for a in ("status", "flee", "eat_food", "recover_position"):
        if a in bridge_set or a in AUTONOMOUS_ALLOWED_ACTIONS:
            priority.append(a)

    # Inject actions the LLM previously requested via describe_actions
    last_action = (last_result or {}).get("action") if isinstance(last_result, dict) else None
    if last_action == "describe_actions":
        prev_docs = (last_result or {}).get("result", {})
        if isinstance(prev_docs, dict):
            for name in (prev_docs.get("actions_docs") or {}).keys():
                priority.append(name)

    # Suggested next actions from last failure
    compact = _compact_last_action_result(last_result)
    if isinstance(compact, dict):
        for key in ("suggested_next_action", "fallback_suggested_next_action"):
            action = compact.get(key)
            if isinstance(action, str) and action:
                priority.append(action)
        # Station-repair actions when relevant
        stop = compact.get("stop_reason")
        if stop in {"no_crafting_table_nearby", "no_furnace_nearby"} or compact.get("failure_type") == "missing_station":
            for a in ("return_to_workspace", "setup_workspace", "place_crafting_table", "place_furnace"):
                priority.append(a)

    # Dimension-relevant actions
    dim = str(dimension or "overworld").replace("minecraft:", "")
    if dim in ("the_nether", "nether"):
        for a in ("navigate_nether_safely", "collect_blaze_rods", "find_nether_fortress",
                  "retreat_from_nether_danger", "leave_nether"):
            priority.append(a)
    elif dim == "the_end":
        for a in ("end_safe_landing", "fight_dragon_phase", "destroy_end_crystal",
                  "destroy_nearby_end_crystals", "return_to_overworld_via_end_portal"):
            priority.append(a)

    # Core overworld progression actions always deserve docs
    for a in (
        "collect_wood", "craft_planks", "craft_sticks", "craft_crafting_table",
        "place_crafting_table", "craft_wooden_pickaxe", "mine_stone",
        "mine_iron_ore", "craft_stone_pickaxe", "smelt_iron",
        "craft_iron_pickaxe", "setup_workspace", "return_to_workspace",
        "find_safe_workspace",
    ):
        priority.append(a)

    # Deduplicate, filter to bridge/allowed, respect max_count
    seen: set[str] = set()
    result: list[str] = []
    for action in priority:
        if action in seen:
            continue
        seen.add(action)
        if action in bridge_set or action in AUTONOMOUS_ALLOWED_ACTIONS:
            result.append(action)
        if len(result) >= max_count:
            break
    return result


def _special_nearby_blocks(nearby_blocks: Any) -> dict[str, Any]:
    if not isinstance(nearby_blocks, dict):
        return {}

    special_names = ("crafting_table", "furnace", "chest")
    return {name: nearby_blocks[name] for name in special_names if name in nearby_blocks}


def _current_facts(summary: dict[str, Any], nearest_workspace: dict[str, Any] | None = None) -> dict[str, Any]:
    counts = summary.get("inventory_counts") if isinstance(summary.get("inventory_counts"), dict) else {}
    nearby_blocks = summary.get("nearby_blocks") if isinstance(summary.get("nearby_blocks"), dict) else {}
    cobblestone_count = _count_item(counts, "cobblestone")
    sticks_count = _count_item(counts, "stick")
    planks_count = _count_suffix(counts, "_planks")
    has_nearby_crafting_table = isinstance(nearby_blocks.get("crafting_table"), dict)
    has_nearby_furnace = isinstance(nearby_blocks.get("furnace"), dict)
    ws = nearest_workspace if isinstance(nearest_workspace, dict) else {}
    ws_exists = bool(ws.get("exists"))

    return {
        "has_wooden_pickaxe": _count_item(counts, "wooden_pickaxe") > 0,
        "has_stone_pickaxe": _count_item(counts, "stone_pickaxe") > 0,
        "has_iron_pickaxe": _count_item(counts, "iron_pickaxe") > 0,
        "has_cobblestone": cobblestone_count > 0,
        "cobblestone_count": cobblestone_count,
        "has_inventory_crafting_table": _count_item(counts, "crafting_table") > 0,
        "has_nearby_crafting_table": has_nearby_crafting_table,
        "has_nearby_furnace": has_nearby_furnace,
        "can_attempt_stone_pickaxe_materials": cobblestone_count >= 3 and sticks_count >= 2 and has_nearby_crafting_table,
        "planks_count": planks_count,
        "sticks_count": sticks_count,
        "known_workspace_has_crafting_table": ws_exists and bool(ws.get("has_crafting_table")),
        "known_workspace_has_furnace": ws_exists and bool(ws.get("has_furnace")),
        "known_workspace_distance": ws.get("distance") if ws_exists else None,
    }


def _compact_last_action_result(last_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(last_result, dict):
        return None

    verifier = last_result.get("verifier") if isinstance(last_result.get("verifier"), dict) else {}
    result = last_result.get("result") if isinstance(last_result.get("result"), dict) else {}
    compact = {
        "action": last_result.get("action"),
        "ok": last_result.get("ok"),
        "error": _short(last_result.get("error")),
        "failure_type": result.get("failure_type") or verifier.get("failure_type"),
        "stop_reason": result.get("stop_reason") or verifier.get("stop_reason"),
        "suggested_next_action": result.get("suggested_next_action") or verifier.get("suggested_next_action"),
        "fallback_suggested_next_action": result.get("fallback_suggested_next_action") or verifier.get("fallback_suggested_next_action"),
        "can_retry": result.get("can_retry") if "can_retry" in result else verifier.get("can_retry"),
        "needed": result.get("needed") or verifier.get("needed"),
        "station_needed": result.get("station_needed") or verifier.get("station_needed"),
        "verifier": {
            "failure_type": verifier.get("failure_type"),
            "stop_reason": verifier.get("stop_reason"),
            "suggested_next_action": verifier.get("suggested_next_action"),
            "recommendation": _short(verifier.get("recommendation")),
        },
    }
    diagnostics = result.get("diagnostics")
    if isinstance(diagnostics, dict):
        compact["diagnostics"] = {
            key: value for key, value in diagnostics.items()
            if key.startswith("rejected") or key == "candidatesChecked"
        }
    flags = _result_flags(last_result.get("result"))
    if flags:
        compact["result_flags"] = flags
        compact.update(flags)
    return compact


def _compact_failure_summary(last_result: dict[str, Any] | None) -> dict[str, Any] | None:
    compact = _compact_last_action_result(last_result)
    if not _last_failure_included(compact):
        return None

    summary = {
        "action": compact.get("action"),
        "ok": compact.get("ok"),
        "error": compact.get("error"),
        "failure_type": compact.get("failure_type"),
        "stop_reason": compact.get("stop_reason"),
        "suggested_next_action": compact.get("suggested_next_action"),
        "fallback_suggested_next_action": compact.get("fallback_suggested_next_action"),
        "needed": compact.get("needed"),
        "station_needed": compact.get("station_needed"),
        "can_retry": compact.get("can_retry"),
    }
    if summary.get("failure_type") == "no_safe_workspace" or summary.get("stop_reason") == "area_cramped":
        summary["priority"] = "placement_repair"
        summary["repair_hint"] = "choose setup_workspace or find_safe_workspace or return_to_surface before retrying placement"
    elif summary.get("failure_type") == "missing_station" or summary.get("stop_reason") in {"no_crafting_table_nearby", "no_furnace_nearby"}:
        station = summary.get("station_needed", "station")
        summary["repair_hint"] = f"return_to_workspace or setup_workspace to get a nearby {station} before retrying"
    return {key: value for key, value in summary.items() if value is not None}


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
        "fallback_suggested_next_action",
        "stop_reason",
        "failure_type",
        "needed",
        "station_needed",
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
        or last_action_result.get("failure_type")
        or last_action_result.get("stop_reason")
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
    compact = {
        "id": event.get("id"),
        "ts": event.get("ts"),
        "historical": True,
        "message": _short(event.get("message")),
        "action": event.get("action"),
        "ok": event.get("ok"),
        "error": _short(event.get("error")),
        "reason": _short(event.get("reason")),
    }
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    for key in (
        "failure_type",
        "stop_reason",
        "suggested_next_action",
        "fallback_suggested_next_action",
        "can_retry",
        "needed",
        "station_needed",
    ):
        if key in result:
            compact[key] = result.get(key)
    return compact


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
        or item.get("stop_reason") == "no_crafting_table_nearby"
        or item.get("station_needed") == "crafting_table"
    ):
        return True

    if current_facts.get("has_nearby_furnace") and (
        "no furnace" in text
        or "furnace found" in text
        or item.get("stop_reason") == "no_furnace_nearby"
        or item.get("station_needed") == "furnace"
    ):
        return True

    return False


def _compact_waypoints(waypoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for wp in waypoints:
        if not isinstance(wp, dict):
            continue
        result.append({
            "label": wp.get("label"),
            "kind": wp.get("kind"),
            "x": wp.get("x"),
            "y": wp.get("y"),
            "z": wp.get("z"),
            "dimension": wp.get("dimension"),
        })
    return result


def _compact_death(last_death: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(last_death, dict):
        return None
    return {
        "x": last_death.get("x"),
        "y": last_death.get("y"),
        "z": last_death.get("z"),
        "dimension": last_death.get("dimension"),
        "cause": last_death.get("cause"),
    }


def _compact_death_state(death_state: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(death_state, dict) or not death_state.get("known"):
        return None
    return {
        "recent": death_state.get("recent"),
        "despawn_warning": death_state.get("despawn_warning"),
        "time_remaining_s": death_state.get("time_remaining_s"),
        "recovery_failures": death_state.get("recovery_failures"),
        "abandoned": death_state.get("abandoned"),
        "suggested_next_action": death_state.get("suggested_next_action"),
    }


def _compact_milestone_state(milestone_state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(milestone_state, dict):
        return {"next_possible_milestones": []}
    return {
        "completed_milestones": milestone_state.get("completed_milestones", []),
        "next_possible_milestones": milestone_state.get("next_possible_milestones", []),
        "counts": milestone_state.get("counts", {}),
    }


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
