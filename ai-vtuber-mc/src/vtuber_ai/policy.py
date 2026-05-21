from typing import Any

from vtuber_ai.action_catalog import CATALOG, catalog_status
from vtuber_ai.schemas import ActionRequest

# ---------------------------------------------------------------------------
# Explicit allowlist (backward compat).  Every name here must also exist in
# CATALOG with status "implemented" or "partial" and exposes_to_llm=True,
# OR be a meta-action like set_vtuber_mood that is explicitly gate-listed.
# ---------------------------------------------------------------------------
ALLOWED_ACTIONS = frozenset(
    {
        "status",
        "say",
        "look_around",
        "explore_nearby",
        "look_at_player",
        "follow_player",
        "stop",
        "come_here",
        "jump",
        "set_vtuber_mood",
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
        "recover_position",
        "unstuck_escape",
        "seek_open_area",
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
        "mark_waypoint",
        "list_waypoints",
        "return_to_waypoint",
        "recover_death_items",
        "abandon_death_recovery",
        "return_to_spawn_or_home",
        "find_safe_workspace",
        "setup_workspace",
        "approach_station",
        "return_to_position",
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
        "place_block",
        "place_water",
        "place_lava",
        "place_bed",
        "place_boat",
        "place_chest",
        "place_furnace",
        "place_torch",
        "craft_wooden_pickaxe",
        "mine_stone",
        "mine_coal",
        "mine_iron_ore",
        "craft_stone_pickaxe",
        "smelt_item",
        "smelt_iron",
        "craft_blaze_powder",
        "craft_diamond_pickaxe",
        "craft_diamond_sword",
        "craft_diamond_armor",
        "equip_best_armor",
        "equip_best_tool",
        "equip_best_weapon",
        "flee",
        "eat_food",
        # combat
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
        # bed actions
        "craft_bed",
        "sleep_if_possible",
        "set_spawn_with_bed",
        "use_bed_bomb",
        "avoid_bed_explosion",
        # nether portal
        "find_lava_pool",
        "collect_water",
        "collect_lava",
        "collect_obsidian",
        "build_nether_portal",
        "cast_nether_portal",
        "craft_flint_and_steel",
        "light_nether_portal",
        "enter_nether",
        "return_to_portal",
        # stronghold / end portal
        "craft_eyes_of_ender",
        "throw_eye_of_ender",
        "locate_stronghold_step",
        "dig_staircase_to_stronghold",
        "scan_for_end_portal_room",
        "activate_end_portal",
        "enter_end",
        # Ender Dragon fight phases
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
        # nether safety / progression
        "equip_gold_armor",
        "avoid_opening_chests_near_piglins",
        "barter_with_piglins",
        "find_nether_fortress",
        "navigate_nether_safely",
        "collect_blaze_rods",
        "retreat_from_nether_danger",
        "leave_nether",
        "describe_actions",
        "debug_collect_drops",
    }
)

ALLOWED_MOODS = frozenset(
    {
        "neutral",
        "happy",
        "surprised",
        "scared",
        "focused",
        "confused",
    }
)

ALLOWED_ACQUIRE_TARGETS = frozenset(
    {
        "oak_log",
        "birch_log",
        "spruce_log",
        "jungle_log",
        "acacia_log",
        "dark_oak_log",
        "mangrove_log",
        "cherry_log",
        "crimson_stem",
        "warped_stem",
        "stone",
        "cobblestone",
        "deepslate",
        "coal_ore",
        "deepslate_coal_ore",
        "iron_ore",
        "deepslate_iron_ore",
        "copper_ore",
        "deepslate_copper_ore",
        "dirt",
        "grass_block",
        "sand",
        "gravel",
    }
)

ALLOWED_ACQUIRE_ACCESS_MODES = frozenset({"exposed", "surface_first", "safe_staircase"})

PLACE_BLOCK_ALLOWED_ITEMS = frozenset({
    "dirt", "cobblestone", "stone", "crafting_table", "furnace",
    "torch", "chest", "obsidian",
    # _planks and _bed families are validated by suffix check below
})
PLACE_MODES = frozenset({"nearby", "floor", "wall", "forward", "under_self", "workspace"})
WORKSPACE_PURPOSES = frozenset({"crafting", "smelting", "storage", "general"})
STATION_TYPES = frozenset({"crafting_table", "furnace", "chest"})
PLACE_DIRECTIONS = frozenset({"north", "south", "east", "west", "up", "down", "forward", "back", "left", "right"})
PLACE_WATER_MODES = frozenset({"nearby", "downward_safety", "portal_casting", "mlg"})

EQUIP_ARMOR_MODES = frozenset({"best", "gold", "iron", "diamond", "netherite", "leather"})
DROP_CRITICAL_ITEMS = frozenset({
    "diamond", "diamond_pickaxe", "diamond_sword", "diamond_helmet",
    "diamond_chestplate", "diamond_leggings", "diamond_boots",
    "ender_pearl", "blaze_rod", "blaze_powder", "ender_eye",
    "iron_pickaxe", "iron_sword", "netherite_ingot", "totem_of_undying",
    "enchanted_book", "elytra", "crafting_table", "furnace",
    "water_bucket", "lava_bucket", "flint_and_steel",
})
LOOT_PRIORITIES   = frozenset({"fortress", "stronghold", "village", "general"})
VALID_WAYPOINT_KINDS = frozenset({
    "home", "surface", "crafting_area", "furnace", "mine_entrance",
    "nether_portal_overworld", "nether_portal_nether", "fortress",
    "blaze_spawner", "stronghold", "end_portal_room", "death_location", "lava_pool", "general",
})
PLACE_LAVA_MODES = frozenset({"portal_casting", "controlled_source"})

ENDER_PEARL_MODES = frozenset({"forward", "escape", "across_gap", "toward_target"})
KILLABLE_PASSIVE_MOBS = frozenset({"cow", "pig", "sheep", "chicken", "rabbit"})
CRAFT_ITEM_ALLOWED_ITEMS = frozenset({
    "furnace",
    "torch",
    "chest",
    "shield",
    "bucket",
    "iron_pickaxe",
    "iron_sword",
    "iron_helmet",
    "iron_chestplate",
    "iron_leggings",
    "iron_boots",
    "iron_armor",
})
CRAFT_ITEM_SINGLE_COUNT = frozenset({
    "shield",
    "bucket",
    "iron_pickaxe",
    "iron_sword",
    "iron_helmet",
    "iron_chestplate",
    "iron_leggings",
    "iron_boots",
    "iron_armor",
})
CRAFT_ITEM_ACTION_ALIASES: dict[str, str] = {
    "crafting_table": "craft_crafting_table",
    "workbench": "craft_crafting_table",
    "planks": "craft_planks",
    "spruce_planks": "craft_planks",
    "oak_planks": "craft_planks",
    "sticks": "craft_sticks",
    "stick": "craft_sticks",
    "wooden_pickaxe": "craft_wooden_pickaxe",
    "stone_pickaxe": "craft_stone_pickaxe",
    "furnace": "craft_furnace",
    "torch": "craft_torches",
    "torches": "craft_torches",
    "chest": "craft_chest",
    "shield": "craft_shield",
    "bucket": "craft_bucket",
    "iron_pickaxe": "craft_iron_pickaxe",
    "iron_sword": "craft_iron_sword",
    "iron_armor": "craft_iron_armor",
    "diamond_pickaxe": "craft_diamond_pickaxe",
    "diamond_sword": "craft_diamond_sword",
    "diamond_armor": "craft_diamond_armor",
    "blaze_powder": "craft_blaze_powder",
    "eye_of_ender": "craft_eyes_of_ender",
    "eyes_of_ender": "craft_eyes_of_ender",
    "bed": "craft_bed",
    "bow": "craft_bow",
    "arrows": "craft_arrows",
    "boat": "craft_boat",
}
CRAFT_ITEM_COUNT_TARGETS = frozenset({"craft_planks", "craft_sticks", "craft_torches", "craft_arrows"})
SMELT_INPUTS = frozenset({
    "raw_iron",
    "raw_gold",
    "raw_beef",
    "raw_porkchop",
    "raw_chicken",
    "raw_mutton",
    "raw_rabbit",
    "cod",
    "salmon",
    "potato",
})
SMELT_FUELS = frozenset({
    "coal",
    "charcoal",
    "oak_planks",
    "birch_planks",
    "spruce_planks",
    "jungle_planks",
    "acacia_planks",
    "dark_oak_planks",
    "mangrove_planks",
    "cherry_planks",
    "crimson_planks",
    "warped_planks",
    "oak_log",
    "birch_log",
    "spruce_log",
    "jungle_log",
    "acacia_log",
    "dark_oak_log",
    "mangrove_log",
    "cherry_log",
    "crimson_stem",
    "warped_stem",
})

STAIRCASE_DIRS = frozenset({
    "north", "south", "east", "west",
    "up_to_surface", "down", "toward_target", "down_to_target",
})
BRIDGE_DIRS = frozenset({"forward", "north", "south", "east", "west"})
PLACE_IN_DIR_DIRS = frozenset({
    "north", "south", "east", "west", "forward", "back", "left", "right", "up", "down",
})
PILLAR_BRIDGE_ALLOWED_BLOCKS = frozenset({"cobblestone", "dirt", "stone", "cobbled_deepslate", "planks"})

_ACTION_ARGS: dict[str, frozenset[str]] = {
    # --- currently implemented ---
    "status": frozenset(),
    "say": frozenset({"message"}),
    "look_around": frozenset({"radius"}),
    "explore_nearby": frozenset({"radius"}),
    "look_at_player": frozenset({"username"}),
    "follow_player": frozenset({"username"}),
    "stop": frozenset(),
    "come_here": frozenset({"username"}),
    "jump": frozenset(),
    "set_vtuber_mood": frozenset({"mood"}),
    "acquire_blocks": frozenset({"targets", "count", "radius", "allowExcavate", "accessMode"}),
    "navigate_to_block_type": frozenset({"targets", "radius"}),
    "collect_wood": frozenset({"count"}),
    "craft_planks": frozenset({"count"}),
    "craft_sticks": frozenset({"count"}),
    "craft_crafting_table": frozenset({"count"}),
    "place_crafting_table": frozenset(),
    "place_block": frozenset({"item", "mode", "direction"}),
    "place_water": frozenset({"mode"}),
    "place_lava": frozenset({"mode"}),
    "place_bed": frozenset(),
    "place_boat": frozenset(),
    "place_chest": frozenset(),
    "place_furnace": frozenset({"radius", "allowPrepareArea"}),
    "place_torch": frozenset(),
    "craft_wooden_pickaxe": frozenset(),
    "mine_stone": frozenset({"count", "radius"}),
    "craft_stone_pickaxe": frozenset(),
    "recover_position": frozenset(),
    "unstuck_escape": frozenset({"radius", "mode"}),
    "check_inventory": frozenset(),
    "check_time_of_day": frozenset(),
    "check_light_level": frozenset(),
    "check_biome": frozenset(),
    "scan_for_hostiles": frozenset({"radius"}),
    "scan_for_passive_mobs": frozenset({"radius"}),
    "scan_for_chests": frozenset({"radius"}),
    "scan_for_specific_block": frozenset({"targets", "radius"}),
    "scan_for_liquids": frozenset({"radius"}),
    "scan_for_structures": frozenset({"radius"}),
    "scan_workspace": frozenset(),
    "drop_item": frozenset({"item", "count", "force"}),
    "equip_armor": frozenset({"mode"}),
    "equip_tool": frozenset({"block", "tool"}),
    "select_hotbar_slot": frozenset({"slot"}),
    "open_chest": frozenset(),
    "loot_chest": frozenset({"priority"}),
    "deposit_items": frozenset({"items"}),
    "withdraw_items": frozenset({"items"}),
    "mark_waypoint": frozenset({"label", "kind"}),
    "list_waypoints": frozenset(),
    "return_to_waypoint": frozenset({"label"}),
    "recover_death_items": frozenset(),
    "find_safe_workspace": frozenset({"radius", "purpose"}),
    "setup_workspace": frozenset({"need_crafting_table", "need_furnace", "need_chest", "radius"}),
    "approach_station": frozenset({"station", "radius"}),
    "return_to_position": frozenset({"x", "y", "z", "dimension", "radius"}),
    "return_to_workspace": frozenset({"purpose"}),
    "return_to_known_position": frozenset({"label"}),
    "set_home_position": frozenset(),
    "dig_staircase": frozenset({"direction", "max_steps"}),
    "return_to_surface": frozenset(),
    "pillar_up": frozenset({"height", "block"}),
    "bridge_gap": frozenset({"direction", "length", "block"}),
    "place_block_in_direction": frozenset({"item", "direction"}),
    "mlg_water_bucket": frozenset(),
    "enter_boat": frozenset(),
    "exit_boat": frozenset(),
    "set_sneak": frozenset({"enabled"}),
    "set_sprint": frozenset({"enabled"}),
    "craft_blaze_powder": frozenset(),
    "craft_diamond_pickaxe": frozenset(),
    "craft_diamond_sword": frozenset(),
    "craft_diamond_armor": frozenset(),
    "equip_best_armor": frozenset(),
    "equip_best_tool": frozenset({"block"}),
    "equip_best_weapon": frozenset(),
    "flee": frozenset(),
    "eat_food": frozenset(),
    # mark_waypoint/list_waypoints/return_to_waypoint now implemented; defined above
    # check_inventory/check_time_of_day/check_light_level/check_biome and all scan_for_* now implemented; defined above
    # find_safe_workspace, dig_staircase, pillar_up, bridge_gap, place_block_in_direction,
    # mlg_water_bucket, enter_boat, exit_boat, set_sneak, set_sprint now implemented; defined above
    # place_block/water/lava/bed/boat/chest/furnace/torch now implemented; defined above
    "craft_item": frozenset({"item", "count"}),
    "craft_furnace": frozenset(),
    "craft_torches": frozenset({"count"}),
    "craft_chest": frozenset(),
    "craft_shield": frozenset(),
    "craft_bucket": frozenset(),
    "craft_iron_pickaxe": frozenset(),
    "craft_iron_sword": frozenset(),
    "craft_iron_armor": frozenset(),
    "craft_bow": frozenset(),
    "craft_arrows": frozenset({"count"}),
    "craft_flint_and_steel": frozenset(),
    "craft_boat": frozenset(),
    "craft_bed": frozenset(),
    "craft_blaze_powder": frozenset(),
    "craft_eyes_of_ender": frozenset({"count"}),
    "craft_diamond_pickaxe": frozenset(),
    "craft_diamond_sword": frozenset(),
    "craft_diamond_armor": frozenset(),
    "mine_coal": frozenset({"count", "radius", "allowExcavate", "accessMode"}),
    "mine_iron_ore": frozenset({"count", "radius"}),
    "mine_diamond_ore": frozenset({"count"}),
    "mine_redstone": frozenset({"count"}),
    "mine_gold_ore": frozenset({"count"}),
    "mine_gravel": frozenset({"count"}),
    "collect_flint": frozenset({"count"}),
    "collect_sand": frozenset({"count"}),
    "collect_water": frozenset(),
    "collect_lava": frozenset(),
    "collect_obsidian": frozenset({"count"}),
    "collect_food": frozenset({"count"}),
    "smelt_item": frozenset({"input", "count", "fuel"}),
    "smelt_iron": frozenset({"count"}),
    "smelt_food": frozenset({"food", "count"}),
    "smelt_gold": frozenset({"count"}),
    # drop_item/equip_armor/tool/select_hotbar_slot/open_chest/loot_chest/deposit_items/withdraw_items now implemented; defined above
    "equip_gold_armor": frozenset(),
    "retreat_from_combat": frozenset(),
    "sleep_if_possible": frozenset(),
    "set_spawn_with_bed": frozenset(),
    "build_emergency_shelter": frozenset(),
    "avoid_hazard": frozenset(),
    "escape_liquid": frozenset(),
    "handle_stuck": frozenset(),
    # recover_death_items now implemented; defined above
    "abandon_death_recovery": frozenset(),
    "return_to_spawn_or_home": frozenset(),
    "attack_mob": frozenset({"mob_type", "radius"}),
    "attack_nearest_hostile": frozenset(),
    "retreat_from_combat": frozenset(),
    "kill_passive_mob": frozenset({"target"}),
    "kill_blaze": frozenset(),
    "kill_enderman": frozenset(),
    "block_with_shield": frozenset(),
    "shoot_bow": frozenset({"target"}),
    "charge_bow": frozenset(),
    "deflect_ghast_fireball": frozenset(),
    "kite_mob": frozenset(),
    "throw_ender_pearl": frozenset({"mode"}),
    "find_lava_pool": frozenset({"radius"}),
    "build_nether_portal": frozenset(),
    "cast_nether_portal": frozenset(),
    "light_nether_portal": frozenset(),
    "enter_nether": frozenset(),
    "leave_nether": frozenset(),
    "return_to_portal": frozenset(),
    "navigate_nether_safely": frozenset({"direction"}),
    "avoid_opening_chests_near_piglins": frozenset(),
    "find_nether_fortress": frozenset({"radius"}),
    "find_bastion_or_piglins": frozenset(),
    "barter_with_piglins": frozenset({"count"}),
    "collect_blaze_rods": frozenset({"count"}),
    "collect_ender_pearls": frozenset({"count"}),
    "retreat_from_nether_danger": frozenset(),
    "throw_eye_of_ender": frozenset(),
    "locate_stronghold_step": frozenset(),
    "dig_staircase_to_stronghold": frozenset(),
    "scan_for_end_portal_room": frozenset(),
    "activate_end_portal": frozenset(),
    "enter_end": frozenset(),
    "end_safe_landing": frozenset(),
    "equip_pumpkin_head": frozenset(),
    "look_down_around_endermen": frozenset(),
    "scan_end_crystals": frozenset(),
    "destroy_end_crystal": frozenset(),
    "destroy_caged_end_crystal": frozenset(),
    "destroy_nearby_end_crystals": frozenset(),
    "attack_perched_dragon": frozenset(),
    "attack_dragon_with_bow": frozenset(),
    "use_bed_bomb": frozenset(),
    "avoid_bed_explosion": frozenset(),
    "dragon_phase_crystals": frozenset(),
    "dragon_phase_circle": frozenset(),
    "dragon_phase_perch": frozenset(),
    "fight_dragon_phase": frozenset(),
    "return_to_overworld_via_end_portal": frozenset(),
    "finish_dragon_fight": frozenset(),
    "describe_actions": frozenset({"actions"}),
    "debug_collect_drops": frozenset({"radius", "targetItems"}),
}

_BOOLEAN_ARG_KEYS: dict[str, frozenset[str]] = {
    "acquire_blocks": frozenset({"allowExcavate"}),
    "mine_coal": frozenset({"allowExcavate"}),
    "setup_workspace": frozenset({"need_crafting_table", "need_furnace", "need_chest"}),
    "drop_item": frozenset({"force"}),
    "set_sneak": frozenset({"enabled"}),
    "set_sprint": frozenset({"enabled"}),
    "place_furnace": frozenset({"allowPrepareArea"}),
}

HARMLESS_COUNT_NO_ARG_ACTIONS = frozenset({
    "status",
    "look_around",
    "stop",
    "jump",
    "craft_furnace",
    "craft_chest",
    "craft_shield",
    "craft_bucket",
    "craft_iron_pickaxe",
    "craft_iron_sword",
    "craft_iron_armor",
    "craft_diamond_pickaxe",
    "craft_diamond_sword",
    "craft_diamond_armor",
    "craft_blaze_powder",
    "craft_eyes_of_ender",
    "craft_wooden_pickaxe",
    "craft_stone_pickaxe",
    "place_crafting_table",
    "place_chest",
    "place_bed",
    "place_boat",
    "place_torch",
    "equip_best_armor",
    "equip_best_tool",
    "equip_best_weapon",
    "eat_food",
    "flee",
    "recover_position",
    "check_inventory",
    "check_time_of_day",
    "check_light_level",
    "check_biome",
})


class PolicyError(ValueError):
    """Raised when an action is outside the safe Minecraft action policy."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


def canonicalize_action_request(action_request: ActionRequest) -> tuple[ActionRequest, dict[str, Any]]:
    """Rewrite forgiving LLM/API aliases to canonical policy actions."""
    request = ActionRequest.model_validate(action_request)
    if request.action != "craft_item":
        return request, {}

    args = dict(request.args or {})
    raw_item = args.get("item")
    if not isinstance(raw_item, str):
        return request, {}

    item = _normalize_craft_item_alias(raw_item)
    canonical_action = CRAFT_ITEM_ACTION_ALIASES.get(item)
    if canonical_action is None:
        return request, {}

    new_args: dict[str, Any] = {}
    if canonical_action in CRAFT_ITEM_COUNT_TARGETS and "count" in args:
        new_args["count"] = args["count"]

    canonical_request = request.model_copy(update={"action": canonical_action, "args": new_args})
    return canonical_request, {
        "action_canonicalized": True,
        "original_action": "craft_item",
        "original_args": dict(request.args or {}),
        "canonical_action": canonical_action,
        "canonicalization_reason": "craft_item item alias",
    }


def normalize_action_args(action_request: ActionRequest) -> tuple[ActionRequest, dict[str, Any]]:
    """Normalize common compact JSON arg shapes before validation."""
    request = ActionRequest.model_validate(action_request)
    list_arg_keys = _list_string_arg_keys(request.action)
    boolean_arg_keys = _BOOLEAN_ARG_KEYS.get(request.action, frozenset())

    args = dict(request.args or {})
    normalized_keys: list[str] = []
    normalization_reasons: list[str] = []
    clamped_args: dict[str, dict[str, int]] = {}
    for key in sorted(list_arg_keys):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            args[key] = [value.strip()]
            normalized_keys.append(key)
            if "string_to_singleton_list" not in normalization_reasons:
                normalization_reasons.append("string_to_singleton_list")

    for key in sorted(boolean_arg_keys):
        value = args.get(key)
        if isinstance(value, str) and value in {"true", "True"}:
            args[key] = True
            normalized_keys.append(key)
            if "string_boolean_to_boolean" not in normalization_reasons:
                normalization_reasons.append("string_boolean_to_boolean")
        elif isinstance(value, str) and value in {"false", "False"}:
            args[key] = False
            normalized_keys.append(key)
            if "string_boolean_to_boolean" not in normalization_reasons:
                normalization_reasons.append("string_boolean_to_boolean")

    _normalize_radius_clamp(
        request.action,
        args,
        normalized_keys=normalized_keys,
        normalization_reasons=normalization_reasons,
        clamped_args=clamped_args,
    )

    if not normalized_keys:
        return request, {}

    info = {
        "args_normalized": True,
        "normalized_arg_keys": normalized_keys,
        "normalization_reason": normalization_reasons[0] if len(normalization_reasons) == 1 else "multiple",
        "normalization_reasons": normalization_reasons,
    }
    if clamped_args:
        info["clampedArgs"] = clamped_args

    return request.model_copy(update={"args": args}), info


def _normalize_radius_clamp(
    action: str,
    args: dict[str, Any],
    *,
    normalized_keys: list[str],
    normalization_reasons: list[str],
    clamped_args: dict[str, dict[str, int]],
) -> None:
    if action not in {"mine_coal", "mine_iron_ore", "mine_stone", "acquire_blocks"}:
        return
    if "radius" not in args:
        return

    value = args["radius"]
    if not isinstance(value, int) or isinstance(value, bool):
        return

    clamped = max(8, min(96, value))
    if clamped == value:
        return

    args["radius"] = clamped
    clamped_args["radius"] = {"from": value, "to": clamped}
    if "radius" not in normalized_keys:
        normalized_keys.append("radius")
    if "arg_clamped" not in normalization_reasons:
        normalization_reasons.append("arg_clamped")


def validate_action(action_request: ActionRequest) -> ActionRequest:
    request, _canonical_info = canonicalize_action_request(action_request)
    request, _normalization_info = normalize_action_args(request)

    # Gate 1: action must be in ALLOWED_ACTIONS.
    if request.action not in ALLOWED_ACTIONS:
        # For catalog actions not yet in ALLOWED_ACTIONS, reject clearly.
        status = catalog_status(request.action)
        if status in {"planned", "stub"}:
            raise PolicyError(
                f"Action '{request.action}' is planned but not yet implemented. "
                "It cannot be executed."
            )
        if status is None:
            allowed = ", ".join(sorted(ALLOWED_ACTIONS))
            raise PolicyError(f"Action '{request.action}' is not allowed. Allowed actions: {allowed}.")
        # partial/implemented but not in ALLOWED_ACTIONS → unknown route
        allowed = ", ".join(sorted(ALLOWED_ACTIONS))
        raise PolicyError(f"Action '{request.action}' is not allowed. Allowed actions: {allowed}.")

    request = _sanitize_action_args(request)
    _reject_unknown_args(request.action, request.args)

    if request.action == "say":
        _validate_say(request.args)
    elif request.action in {"look_at_player", "follow_player", "come_here"}:
        _validate_optional_username(request.action, request.args)
    elif request.action == "set_vtuber_mood":
        _validate_mood(request.args)
    elif request.action == "acquire_blocks":
        _validate_acquire_blocks(request.args)
    elif request.action == "navigate_to_block_type":
        _validate_navigate_to_block_type(request.args)
    elif request.action == "collect_wood":
        _validate_optional_count(request.action, request.args, max_count=16)
    elif request.action in {"craft_planks", "craft_sticks", "craft_crafting_table"}:
        _validate_optional_count(request.action, request.args, max_count=64)
    elif request.action == "craft_item":
        _validate_craft_item(request.args)
    elif request.action == "craft_torches":
        _validate_optional_count("craft_torches", request.args, max_count=64)
    elif request.action in {
        "craft_furnace",
        "craft_chest",
        "craft_shield",
        "craft_bucket",
        "craft_iron_pickaxe",
        "craft_iron_sword",
        "craft_iron_armor",
    }:
        pass
    elif request.action == "mine_stone":
        _validate_optional_count(request.action, request.args, max_count=16)
        _validate_optional_int_range(request.action, request.args, "radius", min_value=8, max_value=96)
    elif request.action == "mine_coal":
        _validate_mine_coal(request.args)
    elif request.action == "mine_iron_ore":
        _validate_optional_count(request.action, request.args, max_count=32)
        _validate_optional_int_range(request.action, request.args, "radius", min_value=8, max_value=96)
    elif request.action == "smelt_item":
        _validate_smelt_item(request.args)
    elif request.action == "smelt_iron":
        _validate_optional_count("smelt_iron", request.args, max_count=32)
    elif request.action == "explore_nearby":
        _validate_optional_int_range(request.action, request.args, "radius", min_value=8, max_value=64)
    elif request.action == "look_around":
        _validate_optional_int_range(request.action, request.args, "radius", min_value=8, max_value=32)
    elif request.action == "equip_best_tool":
        _validate_item_name(request.action, request.args, field="block")
    elif request.action == "debug_collect_drops":
        _validate_debug_collect_drops(request.args)
    elif request.action in {"scan_for_hostiles", "scan_for_passive_mobs", "scan_for_chests", "scan_for_liquids"}:
        _validate_optional_int_range(request.action, request.args, "radius", 8, 64)
    elif request.action == "scan_for_structures":
        _validate_optional_int_range("scan_for_structures", request.args, "radius", 16, 128)
    elif request.action == "scan_for_specific_block":
        _validate_scan_specific_block(request.args)
    elif request.action == "drop_item":
        _validate_drop_item(request.args)
    elif request.action == "equip_armor":
        _validate_enum_optional("equip_armor", request.args, "mode", EQUIP_ARMOR_MODES)
    elif request.action == "equip_tool":
        _validate_item_name("equip_tool", request.args, field="tool")
        _validate_item_name("equip_tool", request.args, field="block")
    elif request.action == "select_hotbar_slot":
        _validate_optional_int_range("select_hotbar_slot", request.args, "slot", 0, 8)
    elif request.action == "loot_chest":
        _validate_enum_optional("loot_chest", request.args, "priority", LOOT_PRIORITIES)
    elif request.action == "deposit_items":
        _validate_items_list("deposit_items", request.args)
        _validate_deposit_items(request.args)
    elif request.action == "withdraw_items":
        _validate_items_list("withdraw_items", request.args)
    elif request.action == "mark_waypoint":
        _validate_mark_waypoint(request.args)
    elif request.action == "return_to_waypoint":
        _validate_waypoint_label("return_to_waypoint", request.args)
    elif request.action in {"recover_death_items", "abandon_death_recovery", "return_to_spawn_or_home"}:
        pass  # no args to validate
    elif request.action == "find_safe_workspace":
        _validate_optional_int_range("find_safe_workspace", request.args, "radius", 8, 64)
        _validate_enum_optional("find_safe_workspace", request.args, "purpose", WORKSPACE_PURPOSES)
    elif request.action == "setup_workspace":
        _validate_optional_int_range("setup_workspace", request.args, "radius", 8, 64)
        _validate_boolean_flag("setup_workspace", request.args, "need_crafting_table")
        _validate_boolean_flag("setup_workspace", request.args, "need_furnace")
        _validate_boolean_flag("setup_workspace", request.args, "need_chest")
    elif request.action == "approach_station":
        _validate_required_enum("approach_station", request.args, "station", STATION_TYPES)
        _validate_optional_int_range("approach_station", request.args, "radius", 2, 6)
    elif request.action == "return_to_position":
        _validate_return_to_position(request.args)
    elif request.action == "return_to_workspace":
        _validate_enum_optional("return_to_workspace", request.args, "purpose", WORKSPACE_PURPOSES)
    elif request.action == "return_to_known_position":
        label = request.args.get("label")
        if label is not None and (not isinstance(label, str) or len(label) > 64 or not label.strip()):
            raise PolicyError("Action 'return_to_known_position' args.label must be a non-empty string ≤64 chars.")
    elif request.action == "set_home_position":
        pass  # no args
    elif request.action == "place_furnace":
        _validate_optional_int_range("place_furnace", request.args, "radius", 1, 8)
        _validate_boolean_flag("place_furnace", request.args, "allowPrepareArea")
    elif request.action == "dig_staircase":
        _validate_dig_staircase(request.args)
    elif request.action == "pillar_up":
        _validate_pillar_up(request.args)
    elif request.action == "bridge_gap":
        _validate_bridge_gap(request.args)
    elif request.action == "place_block_in_direction":
        _validate_place_in_direction(request.args)
    elif request.action in {"set_sneak", "set_sprint"}:
        _validate_boolean_required(request.action, request.args, "enabled")
    elif request.action == "place_block":
        _validate_place_block(request.args)
    elif request.action == "place_water":
        _validate_place_liquid_mode("place_water", request.args, PLACE_WATER_MODES)
    elif request.action == "place_lava":
        _validate_place_liquid_mode("place_lava", request.args, PLACE_LAVA_MODES)
    elif request.action == "attack_mob":
        _validate_attack_mob(request.args)
    elif request.action in {
        "attack_nearest_hostile", "retreat_from_combat", "block_with_shield",
        "charge_bow", "deflect_ghast_fireball", "kite_mob",
        "kill_blaze", "kill_enderman",
    }:
        pass  # no args to validate
    elif request.action == "shoot_bow":
        _validate_item_name("shoot_bow", request.args, field="target")
    elif request.action == "throw_ender_pearl":
        _validate_enum_optional("throw_ender_pearl", request.args, "mode", ENDER_PEARL_MODES)
    elif request.action == "kill_passive_mob":
        _validate_kill_passive_mob(request.args)
    elif request.action == "find_lava_pool":
        _validate_optional_int_range("find_lava_pool", request.args, "radius", 16, 128)
    elif request.action == "collect_obsidian":
        _validate_optional_count("collect_obsidian", request.args, max_count=14)
    elif request.action in {
        "throw_eye_of_ender", "locate_stronghold_step", "dig_staircase_to_stronghold",
        "scan_for_end_portal_room", "activate_end_portal", "enter_end",
    }:
        pass  # no args to validate
    elif request.action in {
        "end_safe_landing", "equip_pumpkin_head", "look_down_around_endermen",
        "scan_end_crystals", "destroy_end_crystal", "destroy_caged_end_crystal",
        "destroy_nearby_end_crystals", "attack_perched_dragon", "attack_dragon_with_bow",
        "dragon_phase_crystals", "dragon_phase_circle", "dragon_phase_perch",
        "fight_dragon_phase", "return_to_overworld_via_end_portal",
    }:
        pass  # no args to validate
    elif request.action == "craft_eyes_of_ender":
        _validate_optional_count("craft_eyes_of_ender", request.args, max_count=12)
    elif request.action in {
        "equip_gold_armor", "avoid_opening_chests_near_piglins",
        "retreat_from_nether_danger", "leave_nether",
    }:
        pass  # no args to validate
    elif request.action == "navigate_nether_safely":
        _validate_enum_optional("navigate_nether_safely", request.args, "direction",
                                frozenset({"north", "south", "east", "west"}))
    elif request.action == "barter_with_piglins":
        _validate_optional_count("barter_with_piglins", request.args, max_count=16)
    elif request.action == "find_nether_fortress":
        _validate_optional_int_range("find_nether_fortress", request.args, "radius", 32, 96)
    elif request.action == "collect_blaze_rods":
        _validate_optional_count("collect_blaze_rods", request.args, max_count=12)
    elif request.action == "describe_actions":
        _validate_describe_actions(request.args)
    elif request.action == "unstuck_escape":
        _validate_optional_int_range("unstuck_escape", request.args, "radius", 4, 16)
        _validate_enum_optional("unstuck_escape", request.args, "mode",
                                frozenset({"safe_random_walk", "dig_clearance", "upward_step", "any"}))

    return request


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _list_string_arg_keys(action: str) -> frozenset[str]:
    spec = CATALOG.get(action)
    if spec is None or not isinstance(spec.args_schema, dict):
        return frozenset()

    keys: set[str] = set()
    for key, description in spec.args_schema.items():
        text = str(description).lower()
        if "list" not in text:
            continue
        if "name" in text or "string" in text or "block" in text or "item" in text or "action" in text:
            keys.add(str(key))
    return frozenset(keys)

def _sanitize_action_args(request: ActionRequest) -> ActionRequest:
    args = dict(request.args or {})
    changed = False
    if (
        request.action in HARMLESS_COUNT_NO_ARG_ACTIONS
        and args.get("count") == 1
    ):
        args.pop("count", None)
        changed = True
    return request.model_copy(update={"args": args}) if changed else request

def _reject_unknown_args(action: str, args: dict[str, Any]) -> None:
    allowed_args = _ACTION_ARGS.get(action, frozenset())
    unknown_args = sorted(set(args) - allowed_args)

    if not unknown_args:
        return

    unknown = ", ".join(unknown_args)
    if not allowed_args:
        raise PolicyError(f"Action '{action}' does not accept args: {unknown}.")

    allowed = ", ".join(sorted(allowed_args))
    raise PolicyError(f"Action '{action}' received unknown args: {unknown}. Allowed args: {allowed}.")


def _validate_say(args: dict[str, Any]) -> None:
    message = args.get("message")

    if not isinstance(message, str) or not message.strip():
        raise PolicyError("Action 'say' requires args.message as a non-empty string.")

    if len(message) > 240:
        raise PolicyError("Action 'say' args.message must be at most 240 characters.")

    if message.lstrip().startswith("/"):
        raise PolicyError("Action 'say' cannot send slash commands.")


def _validate_optional_username(action: str, args: dict[str, Any]) -> None:
    if "username" not in args:
        return

    username = args["username"]
    if not isinstance(username, str) or not username.strip():
        raise PolicyError(f"Action '{action}' args.username must be a non-empty string when provided.")

    if len(username) > 32:
        raise PolicyError(f"Action '{action}' args.username must be at most 32 characters.")


def _validate_mood(args: dict[str, Any]) -> None:
    mood = args.get("mood")

    if not isinstance(mood, str) or mood not in ALLOWED_MOODS:
        allowed = ", ".join(sorted(ALLOWED_MOODS))
        raise PolicyError(f"Action 'set_vtuber_mood' requires args.mood to be one of: {allowed}.")


def _validate_optional_count(action: str, args: dict[str, Any], max_count: int) -> None:
    if "count" not in args:
        return

    count = args["count"]
    if not isinstance(count, int) or isinstance(count, bool):
        raise PolicyError(f"Action '{action}' args.count must be an integer when provided.")

    if count < 1 or count > max_count:
        raise PolicyError(f"Action '{action}' args.count must be between 1 and {max_count}.")


def _validate_craft_item(args: dict[str, Any]) -> None:
    item = args.get("item")
    if not isinstance(item, str) or not item.strip():
        raise PolicyError("Action 'craft_item' requires args.item as a non-empty string.")
    if item not in CRAFT_ITEM_ALLOWED_ITEMS:
        allowed_items = sorted(set(CRAFT_ITEM_ALLOWED_ITEMS) | set(CRAFT_ITEM_ACTION_ALIASES))
        possible_next_actions = sorted({
            action for action in CRAFT_ITEM_ACTION_ALIASES.values()
            if action in ALLOWED_ACTIONS
        } | {
            "describe_actions",
            "look_around",
            "status",
        })
        allowed = ", ".join(allowed_items)
        normalized_item = _normalize_craft_item_alias(item)
        raise PolicyError(
            f"Action 'craft_item' args.item is unsupported_craft_item: {item}. Allowed items: {allowed}.",
            details={
                "failure_type": "invalid_action_args",
                "stop_reason": "unsupported_craft_item",
                "invalid_item": normalized_item,
                "allowed_items": allowed_items,
                "possible_next_actions": possible_next_actions,
            },
        )
    _validate_optional_count("craft_item", args, max_count=64)
    if item in CRAFT_ITEM_SINGLE_COUNT and args.get("count", 1) != 1:
        raise PolicyError(f"Action 'craft_item' args.count must be 1 for {item}.")


def _normalize_craft_item_alias(item: str) -> str:
    return item.strip().lower().replace("-", "_").replace(" ", "_")


def _validate_smelt_item(args: dict[str, Any]) -> None:
    input_name = args.get("input")
    if not isinstance(input_name, str) or not input_name.strip():
        raise PolicyError(
            "Action 'smelt_item' requires args.input as a non-empty string.",
            details={
                "failure_type": "invalid_args",
                "repeatable_now": False,
                "repeat_condition": "Provide a valid args.input before retrying.",
                "failed_because": [{
                    "kind": "invalid_args",
                    "action": "smelt_item",
                    "missing_arg": "input",
                    "expected": "one of allowed smeltable item ids",
                }],
            },
        )
    if input_name not in SMELT_INPUTS:
        raise PolicyError(
            f"Action 'smelt_item' args.input must be one of: {', '.join(sorted(SMELT_INPUTS))}.",
            details={
                "failure_type": "invalid_args",
                "repeatable_now": False,
                "repeat_condition": "Choose a valid input from allowed_values before retrying.",
                "failed_because": [{
                    "kind": "invalid_enum_value",
                    "action": "smelt_item",
                    "arg": "input",
                    "received": input_name,
                    "allowed_values": sorted(SMELT_INPUTS),
                }],
            },
        )
    _validate_optional_count("smelt_item", args, max_count=64)
    fuel = args.get("fuel")
    if fuel is None:
        return
    if not isinstance(fuel, str) or not fuel.strip():
        raise PolicyError("Action 'smelt_item' args.fuel must be a non-empty string when provided.")
    if fuel not in SMELT_FUELS:
        allowed = ", ".join(sorted(SMELT_FUELS))
        raise PolicyError(f"Action 'smelt_item' args.fuel must be one of: {allowed}.")


def _validate_mine_coal(args: dict[str, Any]) -> None:
    _validate_optional_count("mine_coal", args, max_count=32)
    _validate_optional_int_range("mine_coal", args, "radius", min_value=8, max_value=96)
    if "allowExcavate" in args and not isinstance(args["allowExcavate"], bool):
        raise PolicyError("Action 'mine_coal' args.allowExcavate must be a boolean when provided.")
    access_mode = args.get("accessMode")
    if access_mode is not None and access_mode not in ALLOWED_ACQUIRE_ACCESS_MODES:
        allowed = ", ".join(sorted(ALLOWED_ACQUIRE_ACCESS_MODES))
        raise PolicyError(f"Action 'mine_coal' args.accessMode must be one of: {allowed}.")


def _validate_acquire_blocks(args: dict[str, Any]) -> None:
    _validate_acquire_targets("acquire_blocks", args)
    _validate_optional_count("acquire_blocks", args, max_count=32)
    _validate_optional_int_range("acquire_blocks", args, "radius", min_value=8, max_value=96)

    if "allowExcavate" in args and not isinstance(args["allowExcavate"], bool):
        raise PolicyError("Action 'acquire_blocks' args.allowExcavate must be a boolean when provided.")

    access_mode = args.get("accessMode")
    if access_mode is not None and access_mode not in ALLOWED_ACQUIRE_ACCESS_MODES:
        allowed = ", ".join(sorted(ALLOWED_ACQUIRE_ACCESS_MODES))
        raise PolicyError(f"Action 'acquire_blocks' args.accessMode must be one of: {allowed}.")


def _validate_navigate_to_block_type(args: dict[str, Any]) -> None:
    _validate_acquire_targets("navigate_to_block_type", args)
    _validate_optional_int_range("navigate_to_block_type", args, "radius", min_value=8, max_value=96)


def _validate_acquire_targets(action: str, args: dict[str, Any]) -> None:
    targets = args.get("targets")
    if not isinstance(targets, list) or len(targets) == 0:
        raise PolicyError(
            f"Action '{action}' requires args.targets as a non-empty list of allowed resource block names.",
            details={
                "failure_type": "invalid_args",
                "stop_reason": "missing_required_arg",
                "repeatable_now": False,
                "repeat_condition": "Provide a valid non-empty targets list before retrying.",
                "failed_because": [{
                    "kind": "invalid_args",
                    "action": action,
                    "missing_arg": "targets",
                    "expected": "non-empty list of allowed resource blocks",
                }],
            },
        )

    for target in targets:
        if not isinstance(target, str):
            raise PolicyError(
                f"Action '{action}' targets must be strings.",
                details={
                    "failure_type": "invalid_args",
                    "repeatable_now": False,
                    "failed_because": [{"kind": "invalid_args", "action": action, "missing_arg": "targets", "expected": "list of strings"}],
                },
            )
        # Station blocks are not resource-navigation targets.
        if target in STATION_TYPES:
            raise PolicyError(
                f"navigate_to_block_type cannot target '{target}' — stations use approach_station, not navigate_to_block_type.",
                details={
                    "failure_type": "wrong_action_for_target_type",
                    "stop_reason": "wrong_action_for_target_type",
                    "repeatable_now": False,
                    "repeat_condition": "Use approach_station for station blocks (crafting_table, furnace, chest).",
                    "failed_because": [{
                        "kind": "wrong_action_for_target_type",
                        "target": target,
                        "target_type": "station",
                        "action_used": action,
                        "appropriate_action_family": "station_access",
                        "station_action": "approach_station",
                    }],
                },
            )
        if target not in ALLOWED_ACQUIRE_TARGETS:
            allowed = ", ".join(sorted(ALLOWED_ACQUIRE_TARGETS))
            raise PolicyError(
                f"Action '{action}' target is not allowed: {target}. Allowed targets: {allowed}.",
                details={
                    "failure_type": "invalid_args",
                    "repeatable_now": False,
                    "failed_because": [{"kind": "invalid_args", "action": action, "missing_arg": "targets", "expected": "allowed resource block name"}],
                },
            )


def _validate_optional_int_range(
    action: str,
    args: dict[str, Any],
    arg_name: str,
    min_value: int,
    max_value: int,
) -> None:
    if arg_name not in args:
        return

    value = args[arg_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise PolicyError(f"Action '{action}' args.{arg_name} must be an integer when provided.")

    if value < min_value or value > max_value:
        raise PolicyError(f"Action '{action}' args.{arg_name} must be between {min_value} and {max_value}.")


# ---------------------------------------------------------------------------
# Planned-action validator stubs
# These are no-ops today. Wire them into validate_action when the corresponding
# ALLOWED_ACTIONS entry is added and Node implements the action.
# ---------------------------------------------------------------------------

def _validate_generic_count(action: str, args: dict[str, Any], max_count: int = 64) -> None:
    _validate_optional_count(action, args, max_count=max_count)


def _validate_waypoint_name(action: str, args: dict[str, Any]) -> None:
    name = args.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise PolicyError(f"Action '{action}' args.name must be a non-empty string when provided.")
    if name is not None and len(name) > 64:
        raise PolicyError(f"Action '{action}' args.name must be at most 64 characters.")


def _validate_direction(action: str, args: dict[str, Any]) -> None:
    direction = args.get("direction")
    if direction is not None and direction not in {"north", "south", "east", "west", "up", "down"}:
        raise PolicyError(f"Action '{action}' args.direction must be a cardinal direction.")


def _validate_boolean_flag(action: str, args: dict[str, Any], field: str) -> None:
    if field in args and not isinstance(args[field], bool):
        raise PolicyError(f"Action '{action}' args.{field} must be a boolean.")


def _validate_hotbar_slot(action: str, args: dict[str, Any]) -> None:
    slot = args.get("slot")
    if slot is not None:
        if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0 or slot > 8:
            raise PolicyError(f"Action '{action}' args.slot must be an integer 0-8.")


def _validate_item_name(action: str, args: dict[str, Any], field: str = "item") -> None:
    value = args.get(field)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise PolicyError(f"Action '{action}' args.{field} must be a non-empty string when provided.")


def _validate_debug_collect_drops(args: dict[str, Any]) -> None:
    _validate_optional_int_range("debug_collect_drops", args, "radius", 2, 32)
    target_items = args.get("targetItems")
    if target_items is not None:
        if not isinstance(target_items, list) or len(target_items) == 0:
            raise PolicyError("Action 'debug_collect_drops' args.targetItems must be a non-empty list when provided.")
        for t in target_items:
            if not isinstance(t, str) or not t.strip():
                raise PolicyError("Action 'debug_collect_drops' args.targetItems entries must be non-empty strings.")


def _validate_scan_specific_block(args: dict[str, Any]) -> None:
    targets = args.get("targets")
    if not isinstance(targets, list) or len(targets) == 0:
        raise PolicyError(
            "Action 'scan_for_specific_block' requires args.targets as a non-empty list of block names.",
            details={
                "failure_type": "invalid_args",
                "repeatable_now": False,
                "repeat_condition": "Provide a non-empty targets list before retrying.",
                "failed_because": [{
                    "kind": "invalid_args",
                    "action": "scan_for_specific_block",
                    "missing_arg": "targets",
                    "expected": "non-empty list of block names to scan for",
                }],
            },
        )
    for t in targets:
        if not isinstance(t, str) or not t.strip():
            raise PolicyError(
                "Action 'scan_for_specific_block' targets must be non-empty strings.",
                details={
                    "failure_type": "invalid_args",
                    "repeatable_now": False,
                    "repeat_condition": "Provide valid non-empty string block names in targets.",
                    "failed_because": [{
                        "kind": "invalid_args",
                        "action": "scan_for_specific_block",
                        "missing_arg": "targets",
                        "expected": "all targets must be non-empty strings",
                    }],
                },
            )
    _validate_optional_int_range("scan_for_specific_block", args, "radius", 8, 96)


def _validate_deposit_items(args: dict[str, Any]) -> None:
    items = args.get("items", [])
    blocked = [i for i in items if isinstance(i, str) and i in DROP_CRITICAL_ITEMS]
    if blocked:
        raise PolicyError(
            f"Action 'deposit_items' refuses to deposit critical items: {', '.join(blocked)}. "
            "Remove them from the list."
        )


def _validate_drop_item(args: dict[str, Any]) -> None:
    item = args.get("item")
    if not isinstance(item, str) or not item.strip():
        raise PolicyError("Action 'drop_item' requires args.item as a non-empty string.")
    _validate_optional_int_range("drop_item", args, "count", 1, 64)
    if "force" in args and not isinstance(args["force"], bool):
        raise PolicyError("Action 'drop_item' args.force must be a boolean when provided.")
    if item in DROP_CRITICAL_ITEMS and not args.get("force"):
        raise PolicyError(
            f"Action 'drop_item' refuses to drop critical item '{item}'. "
            "Set force=true to override — only do this intentionally."
        )


def _validate_enum_optional(action: str, args: dict[str, Any], field: str, allowed: frozenset[str]) -> None:
    value = args.get(field)
    if value is not None and value not in allowed:
        raise PolicyError(f"Action '{action}' args.{field} must be one of: {', '.join(sorted(allowed))}.")


def _validate_required_enum(action: str, args: dict[str, Any], field: str, allowed: frozenset[str]) -> None:
    value = args.get(field)
    if value not in allowed:
        raise PolicyError(f"Action '{action}' args.{field} must be one of: {', '.join(sorted(allowed))}.")


def _validate_mark_waypoint(args: dict[str, Any]) -> None:
    label = args.get("label")
    if not isinstance(label, str) or not label.strip():
        raise PolicyError("Action 'mark_waypoint' requires args.label as a non-empty string.")
    if len(label) > 64:
        raise PolicyError("Action 'mark_waypoint' args.label must be at most 64 characters.")
    kind = args.get("kind")
    if kind is not None and kind not in VALID_WAYPOINT_KINDS:
        raise PolicyError(
            f"Action 'mark_waypoint' args.kind must be one of: {', '.join(sorted(VALID_WAYPOINT_KINDS))}."
        )


def _validate_waypoint_label(action: str, args: dict[str, Any]) -> None:
    label = args.get("label")
    if not isinstance(label, str) or not label.strip():
        raise PolicyError(f"Action '{action}' requires args.label as a non-empty string.")
    if len(label) > 64:
        raise PolicyError(f"Action '{action}' args.label must be at most 64 characters.")


def _validate_dig_staircase(args: dict[str, Any]) -> None:
    direction = args.get("direction")
    if direction is not None and direction not in STAIRCASE_DIRS:
        raise PolicyError(f"Action 'dig_staircase' args.direction must be one of: {', '.join(sorted(STAIRCASE_DIRS))}.")
    _validate_optional_int_range("dig_staircase", args, "max_steps", 1, 32)


def _validate_pillar_up(args: dict[str, Any]) -> None:
    _validate_optional_int_range("pillar_up", args, "height", 1, 16)
    block = args.get("block")
    if block is not None:
        if not isinstance(block, str) or not block.strip():
            raise PolicyError("Action 'pillar_up' args.block must be a non-empty string when provided.")
        if block not in PILLAR_BRIDGE_ALLOWED_BLOCKS and not block.endswith("_planks"):
            raise PolicyError(f"Action 'pillar_up' block '{block}' is not allowed.")


def _validate_bridge_gap(args: dict[str, Any]) -> None:
    direction = args.get("direction")
    if direction is not None and direction not in BRIDGE_DIRS:
        raise PolicyError(f"Action 'bridge_gap' args.direction must be one of: {', '.join(sorted(BRIDGE_DIRS))}.")
    _validate_optional_int_range("bridge_gap", args, "length", 1, 32)
    block = args.get("block")
    if block is not None:
        if not isinstance(block, str) or not block.strip():
            raise PolicyError("Action 'bridge_gap' args.block must be a non-empty string when provided.")
        if block not in PILLAR_BRIDGE_ALLOWED_BLOCKS and not block.endswith("_planks"):
            raise PolicyError(f"Action 'bridge_gap' block '{block}' is not allowed.")


def _validate_place_in_direction(args: dict[str, Any]) -> None:
    item = args.get("item")
    if not isinstance(item, str) or not item.strip():
        raise PolicyError("Action 'place_block_in_direction' requires args.item as a non-empty string.")
    if (
        item not in PLACE_BLOCK_ALLOWED_ITEMS
        and item not in PILLAR_BRIDGE_ALLOWED_BLOCKS
        and not item.endswith("_planks")
        and not item.endswith("_bed")
    ):
        raise PolicyError(f"Action 'place_block_in_direction' item '{item}' is not allowed.")
    direction = args.get("direction")
    if direction is not None and direction not in PLACE_IN_DIR_DIRS:
        raise PolicyError(f"Action 'place_block_in_direction' direction must be one of: {', '.join(sorted(PLACE_IN_DIR_DIRS))}.")


def _validate_boolean_required(action: str, args: dict[str, Any], field: str) -> None:
    value = args.get(field)
    if not isinstance(value, bool):
        raise PolicyError(f"Action '{action}' requires args.{field} as a boolean.")


_VALID_DIMENSIONS = frozenset({"overworld", "the_nether", "the_end", "minecraft:overworld", "minecraft:the_nether", "minecraft:the_end"})


def _validate_return_to_position(args: dict[str, Any]) -> None:
    for coord in ("x", "y", "z"):
        val = args.get(coord)
        if val is None or not isinstance(val, (int, float)):
            raise PolicyError(f"Action 'return_to_position' requires args.{coord} as a number.")
    dim = args.get("dimension")
    if dim is not None and dim not in _VALID_DIMENSIONS:
        raise PolicyError(f"Action 'return_to_position' args.dimension must be one of: {', '.join(sorted(_VALID_DIMENSIONS))}.")
    radius = args.get("radius")
    if radius is not None and (not isinstance(radius, int) or not (1 <= radius <= 16)):
        raise PolicyError("Action 'return_to_position' args.radius must be an integer 1-16.")


def _validate_place_block(args: dict[str, Any]) -> None:
    item = args.get("item")
    if not isinstance(item, str) or not item.strip():
        raise PolicyError("Action 'place_block' requires args.item as a non-empty string.")
    if (
        item not in PLACE_BLOCK_ALLOWED_ITEMS
        and not item.endswith("_planks")
        and not item.endswith("_bed")
    ):
        raise PolicyError(
            f"Action 'place_block' item '{item}' is not allowed. "
            "Allowed: dirt, cobblestone, stone, crafting_table, furnace, torch, chest, obsidian, *_planks, *_bed."
        )
    if item in {"water_bucket", "lava_bucket"}:
        raise PolicyError("Action 'place_block' cannot place liquids. Use place_water or place_lava.")

    mode = args.get("mode")
    if mode is not None and mode not in PLACE_MODES:
        allowed = ", ".join(sorted(PLACE_MODES))
        raise PolicyError(f"Action 'place_block' args.mode must be one of: {allowed}.")

    direction = args.get("direction")
    if direction is not None and direction not in PLACE_DIRECTIONS:
        allowed = ", ".join(sorted(PLACE_DIRECTIONS))
        raise PolicyError(f"Action 'place_block' args.direction must be one of: {allowed} or null.")


def _validate_place_liquid_mode(action: str, args: dict[str, Any], allowed_modes: frozenset[str]) -> None:
    mode = args.get("mode")
    if mode is not None and mode not in allowed_modes:
        allowed = ", ".join(sorted(allowed_modes))
        raise PolicyError(f"Action '{action}' args.mode must be one of: {allowed}.")


def _validate_items_list(action: str, args: dict[str, Any], field: str = "items") -> None:
    items = args.get(field)
    if items is not None:
        if not isinstance(items, list) or not items:
            raise PolicyError(f"Action '{action}' args.{field} must be a non-empty list when provided.")
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise PolicyError(f"Action '{action}' args.{field} entries must be non-empty strings.")


def _validate_attack_mob(args: dict[str, Any]) -> None:
    mob_type = args.get("mob_type")
    if mob_type is not None and (not isinstance(mob_type, str) or not mob_type.strip()):
        raise PolicyError("Action 'attack_mob' args.mob_type must be a non-empty string when provided.")
    _validate_optional_int_range("attack_mob", args, "radius", 4, 64)


def _validate_kill_passive_mob(args: dict[str, Any]) -> None:
    target = args.get("target")
    if target is not None:
        if not isinstance(target, str) or not target.strip():
            raise PolicyError("Action 'kill_passive_mob' args.target must be a non-empty string when provided.")
        if target not in KILLABLE_PASSIVE_MOBS:
            allowed = ", ".join(sorted(KILLABLE_PASSIVE_MOBS))
            raise PolicyError(
                f"Action 'kill_passive_mob' args.target '{target}' is not a killable passive mob. "
                f"Allowed: {allowed}."
            )


def _validate_describe_actions(args: dict[str, Any]) -> None:
    actions = args.get("actions")
    if not isinstance(actions, list) or not actions:
        raise PolicyError("Action 'describe_actions' requires args.actions as a non-empty list.")
    for item in actions:
        if not isinstance(item, str) or not item.strip():
            raise PolicyError("Action 'describe_actions' args.actions entries must be non-empty strings.")
    if len(actions) > 20:
        raise PolicyError("Action 'describe_actions' args.actions must contain at most 20 action names.")
