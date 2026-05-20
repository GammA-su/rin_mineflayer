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
from vtuber_ai.memory import (
    RA_BLOCK_TTL_TICKS,
    _access_sig_from_verifier,
    action_family_key,
    is_low_information_action,
    is_observation_action,
    pos_bucket,
    resource_acquisition_scoped_key,
    schema_blocked_family_key,
)
from vtuber_ai.requirements import (
    build_requirement_failure_packet,
    check_requirements,
    parse_error_to_failed_requirements,
)
from vtuber_ai.world_memory import get_death_state as _wm_death_state
from vtuber_ai.world_memory import get_relevant_known_places as _wm_relevant_known_places
from vtuber_ai.world_memory import list_waypoints as _wm_list_waypoints
from vtuber_ai.policy import SMELT_FUELS, SMELT_INPUTS, canonicalize_action_request, normalize_action_args
from vtuber_ai.schemas import ActionRequest, BrainDecision
from vtuber_ai.verifier import POSITION_MEANINGFUL_DELTA_BLOCKS


def hard_block_repetitions_enabled() -> bool:
    """Return True if hard blocking of repeated actions is enabled.

    Default is 0 (advisory/stream mode). Set VTUBER_HARD_BLOCK_REPETITIONS=1 to restore
    the old behavior of skipping execution and returning blocked_repetition as the result.
    """
    return os.environ.get("VTUBER_HARD_BLOCK_REPETITIONS", "0").strip() == "1"


def build_repetition_warning(blocked_rec: dict[str, Any]) -> dict[str, Any]:
    """Build an advisory repetition warning payload from a blocked-family record.

    Used in stream/advisory mode (VTUBER_HARD_BLOCK_REPETITIONS=0) to expose
    repetition context to the planner without hard-blocking execution.
    """
    family = blocked_rec.get("family", "unknown")
    failure_count = blocked_rec.get("failure_count", 1)
    failed_because = blocked_rec.get("failed_because") or []
    unblock_condition = (
        blocked_rec.get("unblock_condition")
        or "Move to a different position or change inventory/world state."
    )
    state_change_needed = [unblock_condition] if unblock_condition else []
    severity = "low" if failure_count < 3 else "medium" if failure_count < 5 else "high"
    return {
        "repetition_warning": True,
        "repetition_family": family,
        "recent_failures": failed_because,
        "why_repeating_may_be_low_value": (
            f"This action family has failed {failure_count} time(s) at this location "
            "with no meaningful state change (position, inventory, dimension unchanged)."
        ),
        "state_change_needed": state_change_needed,
        "warning_severity": severity,
    }


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
        "approach_station",
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
If you need to craft at a table and no crafting_table is usable nearby but inventory has crafting_table, place_crafting_table is valid.
Choose the best next action from the actual state.
Do not follow a fixed checklist.
If the last action failed because something was missing, choose an action that obtains or prepares the missing prerequisite.
Do not repeat an unresolved failed action until its missing condition changes, unless you have a new reason.
If current_intent is set, keep that original goal in mind, but you are free to change plans. If repair attempts fail repeatedly, choose a different route that changes inventory, position, station setup, world state, or resource access.
If last_failure_summary.failure_type is partial_progress_timeout: partial progress was made — continuing may be reasonable, but you may choose any valid action.
If the last failure is no_safe_workspace or area_cramped, choose setup_workspace, find_safe_workspace, or return_to_surface before retrying placement.
If a station is visible but too far, you may choose approach_station, return_to_workspace, setup_workspace, or another valid action.
If the last failure has stop_reason no_crafting_table_nearby: if current_facts.known_workspace_has_crafting_table is true, return_to_workspace is valid; otherwise choose setup_workspace, or place_crafting_table if has_inventory_crafting_table is true.
If the last failure has stop_reason no_furnace_nearby: if current_facts.known_workspace_has_furnace is true, return_to_workspace is valid; otherwise choose setup_workspace, or place_furnace if inventory has furnace.
If you need a crafting table or furnace and known_places.nearest_workspace has one within a reasonable distance, choose return_to_workspace instead of placing a new station.
Do not place new stations when a good workspace already exists nearby - return_to_workspace first.
Use return_to_known_position to navigate to a persistent home or workspace by label (or omit label for nearest).
If you lack materials for an item, choose a prerequisite action.
If an action is already satisfied, do not repeat it.
If uncertain or a previous action failed because environment information was missing, choose a sensing action (check_time_of_day, check_light_level, check_biome, scan_for_hostiles, scan_for_specific_block, etc.) to gather information before acting.
When observation_fresh is true: Observation is fresh. Repeating look_around is allowed, but it probably will not change much unless you moved.
Use progress_monitor to avoid loops. If low_information_loop is true and there is no danger, prefer an action that changes inventory, position, world state, station setup, or resource access. You may still choose status/look_around if you have a specific reason.
If workspace_status is present and remembered_workspace_reachable is false: the known workspace was unreachable multiple times and may be stale. Prefer setup_workspace, navigate to a different area, or use another valid action. Current state and current_facts are more reliable than stale workspace memory.
You are in live continuous mode. Do not assume the run ends after failures. If recent actions failed, choose any valid action that changes conditions or gathers useful information.
If live_recovery_status is present and live_recovery_mode is true: multiple recent actions failed consecutively. Do not repeat the same action family. Choose an action that changes inventory, position, world state, station setup, or resource access.
If in The End during the dragon fight, prefer bounded phase actions: end_safe_landing first after entering, then fight_dragon_phase, and return_to_overworld_via_end_portal only after the dragon is gone.
If recently died, decide whether to recover items or restart progression. Prefer recover_death_items only when the death location is recent and not repeatedly lethal; after two recovery failures, choose abandon_death_recovery or return_to_spawn_or_home.
Milestones are awareness, not a deterministic checklist. Use them to understand progress and prerequisites, but choose actions from the actual current state.
If in danger, prioritize survival.
When unresolved_failure or last_failure_summary contains failed_because: use those entries to reason about what changed and what to do next. Do not repeat actions marked repeatable_now=false unless the relevant requirement changed (e.g. inventory item gained, station moved usable, dimension changed). You may choose any valid action.
current_intent remains active until its goal_action succeeds or you deliberately change goals. If dependency_chain is present, the original goal is blocked by a chain of missing prerequisites; reason from latest_failed_requirement (the deepest/newest missing item) to determine what to obtain first. Status, look_around, and check_inventory do not clear intent.
You may choose any action from full_action_list. detailed_action_docs provides arg schemas and descriptions for the most relevant actions. For actions not in detailed_action_docs, use {} for no-argument actions or the arg names shown in the compact signature. Use describe_actions({actions:[...]}) if you need the full schema for an unlisted action. Use canonical action names from full_action_list. Common aliases (e.g. mine_obsidian→collect_obsidian) may be corrected automatically, but do not invent action names.
Use station_affordances, item_affordances, navigation_stall, failed_because, and current state as facts. You may choose any valid action. Avoid repeating status/look_around when observation is fresh and no danger changed.
If repeated_failed_action_loop.active is true, use the failed_because facts and current state before repeating that action family. You may still repeat it if requirements changed.
If blocked_action_families is non-empty, do not repeat an action from those families while repeatable_now=false unless the unblock_condition is met. You may choose any valid action.
If last_action_result has failure_type blocked_repetition: the action was not executed because it repeated a blocked family without state change. Choose a different valid action or satisfy the unblock_condition before retrying.
If repetition_warnings is non-empty, these action families failed repeatedly at this location with no meaningful state change (position, inventory, dimension unchanged). You may still choose them — the world may have changed — but consider exploring, changing position, or trying a different approach first. If warning_severity is high, the action is very likely to fail again without a state change.
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
If crafting_table needed but not usable nearby: if visible but too far, approach_station is valid; if inventory has it, place_crafting_table is valid; if current_facts.known_workspace_has_crafting_table, return_to_workspace is valid; otherwise setup_workspace.
If furnace needed but not usable nearby: same pattern with visible furnace, known_workspace_has_furnace, and place_furnace if inventory has furnace.
If a station is visible but too far, you may choose approach_station, return_to_workspace, setup_workspace, or another valid action.
If last failure is no_safe_workspace or area_cramped: choose setup_workspace, find_safe_workspace, or return_to_surface.
Do not repeat an unresolved failed action until its missing condition changes, unless you have a new reason.
If current_intent is set, keep that original goal in mind but you are free to change plans. Repeated repair failures mean you should choose a different route that changes inventory, position, station setup, world state, or resource access.
If last_failure_summary.failure_type is partial_progress_timeout: partial progress was made — continuing may be reasonable, but you may choose any valid action.
If health is low and hostiles nearby: choose flee.
If in lava: choose flee.
If uncertain or environment info missing: choose a sensing action (check_time_of_day, check_light_level, check_biome, scan_for_hostiles, scan_for_specific_block).
When observation_fresh is true: Observation is fresh. Repeating look_around is allowed, but it probably will not change much unless you moved.
Use progress_monitor to avoid loops. If low_information_loop is true and there is no danger, prefer an action that changes inventory, position, world state, station setup, or resource access. You may still choose status/look_around if you have a specific reason.
If recently died: prefer recover_death_items; after two failures choose abandon_death_recovery.
If workspace_status.remembered_workspace_reachable is false: known workspace is stale or unreachable. Use setup_workspace or navigate elsewhere instead of return_to_workspace.
You are in live continuous mode. Do not assume the run ends after failures. If recent actions failed, choose any valid action that changes conditions or gathers useful information.
If live_recovery_status.live_recovery_mode is true: consecutive failures detected. Choose a different action family that changes state.
Milestones are awareness only. Choose actions from current state, not a fixed checklist.
Use canonical action names from full_action_list. Common aliases (e.g. mine_obsidian→collect_obsidian) corrected automatically.
Use describe_actions({"actions":[...]}) to get full schema for any unlisted action.
Use station_affordances, item_affordances, navigation_stall, failed_because, and current state as facts. Avoid repeating status/look_around when observation is fresh and no danger changed.
If repeated_failed_action_loop.active is true, use the failed_because facts and current state before repeating that action family. You may still repeat it if requirements changed.
If blocked_action_families is non-empty, do not repeat an action from those families while repeatable_now=false unless the unblock_condition is met. You may choose any valid action.
If last_action_result has failure_type blocked_repetition: the action was not executed because it repeated a blocked family without state change. Choose a different valid action or satisfy the unblock_condition before retrying.
If repetition_warnings is non-empty: these action families failed repeatedly at this position with no state change. You may still choose them, but consider an alternative if world state has not changed. High severity means a state change is strongly recommended first."""

ALLOWED_MOODS = frozenset({"neutral", "focused", "happy", "surprised", "scared", "confused"})
FRESH_OBSERVATION_ACTIONS = frozenset({"look_around", "status", "check_inventory"})

# _SMELTABLE_ITEMS and _FUEL_ITEMS replaced by SMELT_INPUTS / SMELT_FUELS from policy
# so item_affordances stays consistent with what smelt_item actually accepts.

_FOOD_ITEMS: frozenset[str] = frozenset({
    "bread", "cooked_beef", "cooked_porkchop", "cooked_chicken",
    "cooked_mutton", "cooked_rabbit", "cooked_cod", "cooked_salmon",
    "apple", "golden_apple", "enchanted_golden_apple",
    "potato", "baked_potato", "carrot", "golden_carrot",
    "beetroot", "beetroot_soup", "mushroom_stew", "rabbit_stew",
    "pumpkin_pie", "melon_slice", "sweet_berries", "glow_berries",
    "honey_bottle", "raw_beef", "raw_porkchop", "raw_chicken",
    "raw_mutton", "raw_rabbit", "raw_cod", "raw_salmon",
})

_TOOL_SUFFIXES: tuple[str, ...] = ("_pickaxe", "_sword", "_axe", "_shovel", "_hoe")

_NAV_FAILURE_TYPES: frozenset[str] = frozenset({
    "navigation_failed", "path_timeout", "target_unreachable",
    "resource_acquisition_failed",
})

_RELATED_FAILURE_TYPES: frozenset[str] = frozenset({
    "invalid_action", "invalid_action_args", "invalid_args",
    "missing_materials", "missing_station", "no_progress",
})


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
    recent_ticks = status.get("recent_ticks") if isinstance(status.get("recent_ticks"), list) else []
    unresolved_failure = _unresolved_failure_from_ticks(recent_ticks, current_facts)
    current_intent = _current_intent_from_ticks(recent_ticks, current_facts)
    progress_monitor = _progress_monitor_from_ticks(recent_ticks, summary)
    observation_freshness = _observation_freshness_from_ticks(recent_ticks, progress_monitor=progress_monitor)
    progress_monitor["repeated_sensing_count"] = observation_freshness["repeated_sensing_count"]
    _lmc = progress_monitor.get("last_meaningful_changes")
    progress_monitor["last_meaningful_change"] = (_lmc[0] if isinstance(_lmc, list) and _lmc else None)
    workspace_status = _workspace_status_from_ticks(recent_ticks)
    station_access_status = _station_access_status_from_ticks_and_summary(recent_ticks, summary)
    live_recovery_status = _live_recovery_status_from_ticks(recent_ticks)
    milestone_state = build_milestone_state(
        status=raw_status,
        recent_memory=recent_memory,
        recent_ticks=recent_ticks,
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
        unresolved_failure=unresolved_failure,
        current_facts=current_facts,
        dimension=summary.get("dimension"),
        bridge_actions=bridge_actions,
        max_count=max_detailed,
        current_intent=current_intent,
    )
    detailed_action_docs = get_detailed_action_docs(relevant_names)

    show_pna = os.getenv("VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM", "0").strip() == "1"

    # Advisory vs hard-block mode for repeated actions.
    # Hard mode (VTUBER_HARD_BLOCK_REPETITIONS=1): expose blocked families and skip execution.
    # Advisory mode (default, =0): expose repetition_warnings; LLM may still choose the action.
    _all_blocked = _blocked_action_families(recent_ticks, summary)
    if hard_block_repetitions_enabled():
        _blocked_for_llm = _all_blocked
        _repetition_warnings: list[dict[str, Any]] = []
    else:
        _blocked_for_llm = []
        _repetition_warnings = [build_repetition_warning(bf) for bf in _all_blocked]

    return {
        "mission": mission,
        "planner_instruction": "Current state and current_facts are authoritative. Memory may be stale. If memory conflicts with current inventory or nearby blocks, trust current_facts.",
        "current_intent": _compact_current_intent(current_intent, show_possible_next_actions=show_pna),
        "unresolved_failure": _enrich_failure_with_requirements(unresolved_failure, current_facts, show_possible_next_actions=show_pna),
        "station_affordances": _station_affordances(summary),
        "item_affordances": _item_affordances(summary),
        "inventory_efficiency": _inventory_efficiency(summary),
        "navigation_stall": _navigation_stall_from_ticks(recent_ticks, summary),
        "repeated_failed_action_loop": _repeated_failed_action_family(recent_ticks, summary),
        "blocked_action_families": _blocked_for_llm,
        "repetition_warnings": _repetition_warnings,
        "continuation_facts": _continuation_facts_from_ticks(recent_ticks),
        "workspace_status": workspace_status,
        "station_access_status": station_access_status,
        "live_recovery_status": live_recovery_status,
        "progress_monitor": progress_monitor,
        "observation_fresh": observation_freshness["observation_fresh"],
        "repeated_sensing_count": observation_freshness["repeated_sensing_count"],
        "last_observation_tick": observation_freshness["last_observation_tick"],
        "last_observation_summary": observation_freshness["last_observation_summary"],
        "last_failure_summary": _compact_failure_summary(last_result, show_pna=show_pna),
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
        "last_action_result": _compact_last_action_result_for_llm(last_result, show_pna=show_pna),
        "full_action_list": full_action_list,
        "detailed_action_docs": detailed_action_docs,
        "known_waypoints": _compact_waypoints(waypoints),
        "known_places": known_places,
        "last_death": recent_death,
        "death_state": _compact_death_state(death_state),
        "milestones": _compact_milestone_state(milestone_state),
        "recent_completed_intents": _recent_completed_intents_from_ticks(recent_ticks),
        "recent_resource_successes": _recent_resource_successes_from_ticks(recent_ticks, summary),
        "resource_sufficiency": _resource_sufficiency(summary),
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
    _unresolved_failure = compact_context.get("unresolved_failure") if isinstance(compact_context.get("unresolved_failure"), dict) else None
    _current_intent = compact_context.get("current_intent") if isinstance(compact_context.get("current_intent"), dict) else None
    _last_observation_summary = compact_context.get("last_observation_summary")
    _progress_monitor = compact_context.get("progress_monitor") if isinstance(compact_context.get("progress_monitor"), dict) else {}
    _recent_ticks_for_diag = state.get("recent_ticks") if isinstance(state.get("recent_ticks"), list) else []
    _blocked_families = compact_context.get("blocked_action_families") or []
    diagnostics = {
        "llm_latency_sec": 0.0,
        "prompt_size_chars": prompt_size_chars,
        "prompt_budget_exceeded": prompt_size_chars > max_prompt_chars,
        "planner_output_mode": output_mode,
        "llm_state_packet_preview": user_content[:1200],
        "last_failure_included": _last_failure_included(compact_context.get("last_action_result")),
        "last_relevant_failure_included": compact_context.get("last_relevant_failure") is not None,
        "unresolved_failure_included": _unresolved_failure is not None,
        "unresolved_failure_action": (_unresolved_failure or {}).get("action"),
        "unresolved_failure_age_ticks": (_unresolved_failure or {}).get("age_ticks"),
        "unresolved_failure_possible_next_actions": (_unresolved_failure or {}).get("possible_next_actions"),
        "current_intent_included": _current_intent is not None,
        "current_intent_goal_action": (_current_intent or {}).get("goal_action"),
        "current_intent_blocking_problem": (_current_intent or {}).get("blocking_problem"),
        "repair_attempts_count": (_current_intent or {}).get("repair_attempts_count", 0),
        "repeated_repair_failure_count": (_current_intent or {}).get("repeated_repair_failure_count", 0),
        "observation_fresh": bool(compact_context.get("observation_fresh")),
        "repeated_sensing_count": compact_context.get("repeated_sensing_count", 0),
        "last_observation_tick": compact_context.get("last_observation_tick"),
        "last_observation_action": (_last_observation_summary or {}).get("action") if isinstance(_last_observation_summary, dict) else None,
        "low_information_loop": bool(_progress_monitor.get("low_information_loop")),
        "state_changed_recently": bool(_progress_monitor.get("state_changed_recently")),
        "ticks_since_last_material_progress": _progress_monitor.get("ticks_since_last_material_progress"),
        "ticks_since_last_position_progress": _progress_monitor.get("ticks_since_last_position_progress"),
        "last_meaningful_change": (_progress_monitor.get("last_meaningful_changes") or [None])[0]
        if isinstance(_progress_monitor.get("last_meaningful_changes"), list)
        else None,
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
        # Affordance / progress diagnostics (debug only — not sent to LLM)
        "station_affordances": compact_context.get("station_affordances"),
        "item_affordances": compact_context.get("item_affordances"),
        "navigation_stall": compact_context.get("navigation_stall"),
        "progress_monitor": _progress_monitor,
        "repeated_failed_action_loop": compact_context.get("repeated_failed_action_loop"),
        "repeated_failed_action_count": (compact_context.get("repeated_failed_action_loop") or {}).get("count"),
        "repeated_failed_action_name": (compact_context.get("repeated_failed_action_loop") or {}).get("action"),
        "repeated_failed_state_changed": (compact_context.get("repeated_failed_action_loop") or {}).get("state_changed_since_first_failure"),
        "invalid_action_loop": _invalid_action_loop(_recent_ticks_for_diag),
        "recent_completed_intents": compact_context.get("recent_completed_intents"),
        "blocked_action_families_count": len(_blocked_families),
        "blocked_action_families": _blocked_families,
        "chose_blocked_action_family": False,
        "blocked_action_family_name": None,
        "unblock_condition": None,
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
    canonical_info: dict[str, Any] = {}
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
        decision, canonical_info = _canonicalize_decision_action(decision)
        decision = _normalize_decision(decision)
    except Exception as exc:
        info: dict[str, Any] = {
            **diagnostics,
            **alias_info,
            **canonical_info,
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
            **canonical_info,
            "fallback_reason": f"LLM chose disallowed action: {decision.action}.",
            "model": model,
            "llm_latency_sec": llm_latency_sec,
            "raw_llm_output_chars": len(raw_content) if raw_content is not None else 0,
            "parsed_compact_output": parsed_compact_output,
            "completion_tokens": completion_tokens,
        }

    _chosen_family = action_family_key(
        decision.action, decision.args if isinstance(decision.args, dict) else {}
    )
    _blocked_match = next(
        (bf for bf in _blocked_families if bf.get("blocked") and bf.get("family") == _chosen_family),
        None,
    )
    return decision, {
        **diagnostics,
        **alias_info,
        **canonical_info,
        "model": model,
        "llm_latency_sec": llm_latency_sec,
        "raw_llm_output_chars": len(raw_content) if raw_content is not None else 0,
        "parsed_compact_output": parsed_compact_output,
        "completion_tokens": completion_tokens,
        "chose_blocked_action_family": _blocked_match is not None,
        "blocked_action_family_name": _blocked_match.get("family") if _blocked_match else None,
        "unblock_condition": _blocked_match.get("unblock_condition") if _blocked_match else None,
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


def _canonicalize_decision_action(decision: BrainDecision) -> tuple[BrainDecision, dict[str, Any]]:
    request = ActionRequest(action=decision.action, args=decision.args)
    canonical_request, info = canonicalize_action_request(request)
    normalized_request, normalization_info = normalize_action_args(canonical_request)
    combined_info = {**info, **normalization_info}
    if not combined_info:
        return decision, {}

    return BrainDecision(
        objective=decision.objective,
        action=normalized_request.action,
        args=normalized_request.args,
        speech=decision.speech,
        mood=decision.mood,
        reason=decision.reason,
    ), combined_info


def _normalize_decision(decision: BrainDecision) -> BrainDecision:
    mood = decision.mood if decision.mood in ALLOWED_MOODS else "neutral"
    args = dict(decision.args)

    if decision.action in {"collect_wood", "mine_stone", "mine_coal", "mine_iron_ore"} and "count" in args:
        args["count"] = _clamp_int(args["count"], 1, 16)
    if decision.action in {"mine_stone", "mine_coal", "mine_iron_ore"} and "radius" in args:
        args["radius"] = _clamp_int(args["radius"], 4, 96)
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
    elif decision.action == "approach_station":
        if args.get("station") not in {"crafting_table", "furnace", "chest"}:
            args["station"] = "crafting_table"
        if "radius" in args:
            args["radius"] = _clamp_int(args["radius"], 2, 6)
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
    unresolved_failure: dict[str, Any] | None,
    current_facts: dict[str, Any],
    dimension: str | None,
    bridge_actions: list[str] | tuple[str, ...],
    max_count: int = 12,
    current_intent: dict[str, Any] | None = None,
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
        if stop in {"no_crafting_table_nearby", "no_furnace_nearby", "station_visible_but_too_far"} or compact.get("failure_type") == "missing_station":
            for a in ("approach_station", "return_to_workspace", "setup_workspace", "place_crafting_table", "place_furnace"):
                priority.append(a)

    if isinstance(unresolved_failure, dict):
        for action in unresolved_failure.get("possible_next_actions") or []:
            if isinstance(action, str):
                priority.append(action)
        failed_action = unresolved_failure.get("action")
        if isinstance(failed_action, str):
            priority.append(failed_action)

    if isinstance(current_intent, dict):
        for action in current_intent.get("possible_next_actions") or []:
            if isinstance(action, str):
                priority.append(action)
        goal = current_intent.get("goal_action")
        if isinstance(goal, str):
            priority.append(goal)

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
        "craft_iron_pickaxe", "setup_workspace", "approach_station", "return_to_workspace",
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
    coal_or_charcoal_count = _count_item(counts, "coal") + _count_item(counts, "charcoal")
    iron_ingot_count = _count_item(counts, "iron_ingot")
    craft_usable_radius = 6.0
    furnace_usable_radius = 6.0
    crafting_table = _station_observation(nearby_blocks.get("crafting_table"), craft_usable_radius)
    furnace = _station_observation(nearby_blocks.get("furnace"), furnace_usable_radius)
    has_visible_crafting_table = crafting_table["visible"]
    has_nearby_crafting_table_usable = crafting_table["usable"]
    has_visible_furnace = furnace["visible"]
    has_nearby_furnace_usable = furnace["usable"]
    ws = nearest_workspace if isinstance(nearest_workspace, dict) else {}
    ws_exists = bool(ws.get("exists"))

    return {
        "has_wooden_pickaxe": _count_item(counts, "wooden_pickaxe") > 0,
        "has_stone_pickaxe": _count_item(counts, "stone_pickaxe") > 0,
        "has_iron_pickaxe": _count_item(counts, "iron_pickaxe") > 0,
        "has_cobblestone": cobblestone_count > 0,
        "cobblestone_count": cobblestone_count,
        "has_inventory_crafting_table": _count_item(counts, "crafting_table") > 0,
        "has_inventory_furnace": _count_item(counts, "furnace") > 0,
        "has_nearby_crafting_table": has_visible_crafting_table,
        "has_visible_crafting_table": has_visible_crafting_table,
        "has_nearby_crafting_table_usable": has_nearby_crafting_table_usable,
        "nearest_crafting_table_distance": crafting_table["distance"],
        "nearest_crafting_table_position": crafting_table["position"],
        "has_nearby_furnace": has_visible_furnace,
        "has_visible_furnace": has_visible_furnace,
        "has_nearby_furnace_usable": has_nearby_furnace_usable,
        "nearest_furnace_distance": furnace["distance"],
        "nearest_furnace_position": furnace["position"],
        "can_attempt_stone_pickaxe_materials": cobblestone_count >= 3 and sticks_count >= 2 and has_nearby_crafting_table_usable,
        "planks_count": planks_count,
        "sticks_count": sticks_count,
        "coal_or_charcoal_count": coal_or_charcoal_count,
        "has_coal_or_charcoal": coal_or_charcoal_count > 0,
        "iron_ingot_count": iron_ingot_count,
        "known_workspace_has_crafting_table": ws_exists and bool(ws.get("has_crafting_table")),
        "known_workspace_has_furnace": ws_exists and bool(ws.get("has_furnace")),
        "known_workspace_distance": ws.get("distance") if ws_exists else None,
    }


def _station_observation(block: Any, usable_radius: float) -> dict[str, Any]:
    if not isinstance(block, dict):
        return {"visible": False, "usable": False, "distance": None, "position": None}
    distance = block.get("distance")
    usable = not isinstance(distance, (int, float)) or distance <= usable_radius
    return {
        "visible": True,
        "usable": usable,
        "distance": distance if isinstance(distance, (int, float)) else None,
        "position": block.get("position") if isinstance(block.get("position"), dict) else None,
    }


def _station_affordances(summary: dict[str, Any]) -> dict[str, Any]:
    counts = summary.get("inventory_counts") or {}
    nearby_blocks = summary.get("nearby_blocks") or {}

    stations = ("crafting_table", "furnace", "chest")
    carried_stations: dict[str, int] = {}
    usable_nearby_stations: dict[str, bool] = {}

    for station in stations:
        carried_stations[station] = _count_item(counts, station)
        nearby = nearby_blocks.get(station)
        if isinstance(nearby, dict):
            distance = nearby.get("distance")
            usable = not isinstance(distance, (int, float)) or distance <= 6.0
        else:
            usable = bool(nearby)
        usable_nearby_stations[station] = usable

    station_gap_facts = []
    for station in stations:
        if carried_stations.get(station, 0) > 0 and not usable_nearby_stations.get(station, False):
            station_gap_facts.append({
                "station": station,
                "in_inventory": True,
                "usable_nearby": False,
                "fact": "station is carried but not usable nearby",
            })

    return {
        "carried_stations": carried_stations,
        "usable_nearby_stations": usable_nearby_stations,
        "station_gap_facts": station_gap_facts,
    }


def _item_affordances(summary: dict[str, Any]) -> dict[str, Any]:
    counts = summary.get("inventory_counts") or {}

    fuel_items = {
        k: v for k, v in counts.items()
        if k in SMELT_FUELS and isinstance(v, int) and not isinstance(v, bool) and v > 0
    }
    smeltable_items = {
        k: v for k, v in counts.items()
        if k in SMELT_INPUTS and isinstance(v, int) and not isinstance(v, bool) and v > 0
    }
    has_building_blocks = any(
        isinstance(v, int) and not isinstance(v, bool) and v > 0
        for k, v in counts.items()
        if (k.endswith("_planks") or k.endswith("_log") or k.endswith("_stem")
            or k in ("cobblestone", "dirt", "gravel", "sand", "stone"))
    )
    tool_duplicates = {
        k: v for k, v in counts.items()
        if isinstance(v, int) and not isinstance(v, bool) and v > 2
        and any(k.endswith(s) for s in _TOOL_SUFFIXES)
    }
    food_count = sum(
        v for k, v in counts.items()
        if k in _FOOD_ITEMS and isinstance(v, int) and not isinstance(v, bool) and v > 0
    )
    torch_count = _count_item(counts, "torch")

    return {
        "has_fuel": bool(fuel_items),
        "fuel_items": fuel_items,
        "has_smeltable_items": bool(smeltable_items),
        "smeltable_items": smeltable_items,
        "has_building_blocks": has_building_blocks,
        "tool_duplicates": tool_duplicates,
        "low_consumables": {
            "food": food_count == 0,
            "torches": torch_count == 0,
        },
    }


def _inventory_efficiency(summary: dict[str, Any]) -> dict[str, Any]:
    counts = summary.get("inventory_counts") or {}
    duplicate_tools = {
        k: v for k, v in counts.items()
        if isinstance(v, int) and not isinstance(v, bool) and v > 2
        and any(k.endswith(s) for s in _TOOL_SUFFIXES)
    }
    slots_used = sum(
        1 for v in counts.values()
        if isinstance(v, int) and not isinstance(v, bool) and v > 0
    )
    result: dict[str, Any] = {
        "duplicate_tools": duplicate_tools,
        "inventory_slots_used": slots_used,
    }
    if duplicate_tools:
        result["note"] = "Several duplicate tools occupy inventory slots."
    return result


def _navigation_stall_from_ticks(
    recent_ticks: list[dict[str, Any]],
    summary: dict[str, Any],  # noqa: ARG001  (reserved for future position cross-check)
) -> dict[str, Any] | None:
    window = [t for t in recent_ticks[:5] if isinstance(t, dict)]

    nav_failure_count = 0
    last_failed_targets: list[str] = []
    position_changes: list[bool] = []

    for tick in window:
        before_pos = _position_from_tick_state(
            tick.get("before_state") or _decode_jsonish(tick.get("before_state_json"))
        )
        after_pos = _position_from_tick_state(
            tick.get("after_state") or _decode_jsonish(tick.get("after_state_json"))
        )
        if before_pos and after_pos:
            position_changes.append(_position_distance(before_pos, after_pos) > 1.0)

        if _tick_ok(tick) is True:
            continue

        action = tick.get("action")
        verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else {}
        result = tick.get("result") if isinstance(tick.get("result"), dict) else {}
        error = str(tick.get("error") or "").lower()
        failure_type = str(verifier.get("failure_type") or result.get("failure_type") or "")

        is_nav_fail = (
            failure_type in _NAV_FAILURE_TYPES
            or "navigation" in error
            or "timed out pathing" in error
            or "no accessible target block" in error
            or "exploration path failed" in error
        )
        if not is_nav_fail:
            continue

        nav_failure_count += 1
        args = tick.get("args") if isinstance(tick.get("args"), dict) else {}
        targets = args.get("targets") or args.get("target") or result.get("targets")
        if isinstance(targets, list):
            last_failed_targets.extend(t for t in targets if isinstance(t, str))
        elif isinstance(targets, str):
            last_failed_targets.append(targets)
        elif action == "mine_iron_ore":
            last_failed_targets.append("iron_ore")
        elif action == "mine_coal":
            last_failed_targets.append("coal_ore")

    if nav_failure_count == 0:
        return None

    observation_fresh = any(
        t.get("action") in FRESH_OBSERVATION_ACTIONS and _tick_ok(t) is True
        for t in window
    )

    return {
        "recent_navigation_failures": nav_failure_count,
        "last_failed_targets": list(dict.fromkeys(last_failed_targets))[:3],
        "position_changed_recently": any(position_changes),
        "observation_fresh": observation_fresh,
        "fact": "Recent movement/resource navigation attempts failed from this area.",
    }


def _tick_failure_type(tick: dict[str, Any]) -> str:
    verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else _decode_jsonish(tick.get("verifier_json"))
    result = tick.get("result") if isinstance(tick.get("result"), dict) else {}
    vft = verifier.get("failure_type") if isinstance(verifier, dict) else None
    rft = result.get("failure_type") if isinstance(result, dict) else None
    return str(vft or rft or "")


def _repeated_failed_action_family(
    recent_ticks: list[dict[str, Any]],
    current_summary: dict[str, Any],
) -> dict[str, Any] | None:
    """Detect repeated failures of the same action family in the last N ticks.

    Activates when same action fails 2+ times in the last 5 ticks, or
    3+ times in the 6-tick window with related failure types.
    """
    N = 6
    SHORT_WINDOW = 5
    SHORT_THRESHOLD = 2
    LONG_THRESHOLD = 3

    ticks = [t for t in recent_ticks[:N] if isinstance(t, dict)]
    failures_by_action: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for i, tick in enumerate(ticks):
        if _tick_ok(tick) is not False:
            continue
        action = tick.get("action")
        if not isinstance(action, str) or is_observation_action(action):
            continue
        if _tick_meaningful_progress_signals(tick):
            continue
        failures_by_action.setdefault(action, []).append((i, tick))

    if not failures_by_action:
        return None

    best_action: str | None = None
    best_pairs: list[tuple[int, dict[str, Any]]] = []
    for action, pairs in failures_by_action.items():
        short_count = sum(1 for (i, _) in pairs if i < SHORT_WINDOW)
        related_count = sum(
            1 for (_, t) in pairs if _tick_failure_type(t) in _RELATED_FAILURE_TYPES
        )
        if short_count >= SHORT_THRESHOLD or related_count >= LONG_THRESHOLD:
            if len(pairs) > len(best_pairs):
                best_action = action
                best_pairs = pairs

    if best_action is None:
        return None

    failure_types = list(dict.fromkeys(
        ft for (_, t) in best_pairs
        if (ft := _tick_failure_type(t)) and ft != "none"
    ))

    newest_tick = best_pairs[0][1]
    verifier = newest_tick.get("verifier") if isinstance(newest_tick.get("verifier"), dict) else _decode_jsonish(newest_tick.get("verifier_json"))
    last_failed_because = (verifier.get("failed_because") if isinstance(verifier, dict) else None) or []
    if not isinstance(last_failed_because, list):
        last_failed_because = []

    oldest_tick = best_pairs[-1][1]
    oldest_before = oldest_tick.get("before_state") or _decode_jsonish(oldest_tick.get("before_state_json"))
    oldest_counts = _inventory_counts_from_tick_state(oldest_before)
    current_counts = dict(current_summary.get("inventory_counts") or {})
    state_changed = oldest_counts != current_counts

    return {
        "active": True,
        "action": best_action,
        "count": len(best_pairs),
        "failure_types": failure_types,
        "state_changed_since_first_failure": state_changed,
        "last_failed_because": last_failed_because,
        "lesson": "This action family has failed repeatedly. Repeating it without changed requirements is unlikely to help.",
    }


def _family_unblock_condition(family: str) -> str:
    if family.startswith("action_schema:"):
        rest = family[len("action_schema:"):]
        colon = rest.find(":")
        if colon > 0:
            action_name = rest[:colon]
            constraint = rest[colon + 1:]
            if constraint.startswith("missing_"):
                arg_name = constraint[len("missing_"):]
                return f"Provide required arg `{arg_name}` for `{action_name}`."
        return "Provide all required args for this action."
    if family.startswith("drop_collection:"):
        rest = family[len("drop_collection:"):]
        colon = rest.find(":")
        if colon > 0:
            resource = rest[:colon]
            return (
                f"This specific {resource} drop fell deep with no safe stand. "
                f"Mine a different {resource} block — the drop will land at a new position."
            )
        resource = rest
        return (
            f"Drop was unreachable after mining {resource}. "
            f"Move to a different position or wait for the drop to become accessible, "
            f"then retry mine_{resource} elsewhere."
        )
    if family.startswith("resource_acquisition:"):
        block = family[len("resource_acquisition:"):]
        return (
            f"Retry after position changes, {block} accessibility changes, "
            f"or new {block} is observed nearby."
        )
    if family == "action:smelt_item":
        return "Retry only after input items, fuel, or furnace availability change."
    if family == "action:scan_for_specific_block":
        return "Retry after target specification changes or position changes significantly."
    if family.startswith("navigation_target:"):
        target = family[len("navigation_target:"):]
        return f"Retry after position changes or {target} accessibility changes."
    if family.startswith("station_access:"):
        station = family[len("station_access:"):]
        return f"Retry after {station} is placed, moved closer, or approached."
    return "Retry after requirements or environment change."


_EXPENSIVE_ACTIONS: frozenset[str] = frozenset({
    "mine_iron_ore",
    "mine_coal",
    "mine_stone",
    "acquire_blocks",
    "navigate_to_block_type",
    "explore_nearby",
})
_FAST_BLOCK_WINDOW = 4
_FAST_BLOCK_MIN_TIMEOUTS = 2
_RA_BLOCK_WINDOW = 8  # Extended look-back for resource-acquisition scoped blocks

# Drop-collection-specific stop reasons emitted by the JS bridge.
_DROP_COLLECTION_STOP_REASONS: frozenset[str] = frozenset({
    "drop_collection_partial_progress",
    "mined_target_but_drop_not_collected",
    "drop_unreachable",
    "drop_local_excavation_progress",
    "drop_disappeared_without_inventory_delta",
    "drop_direct_walk_no_progress",
    "drop_no_safe_stand",
    "drop_close_but_no_pickup_attempt",
    "drop_deep_unreachable",
})
# failed_because.kind values that indicate a drop-collection failure.
_DROP_COLLECTION_FAILED_BECAUSE_KINDS: frozenset[str] = frozenset({
    "mined_target_but_drop_not_collected",
    "drop_collection_failed",
    "internal_drop_collection_bug",
    "drop_deep_unreachable",
})


def _is_timeout_tick(tick: dict[str, Any]) -> bool:
    """Return True if this failure tick was caused by a pure (no-progress) timeout.

    partial_progress_timeout means the bot made real physical progress before the
    clock expired — treating it as a hard block would penalise useful work.
    """
    if _tick_meaningful_progress_signals(tick):
        return False
    ft = _tick_failure_type(tick)
    if ft in {"partial_progress_timeout", "close_range_access_failed"}:
        return False
    # Mined-but-not-collected and specific drop/path failures are real progress, not hard blocks.
    stop = tick.get("stop_reason") or ""
    if stop in {
        "mined_target_but_drop_not_collected",
        "close_range_access_timeout",
        "drop_unreachable",
        "drop_disappeared_without_inventory_delta",
        "path_planning_timeout",
    }:
        return False
    if ft == "action_timeout":
        return True
    verifier = (
        tick.get("verifier") if isinstance(tick.get("verifier"), dict)
        else _decode_jsonish(tick.get("verifier_json"))
    )
    if isinstance(verifier, dict):
        if verifier.get("failure_type") == "partial_progress_timeout":
            return False
        fb = verifier.get("failed_because")
        if isinstance(fb, list) and any(
            isinstance(e, dict) and e.get("kind") == "action_timeout" for e in fb
        ):
            return True
    error = (tick.get("error") or "").lower()
    return "timed out" in error or "timeout" in error


def _is_drop_collection_failure_tick(tick: dict[str, Any]) -> bool:
    """Return True if mining succeeded (minedTargetBlocks > 0) but drop collection failed.

    These ticks must not contribute to resource_acquisition:* blocks.
    They are always partial_progress_timeout on the JS side.
    """
    if _tick_failure_type(tick) != "partial_progress_timeout":
        return False

    result, verifier = _tick_payloads(tick)

    # Must have mined at least one block (top-level, diagnostics, or failed_because).
    mined: bool = bool(_as_positive_number(result.get("minedTargetBlocks")))
    if not mined:
        diag = verifier.get("diagnostics") if isinstance(verifier.get("diagnostics"), dict) else {}
        mined = bool(_as_positive_number(diag.get("minedTargetBlocks")))
    if not mined:
        for src in (result, verifier):
            for fb in (src.get("failed_because") or []):
                if isinstance(fb, dict) and _as_positive_number(fb.get("minedTargetBlocks")):
                    mined = True
                    break
            if mined:
                break
    if not mined:
        return False

    # Drop-specific stop_reason at top level.
    stop_reason = str(result.get("stop_reason") or verifier.get("stop_reason") or "")
    if stop_reason in _DROP_COLLECTION_STOP_REASONS:
        return True

    # Drop-specific kind or dropRecoveryFailureReason in failed_because entries.
    for src in (result, verifier):
        for fb in (src.get("failed_because") or []):
            if not isinstance(fb, dict):
                continue
            if fb.get("kind") in _DROP_COLLECTION_FAILED_BECAUSE_KINDS:
                return True
            if fb.get("dropRecoveryFailureReason"):
                return True

    # Top-level dropRecoveryFailureReason (JS stores it there too).
    if result.get("dropRecoveryFailureReason"):
        return True

    return False


def _extract_drop_collection_diagnostics(tick: dict[str, Any]) -> dict[str, Any]:
    """Extract diagnostics from a drop_collection failure tick for the block record."""
    result, _verifier = _tick_payloads(tick)
    diag: dict[str, Any] = {"blocked_family_type": "drop_collection"}

    for src_key, out_key in (
        ("dropRecoveryFailureReason", "recovery_failure_reason"),
        ("dropEntityPosition", "drop_position"),
        ("dropBlockedBy", "blocker"),
        ("minedTargetBlocks", "minedTargetBlocks"),
        ("blockerReason", "blocker_reason"),
        ("blockerIntersectsMovementVolume", "blocker_intersects_movement_volume"),
        ("abandonedDropReason", "abandoned_drop_reason"),
        ("dropCollectionAbandoned", "drop_collection_abandoned"),
    ):
        v = result.get(src_key)
        if v is not None:
            diag[out_key] = v

    # Also look inside failed_because for richer data.
    for fb in (result.get("failed_because") or []):
        if not isinstance(fb, dict):
            continue
        for src_key, out_key in (
            ("dropRecoveryFailureReason", "recovery_failure_reason"),
            ("dropEntityPosition", "drop_position"),
            ("dropBlockedBy", "blocker"),
            ("blockerReason", "blocker_reason"),
            ("blockerIntersectsMovementVolume", "blocker_intersects_movement_volume"),
            ("same_drop_retry_not_recommended", "same_drop_retry_not_recommended"),
            ("drop_collection_family", "drop_collection_family"),
            ("continuation_relevant", "continuation_relevant"),
        ):
            if fb.get(src_key) is not None and out_key not in diag:
                diag[out_key] = fb[src_key]

    return diag


def _tick_payloads(tick: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = tick.get("result") if isinstance(tick.get("result"), dict) else _decode_jsonish(tick.get("result_json"))
    verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else _decode_jsonish(tick.get("verifier_json"))
    return (
        result if isinstance(result, dict) else {},
        verifier if isinstance(verifier, dict) else {},
    )


def _as_positive_number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and value > 0 else 0.0


def _progress_signal_map(raw: Any) -> dict[str, Any]:
    signals: dict[str, Any] = {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                key, _, value = item.partition(":")
                if key:
                    signals[key] = value if value else True
    return signals


def _inventory_delta_non_empty(value: Any) -> bool:
    return isinstance(value, dict) and any(isinstance(v, (int, float)) and v != 0 for v in value.values())


def _tick_meaningful_progress_signals(tick: dict[str, Any]) -> dict[str, Any]:
    """Return generic progress signals for a failed tick, empty when it made no progress."""
    result, verifier = _tick_payloads(tick)
    diagnostics = verifier.get("diagnostics") if isinstance(verifier.get("diagnostics"), dict) else {}
    signals: dict[str, Any] = {}
    failure_type = _tick_failure_type(tick)
    stop_reason = str(result.get("stop_reason") or verifier.get("stop_reason") or tick.get("stop_reason") or "")

    def add(name: str, value: Any = True) -> None:
        signals[name] = value

    if result.get("partial_success") is True or verifier.get("partial_success") is True:
        add("partial_success", True)
    if failure_type == "partial_progress_timeout":
        add("failure_type", failure_type)
    if "partial_progress" in stop_reason or stop_reason in {"drop_collection_partial_progress", "drop_local_excavation_progress"}:
        add("stop_reason", stop_reason)

    merged_sources = [result, diagnostics]
    for source in merged_sources:
        if _as_positive_number(source.get("minedTargetBlocks")):
            add("minedTargetBlocks", source.get("minedTargetBlocks"))
        if _as_positive_number(source.get("excavatedBlocks")):
            add("excavatedBlocks", source.get("excavatedBlocks"))
        if source.get("dropDistanceImproved") is True:
            add("dropDistanceImproved", True)
        if _as_positive_number(source.get("distance_moved")):
            add("distance_moved", source.get("distance_moved"))
        if _inventory_delta_non_empty(source.get("inventory_delta")):
            add("inventory_delta", source.get("inventory_delta"))
        if _as_positive_number(source.get("collected")):
            add("collected", source.get("collected"))
        if _as_positive_number(source.get("targetInventoryDelta")):
            add("targetInventoryDelta", source.get("targetInventoryDelta"))
        # Additional top-level progress fields the bot may report.
        if source.get("botPositionChanged") is True:
            add("botPositionChanged", True)
        if source.get("continuation_relevant") is True:
            add("continuation_relevant", True)
        if source.get("dropLocalPathSucceeded") is True:
            add("dropLocalPathSucceeded", True)
        # distanceToDropEnd < distanceToDropStart → drop distance improved.
        _dts = _as_positive_number(source.get("distanceToDropStart"))
        _dte = _as_positive_number(source.get("distanceToDropEnd"))
        if _dts and _dte and _dte < _dts:
            add("dropDistanceImproved", True)

    # Also check verifier top-level for continuation_relevant (hoisted by
    # _extract_partial_progress_facts into verifier.diagnostics).
    if verifier.get("continuation_relevant") is True:
        add("continuation_relevant", True)

    for source in [result, verifier]:
        failed_because = source.get("failed_because")
        if not isinstance(failed_because, list):
            continue
        for entry in failed_because:
            if not isinstance(entry, dict):
                continue
            progress_signals = _progress_signal_map(entry.get("progress_signals"))
            if progress_signals:
                add("progress_signals", progress_signals)
                if "inventory_delta" in progress_signals and _inventory_delta_non_empty(progress_signals.get("inventory_delta")):
                    add("inventory_delta", progress_signals["inventory_delta"])
                if "distance_moved" in progress_signals and _as_positive_number(progress_signals.get("distance_moved")):
                    add("distance_moved", progress_signals["distance_moved"])
                if "excavatedBlocks" in progress_signals or "excavated_blocks" in progress_signals:
                    add("excavatedBlocks", progress_signals.get("excavatedBlocks") or progress_signals.get("excavated_blocks"))
                if "minedTargetBlocks" in progress_signals or "mined_target_blocks" in progress_signals:
                    add("minedTargetBlocks", progress_signals.get("minedTargetBlocks") or progress_signals.get("mined_target_blocks"))
            if entry.get("continuation_relevant"):
                add("continuation_relevant", True)
            for key in ("minedTargetBlocks", "excavatedBlocks", "collected", "targetInventoryDelta"):
                if _as_positive_number(entry.get(key)):
                    add(key, entry.get(key))
            if entry.get("dropDistanceImproved") is True:
                add("dropDistanceImproved", True)
            if entry.get("botPositionChanged") is True:
                add("botPositionChanged", True)
            if entry.get("dropLocalPathSucceeded") is True:
                add("dropLocalPathSucceeded", True)
    return signals


_STATION_USABLE_RADIUS = 6.0
_TRACKED_STATIONS = ("crafting_table", "furnace", "chest")


def _station_access_status_from_ticks_and_summary(
    recent_ticks: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Per-station factual state: current visibility/usability plus approach history."""
    nearby_blocks = summary.get("nearby_blocks") if isinstance(summary.get("nearby_blocks"), dict) else {}

    last_approach_age: dict[str, int] = {}
    for age, tick in enumerate(recent_ticks[:8]):
        if not isinstance(tick, dict) or _tick_ok(tick) is not True:
            continue
        action = tick.get("action")
        if not isinstance(action, str) or action != "approach_station":
            continue
        args = tick.get("args") if isinstance(tick.get("args"), dict) else {}
        station = args.get("station")
        if isinstance(station, str) and station in _TRACKED_STATIONS and station not in last_approach_age:
            last_approach_age[station] = age

    result: dict[str, Any] = {}
    for station in _TRACKED_STATIONS:
        block = nearby_blocks.get(station)
        if isinstance(block, dict):
            distance = block.get("distance")
            usable = not isinstance(distance, (int, float)) or distance <= _STATION_USABLE_RADIUS
            entry: dict[str, Any] = {
                "visible": True,
                "usable": usable,
                "distance": distance if isinstance(distance, (int, float)) else None,
            }
        else:
            usable = False
            entry = {"visible": False, "usable": False, "distance": None}

        if station in last_approach_age:
            entry["last_approach_success_tick"] = last_approach_age[station]
            if usable and last_approach_age[station] <= 2:
                entry["repeated_approach_warning"] = True

        result[station] = entry

    return result


def _workspace_status_from_ticks(recent_ticks: list[dict[str, Any]], window: int = 8) -> dict[str, Any] | None:
    """Return workspace_status when recent ticks show repeated return_to_workspace path failures."""
    ws_timeout_count = 0
    station_missing: list[str] = []
    last_failure: str | None = None
    for tick in recent_ticks[:window]:
        if not isinstance(tick, dict):
            continue
        action = tick.get("action")
        if not isinstance(action, str) or action != "return_to_workspace":
            continue
        if _tick_ok(tick) is True:
            ws_timeout_count = 0
            continue
        result, verifier = _tick_payloads(tick)
        ft = str(verifier.get("failure_type") or result.get("failure_type") or "")
        stop_reason = str(result.get("stop_reason") or verifier.get("stop_reason") or "")
        if "path_timeout" in ft or "path_timeout" in stop_reason or "navigation_failed" in ft:
            ws_timeout_count += 1
            last_failure = "path_timeout"
        sn = result.get("station_needed")
        if isinstance(sn, str) and sn and sn not in station_missing:
            station_missing.append(sn)
    if ws_timeout_count < 2:
        return None
    return {
        "remembered_workspace_reachable": False,
        "failure_count": ws_timeout_count,
        "last_failure": last_failure or "path_timeout",
        "station_missing_near_current_position": station_missing,
        "fact": "Remembered workspace may be stale or unreachable from current position.",
    }


def _live_recovery_status_from_ticks(recent_ticks: list[dict[str, Any]], window: int = 8) -> dict[str, Any] | None:
    """Return live_recovery_status when recent ticks show 3+ consecutive failures (newest-first)."""
    consecutive = 0
    failure_actions: list[str] = []
    failure_types: list[str] = []
    for tick in recent_ticks[:window]:
        if not isinstance(tick, dict):
            break
        ok = _tick_ok(tick)
        if ok is True:
            break
        consecutive += 1
        action = tick.get("action")
        if isinstance(action, str) and action not in failure_actions:
            failure_actions.append(action)
        result, verifier = _tick_payloads(tick)
        ft = str(verifier.get("failure_type") or result.get("failure_type") or "")
        if ft and ft not in failure_types:
            failure_types.append(ft)
    if consecutive < 3:
        return None
    pattern = ", ".join(failure_actions) if failure_actions else "unknown"
    stalled = failure_types[0] if failure_types else "unknown"
    return {
        "live_recovery_mode": True,
        "consecutive_failure_count": consecutive,
        "recent_failure_pattern": pattern,
        "stalled_reason": stalled,
        "must_change_conditions": True,
    }


def _continuation_facts_from_ticks(recent_ticks: list[dict[str, Any]], window: int = 6) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tick in recent_ticks[:window]:
        if not isinstance(tick, dict):
            continue
        action = tick.get("action")
        if not isinstance(action, str):
            continue
        args = tick.get("args") if isinstance(tick.get("args"), dict) else {}
        family = action_family_key(action, args)
        if not isinstance(family, str) or not family.startswith("resource_acquisition:") or family in seen:
            continue
        signals = _tick_meaningful_progress_signals(tick)
        # Also emit a continuation fact for partial_progress_timeout ticks even
        # if signal detection returns empty (e.g. all signals are in nested fields
        # that weren't parsed).  The failure_type alone is authoritative.
        is_partial_progress_type = _tick_failure_type(tick) == "partial_progress_timeout"
        if not signals and not is_partial_progress_type:
            continue
        # Skip ticks that explicitly opted out of continuation. The JS sets
        # continuation_relevant=false for drop_deep_unreachable (mining happened but
        # the specific drop fell deep with no safe stand). Mining a different block
        # is fine; retrying the same drop is not.
        result_payload, _v = _tick_payloads(tick)
        if result_payload.get("continuation_relevant") is False:
            continue
        facts.append({
            "continuation_relevant": True,
            "continuation_family": family,
            "reason": "previous attempt made partial progress",
            "last_progress_signals": signals,
        })
        seen.add(family)
    return facts


def _pos_distance(pos_a: dict[str, Any] | None, pos_b: dict[str, Any] | None) -> float:
    if not pos_a or not pos_b:
        return 0.0
    dx = pos_b.get("x", 0) - pos_a.get("x", 0)
    dy = pos_b.get("y", 0) - pos_a.get("y", 0)
    dz = pos_b.get("z", 0) - pos_a.get("z", 0)
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def _blocked_action_families(
    recent_ticks: list[dict[str, Any]],
    current_summary: dict[str, Any],
    window: int = 6,
    min_failures: int = 2,
) -> list[dict[str, Any]]:
    """Detect action families that have failed repeatedly without meaningful state change.

    A family is blocked when either:
    - Fast path (expensive actions only): ≥ _FAST_BLOCK_MIN_TIMEOUTS timeout failures
      within _FAST_BLOCK_WINDOW ticks and position has not changed meaningfully.
    - Standard path: ≥ min_failures failures within window AND position, inventory,
      and dimension have not changed since the oldest failure.

    Returns a list of blocked-family records ready for the LLM state packet.
    """
    ticks = [t for t in recent_ticks[:window] if isinstance(t, dict)]
    ra_ticks = [t for t in recent_ticks[:_RA_BLOCK_WINDOW] if isinstance(t, dict)]

    # Precompute which families had a successful tick in the window → those are cleared.
    _successful_families: set[str] = set()
    _progress_by_family: dict[str, int] = {}
    # Track drop_collection failures by resource family (e.g. resource_acquisition:coal →
    # drop_collection diagnostics).  Used to redirect resource_acquisition:* blocks.
    _dc_info_by_resource_family: dict[str, dict[str, Any]] = {}
    # Track whether an exploration action succeeded → clear all RA scoped blocks.
    _ra_cleared_by_exploration: bool = False
    for age, t in enumerate(ra_ticks):
        t_action = t.get("action")
        if not isinstance(t_action, str):
            continue
        # Successful explore_nearby/look_around → clear all RA scoped blocks.
        if _tick_ok(t) is True and t_action in {"explore_nearby", "look_around"}:
            _ra_cleared_by_exploration = True
        t_args = t.get("args") if isinstance(t.get("args"), dict) else {}
        t_family = action_family_key(t_action, t_args)
        if t_family is None:
            continue
        if _tick_ok(t) is True:
            _successful_families.add(t_family)
            # A successful resource action also clears any drop_collection:* sibling.
            if t_family.startswith("resource_acquisition:"):
                _successful_families.add(
                    f"drop_collection:{t_family[len('resource_acquisition:'):]}"
                )
        elif _tick_ok(t) is False and _tick_meaningful_progress_signals(t):
            if t_family not in _progress_by_family or age < _progress_by_family[t_family]:
                _progress_by_family[t_family] = age
            # Detect drop_collection failure for this resource family.
            if (
                t_family.startswith("resource_acquisition:")
                and t_family not in _dc_info_by_resource_family
                and _is_drop_collection_failure_tick(t)
            ):
                _dc_info_by_resource_family[t_family] = _extract_drop_collection_diagnostics(t)

    failures_by_family: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for age, tick in enumerate(ticks):
        if _tick_ok(tick) is not False:
            continue
        action = tick.get("action")
        if not isinstance(action, str):
            continue
        args = tick.get("args") if isinstance(tick.get("args"), dict) else {}
        family = action_family_key(action, args)
        if family is None:
            continue
        # RA families are handled separately via scoped key grouping.
        if family.startswith("resource_acquisition:"):
            continue
        # Hard guard: partial_progress_timeout ticks always represent useful work.
        # They must never count toward a block, regardless of signal detection.
        if _tick_failure_type(tick) == "partial_progress_timeout":
            continue
        progress_age = _progress_by_family.get(family)
        if _tick_meaningful_progress_signals(tick):
            continue
        if progress_age is not None and age > progress_age:
            continue
        failures_by_family.setdefault(family, []).append((age, tick))

    current_pos = current_summary.get("position")
    current_counts = dict(current_summary.get("inventory_counts") or {})
    current_dim = current_summary.get("dimension")
    current_bucket = pos_bucket(current_pos)

    # --- RA scoped failure collection (extended window, grouped by position+access sig) ---
    # Each group uses a key: resource_acquisition:<resource>:<dim>:<bucket>:<access_sig>
    # so that failures with different failure modes or at different positions never merge.
    ra_failures_by_scoped: dict[str, tuple[str, list[tuple[int, dict[str, Any]]]]] = {}
    for age, tick in enumerate(ra_ticks):
        if _tick_ok(tick) is not False:
            continue
        action = tick.get("action")
        if not isinstance(action, str):
            continue
        args = tick.get("args") if isinstance(tick.get("args"), dict) else {}
        family = action_family_key(action, args)
        if not family or not family.startswith("resource_acquisition:"):
            continue
        if _tick_failure_type(tick) == "partial_progress_timeout":
            continue
        if _tick_meaningful_progress_signals(tick):
            continue
        progress_age = _progress_by_family.get(family)
        if progress_age is not None and age > progress_age:
            continue
        resource = family[len("resource_acquisition:"):]
        after_state = tick.get("after_state") or _decode_jsonish(tick.get("after_state_json"))
        tick_pos = _position_from_tick_state(after_state)
        tick_dim = (
            (after_state.get("summary") or after_state).get("dimension")
            if isinstance(after_state, dict) else None
        )
        access_sig = _access_sig_from_verifier(tick)
        scoped_key = resource_acquisition_scoped_key(resource, tick_dim, tick_pos, access_sig)
        if scoped_key not in ra_failures_by_scoped:
            ra_failures_by_scoped[scoped_key] = (family, [])
        ra_failures_by_scoped[scoped_key][1].append((age, tick))

    blocked: list[dict[str, Any]] = []
    for family, pairs in failures_by_family.items():
        if family in _successful_families:
            continue
        # Clear position-specific drop families (drop_collection:<resource>:<pos>) when
        # the resource was successfully acquired (drop_collection:<resource> cleared).
        if family.startswith("drop_collection:"):
            rest = family[len("drop_collection:"):]
            if ":" in rest:
                base = f"drop_collection:{rest.split(':')[0]}"
                if base in _successful_families:
                    continue
        if not pairs:
            continue

        is_expensive_family = any(t.get("action") in _EXPENSIVE_ACTIONS for (_, t) in pairs)

        # --- Fast-block path: expensive actions with timeout failures ---
        fast_blocked = False
        created_tick: int = pairs[0][0]
        created_reason: str = f"{len(pairs)}_failures_in_window"

        if is_expensive_family:
            recent_timeout_pairs = [
                (age, tick) for (age, tick) in pairs
                if age < _FAST_BLOCK_WINDOW and _is_timeout_tick(tick)
            ]
            if len(recent_timeout_pairs) >= _FAST_BLOCK_MIN_TIMEOUTS:
                oldest_fast = recent_timeout_pairs[-1][1]
                oldest_fast_after = (
                    oldest_fast.get("after_state")
                    or _decode_jsonish(oldest_fast.get("after_state_json"))
                )
                oldest_fast_pos = _position_from_tick_state(oldest_fast_after)
                oldest_fast_counts = _inventory_counts_from_tick_state(oldest_fast_after)
                oldest_fast_dim = (
                    (oldest_fast_after.get("summary") or oldest_fast_after).get("dimension")
                    if isinstance(oldest_fast_after, dict) else None
                )
                inv_changed_fast = oldest_fast_counts != current_counts
                dim_changed_fast = bool(oldest_fast_dim and current_dim and oldest_fast_dim != current_dim)
                if (
                    _pos_distance(oldest_fast_pos, current_pos) <= POSITION_MEANINGFUL_DELTA_BLOCKS
                    and not inv_changed_fast
                    and not dim_changed_fast
                ):
                    fast_blocked = True
                    # created_tick = age of the timeout that completed the threshold
                    created_tick = recent_timeout_pairs[_FAST_BLOCK_MIN_TIMEOUTS - 1][0]
                    created_reason = (
                        f"{len(recent_timeout_pairs)}_timeouts_in_{_FAST_BLOCK_WINDOW}"
                        "_ticks_no_position_change"
                    )

        # --- Standard path ---
        if not fast_blocked:
            if len(pairs) < min_failures:
                continue
            oldest_tick = pairs[-1][1]
            oldest_after = oldest_tick.get("after_state") or _decode_jsonish(oldest_tick.get("after_state_json"))
            oldest_pos = _position_from_tick_state(oldest_after)
            oldest_counts = _inventory_counts_from_tick_state(oldest_after)
            oldest_dim = (
                (oldest_after.get("summary") or oldest_after).get("dimension")
                if isinstance(oldest_after, dict)
                else None
            )

            pos_moved = _pos_distance(oldest_pos, current_pos) > POSITION_MEANINGFUL_DELTA_BLOCKS
            inventory_changed = oldest_counts != current_counts
            dimension_changed = bool(oldest_dim and current_dim and oldest_dim != current_dim)

            if pos_moved or inventory_changed or dimension_changed:
                continue

            created_tick = pairs[min_failures - 1][0]
            created_reason = (
                f"{len(pairs)}_failures_expensive_action"
                if is_expensive_family
                else f"{len(pairs)}_failures_in_window"
            )

        failure_types = list(dict.fromkeys(
            ft for (_, t) in pairs
            if (ft := _tick_failure_type(t)) and ft not in {"", "none"}
        ))

        newest_tick = pairs[0][1]
        newest_verifier = (
            newest_tick.get("verifier") if isinstance(newest_tick.get("verifier"), dict)
            else _decode_jsonish(newest_tick.get("verifier_json"))
        )
        last_failed_because: list[dict[str, Any]] = []
        if isinstance(newest_verifier, dict):
            raw_fb = newest_verifier.get("failed_because")
            if isinstance(raw_fb, list):
                last_failed_because = raw_fb

        # When mining succeeded but drop collection failed, do not block the broad
        # resource_acquisition:* family.  Use the narrower drop_collection:* family
        # so the LLM knows the issue is drop accessibility, not coal availability.
        # For deep/unreachable drops, use a position-specific key so resource_acquisition:*
        # is never blocked and the LLM knows only that specific drop is abandoned.
        dc_info = (
            _dc_info_by_resource_family.get(family)
            if family.startswith("resource_acquisition:")
            else None
        )
        if dc_info is not None:
            resource = family[len("resource_acquisition:"):]
            pos_specific = dc_info.get("drop_collection_family")
            effective_family = pos_specific if pos_specific else f"drop_collection:{resource}"
        else:
            effective_family = family
        blocked.append({
            "family": effective_family,
            "blocked": True,
            "failure_count": len(pairs),
            "last_failures": failure_types,
            "failed_because": last_failed_because,
            "repeatable_now": False,
            "unblock_condition": _family_unblock_condition(effective_family),
            "expensive_action_family": is_expensive_family,
            "blocked_created_tick": created_tick,
            "blocked_created_reason": created_reason,
            **(dc_info if dc_info is not None else {}),
        })

    # --- RA scoped block building ---
    # Groups that share the same position bucket AND same access signature contribute
    # to a block keyed by the broad family so find_blocked_family still works.
    # Blocks only form when the bot is still in the same 8-block bucket as the failures.
    if not _ra_cleared_by_exploration:
        for scoped_key, (broad_family, ra_pairs) in ra_failures_by_scoped.items():
            if broad_family in _successful_families:
                continue
            if not ra_pairs:
                continue

            # Position-bucket guard: current bucket must match the failure bucket.
            # Extract bucket from scoped_key segments: ra:<resource>:<dim>:<bucket>:<sig>
            sk_parts = scoped_key.split(":")
            failure_bucket = sk_parts[3] if len(sk_parts) >= 5 else "unknown"
            if current_bucket != failure_bucket:
                continue  # bot is in a different area → no block

            is_expensive_ra = any(t.get("action") in _EXPENSIVE_ACTIONS for (_, t) in ra_pairs)

            ra_fast_blocked = False
            ra_created_tick: int = ra_pairs[0][0]
            ra_created_reason: str = f"{len(ra_pairs)}_ra_failures_scoped"

            if is_expensive_ra:
                ra_timeout_pairs = [
                    (age, tick) for (age, tick) in ra_pairs
                    if age < _FAST_BLOCK_WINDOW and _is_timeout_tick(tick)
                ]
                if len(ra_timeout_pairs) >= _FAST_BLOCK_MIN_TIMEOUTS:
                    oldest_rt = ra_timeout_pairs[-1][1]
                    oldest_rt_after = (
                        oldest_rt.get("after_state")
                        or _decode_jsonish(oldest_rt.get("after_state_json"))
                    )
                    oldest_rt_pos = _position_from_tick_state(oldest_rt_after)
                    oldest_rt_counts = _inventory_counts_from_tick_state(oldest_rt_after)
                    oldest_rt_dim = (
                        (oldest_rt_after.get("summary") or oldest_rt_after).get("dimension")
                        if isinstance(oldest_rt_after, dict) else None
                    )
                    if (
                        _pos_distance(oldest_rt_pos, current_pos) <= POSITION_MEANINGFUL_DELTA_BLOCKS
                        and oldest_rt_counts == current_counts
                        and not (oldest_rt_dim and current_dim and oldest_rt_dim != current_dim)
                    ):
                        ra_fast_blocked = True
                        ra_created_tick = ra_timeout_pairs[_FAST_BLOCK_MIN_TIMEOUTS - 1][0]
                        ra_created_reason = (
                            f"{len(ra_timeout_pairs)}_timeouts_in_{_FAST_BLOCK_WINDOW}"
                            "_ticks_no_position_change"
                        )

            if not ra_fast_blocked:
                if len(ra_pairs) < min_failures:
                    continue
                oldest_ra = ra_pairs[-1][1]
                oldest_ra_after = (
                    oldest_ra.get("after_state")
                    or _decode_jsonish(oldest_ra.get("after_state_json"))
                )
                oldest_ra_pos = _position_from_tick_state(oldest_ra_after)
                oldest_ra_counts = _inventory_counts_from_tick_state(oldest_ra_after)
                oldest_ra_dim = (
                    (oldest_ra_after.get("summary") or oldest_ra_after).get("dimension")
                    if isinstance(oldest_ra_after, dict) else None
                )
                if (
                    _pos_distance(oldest_ra_pos, current_pos) > POSITION_MEANINGFUL_DELTA_BLOCKS
                    or oldest_ra_counts != current_counts
                    or (oldest_ra_dim and current_dim and oldest_ra_dim != current_dim)
                ):
                    continue
                ra_created_tick = ra_pairs[min_failures - 1][0]
                ra_created_reason = f"{len(ra_pairs)}_ra_failures_scoped"

            # TTL: if the qualifying failure is older than RA_BLOCK_TTL_TICKS, the block expired.
            if ra_created_tick >= RA_BLOCK_TTL_TICKS:
                continue

            ra_failure_types = list(dict.fromkeys(
                ft for (_, t) in ra_pairs
                if (ft := _tick_failure_type(t)) and ft not in {"", "none"}
            ))
            ra_newest = ra_pairs[0][1]
            ra_newest_verifier = (
                ra_newest.get("verifier") if isinstance(ra_newest.get("verifier"), dict)
                else _decode_jsonish(ra_newest.get("verifier_json"))
            )
            ra_failed_because: list[dict[str, Any]] = []
            if isinstance(ra_newest_verifier, dict):
                raw_rfb = ra_newest_verifier.get("failed_because")
                if isinstance(raw_rfb, list):
                    ra_failed_because = raw_rfb

            expires_in = max(0, RA_BLOCK_TTL_TICKS - ra_created_tick)

            # Check for drop_collection redirect (same logic as standard path).
            dc_info_ra = _dc_info_by_resource_family.get(broad_family)
            if dc_info_ra is not None:
                ra_resource = broad_family[len("resource_acquisition:"):]
                pos_specific_ra = dc_info_ra.get("drop_collection_family")
                effective_ra_family = pos_specific_ra if pos_specific_ra else f"drop_collection:{ra_resource}"
            else:
                effective_ra_family = broad_family

            blocked.append({
                "family": effective_ra_family,
                "blocked": True,
                "failure_count": len(ra_pairs),
                "last_failures": ra_failure_types,
                "failed_because": ra_failed_because,
                "repeatable_now": False,
                "unblock_condition": _family_unblock_condition(effective_ra_family),
                "expensive_action_family": is_expensive_ra,
                "blocked_created_tick": ra_created_tick,
                "blocked_created_reason": ra_created_reason,
                "blocked_key": scoped_key,
                "blocked_scope": f"dim={current_dim or 'unknown'} bucket={current_bucket}",
                "blocked_expires_in_ticks": expires_in,
                "unblock_conditions": [
                    "move_8_blocks",
                    "explore_success",
                    "new_target_seen",
                    "target_signature_changed",
                    "ttl_expired",
                ],
                **(dc_info_ra if dc_info_ra is not None else {}),
            })

    # Post-build softening: if any recent tick for a resource_acquisition (or its
    # drop_collection sibling) family had meaningful progress, mark the block
    # repeatable_now so the LLM can retry immediately.
    softened: list[dict[str, Any]] = []
    for bf in blocked:
        bf_family = bf.get("family", "")
        # Determine the resource_acquisition family to check for progress signals.
        if bf_family.startswith("resource_acquisition:"):
            check_family = bf_family
        elif bf_family.startswith("drop_collection:"):
            check_family = f"resource_acquisition:{bf_family[len('drop_collection:'):]}"
        else:
            softened.append(bf)
            continue
        recent_progress = any(
            _tick_ok(t) is False
            and _tick_failure_type(t) == "partial_progress_timeout"
            for t in ticks
            if isinstance(t, dict)
            and action_family_key(
                t.get("action", ""),
                t.get("args") if isinstance(t.get("args"), dict) else {},
            ) == check_family
        ) or any(
            _tick_ok(t) is False
            and bool(_tick_meaningful_progress_signals(t))
            for t in ticks
            if isinstance(t, dict)
            and action_family_key(
                t.get("action", ""),
                t.get("args") if isinstance(t.get("args"), dict) else {},
            ) == check_family
        )
        if recent_progress:
            bf = dict(bf)
            bf["repeatable_now"] = True
            bf["unblock_condition_change_reason"] = "partial_progress_made"
        softened.append(bf)
    blocked = softened

    # --- Deep/unreachable drop blocks (informational, position-specific) ---
    # These ticks are partial_progress_timeout so they never enter failures_by_family.
    # We create one block per position-specific family directly from dc_info.
    # find_blocked_family won't match these against mine_* calls (wrong prefix),
    # so they are purely informational context for the LLM.
    for ra_family, dc_info in _dc_info_by_resource_family.items():
        pos_family = dc_info.get("drop_collection_family")
        if not pos_family:
            continue
        if any(bf.get("family") == pos_family for bf in blocked):
            continue
        if pos_family in _successful_families:
            continue
        _rest = pos_family[len("drop_collection:"):]
        if ":" in _rest and f"drop_collection:{_rest.split(':')[0]}" in _successful_families:
            continue
        blocked.append({
            "family": pos_family,
            "blocked": True,
            "failure_count": 1,
            "last_failures": ["drop_deep_unreachable"],
            "failed_because": [],
            "repeatable_now": False,
            "unblock_condition": _family_unblock_condition(pos_family),
            "expensive_action_family": True,
            "blocked_created_tick": 0,
            "blocked_created_reason": "deep_drop_unreachable",
            **{k: v for k, v in dc_info.items() if k != "blocked_family_type"},
        })

    # --- Schema families: invalid_args with missing required arg → blocked after 1 failure ---
    # These blocks are arg-based: they clear when the LLM provides the missing arg,
    # not when position or inventory changes. The arg check is in find_blocked_family.
    # They also clear when the action succeeds (tracked per action name, not family key).
    _successful_actions: set[str] = {
        t.get("action") for t in ticks
        if _tick_ok(t) is True and isinstance(t.get("action"), str)
    }

    schema_failures: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for age, tick in enumerate(ticks):
        if _tick_ok(tick) is not False:
            continue
        action = tick.get("action")
        if not isinstance(action, str):
            continue
        v = (
            tick.get("verifier") if isinstance(tick.get("verifier"), dict)
            else _decode_jsonish(tick.get("verifier_json"))
        )
        if not isinstance(v, dict) or v.get("failure_type") not in {"invalid_args", "invalid_action_args"}:
            continue
        fb = v.get("failed_because")
        if not isinstance(fb, list):
            continue
        schema_key = schema_blocked_family_key(action, fb)
        if schema_key is None:
            continue
        schema_failures.setdefault(schema_key, []).append((age, tick))

    for family, pairs in schema_failures.items():
        # Clear if the action succeeded anywhere in the window.
        action_in_family = family[len("action_schema:"):].split(":")[0]
        if action_in_family in _successful_actions:
            continue
        newest_tick = pairs[0][1]
        newest_verifier = (
            newest_tick.get("verifier") if isinstance(newest_tick.get("verifier"), dict)
            else _decode_jsonish(newest_tick.get("verifier_json"))
        )
        last_failed_because = []
        if isinstance(newest_verifier, dict):
            raw_fb = newest_verifier.get("failed_because")
            if isinstance(raw_fb, list):
                last_failed_because = raw_fb
        blocked.append({
            "family": family,
            "blocked": True,
            "failure_count": len(pairs),
            "last_failures": ["invalid_args"],
            "failed_because": last_failed_because,
            "repeatable_now": False,
            "unblock_condition": _family_unblock_condition(family),
            "expensive_action_family": False,
            "blocked_created_tick": pairs[0][0],
            "blocked_created_reason": "invalid_args_schema_violation",
        })

    return blocked


def find_blocked_family(
    action: str,
    args: dict[str, Any] | None,
    recent_ticks: list[dict[str, Any]],
    current_summary: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the blocked-family record for this action, or None if not blocked.

    Called from the pre-execution path in autonomy.py before sending to the bridge.
    Schema families (action_schema:*) are checked first and cleared when the LLM
    provides the previously missing arg. Standard families are checked second.
    """
    blocked = _blocked_action_families(recent_ticks, current_summary)
    _args = args or {}

    # Schema families take priority — args-based unblock is more specific than
    # position/inventory checks and applies even when action_family_key returns None.
    schema_prefix = f"action_schema:{action}:"
    for bf in blocked:
        bf_family = bf.get("family", "")
        if not bf_family.startswith(schema_prefix):
            continue
        constraint = bf_family[len(schema_prefix):]
        if constraint.startswith("missing_"):
            missing_arg = constraint[len("missing_"):]
            if not _args.get(missing_arg):  # arg still absent or empty → still blocked
                return bf

    # Standard family check
    family = action_family_key(action, args)
    if family is None:
        return None
    match = next((bf for bf in blocked if bf.get("family") == family), None)
    if match is not None:
        return match

    # For resource_acquisition:* families also check the narrower drop_collection:* sibling.
    # A drop_collection block blocks the same action at the same position; clearing happens
    # when position changes meaningfully or the resource is successfully collected.
    if family.startswith("resource_acquisition:"):
        dc_family = f"drop_collection:{family[len('resource_acquisition:'):]}"
        return next((bf for bf in blocked if bf.get("family") == dc_family), None)

    return None


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
        "nearest_station_distance": result.get("nearest_station_distance") or verifier.get("nearest_station_distance"),
        "usable_radius": result.get("usable_radius") or verifier.get("usable_radius"),
        "missing_materials": _normalize_missing_materials(
            result.get("missing_materials") or verifier.get("missing_materials")
        ),
        "possible_next_actions": result.get("possible_next_actions") or verifier.get("possible_next_actions"),
        "lesson": result.get("lesson") or verifier.get("lesson"),
        "verifier": {
            "failure_type": verifier.get("failure_type"),
            "stop_reason": verifier.get("stop_reason"),
            "suggested_next_action": verifier.get("suggested_next_action"),
            "recommendation": _short(verifier.get("recommendation")),
            "failed_because": verifier.get("failed_because") or None,
            "repeatable_now": verifier.get("repeatable_now"),
            "repeat_condition": verifier.get("repeat_condition") or None,
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
        # Re-normalize missing_materials: _result_flags may have returned raw bot dicts.
        if "missing_materials" in compact:
            compact["missing_materials"] = _normalize_missing_materials(compact["missing_materials"])
    return compact


def _compact_last_action_result_for_llm(
    last_result: dict[str, Any] | None,
    show_pna: bool = False,
) -> dict[str, Any] | None:
    """Like _compact_last_action_result but strips action-suggestion fields for the LLM."""
    compact = _compact_last_action_result(last_result)
    if compact is None:
        return None
    if not show_pna:
        compact.pop("suggested_next_action", None)
        compact.pop("fallback_suggested_next_action", None)
        compact.pop("possible_next_actions", None)
        verifier = compact.get("verifier")
        if isinstance(verifier, dict):
            verifier.pop("suggested_next_action", None)
    return compact


def _compact_failure_summary(
    last_result: dict[str, Any] | None,
    show_pna: bool = False,
) -> dict[str, Any] | None:
    compact = _compact_last_action_result(last_result)
    if not _last_failure_included(compact):
        return None

    failure_type = compact.get("failure_type")
    is_partial_progress = failure_type == "partial_progress_timeout"

    summary: dict[str, Any] = {
        "action": compact.get("action"),
        "ok": compact.get("ok"),
        "error": compact.get("error"),
        "failure_type": failure_type,
        "stop_reason": compact.get("stop_reason"),
        "needed": compact.get("needed"),
        "station_needed": compact.get("station_needed"),
        "nearest_station_distance": compact.get("nearest_station_distance"),
        "usable_radius": compact.get("usable_radius"),
        "missing_materials": compact.get("missing_materials"),
        "lesson": compact.get("lesson"),
        "can_retry": compact.get("can_retry"),
    }

    if show_pna:
        summary["suggested_next_action"] = compact.get("suggested_next_action")
        summary["fallback_suggested_next_action"] = compact.get("fallback_suggested_next_action")
        summary["possible_next_actions"] = compact.get("possible_next_actions")

    # For partial_progress_timeout expose factual progress fields instead of action hints.
    if is_partial_progress:
        verifier = (compact.get("verifier") or {})
        raw_result = (last_result or {}).get("result") if isinstance((last_result or {}).get("result"), dict) else {}
        diag = verifier.get("diagnostics") or compact.get("diagnostics") or {}
        summary["partial_success"] = True
        if diag.get("continuation_relevant"):
            summary["continuation_relevant"] = True
        if diag.get("progress_made"):
            summary["progress_made"] = True
        if diag.get("distance_moved") is not None:
            summary["distance_moved"] = diag["distance_moved"]
        if diag.get("inventory_delta"):
            summary["inventory_delta"] = diag["inventory_delta"]
        if diag.get("accessCandidatesFound") is not None:
            summary["accessCandidatesFound"] = diag["accessCandidatesFound"]
        if diag.get("excavatedBlocks") is not None:
            summary["excavatedBlocks"] = diag["excavatedBlocks"]

    if summary.get("failure_type") == "no_safe_workspace" or summary.get("stop_reason") == "area_cramped":
        summary["priority"] = "placement_repair"
        summary["repair_hint"] = "choose setup_workspace or find_safe_workspace or return_to_surface before retrying placement"
    elif summary.get("failure_type") == "missing_station" or summary.get("stop_reason") in {"no_crafting_table_nearby", "no_furnace_nearby"}:
        station = summary.get("station_needed", "station")
        if summary.get("stop_reason") == "station_visible_but_too_far":
            summary["repair_hint"] = "station is visible but outside usable radius; approach_station, return_to_workspace, or setup_workspace are valid choices"
        else:
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
        "nearest_station_distance",
        "nearest_station_position",
        "usable_radius",
        "missing_materials",
        "possible_next_actions",
        "lesson",
        "inventory",
        "skipped_execution",
        "blocked_family",
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
    direct_failure_type = last_action_result.get("failure_type")
    return bool(
        last_action_result.get("ok") is False
        or last_action_result.get("error")
        or (direct_failure_type and direct_failure_type != "none")
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


def _unresolved_failure_from_ticks(
    recent_ticks: list[dict[str, Any]],
    current_facts: dict[str, Any],
) -> dict[str, Any] | None:
    successful_actions: set[str] = set()
    material_successes: list[str] = []

    for age, tick in enumerate(recent_ticks):
        if not isinstance(tick, dict):
            continue

        action = tick.get("action")
        ok = _tick_ok(tick)
        if ok is True:
            if isinstance(action, str):
                successful_actions.add(action)
                if not is_observation_action(action) and _tick_materially_changed(tick):
                    material_successes.append(action)
            continue

        last_result = _tick_to_last_action_result(tick)
        compact = _compact_last_action_result(last_result)
        if not _last_failure_included(compact):
            continue
        if is_observation_action(compact.get("action")):
            continue

        failed_action = compact.get("action")
        if isinstance(failed_action, str) and failed_action in successful_actions:
            continue

        unresolved = _enrich_unresolved_failure(compact, current_facts, age)
        if _is_stale_failure(unresolved, current_facts):
            continue
        if _missing_condition_resolved(unresolved, current_facts):
            continue
        if _resolved_by_related_material_success(unresolved, material_successes):
            continue
        return unresolved

    return None


def _tick_to_last_action_result(tick: dict[str, Any]) -> dict[str, Any]:
    result = tick.get("result") if isinstance(tick.get("result"), dict) else _decode_jsonish(tick.get("result_json"))
    verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else _decode_jsonish(tick.get("verifier_json"))
    return {
        "action": tick.get("action"),
        "ok": _tick_ok(tick),
        "error": tick.get("error"),
        "result": result if isinstance(result, dict) else {},
        "verifier": verifier if isinstance(verifier, dict) else {},
    }


def _tick_ok(tick: dict[str, Any]) -> bool | None:
    ok = tick.get("ok")
    if isinstance(ok, bool):
        return ok
    if isinstance(ok, int):
        return bool(ok)
    return None


def _decode_jsonish(value: Any) -> Any:
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _progress_monitor_from_ticks(recent_ticks: list[dict[str, Any]], current_summary: dict[str, Any]) -> dict[str, Any]:
    ticks = [tick for tick in recent_ticks if isinstance(tick, dict)]
    window = ticks[:5]
    changes_by_age = [_meaningful_changes_for_tick(tick) for tick in ticks]
    recent_changes = changes_by_age[:5]

    inventory_changed_recently = any("inventory" in changes for changes in recent_changes)
    position_changed_recently = any("position" in changes or "dimension" in changes for changes in recent_changes)
    world_observation_changed_recently = any("world_observation" in changes or "station_state" in changes or "target_access" in changes for changes in recent_changes)
    danger_changed_recently = any("danger" in changes or "vitals" in changes for changes in recent_changes)
    state_changed_recently = any(changes for changes in recent_changes)

    repeated_action = _recent_action_repetition(ticks)
    low_info_run = _recent_low_information_run(ticks)
    low_info_changes = changes_by_age[:low_info_run]
    danger_now = _summary_has_danger(current_summary)
    low_information_loop = (
        low_info_run >= 3
        and not any(changes for changes in low_info_changes)
        and not danger_now
        and not danger_changed_recently
    )

    last_meaningful_changes = _last_meaningful_changes(ticks, changes_by_age, limit=5)
    stagnation_reason = None
    if low_information_loop:
        stagnation_reason = "Repeated sensing/status actions without new inventory, position, or world changes."
    elif not state_changed_recently and ticks:
        stagnation_reason = "Recent actions did not change inventory, position, danger, or known world information."

    return {
        "state_changed_recently": state_changed_recently,
        "inventory_changed_recently": inventory_changed_recently,
        "position_changed_recently": position_changed_recently,
        "world_observation_changed_recently": world_observation_changed_recently,
        "danger_changed_recently": danger_changed_recently,
        "recent_action_repetition": repeated_action,
        "low_information_loop": low_information_loop,
        "ticks_since_last_material_progress": _ticks_since_change(changes_by_age, {"inventory", "action_effect"}),
        "ticks_since_last_position_progress": _ticks_since_change(changes_by_age, {"position", "dimension"}),
        "last_meaningful_changes": last_meaningful_changes,
        "stagnation_reason": stagnation_reason,
    }


def _meaningful_changes_for_tick(tick: dict[str, Any]) -> set[str]:
    before_state = tick.get("before_state") or _decode_jsonish(tick.get("before_state_json"))
    after_state = tick.get("after_state") or _decode_jsonish(tick.get("after_state_json"))
    before_summary = _tick_state_summary(before_state)
    after_summary = _tick_state_summary(after_state)
    changes: set[str] = set()

    if _inventory_counts_from_tick_state(before_state) != _inventory_counts_from_tick_state(after_state):
        changes.add("inventory")

    before_pos = _position_from_tick_state(before_state)
    after_pos = _position_from_tick_state(after_state)
    if before_pos and after_pos and _position_distance(before_pos, after_pos) > 1.0:
        changes.add("position")

    if _dimension_from_summary(before_summary) != _dimension_from_summary(after_summary):
        changes.add("dimension")

    if _vitals_signature(before_summary) != _vitals_signature(after_summary):
        changes.add("vitals")
    if _danger_signature(before_summary) != _danger_signature(after_summary):
        changes.add("danger")

    before_world = _world_observation_signature(before_summary)
    after_world = _world_observation_signature(after_summary)
    result = tick.get("result") if isinstance(tick.get("result"), dict) else _decode_jsonish(tick.get("result_json"))
    result_world = _world_observation_signature(result if isinstance(result, dict) else {})
    if before_world != after_world or (_world_signature_has_info(result_world) and result_world != before_world):
        changes.add("world_observation")

    if _station_signature(before_summary) != _station_signature(after_summary):
        changes.add("station_state")

    if isinstance(result, dict) and any(key in result for key in ("targetCandidatesFound", "accessCandidatesFound", "exposedCandidatesFound")):
        changes.add("target_access")

    action = tick.get("action")
    verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else _decode_jsonish(tick.get("verifier_json"))
    verifier_success = isinstance(verifier, dict) and verifier.get("success") is True
    if _tick_ok(tick) is True and isinstance(action, str) and not is_low_information_action(action) and verifier_success:
        changes.add("action_effect")

    return changes


def _repeated_failed_action_loop(
    recent_ticks: list[dict[str, Any]],
    progress_monitor: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a diagnostic if the same non-observation action failed ≥2 times in a row."""
    pm = progress_monitor or {}
    repetition = pm.get("recent_action_repetition")
    if not isinstance(repetition, dict):
        return None
    action = repetition.get("action")
    count = repetition.get("count")
    if not isinstance(action, str) or not isinstance(count, int) or count < 2:
        return None
    if is_observation_action(action):
        return None
    ticks = [t for t in recent_ticks if isinstance(t, dict)]
    failed_count = sum(1 for t in ticks[:count] if t.get("action") == action and _tick_ok(t) is False)
    if failed_count < 2:
        return None
    return {
        "action": action,
        "count": count,
        "failed_count": failed_count,
        "fact": f"{action} failed {failed_count}/{count} times in a row — may be stuck",
    }


def _invalid_action_loop(recent_ticks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return a diagnostic if recent ticks contain invalid_action or invalid_action_args failures."""
    invalid_types = {"invalid_action", "invalid_action_args"}
    actions: list[str] = []
    for tick in recent_ticks:
        if not isinstance(tick, dict):
            continue
        verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else _decode_jsonish(tick.get("verifier_json"))
        ft = (verifier or {}).get("failure_type") if isinstance(verifier, dict) else None
        if ft in invalid_types:
            action = tick.get("action")
            if isinstance(action, str):
                actions.append(action)
    if not actions:
        return None
    return {
        "invalid_action_count": len(actions),
        "actions": actions,
        "fact": f"{len(actions)} recent tick(s) chose invalid actions: {', '.join(actions)}",
    }


def _recent_action_repetition(ticks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not ticks:
        return None
    first_action = ticks[0].get("action")
    if not isinstance(first_action, str):
        return None
    count = 0
    for tick in ticks:
        if tick.get("action") != first_action:
            break
        count += 1
    return {"action": first_action, "count": count}


def _recent_low_information_run(ticks: list[dict[str, Any]]) -> int:
    count = 0
    for tick in ticks:
        action = tick.get("action")
        if not is_low_information_action(action):
            break
        count += 1
    return count


def _ticks_since_change(changes_by_age: list[set[str]], change_types: set[str]) -> int:
    for age, changes in enumerate(changes_by_age):
        if changes & change_types:
            return age
    return len(changes_by_age)


def _last_meaningful_changes(ticks: list[dict[str, Any]], changes_by_age: list[set[str]], limit: int) -> list[str]:
    labels: list[str] = []
    for tick, changes in zip(ticks, changes_by_age, strict=False):
        action = tick.get("action")
        action_name = action if isinstance(action, str) else "action"
        if "inventory" in changes:
            labels.append(f"{action_name}_inventory_changed")
        if "position" in changes or "dimension" in changes:
            labels.append(f"{action_name}_position_changed")
        if "world_observation" in changes or "station_state" in changes:
            labels.append(f"{action_name}_world_info_changed")
        if "danger" in changes or "vitals" in changes:
            labels.append(f"{action_name}_danger_or_vitals_changed")
        if not changes.isdisjoint({"action_effect", "target_access"}) and not any(label.startswith(f"{action_name}_") for label in labels[-4:]):
            labels.append(f"{action_name}_succeeded")
        if len(labels) >= limit:
            break
    return labels[:limit]


def _position_distance(before: dict[str, Any], after: dict[str, Any]) -> float:
    try:
        dx = float(after.get("x", 0)) - float(before.get("x", 0))
        dy = float(after.get("y", 0)) - float(before.get("y", 0))
        dz = float(after.get("z", 0)) - float(before.get("z", 0))
    except (TypeError, ValueError):
        return 0.0
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def _dimension_from_summary(summary: dict[str, Any]) -> str | None:
    value = summary.get("dimension")
    return str(value) if value is not None else None


def _vitals_signature(summary: dict[str, Any]) -> tuple[Any, Any]:
    return summary.get("health"), summary.get("food")


def _danger_signature(summary: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    movement = summary.get("movement") if isinstance(summary.get("movement"), dict) else {}
    return (
        bool(summary.get("hostile_nearby")),
        bool(movement.get("inLava")),
        bool(movement.get("inWater")),
        summary.get("air"),
    )


def _summary_has_danger(summary: dict[str, Any]) -> bool:
    movement = summary.get("movement") if isinstance(summary.get("movement"), dict) else {}
    health = summary.get("health")
    return bool(
        summary.get("hostile_nearby")
        or movement.get("inLava")
        or (movement.get("inWater") and isinstance(summary.get("air"), (int, float)) and summary.get("air") <= 80)
        or (isinstance(health, (int, float)) and health <= 6)
    )


def _world_observation_signature(summary: dict[str, Any]) -> tuple[Any, Any]:
    if not isinstance(summary, dict):
        return (), ()
    block_counts = summary.get("nearby_block_counts") or summary.get("nearbyBlockCounts") or {}
    blocks = summary.get("nearby_blocks") or summary.get("nearbyBlocks") or {}
    entities = summary.get("nearby_entities") or summary.get("nearbyEntities") or []
    if not block_counts and isinstance(summary.get("nearbyBlockCounts"), dict):
        block_counts = summary["nearbyBlockCounts"]
    if not entities and isinstance(summary.get("nearbyEntities"), list):
        entities = summary["nearbyEntities"]
    block_sig = tuple(sorted((str(k), v) for k, v in block_counts.items())) if isinstance(block_counts, dict) else ()
    block_detail_sig = tuple(sorted(str(k) for k, v in blocks.items() if v)) if isinstance(blocks, dict) else ()
    entity_sig = tuple(sorted(
        str(entity.get("name") or entity.get("type") or entity.get("username") or "entity")
        for entity in entities
        if isinstance(entity, dict)
    )) if isinstance(entities, list) else ()
    return (block_sig, block_detail_sig), entity_sig


def _world_signature_has_info(signature: tuple[Any, Any]) -> bool:
    if not isinstance(signature, tuple) or len(signature) != 2:
        return False
    block_part, entity_part = signature
    if isinstance(block_part, tuple) and any(bool(part) for part in block_part):
        return True
    return bool(entity_part)


def _station_signature(summary: dict[str, Any]) -> tuple[Any, ...]:
    blocks = summary.get("nearby_blocks") or summary.get("nearbyBlocks") or {}
    if not isinstance(blocks, dict):
        return ()
    sig: list[tuple[str, Any]] = []
    for station in ("crafting_table", "furnace", "chest"):
        value = blocks.get(station)
        if isinstance(value, dict):
            sig.append((station, value.get("distance"), _position_tuple(value.get("position"))))
        elif value:
            sig.append((station, True))
    return tuple(sig)


def _position_tuple(position: Any) -> tuple[Any, Any, Any] | None:
    if not isinstance(position, dict):
        return None
    return position.get("x"), position.get("y"), position.get("z")


def _observation_freshness_from_ticks(
    recent_ticks: list[dict[str, Any]],
    progress_monitor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repeated_sensing_count = 0
    last_observation_tick: int | None = None
    last_observation_summary: dict[str, Any] | None = None

    for age, tick in enumerate(recent_ticks):
        if not isinstance(tick, dict):
            continue
        action = tick.get("action")
        if not isinstance(action, str) or action not in FRESH_OBSERVATION_ACTIONS:
            continue
        if _tick_ok(tick) is not True:
            continue
        if age < 2:
            repeated_sensing_count += 1
        if last_observation_summary is None:
            last_observation_tick = age
            last_observation_summary = _compact_observation_tick(tick, age, recent_ticks)

    if isinstance(progress_monitor, dict) and progress_monitor.get("low_information_loop"):
        repetition = progress_monitor.get("recent_action_repetition")
        if isinstance(repetition, dict) and isinstance(repetition.get("count"), int):
            repeated_sensing_count = max(repeated_sensing_count, repetition["count"])

    return {
        "observation_fresh": repeated_sensing_count > 0 or bool(progress_monitor and progress_monitor.get("low_information_loop")),
        "repeated_sensing_count": repeated_sensing_count,
        "last_observation_tick": last_observation_tick,
        "last_observation_summary": last_observation_summary,
    }


def _compact_observation_tick(tick: dict[str, Any], age: int, recent_ticks: list[dict[str, Any]]) -> dict[str, Any]:
    result = tick.get("result") if isinstance(tick.get("result"), dict) else _decode_jsonish(tick.get("result_json"))
    after_state = tick.get("after_state") or _decode_jsonish(tick.get("after_state_json"))
    after_summary = _tick_state_summary(after_state)

    compact: dict[str, Any] = {
        "action": tick.get("action"),
        "age_ticks": age,
        "moved_since_observation": _moved_since_observation(age, recent_ticks),
    }
    position = _position_from_tick_state(after_state)
    if position:
        compact["position"] = position

    inventory_counts = _inventory_counts_from_tick_state(after_state)
    if inventory_counts:
        compact["inventory_counts"] = inventory_counts

    if isinstance(result, dict):
        if isinstance(result.get("radius"), (int, float)):
            compact["radius"] = result.get("radius")
        if isinstance(result.get("counts"), dict):
            compact["inventory_counts"] = {
                str(k): int(v) for k, v in result["counts"].items()
                if isinstance(v, int) and not isinstance(v, bool)
            }
        nearby_block_counts = result.get("nearbyBlockCounts") or result.get("nearby_block_counts")
        if isinstance(nearby_block_counts, dict):
            compact["nearbyBlockCounts"] = _top_counts(nearby_block_counts, limit=10)
        if isinstance(result.get("nearbyEntities"), list):
            compact["nearbyEntitiesCount"] = len(result["nearbyEntities"])
        if isinstance(result.get("nearbyPlayers"), list):
            compact["nearbyPlayersCount"] = len(result["nearbyPlayers"])

    nearby_block_counts = after_summary.get("nearby_block_counts") or after_summary.get("nearbyBlockCounts")
    if "nearbyBlockCounts" not in compact and isinstance(nearby_block_counts, dict):
        compact["nearbyBlockCounts"] = _top_counts(nearby_block_counts, limit=10)
    nearby_entities = after_summary.get("nearby_entities") or after_summary.get("nearbyEntities")
    if "nearbyEntitiesCount" not in compact and isinstance(nearby_entities, list):
        compact["nearbyEntitiesCount"] = len(nearby_entities)

    return compact


def _tick_state_summary(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else state
    return summary if isinstance(summary, dict) else {}


def _moved_since_observation(observation_age: int, recent_ticks: list[dict[str, Any]]) -> bool:
    for newer_tick in recent_ticks[:observation_age]:
        if isinstance(newer_tick, dict) and _tick_position_changed(newer_tick):
            return True
    return False


def _tick_position_changed(tick: dict[str, Any]) -> bool:
    before_pos = _position_from_tick_state(tick.get("before_state") or _decode_jsonish(tick.get("before_state_json")))
    after_pos = _position_from_tick_state(tick.get("after_state") or _decode_jsonish(tick.get("after_state_json")))
    return bool(before_pos and after_pos and before_pos != after_pos)


def _tick_materially_changed(tick: dict[str, Any]) -> bool:
    before_counts = _inventory_counts_from_tick_state(tick.get("before_state") or _decode_jsonish(tick.get("before_state_json")))
    after_counts = _inventory_counts_from_tick_state(tick.get("after_state") or _decode_jsonish(tick.get("after_state_json")))
    if before_counts != after_counts:
        return True

    return _tick_position_changed(tick)


def _inventory_counts_from_tick_state(state: Any) -> dict[str, int]:
    if not isinstance(state, dict):
        return {}
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else state
    counts = summary.get("inventory_counts")
    if isinstance(counts, dict):
        return {str(k): int(v) for k, v in counts.items() if isinstance(v, int) and not isinstance(v, bool)}
    inventory = summary.get("inventory")
    if isinstance(inventory, list):
        result: dict[str, int] = {}
        for item in inventory:
            if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("count"), int):
                result[item["name"]] = result.get(item["name"], 0) + item["count"]
        return result
    return {}


def _position_from_tick_state(state: Any) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else state
    position = summary.get("position")
    return position if isinstance(position, dict) else None


def _enrich_unresolved_failure(
    compact: dict[str, Any],
    current_facts: dict[str, Any],
    age_ticks: int,
) -> dict[str, Any]:
    unresolved = {
        key: compact.get(key)
        for key in (
            "action",
            "ok",
            "error",
            "failure_type",
            "stop_reason",
            "needed",
            "station_needed",
            "missing_materials",
            "possible_next_actions",
            "lesson",
            "suggested_next_action",
            "fallback_suggested_next_action",
            "can_retry",
            "verifier",
        )
        if compact.get(key) is not None
    }
    unresolved["age_ticks"] = age_ticks

    missing = unresolved.get("missing_materials")
    if not isinstance(missing, list):
        missing = _infer_missing_materials_from_compact(compact)
        if missing:
            unresolved["missing_materials"] = missing

    if missing and unresolved.get("failure_type") in {None, "no_progress"}:
        unresolved["failure_type"] = "missing_materials"
    if missing and not unresolved.get("stop_reason"):
        unresolved["stop_reason"] = "missing_materials"
    if missing and not unresolved.get("possible_next_actions"):
        unresolved["possible_next_actions"] = _possible_next_actions_for_missing_materials(missing, current_facts)
    if unresolved.get("action") == "craft_torches" and missing and not unresolved.get("lesson"):
        unresolved["lesson"] = "Torches need sticks and coal or charcoal."

    return unresolved


def _infer_missing_materials_from_compact(compact: dict[str, Any]) -> list[str]:
    text = " ".join(str(compact.get(key) or "") for key in ("error", "needed")).lower()
    if "missing material" not in text:
        return []
    materials: list[str] = []
    for part in text.split(":", 1)[-1].split(","):
        token = part.strip().split(" x", 1)[0].strip(" .").replace(" or ", "_or_").replace(" ", "_")
        if token:
            materials.append(token)
    return _unique(materials)


def _possible_next_actions_for_missing_materials(missing: list[str], current_facts: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    for material in missing:
        if material == "stick":
            if current_facts.get("planks_count", 0) > 0:
                actions.append("craft_sticks")
            else:
                actions.extend(["collect_wood", "craft_planks"])
        elif material == "coal_or_charcoal":
            if current_facts.get("has_wooden_pickaxe") or current_facts.get("has_stone_pickaxe") or current_facts.get("has_iron_pickaxe"):
                actions.append("mine_coal")
            actions.append("collect_wood")
        elif material == "cobblestone":
            actions.append("mine_stone")
        elif material == "iron_ingot":
            actions.extend(["mine_iron_ore", "smelt_iron"])
        elif material == "crafting_table":
            actions.extend(["craft_crafting_table", "place_crafting_table", "setup_workspace"])
        elif material == "furnace":
            actions.extend(["craft_furnace", "place_furnace", "setup_workspace"])
    actions.append("look_around")
    return _unique(actions)


def _missing_condition_resolved(failure: dict[str, Any], current_facts: dict[str, Any]) -> bool:
    missing = failure.get("missing_materials")
    if not isinstance(missing, list) or not missing:
        return False
    return all(_material_available(material, current_facts) for material in missing)


def _material_available(material: str, current_facts: dict[str, Any]) -> bool:
    if material == "stick":
        return current_facts.get("sticks_count", 0) > 0
    if material == "coal_or_charcoal":
        return current_facts.get("coal_or_charcoal_count", 0) > 0
    if material == "cobblestone":
        return current_facts.get("cobblestone_count", 0) > 0
    if material == "iron_ingot":
        return current_facts.get("iron_ingot_count", 0) > 0
    if material == "crafting_table":
        return bool(current_facts.get("has_inventory_crafting_table") or current_facts.get("has_nearby_crafting_table_usable"))
    if material == "furnace":
        return bool(current_facts.get("has_inventory_furnace") or current_facts.get("has_nearby_furnace_usable"))
    return False


def _resolved_by_related_material_success(failure: dict[str, Any], material_successes: list[str]) -> bool:
    possible = failure.get("possible_next_actions")
    if not isinstance(possible, list):
        return False
    possible_set = {action for action in possible if isinstance(action, str)}
    return any(action in possible_set for action in material_successes)


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
        "missing_materials",
        "possible_next_actions",
        "lesson",
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

    if current_facts.get("has_nearby_crafting_table_usable") and (
        "no crafting table" in text
        or "missing crafting table" in text
        or "crafting table found" in text
        or action == "place_crafting_table"
        or item.get("stop_reason") == "no_crafting_table_nearby"
        or item.get("station_needed") == "crafting_table"
    ):
        return True

    if current_facts.get("has_nearby_furnace_usable") and (
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


def _current_intent_from_ticks(
    recent_ticks: list[dict[str, Any]],
    current_facts: dict[str, Any],
) -> dict[str, Any] | None:
    """Find the original goal action that started a material-repair chain.

    Walks ticks oldest-first, finds the deepest unresolved missing_materials
    failure, then collects all newer ticks as repair_attempts.  Clears when
    the goal action succeeds, all materials resolve, or the failure is stale.
    """
    successful_actions: set[str] = set()
    goal_age: int | None = None
    goal_action: str | None = None
    goal_compact: dict[str, Any] | None = None

    for age, tick in enumerate(recent_ticks):
        if not isinstance(tick, dict):
            continue
        action = tick.get("action")
        ok = _tick_ok(tick)
        if ok is True:
            # Sensing actions do NOT count as clearing the goal
            if isinstance(action, str) and not is_observation_action(action):
                successful_actions.add(action)
            continue

        last_result = _tick_to_last_action_result(tick)
        compact = _compact_last_action_result(last_result)
        if not compact or not _last_failure_included(compact):
            continue
        if is_observation_action(compact.get("action")):
            continue

        failed_action = compact.get("action")
        if isinstance(failed_action, str) and failed_action in successful_actions:
            continue

        missing = compact.get("missing_materials")
        if not isinstance(missing, list) or not missing:
            continue

        # Keep the oldest qualifying failure as the goal.
        goal_age = age
        goal_action = failed_action
        goal_compact = compact

    if goal_age is None or goal_action is None or goal_compact is None:
        return None
    if goal_action in successful_actions:
        return None
    if _is_stale_failure(goal_compact, current_facts):
        return None

    original_missing: list[str] = _normalize_missing_materials(goal_compact.get("missing_materials")) or []
    still_missing = [m for m in original_missing if not _material_available(m, current_facts)]

    # Collect repair_attempts: ticks newer than goal_age (lower age index).
    repair_attempts: list[dict[str, Any]] = []
    dependency_chain: list[str] = [goal_action]
    latest_failed_requirement: dict[str, Any] | None = None

    for age, tick in enumerate(recent_ticks):
        if age >= goal_age:
            break
        if not isinstance(tick, dict):
            continue
        action = tick.get("action")
        if not action or is_observation_action(action):
            continue
        ok = _tick_ok(tick)
        entry: dict[str, Any] = {"action": action, "ok": ok is True}
        if ok is not True:
            last_result = _tick_to_last_action_result(tick)
            compact_rep = _compact_last_action_result(last_result) or {}
            ft = compact_rep.get("failure_type")
            if ft:
                entry["failure_type"] = ft
            dep_missing = compact_rep.get("missing_materials")
            if isinstance(dep_missing, list) and dep_missing and action not in dependency_chain:
                dependency_chain.append(action)
            tick_verifier = tick.get("verifier")
            if isinstance(tick_verifier, dict):
                fb = tick_verifier.get("failed_because")
                if isinstance(fb, list) and fb:
                    latest_failed_requirement = fb[0]
        repair_attempts.append(entry)

    # Remove materials whose dedicated repair action already succeeded.
    successful_repairs = {r["action"] for r in repair_attempts if r["ok"]}
    if successful_repairs and still_missing:
        filtered: list[str] = []
        for material in still_missing:
            providers = _possible_next_actions_for_missing_materials([material], current_facts)
            if any(a in successful_repairs for a in providers):
                continue
            filtered.append(material)
        still_missing = filtered

    if not still_missing:
        return None

    # Count repeated repair failures within the same action.
    repair_failure_counts: dict[str, int] = {}
    for r in repair_attempts:
        if not r["ok"]:
            a = str(r.get("action", ""))
            repair_failure_counts[a] = repair_failure_counts.get(a, 0) + 1
    repeated_repair_failure_count = sum(1 for c in repair_failure_counts.values() if c >= 2)

    # Lesson: coal-specific when coal repairs repeatedly fail; generic otherwise.
    lesson: str | None = None
    if repeated_repair_failure_count > 0:
        if "coal_or_charcoal" in still_missing:
            lesson = (
                "Coal is not accessible from here; consider explore_nearby, "
                "return_to_surface, or use wood/charcoal route if implemented."
            )
        else:
            lesson = "Repeated repair failures; consider explore_nearby, look_around, or a different approach."
    elif goal_compact.get("lesson"):
        lesson = goal_compact["lesson"]

    successes = [r["action"] for r in repair_attempts if r["ok"]]
    failures = [r["action"] for r in repair_attempts if not r["ok"]]
    summary_parts: list[str] = []
    if successes:
        summary_parts.append(f"{', '.join(successes)} succeeded")
    if failures:
        summary_parts.append(f"{'/'.join(failures)} failed")
    repair_attempts_summary = "; ".join(summary_parts) if summary_parts else None

    blocking_problem = f"missing {', '.join(still_missing)}"
    possible_next = _possible_next_actions_for_missing_materials(still_missing, current_facts)

    result: dict[str, Any] = {
        "goal_action": goal_action,
        "goal_failure_type": goal_compact.get("failure_type"),
        "blocking_problem": blocking_problem,
        "missing_materials": still_missing,
        "repair_attempts": repair_attempts,
        "possible_next_actions": possible_next,
        "repeated_repair_failure_count": repeated_repair_failure_count,
        "age_ticks": goal_age,
    }
    if len(dependency_chain) > 1:
        result["dependency_chain"] = dependency_chain
    if latest_failed_requirement:
        result["latest_failed_requirement"] = latest_failed_requirement
    if repair_attempts_summary:
        result["repair_attempts_summary"] = repair_attempts_summary
    if lesson:
        result["lesson"] = lesson
    return result


def _compact_current_intent(
    intent: dict[str, Any] | None,
    show_possible_next_actions: bool = False,
) -> dict[str, Any] | None:
    """Compact form of current_intent sent in the LLM state packet."""
    if not isinstance(intent, dict):
        return None
    compact: dict[str, Any] = {
        "goal_action": intent["goal_action"],
        "blocking_problem": intent["blocking_problem"],
        "repair_attempts_count": len(intent.get("repair_attempts") or []),
        "repeated_repair_failure_count": intent.get("repeated_repair_failure_count", 0),
        "age_ticks": intent.get("age_ticks", 0),
    }
    if show_possible_next_actions:
        compact["possible_next_actions"] = intent.get("possible_next_actions")
    dep_chain = intent.get("dependency_chain")
    if dep_chain:
        compact["dependency_chain"] = dep_chain
    latest_fr = intent.get("latest_failed_requirement")
    if latest_fr:
        compact["latest_failed_requirement"] = latest_fr
    summary = intent.get("repair_attempts_summary")
    if summary:
        compact["repair_attempts_summary"] = summary
    lesson = intent.get("lesson")
    if lesson:
        compact["lesson"] = lesson
    return compact


def _recent_completed_intents_from_ticks(
    recent_ticks: list[dict[str, Any]],
    window: int = 5,
    max_count: int = 3,
) -> list[dict[str, Any]]:
    """Return recently-succeeded non-observation actions as completed intent records.

    Ticks are newest-first; age_ticks=0 is most recent.
    For resource acquisition families, adds resource_family and inventory_delta (if any).
    """
    completed: list[dict[str, Any]] = []
    for age, tick in enumerate(recent_ticks[:window]):
        if not isinstance(tick, dict):
            continue
        if _tick_ok(tick) is not True:
            continue
        action = tick.get("action")
        if not isinstance(action, str) or is_observation_action(action):
            continue
        args = tick.get("args") if isinstance(tick.get("args"), dict) else {}
        entry: dict[str, Any] = {"action": action, "result": "succeeded", "age_ticks": age}
        for key, value in args.items():
            if value is None or value == {} or value == []:
                continue
            if key in {"count", "radius"}:
                continue
            entry[key] = value

        # Resource acquisition: add resource_family and inventory_delta.
        family = action_family_key(action, args)
        if isinstance(family, str) and family.startswith("resource_acquisition:"):
            entry["resource_family"] = family[len("resource_acquisition:"):]
            before_counts = _inventory_counts_from_tick_state(
                tick.get("before_state") or _decode_jsonish(tick.get("before_state_json"))
            )
            after_counts = _inventory_counts_from_tick_state(
                tick.get("after_state") or _decode_jsonish(tick.get("after_state_json"))
            )
            delta = {
                item: after_counts[item] - before_counts.get(item, 0)
                for item in after_counts
                if after_counts[item] > before_counts.get(item, 0)
            }
            if delta:
                entry["inventory_delta"] = delta

        completed.append(entry)
        if len(completed) >= max_count:
            break
    return completed


_SUFFICIENCY_THRESHOLDS: dict[str, int] = {
    "coal": 8,
    "charcoal": 8,
    "raw_iron": 3,
    "cobblestone": 8,
}


def _resource_family_to_item_name(resource_family: str) -> str | None:
    """Map a resource_acquisition family suffix to its primary inventory item name."""
    _MAP: dict[str, str] = {
        "iron_ore": "raw_iron",
        "coal": "coal",
        "coal_ore": "coal",
        "stone": "cobblestone",
    }
    return _MAP.get(resource_family, resource_family)


def _resource_sufficiency(summary: dict[str, Any]) -> dict[str, Any]:
    """Return per-resource sufficiency facts for resources currently in inventory."""
    counts = summary.get("inventory_counts") or {}
    result: dict[str, Any] = {}
    for item, threshold in _SUFFICIENCY_THRESHOLDS.items():
        count = counts.get(item, 0)
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            result[item] = {
                "count": count,
                "sufficient_for_basic_needs": count >= threshold,
            }
    # Combine coal + charcoal when only one is present to avoid duplication.
    if "coal" not in result and "charcoal" not in result:
        coal_total = counts.get("coal", 0) + counts.get("charcoal", 0)
        if coal_total > 0:
            result["coal"] = {
                "count": coal_total,
                "sufficient_for_basic_needs": coal_total >= 8,
            }
    return result


def _recent_resource_successes_from_ticks(
    recent_ticks: list[dict[str, Any]],
    current_summary: dict[str, Any],
    window: int = 5,
) -> dict[str, Any]:
    """Return the most recent successful resource acquisition per family.

    Keyed by resource_family: {action, ticks_ago, inventory_count, fact}.
    inventory_count is from the after_state of the success tick (or current inventory).
    """
    result: dict[str, Any] = {}
    current_counts = current_summary.get("inventory_counts") or {}

    for age, tick in enumerate(recent_ticks[:window]):
        if not isinstance(tick, dict) or _tick_ok(tick) is not True:
            continue
        action = tick.get("action")
        if not isinstance(action, str):
            continue
        args = tick.get("args") if isinstance(tick.get("args"), dict) else {}
        family = action_family_key(action, args)
        if not isinstance(family, str) or not family.startswith("resource_acquisition:"):
            continue
        resource_family = family[len("resource_acquisition:"):]
        if resource_family in result:
            continue  # keep the most recent (lowest age)

        item_name = _resource_family_to_item_name(resource_family)
        after_counts = _inventory_counts_from_tick_state(
            tick.get("after_state") or _decode_jsonish(tick.get("after_state_json"))
        )
        inventory_count = (
            after_counts.get(item_name, 0) if item_name else 0
        ) or (current_counts.get(item_name, 0) if item_name else 0)

        result[resource_family] = {
            "action": action,
            "ticks_ago": age,
            "inventory_count": inventory_count,
            "fact": "This resource was recently acquired successfully.",
        }

    return result


def _enrich_failure_with_requirements(
    unresolved_failure: dict[str, Any] | None,
    current_facts: dict[str, Any],
    show_possible_next_actions: bool = False,
) -> dict[str, Any] | None:
    """Annotate unresolved_failure with failed_because from the requirements system.

    Priority:
    1. Use failed_because already stored in the verifier dict (set at verify_action time).
    2. Check catalog typed requirements against current_facts.
    3. Fall back to error-string parsing.
    """
    if not isinstance(unresolved_failure, dict):
        return None

    enriched = dict(unresolved_failure)

    if not show_possible_next_actions:
        enriched.pop("possible_next_actions", None)
        enriched.pop("suggested_next_action", None)
        enriched.pop("fallback_suggested_next_action", None)

    action = enriched.get("action")
    if not isinstance(action, str):
        return enriched

    # 1. Use already-computed failed_because from verifier (preferred — computed once at tick time)
    verifier = enriched.get("verifier") if isinstance(enriched.get("verifier"), dict) else {}
    pre_failed_because = verifier.get("failed_because") if verifier else enriched.get("failed_because")
    if isinstance(pre_failed_because, list) and pre_failed_because:
        if "failed_because" not in enriched:
            enriched["failed_because"] = pre_failed_because
        if "repeatable_now" not in enriched:
            enriched["repeatable_now"] = verifier.get("repeatable_now", False)
        enriched.setdefault("repeat_condition", "Only retry after missing requirements changed.")
        return enriched

    # 2. Catalog typed requirements against current_facts
    spec = CATALOG.get(action)
    failed_because: list[dict] = []
    repeatable_now: bool | None = None

    if spec and spec.requirements:
        report = check_requirements(spec.requirements, dict(current_facts))
        if not report.ok:
            failed_because = [fr.to_dict() for fr in report.failed_requirements]
            repeatable_now = report.repeatable_now

    # 3. Error-string fallback
    if not failed_because:
        error = enriched.get("error")
        result = enriched.get("result") if isinstance(enriched.get("result"), dict) else {}
        parsed = parse_error_to_failed_requirements(
            error=error, action=action, result=result, facts=current_facts,
        )
        if parsed:
            failed_because = [fr.to_dict() for fr in parsed]
            repeatable_now = False

    if failed_because:
        enriched["failed_because"] = failed_because
        enriched["repeat_condition"] = "Only retry after missing requirements changed."
        if repeatable_now is not None:
            enriched["repeatable_now"] = repeatable_now

    return enriched


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


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


def _normalize_missing_materials(materials: Any) -> list[str] | None:
    """Coerce bot-sent dicts like {"name":"stick",...} to plain strings."""
    if not isinstance(materials, list):
        return None
    return [m["name"] if isinstance(m, dict) else str(m) for m in materials] or None


def _short(value: Any, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."
