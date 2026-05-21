"""
Action Capability Map v2.

Single source of truth for every high-level skill the AI may ever learn.
Rules:
  - status "implemented"  → action exists and works in Node + Python.
  - status "partial"      → action exists but is not robust/fully tested.
  - status "stub"         → Node has a structured not-implemented handler.
  - status "planned"      → roadmap only; no Node implementation yet.
  - exposes_to_llm=True   → action may appear in the LLM state packet.
                            Only set for implemented/partial actions.
  - planned/stub actions are NOT sent to the LLM and NOT allowed by policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vtuber_ai.requirements import (
    Effect,
    Requirement,
    REQ_INVENTORY_ITEM,
    REQ_INVENTORY_ANY,
    REQ_STATION_USABLE,
    REQ_TOOL_TIER,
    REQ_DIMENSION,
    REQ_ACCESSIBLE_BLOCK,
    REQ_HEALTH_MIN,
)


@dataclass
class ActionSpec:
    name: str
    category: str
    # "implemented" | "partial" | "stub" | "planned"
    status: str
    # "low" | "medium" | "high" | "critical"
    risk: str
    description: str
    verifier_signature: str
    # "safe_retry" | "idempotent" | "stateful_retry" | "stateful_no_retry" | "destructive"
    retry_policy: str
    args_schema: dict[str, Any] = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    requires_world_state: list[str] = field(default_factory=list)
    moves_bot: bool = False
    can_dig: bool = False
    can_place: bool = False
    can_fight: bool = False
    can_use_container: bool = False
    exposes_to_llm: bool = False
    # Generic typed requirements and effects (new in v3)
    requirements: list[Requirement] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)


def _s(
    name: str,
    category: str,
    status: str,
    risk: str,
    description: str,
    verifier_signature: str,
    retry_policy: str,
    args_schema: dict[str, Any] | None = None,
    preconditions: list[str] | None = None,
    produces: list[str] | None = None,
    consumes: list[str] | None = None,
    requires_world_state: list[str] | None = None,
    moves_bot: bool = False,
    can_dig: bool = False,
    can_place: bool = False,
    can_fight: bool = False,
    can_use_container: bool = False,
    exposes_to_llm: bool | None = None,
    requirements: list[Requirement] | None = None,
    effects: list[Effect] | None = None,
) -> ActionSpec:
    expose = exposes_to_llm if exposes_to_llm is not None else status in {"implemented", "partial"}
    return ActionSpec(
        name=name,
        category=category,
        status=status,
        risk=risk,
        description=description,
        verifier_signature=verifier_signature,
        retry_policy=retry_policy,
        args_schema=args_schema or {},
        preconditions=preconditions or [],
        produces=produces or [],
        consumes=consumes or [],
        requires_world_state=requires_world_state or [],
        moves_bot=moves_bot,
        can_dig=can_dig,
        can_place=can_place,
        can_fight=can_fight,
        can_use_container=can_use_container,
        exposes_to_llm=expose,
        requirements=requirements or [],
        effects=effects or [],
    )


# ---------------------------------------------------------------------------
# Full catalog definition
# ---------------------------------------------------------------------------

_CATALOG_LIST: list[ActionSpec] = [

    # -----------------------------------------------------------------------
    # CORE / CONTROL
    # -----------------------------------------------------------------------
    _s("status", "core_control", "implemented", "low",
       "Return current bot status, health, food, position, inventory, and nearby observations.",
       "verify_action_result_ok", "idempotent"),

    _s("say", "core_control", "implemented", "low",
       "Send a short safe chat message (1-240 chars, no slash commands).",
       "verify_action_result_ok", "safe_retry",
       args_schema={"message": "1-240 chars, not a slash command"}),

    _s("look_around", "core_control", "implemented", "low",
       "Refresh nearby observations without moving far.",
       "verify_action_result_ok", "idempotent",
       args_schema={"radius": "8-32 optional"}),

    _s("explore_nearby", "core_control", "implemented", "low",
       "Cautiously scout nearby terrain.",
       "verify_position_changed", "safe_retry",
       args_schema={"radius": "8-64 optional"},
       moves_bot=True),

    _s("stop", "core_control", "implemented", "low",
       "Stop all movement and clear controls.",
       "verify_action_result_ok", "idempotent"),

    _s("jump", "core_control", "implemented", "low",
       "Perform one short jump. Useful to escape soft stuck states.",
       "verify_action_result_ok", "safe_retry"),

    _s("recover_position", "core_control", "implemented", "medium",
       "Clear controls, escape liquid, or reposition to a safe stand position. "
       "Use when the bot seems stuck.",
       "verify_position_changed", "safe_retry",
       moves_bot=True),

    _s("return_to_surface", "core_control", "implemented", "medium",
       "Pathfind or dig-staircase upward until reaching open sky. "
       "Returns partial_success + can_retry if not complete.",
       "verify_position_changed", "stateful_retry",
       preconditions=["bot_is_underground"],
       moves_bot=True, can_dig=True),

    _s("unstuck_escape", "recovery", "implemented", "medium",
       "Emergency escape for cramped underground navigation stalls. "
       "Tries pathfinding to nearby safe positions, then digs body/head clearance if stuck. "
       "Use when repeated return_to_surface/setup_workspace/approach_station fail with no movement. "
       "Returns distance_moved, y_delta, blocks_dug, clearance_created, escape_strategy_used.",
       "verify_position_changed", "safe_retry",
       moves_bot=True, can_dig=True,
       args_schema={
           "radius": {"type": "number", "default": 8, "min": 4, "max": 16},
           "mode": {"type": "string", "enum": ["safe_random_walk", "dig_clearance", "upward_step", "any"], "default": "any"},
       }),

    _s("seek_open_area", "recovery", "implemented", "low",
       "Move toward a more open, surface-adjacent, or wood-accessible position. "
       "Scores candidates by sky-light level, height gain, nearby logs/leaves, and danger avoidance. "
       "Use as a recovery action when collect_wood repeatedly fails target_not_found or target_unreachable "
       "and the environment (not pathfinding) is the bottleneck — the bot needs to be somewhere else. "
       "Returns start/end position, distance_moved, y_delta, sky_visible, nearby_logs counts, selected_strategy.",
       "verify_position_changed", "safe_retry",
       args_schema={
           "radius": {"type": "number", "default": 32, "min": 8, "max": 64},
           "preferSurface": {"type": "boolean", "default": True},
       },
       moves_bot=True,
       exposes_to_llm=True),

    _s("mark_waypoint", "core_control", "implemented", "low",
       "Save the current position and dimension as a named waypoint. "
       "Kinds: home|surface|crafting_area|furnace|mine_entrance|nether_portal_overworld|"
       "nether_portal_nether|fortress|blaze_spawner|stronghold|end_portal_room|death_location|general.",
       "verify_action_result_ok", "idempotent",
       args_schema={"label": "waypoint name (required)", "kind": "waypoint kind optional"}),

    _s("list_waypoints", "core_control", "implemented", "low",
       "Return all saved waypoints from this session and the Python database.",
       "verify_action_result_ok", "idempotent"),

    _s("return_to_waypoint", "core_control", "implemented", "medium",
       "Pathfind to a named saved waypoint. Fails with dimension suggestion if waypoint is in another dimension.",
       "verify_position_changed", "stateful_retry",
       args_schema={"label": "waypoint name (required)"},
       requires_world_state=["waypoint_exists"],
       moves_bot=True),

    _s("navigate_to_block_type", "core_control", "implemented", "low",
       "Move near a resource/world block (logs, stone, coal_ore, iron_ore, etc.). "
       "NOT for stations — use approach_station for crafting_table, furnace, or chest.",
       "verify_position_changed", "stateful_retry",
       args_schema={"targets": "allowed resource block names list (no stations)", "radius": "8-96 optional"},
       preconditions=["target_block_in_radius"],
       moves_bot=True),

    _s("acquire_blocks", "core_control", "implemented", "medium",
       "Collect safe allowlisted blocks using surface search or limited safe staircase access.",
       "verify_inventory_added", "stateful_retry",
       args_schema={
           "targets": "allowed block names list",
           "count": "1-32 optional",
           "radius": "8-96 optional",
           "allowExcavate": "boolean optional",
           "accessMode": "surface_first|safe_staircase optional",
       },
       preconditions=["target_block_in_radius"],
       produces=["target_items"],
       moves_bot=True, can_dig=True),

    # -----------------------------------------------------------------------
    # SENSING
    # -----------------------------------------------------------------------
    _s("check_inventory", "sensing", "implemented", "low",
       "Return structured inventory counts, equipment slots, and hotbar layout.",
       "verify_action_result_ok", "idempotent"),

    _s("check_time_of_day", "sensing", "implemented", "low",
       "Return timeOfDay (0-24000), day count, isDay/isNight, and moon phase.",
       "verify_action_result_ok", "idempotent"),

    _s("check_light_level", "sensing", "implemented", "low",
       "Return block/sky light at bot position plus a safe_from_spawns flag (>= 8). "
       "Falls back to heuristic if Mineflayer cannot read raw light values.",
       "verify_action_result_ok", "idempotent"),

    _s("check_biome", "sensing", "implemented", "low",
       "Return the biome id and name at the bot's current position and dimension.",
       "verify_action_result_ok", "idempotent"),

    _s("scan_for_hostiles", "sensing", "implemented", "low",
       "Return nearby hostile entities with type, distance, position, and immediate_danger flag. "
       "Choose this when uncertain whether combat or flight is needed.",
       "verify_action_result_ok", "idempotent",
       args_schema={"radius": "8-64 optional (default 32)"}),

    _s("scan_for_passive_mobs", "sensing", "implemented", "low",
       "Return nearby passive mobs with food_sources and wool_sources counts. "
       "Useful before kill_passive_mob or collect_food.",
       "verify_action_result_ok", "idempotent",
       args_schema={"radius": "8-64 optional (default 32)"}),

    _s("scan_for_chests", "sensing", "implemented", "low",
       "Locate nearby chest/barrel blocks. Read-only — does not open them. "
       "Use open_chest or loot_chest afterward.",
       "verify_action_result_ok", "idempotent",
       args_schema={"radius": "8-64 optional (default 16)"}),

    _s("scan_for_specific_block", "sensing", "implemented", "low",
       "Scan for specific named blocks within radius. "
       "REQUIRED: targets must be a non-empty list of exact block names, e.g. [\"oak_log\", \"birch_log\"]. "
       "MAX 6 TARGETS per call — the bot scans only the first 6 targets in the list; excess targets are silently ignored. "
       "Omitting targets or passing an empty list causes an invalid_args error. "
       "Returns nearest occurrence of each scanned target. Read-only.",
       "verify_action_result_ok", "idempotent",
       args_schema={"targets": "REQUIRED non-empty list of up to 6 block names to scan for", "radius": "8-96 optional (default 32)"}),

    _s("scan_for_liquids", "sensing", "implemented", "low",
       "Detect nearby water and lava clusters with distance and danger flags. "
       "Useful before pillar_up, bridge_gap, or place_water.",
       "verify_action_result_ok", "idempotent",
       args_schema={"radius": "8-32 optional (default 16)"}),

    _s("scan_for_structures", "sensing", "implemented", "low",
       "Detect generated structures nearby using indicator blocks "
       "(nether_fortress, stronghold, village, dungeon, desert_temple, etc.). "
       "Returns hints — not definitive. Use when exploring for blaze rods or End portal.",
       "verify_action_result_ok", "idempotent",
       args_schema={"radius": "16-128 optional (default 48)"}),

    _s("scan_workspace", "sensing", "implemented", "low",
       "Detect nearby crafting_table, furnace, and chest within radius 8 and report workspace safety/open-space score. "
       "Use this before deciding whether to reuse a known workspace or place a missing station.",
       "verify_action_result_ok", "idempotent"),

    _s("debug_collect_drops", "sensing", "implemented", "low",
       "Attempt to collect item drops already on the ground near the bot's current position. "
       "Does not mine or path to resources. Useful for manually testing drop pickup logic. "
       "Returns full drop-collection diagnostics (nearestDropDistance, dropCollectionMethod, closeDropPickupAttempted, etc.).",
       "verify_action_result_ok", "idempotent",
       args_schema={
           "radius": "2-32 optional (default 8)",
           "targetItems": "string[] optional — item names to collect (default: coal, raw_iron, cobblestone, stone)",
       },
       moves_bot=True),

    # -----------------------------------------------------------------------
    # MOVEMENT / POSITIONING
    # -----------------------------------------------------------------------
    _s("find_safe_workspace", "movement", "implemented", "low",
       "Move to and remember a safe open workspace for crafting/smelting/storage. "
       "Use after placement fails because area is cramped. Does NOT place any stations — only moves and remembers. "
       "Returns open_space_score, can_place_crafting_table/furnace/chest, suggested_next_action.",
       "verify_position_changed", "safe_retry",
       args_schema={"radius": "8-64 optional", "purpose": "crafting|smelting|storage|general optional"},
       moves_bot=True),

    _s("setup_workspace", "movement", "partial", "medium",
       "Create or update a safe workspace with crafting table/furnace/chest. "
       "Navigates to a safe open area (prefers known workspace if nearby), then places requested stations. "
       "Does not place stations in cramped tunnels. "
       "Returns has_crafting_table, has_furnace, has_chest, placed, missing, suggested_next_action.",
       "verify_action_result_ok", "safe_retry",
       args_schema={
           "need_crafting_table": "bool optional (default true)",
           "need_furnace": "bool optional (default false)",
           "need_chest": "bool optional (default false)",
           "radius": "8-64 optional",
       },
       moves_bot=True, can_place=True),

    _s("approach_station", "movement", "implemented", "low",
       "Move close enough to use a station: crafting_table, furnace, or chest. "
       "Use this for stations — NOT navigate_to_block_type which is for resource blocks.",
       "verify_action_result_ok", "safe_retry",
       args_schema={"station": "crafting_table|furnace|chest required", "radius": "2-6 default 3"},
       preconditions=["station_visible"],
       requires_world_state=["station_visible"],
       moves_bot=True),

    _s("return_to_position", "movement", "implemented", "low",
       "Pathfind to explicit xyz coordinates in the current dimension. "
       "Fails with dimension_mismatch if target is in a different dimension. "
       "Internal action — Python dispatches it; not for direct LLM use.",
       "verify_position_changed", "safe_retry",
       args_schema={"x": "number required", "y": "number required", "z": "number required",
                    "dimension": "overworld|the_nether|the_end optional", "radius": "1-16 optional (default 3)"},
       moves_bot=True,
       exposes_to_llm=False),

    _s("return_to_workspace", "movement", "implemented", "low",
       "Return to remembered workspace/base station for crafting, smelting, or storage. "
       "Finds nearest known workspace in current dimension via persistent memory. "
       "If no workspace known, returns suggested_next_action=setup_workspace. "
       "Prefer this over placing new stations when a known workspace exists nearby.",
       "verify_position_changed", "safe_retry",
       args_schema={"purpose": "crafting|smelting|storage|general optional"},
       moves_bot=True),

    _s("return_to_known_position", "movement", "implemented", "low",
       "Navigate to a named persistent waypoint or nearest home/workspace. "
       "Without label: finds nearest home or workspace. With label: navigates to that specific waypoint.",
       "verify_position_changed", "safe_retry",
       args_schema={"label": "waypoint label optional (max 64 chars)"},
       moves_bot=True),

    _s("set_home_position", "movement", "implemented", "low",
       "Mark current position as home base. Remembered persistently across sessions. "
       "Use once after reaching a safe base camp.",
       "verify_action_result_ok", "safe_retry",
       args_schema={},
       moves_bot=False),

    _s("dig_staircase", "movement", "implemented", "medium",
       "Carve a 1×2 staircase corridor. Never digs straight down. "
       "Directions: north|south|east|west|up_to_surface|down|toward_target|down_to_target.",
       "verify_position_changed", "stateful_retry",
       args_schema={"direction": "north|south|east|west|up_to_surface|down|toward_target|down_to_target optional", "max_steps": "1-32 optional"},
       preconditions=["has_pickaxe"],
       moves_bot=True, can_dig=True),

    _s("pillar_up", "movement", "implemented", "medium",
       "Jump and place a block underfoot to rise one block at a time. "
       "Uses cobblestone, dirt, or planks. Returns height_gained.",
       "verify_position_changed", "stateful_retry",
       args_schema={"height": "1-16 optional", "block": "cobblestone|dirt|stone|planks optional"},
       preconditions=["has_pillar_material"],
       consumes=["pillar_block"],
       moves_bot=True, can_place=True),

    _s("bridge_gap", "movement", "implemented", "high",
       "Sneak-place blocks forward over a gap. Stops at lava or walls. "
       "Directions: forward|north|south|east|west.",
       "verify_block_placed", "stateful_retry",
       args_schema={"direction": "forward|north|south|east|west optional", "length": "1-32 optional", "block": "allowed block optional"},
       preconditions=["has_bridge_material"],
       consumes=["bridge_block"],
       moves_bot=True, can_place=True),

    _s("place_block_in_direction", "movement", "implemented", "medium",
       "Place one block in a given direction relative to the bot at floor level. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_block_placed", "idempotent",
       args_schema={"item": "allowed item name", "direction": "north|south|east|west|forward|back|left|right|up|down optional"},
       preconditions=["has_item_in_inventory"],
       consumes=["item"],
       can_place=True),

    _s("mlg_water_bucket", "movement", "implemented", "high",
       "Place water below the bot while falling to cancel fall damage. "
       "Returns not_applicable if bot is not falling.",
       "verify_action_result_ok", "stateful_no_retry",
       preconditions=["has_water_bucket"],
       consumes=["water_bucket"],
       can_place=True),

    _s("enter_boat", "movement", "implemented", "medium",
       "Mount a nearby boat entity. Places a boat from inventory if none nearby and water is available.",
       "verify_action_result_ok", "safe_retry",
       moves_bot=True),

    _s("exit_boat", "movement", "implemented", "low",
       "Dismount the current boat safely.",
       "verify_action_result_ok", "idempotent",
       moves_bot=True),

    _s("set_sneak", "movement", "implemented", "low",
       "Toggle sneak on or off. Use before bridging or working near edges.",
       "verify_action_result_ok", "idempotent",
       args_schema={"enabled": "boolean (required)"}),

    _s("set_sprint", "movement", "implemented", "low",
       "Toggle sprint on or off.",
       "verify_action_result_ok", "idempotent",
       args_schema={"enabled": "boolean (required)"}),

    # -----------------------------------------------------------------------
    # GENERIC PLACEMENT
    # -----------------------------------------------------------------------
    _s("place_block", "placement", "implemented", "medium",
       "Place an allowlisted item (dirt, cobblestone, stone, crafting_table, furnace, torch, chest, obsidian, any _planks or _bed). "
       "Modes: nearby (default), floor, wall, forward, under_self, workspace. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_block_placed", "idempotent",
       args_schema={
           "item": "allowed item name (see PLACE_BLOCK_ALLOWED_ITEMS)",
           "mode": "nearby|floor|wall|forward|under_self|workspace optional",
           "direction": "north|south|east|west|up|down|forward|back|left|right|null optional",
       },
       preconditions=["has_item_in_inventory"],
       consumes=["item"],
       can_place=True),

    _s("place_crafting_table", "placement", "implemented", "low",
       "Place a crafting table from inventory on a safe adjacent block. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_block_placed", "idempotent",
       preconditions=["has_crafting_table_in_inventory"],
       consumes=["crafting_table"],
       produces=["nearby_crafting_table"],
       can_place=True),

    _s("place_furnace", "placement", "implemented", "low",
       "Place a furnace from inventory on a safe adjacent block. "
       "Returns station_already_available if a furnace is already nearby. "
       "If no furnace in inventory returns missing_placeable_item. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_block_placed", "idempotent",
       args_schema={"radius": "1-8 optional (default 4)", "allowPrepareArea": "bool optional (default true)"},
       preconditions=["has_furnace_in_inventory"],
       consumes=["furnace"],
       can_place=True),

    _s("place_torch", "placement", "implemented", "low",
       "Place a torch on the nearest solid floor surface. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_block_placed", "idempotent",
       preconditions=["has_torch_in_inventory"],
       consumes=["torch"],
       can_place=True),

    _s("place_chest", "placement", "implemented", "low",
       "Place a chest on a safe adjacent block. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_block_placed", "idempotent",
       preconditions=["has_chest_in_inventory"],
       consumes=["chest"],
       can_place=True),

    _s("place_bed", "placement", "implemented", "medium",
       "Place a bed with 2-block footprint check. Warns if not in Overworld (sleeping causes explosion in Nether/End). "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_bed_placed", "idempotent",
       preconditions=["has_bed_in_inventory"],
       consumes=["bed"],
       produces=["nearby_bed"],
       can_place=True),

    _s("place_boat", "placement", "implemented", "low",
       "Place a boat on a nearby water surface. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_action_result_ok", "idempotent",
       preconditions=["has_boat_in_inventory", "water_nearby"],
       consumes=["boat"],
       can_place=True),

    _s("place_water", "placement", "implemented", "high",
       "Pour water from a water_bucket. Modes: nearby (default), downward_safety, portal_casting. "
       "For mlg, use mlg_water_bucket instead. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_liquid_placed", "stateful_no_retry",
       args_schema={"mode": "nearby|downward_safety|portal_casting optional"},
       preconditions=["has_water_bucket"],
       consumes=["water_bucket"],
       can_place=True),

    _s("place_lava", "placement", "implemented", "critical",
       "Pour lava from a lava_bucket. Restricted modes only: portal_casting, controlled_source. "
       "Enforces minimum safe distance and flammable-block checks. "
       "If placement fails due to cramped area, choose find_safe_workspace or return_to_surface before retrying.",
       "verify_liquid_placed", "destructive",
       args_schema={"mode": "portal_casting|controlled_source optional"},
       preconditions=["has_lava_bucket"],
       consumes=["lava_bucket"],
       can_place=True),

    # -----------------------------------------------------------------------
    # CRAFTING
    # -----------------------------------------------------------------------
    _s("craft_item", "crafting", "implemented", "low",
       "craft_item(item) only for generic supported utility/iron items. Prefer specific craft_* actions when listed.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"item": "furnace|torch|chest|shield|bucket|iron_pickaxe|iron_sword|iron_helmet|iron_chestplate|iron_leggings|iron_boots|iron_armor", "count": "1-64 optional; forced to 1 for tools/armor/bucket/shield"},
       requires_world_state=["crafting_table_nearby_if_2x2_recipe"]),

    _s("craft_planks", "crafting", "implemented", "low",
       "Craft planks from any logs or stems in inventory.",
       "verify_inventory_added", "safe_retry",
       args_schema={"count": "1-64 optional"},
       preconditions=["has_logs_or_stems"],
       consumes=["log_or_stem"],
       produces=["planks"]),

    _s("craft_sticks", "crafting", "implemented", "low",
       "Craft sticks from planks in inventory.",
       "verify_inventory_added", "safe_retry",
       args_schema={"count": "1-64 optional"},
       preconditions=["has_planks"],
       consumes=["planks"],
       produces=["stick"]),

    _s("craft_crafting_table", "crafting", "implemented", "low",
       "Craft one crafting table from planks.",
       "verify_inventory_added", "safe_retry",
       args_schema={"count": "1 optional"},
       preconditions=["has_4_planks"],
       consumes=["planks"],
       produces=["crafting_table"]),

    _s("craft_wooden_pickaxe", "crafting", "implemented", "low",
       "Craft a wooden pickaxe at a nearby crafting table.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_3_planks", "has_2_sticks"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["planks", "stick"],
       produces=["wooden_pickaxe"],
       requirements=[
           Requirement(kind=REQ_STATION_USABLE, station="crafting_table"),
           Requirement(kind=REQ_INVENTORY_ANY, items=[
               "oak_planks","birch_planks","spruce_planks","jungle_planks",
               "acacia_planks","dark_oak_planks","mangrove_planks","cherry_planks",
           ], count=3),
           Requirement(kind=REQ_INVENTORY_ITEM, item="stick", count=2),
       ]),

    _s("craft_stone_pickaxe", "crafting", "implemented", "low",
       "Craft a stone pickaxe at a nearby crafting table.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_3_cobblestone", "has_2_sticks"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["cobblestone", "stick"],
       produces=["stone_pickaxe"],
       requirements=[
           Requirement(kind=REQ_STATION_USABLE, station="crafting_table"),
           Requirement(kind=REQ_INVENTORY_ITEM, item="cobblestone", count=3),
           Requirement(kind=REQ_INVENTORY_ITEM, item="stick", count=2),
       ]),

    _s("craft_furnace", "crafting", "implemented", "low",
       "Craft a furnace from 8 cobblestone at a crafting table.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_8_cobblestone"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["cobblestone"],
       produces=["furnace"]),

    _s("craft_torches", "crafting", "implemented", "low",
       "Craft torches from coal and sticks.",
       "verify_inventory_added", "safe_retry",
       args_schema={"count": "1-64 optional"},
       preconditions=["has_coal", "has_sticks"],
       consumes=["coal", "stick"],
       produces=["torch"],
       requirements=[
           Requirement(kind=REQ_INVENTORY_ANY, items=["coal", "charcoal"], count=1),
           Requirement(kind=REQ_INVENTORY_ITEM, item="stick", count=1),
       ]),

    _s("craft_chest", "crafting", "implemented", "low",
       "Craft a chest from 8 planks at a crafting table.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_8_planks"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["planks"],
       produces=["chest"]),

    _s("craft_shield", "crafting", "implemented", "low",
       "Craft a shield from planks and iron ingot.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_planks", "has_iron_ingot"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["planks", "iron_ingot"],
       produces=["shield"]),

    _s("craft_bucket", "crafting", "implemented", "low",
       "Craft an iron bucket from 3 iron ingots.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_3_iron_ingots"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["iron_ingot"],
       produces=["bucket"]),

    _s("craft_iron_pickaxe", "crafting", "implemented", "low",
       "Craft an iron pickaxe at a crafting table.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_3_iron_ingots", "has_2_sticks"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["iron_ingot", "stick"],
       produces=["iron_pickaxe"]),

    _s("craft_iron_sword", "crafting", "implemented", "low",
       "Craft an iron sword at a crafting table.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_2_iron_ingots", "has_1_stick"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["iron_ingot", "stick"],
       produces=["iron_sword"]),

    _s("craft_iron_armor", "crafting", "implemented", "low",
       "Craft iron armor pieces in priority order (chestplate, leggings, helmet, boots), equipping crafted pieces.",
       "verify_inventory_added", "stateful_retry",
       preconditions=["has_nearby_crafting_table", "has_iron_ingots_for_at_least_one_piece"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["iron_ingot"],
       produces=["iron_helmet", "iron_chestplate", "iron_leggings", "iron_boots"]),

    _s("craft_bow", "crafting", "planned", "low",
       "Craft a bow from sticks and string.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_3_sticks", "has_3_string"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["stick", "string"],
       produces=["bow"]),

    _s("craft_arrows", "crafting", "planned", "low",
       "Craft arrows from flint, stick, and feather.",
       "verify_inventory_added", "safe_retry",
       args_schema={"count": "1-64 optional"},
       preconditions=["has_flint", "has_sticks", "has_feather"],
       consumes=["flint", "stick", "feather"],
       produces=["arrow"]),

    _s("craft_flint_and_steel", "crafting", "implemented", "medium",
       "Craft flint and steel from iron ingot and flint. "
       "Tries 2×2 inventory craft first; falls back to a crafting table if needed.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_iron_ingot", "has_flint"],
       consumes=["iron_ingot", "flint"],
       produces=["flint_and_steel"]),

    _s("craft_boat", "crafting", "planned", "low",
       "Craft a boat from 5 planks.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_5_planks"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["planks"],
       produces=["boat"]),

    _s("craft_bed", "crafting", "implemented", "low",
       "Craft a bed from 3 planks and 3 same-color wool using a nearby crafting table. "
       "Automatically selects whichever wool color you have at least 3 of. "
       "Returns the bed item name and count crafted.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_3_planks", "has_3_same_color_wool"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["planks", "wool"],
       produces=["bed"]),

    _s("craft_blaze_powder", "crafting", "implemented", "low",
       "Convert blaze rods into blaze powder for Eyes of Ender. 1 rod → 2 powder, no crafting table needed.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_blaze_rod"],
       consumes=["blaze_rod"],
       produces=["blaze_powder"]),

    _s("craft_eyes_of_ender", "crafting", "implemented", "medium",
       "Craft Eyes of Ender from ender pearls and blaze powder (no crafting table needed). "
       "1 ender_pearl + 1 blaze_powder → 1 ender_eye. Crafts up to min(pearls, powder) if count omitted.",
       "verify_inventory_added", "safe_retry",
       args_schema={"count": "1-12 optional"},
       preconditions=["has_ender_pearls", "has_blaze_powder"],
       consumes=["ender_pearl", "blaze_powder"],
       produces=["ender_eye"]),

    _s("craft_diamond_pickaxe", "crafting", "implemented", "low",
       "Craft diamond pickaxe, needed to mine obsidian. Requires crafting table, 3 diamonds, 2 sticks.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_3_diamonds", "has_2_sticks"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["diamond", "stick"],
       produces=["diamond_pickaxe"]),

    _s("craft_diamond_sword", "crafting", "implemented", "low",
       "Craft a diamond sword at a crafting table. Requires 2 diamonds and 1 stick.",
       "verify_inventory_added", "safe_retry",
       preconditions=["has_nearby_crafting_table", "has_2_diamonds", "has_1_stick"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["diamond", "stick"],
       produces=["diamond_sword"]),

    _s("craft_diamond_armor", "crafting", "implemented", "low",
       "Craft diamond armor pieces in priority order (chestplate, leggings, helmet, boots). Equips each piece after crafting.",
       "verify_inventory_added", "stateful_retry",
       preconditions=["has_nearby_crafting_table", "has_diamonds_for_at_least_one_piece"],
       requires_world_state=["crafting_table_nearby"],
       consumes=["diamond"],
       produces=["diamond_helmet", "diamond_chestplate", "diamond_leggings", "diamond_boots"]),

    # -----------------------------------------------------------------------
    # RESOURCE ACQUISITION
    # -----------------------------------------------------------------------
    _s("collect_wood", "resource", "implemented", "low",
       "Collect nearby logs or stems (radius 32, count 1-16).",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-16"},
       produces=["log_or_stem"],
       moves_bot=True, can_dig=True),

    _s("mine_stone", "resource", "implemented", "medium",
       "Mine exposed stone to obtain cobblestone. Requires a pickaxe and health >= 10.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-16"},
       preconditions=["has_pickaxe", "health_gte_10"],
       produces=["cobblestone"],
       moves_bot=True, can_dig=True,
       requirements=[
           Requirement(kind=REQ_TOOL_TIER, tier="wood", tool_type="pickaxe"),
           Requirement(kind=REQ_HEALTH_MIN, value=10.0),
       ]),

    _s("mine_coal", "resource", "implemented", "medium",
       "Mine coal ore. Requires a pickaxe. Handles buried coal via bounded safe staircase excavation.",
       "verify_inventory_added", "stateful_retry",
       args_schema={
           "count": "1-32 optional",
           "radius": "8-96 optional (default 32)",
           "allowExcavate": "boolean optional (default true) — allow digging toward buried coal",
           "accessMode": "exposed|surface_first|safe_staircase optional (default safe_staircase)",
       },
       preconditions=["has_pickaxe"],
       produces=["coal"],
       moves_bot=True, can_dig=True,
       requirements=[
           Requirement(kind=REQ_TOOL_TIER, tier="wood", tool_type="pickaxe"),
       ]),

    _s("mine_iron_ore", "resource", "implemented", "medium",
       "Mine iron ore. Requires a stone pickaxe or better.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-32 optional"},
       preconditions=["has_stone_pickaxe_or_better"],
       produces=["raw_iron"],
       moves_bot=True, can_dig=True,
       requirements=[
           Requirement(kind=REQ_TOOL_TIER, tier="stone", tool_type="pickaxe"),
       ]),

    _s("mine_diamond_ore", "resource", "planned", "high",
       "Mine diamond ore. Requires an iron pickaxe or better.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-8"},
       preconditions=["has_iron_pickaxe_or_better"],
       produces=["diamond"],
       moves_bot=True, can_dig=True),

    _s("mine_redstone", "resource", "planned", "medium",
       "Mine redstone ore. Requires an iron pickaxe or better.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-16"},
       preconditions=["has_iron_pickaxe_or_better"],
       produces=["redstone"],
       moves_bot=True, can_dig=True),

    _s("mine_gold_ore", "resource", "planned", "medium",
       "Mine gold ore. Requires an iron pickaxe or better.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-8"},
       preconditions=["has_iron_pickaxe_or_better"],
       produces=["raw_gold"],
       moves_bot=True, can_dig=True),

    _s("mine_gravel", "resource", "planned", "low",
       "Mine gravel to obtain flint.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-16"},
       produces=["gravel", "flint"],
       moves_bot=True, can_dig=True),

    _s("collect_flint", "resource", "planned", "low",
       "Collect flint by mining gravel blocks.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-8"},
       produces=["flint"],
       moves_bot=True, can_dig=True),

    _s("collect_sand", "resource", "planned", "low",
       "Collect sand blocks.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-16"},
       produces=["sand"],
       moves_bot=True, can_dig=True),

    _s("collect_water", "resource", "implemented", "medium",
       "Fill an empty bucket with water from a water source block within 32 blocks. "
       "Navigates to the source and activates with bucket. Requires an empty bucket.",
       "verify_inventory_added", "stateful_retry",
       preconditions=["has_empty_bucket", "water_source_nearby"],
       consumes=["bucket"],
       produces=["water_bucket"],
       moves_bot=True, can_use_container=True),

    _s("collect_lava", "resource", "implemented", "critical",
       "Fill an empty bucket with lava from a lava source block within 24 blocks. "
       "Approaches from a safe direction; aborts if bot is in liquid. Requires an empty bucket.",
       "verify_inventory_added", "stateful_no_retry",
       preconditions=["has_empty_bucket", "lava_source_nearby"],
       consumes=["bucket"],
       produces=["lava_bucket"],
       moves_bot=True, can_use_container=True),

    _s("collect_obsidian", "resource", "implemented", "high",
       "Mine obsidian blocks. Requires a diamond or netherite pickaxe. "
       "Skips blocks with lava directly below. Returns collected count and partial flag.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-14 optional"},
       preconditions=["has_diamond_pickaxe"],
       produces=["obsidian"],
       moves_bot=True, can_dig=True,
       requirements=[
           Requirement(kind=REQ_TOOL_TIER, tier="diamond", tool_type="pickaxe"),
       ]),

    _s("collect_food", "resource", "planned", "medium",
       "Hunt or harvest food from passive mobs or crops.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-8 optional"},
       produces=["food"],
       can_fight=True),

    # -----------------------------------------------------------------------
    # FURNACE / SMELTING
    # -----------------------------------------------------------------------
    _s("smelt_item", "smelting", "partial", "low",
       "Smelt a smeltable input in a nearby furnace. input must be one of the allowed_values listed in the schema. Returns partial_success/can_retry if output is still cooking.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"input": "raw_iron|raw_gold|raw_beef|raw_chicken|raw_mutton|raw_porkchop|raw_rabbit|cod|salmon|potato", "count": "1-64 optional", "fuel": "coal|charcoal|planks/logs optional"},
       preconditions=["has_furnace_nearby", "has_fuel"],
       requires_world_state=["furnace_nearby"],
       can_use_container=True),

    _s("smelt_iron", "smelting", "partial", "low",
       "Smelt raw iron into iron ingots using a nearby furnace. Bounded wait may return partial progress.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-32 optional"},
       preconditions=["has_furnace_nearby", "has_raw_iron", "has_fuel"],
       requires_world_state=["furnace_nearby"],
       consumes=["raw_iron", "fuel"],
       produces=["iron_ingot"],
       can_use_container=True),

    _s("smelt_food", "smelting", "planned", "low",
       "Cook raw food in a nearby furnace.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"food": "raw food item name", "count": "1-16 optional"},
       preconditions=["has_furnace_nearby", "has_raw_food", "has_fuel"],
       requires_world_state=["furnace_nearby"],
       consumes=["raw_food", "fuel"],
       produces=["cooked_food"],
       can_use_container=True),

    _s("smelt_gold", "smelting", "planned", "low",
       "Smelt raw gold into gold ingots.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-16 optional"},
       preconditions=["has_furnace_nearby", "has_raw_gold", "has_fuel"],
       requires_world_state=["furnace_nearby"],
       consumes=["raw_gold", "fuel"],
       produces=["gold_ingot"],
       can_use_container=True),

    # -----------------------------------------------------------------------
    # INVENTORY / EQUIPMENT / CONTAINERS
    # -----------------------------------------------------------------------
    _s("drop_item", "inventory", "implemented", "medium",
       "Drop an item from inventory. Critical items (diamonds, ender pearls, pickaxes) are blocked unless force=true.",
       "verify_action_result_ok", "stateful_no_retry",
       args_schema={"item": "item name (required)", "count": "1-64 optional", "force": "boolean optional — allow dropping critical items"}),

    _s("equip_armor", "inventory", "implemented", "low",
       "Equip armor by mode: best|gold|iron|diamond|netherite|leather. Gold mode for Piglin neutrality.",
       "verify_action_result_ok", "safe_retry",
       args_schema={"mode": "best|gold|iron|diamond|netherite|leather optional (default: best)"}),

    _s("equip_gold_armor", "inventory", "implemented", "medium",
       "Equip one gold armor piece (prefer boots, then helmet, chestplate, leggings) to prevent Piglin aggro.",
       "verify_action_result_ok", "safe_retry"),

    _s("equip_tool", "inventory", "implemented", "low",
       "Equip a specific tool or the best tool for a block. "
       "Provide block= for auto-select or tool= for a specific item.",
       "verify_action_result_ok", "safe_retry",
       args_schema={"block": "block name optional", "tool": "specific tool item name optional"}),

    _s("equip_best_tool", "inventory", "implemented", "low",
       "Equip the best tool for a block before mining. Pass block name to match tool type; omit for best pickaxe.",
       "verify_action_result_ok", "safe_retry",
       args_schema={"block": "target block name optional"}),

    _s("equip_best_weapon", "inventory", "implemented", "low",
       "Equip the best available weapon. Prefers diamond sword > iron > stone > wooden; falls back to axe.",
       "verify_action_result_ok", "safe_retry"),

    _s("equip_best_armor", "inventory", "implemented", "low",
       "Equip best available armor by slot. Prefers diamond > iron > gold > leather.",
       "verify_action_result_ok", "safe_retry"),

    _s("select_hotbar_slot", "inventory", "implemented", "low",
       "Set the active hotbar slot (0-8). Mainly used for tool selection.",
       "verify_action_result_ok", "idempotent",
       args_schema={"slot": "0-8 (required)"},
       exposes_to_llm=False),

    _s("open_chest", "inventory", "implemented", "low",
       "Open a nearby chest and return its contents summary.",
       "verify_action_result_ok", "idempotent",
       requires_world_state=["chest_nearby"],
       can_use_container=True),

    _s("loot_chest", "inventory", "implemented", "medium",
       "Open a nearby chest and take useful items. "
       "priority: fortress|stronghold|village|general (default: general).",
       "verify_inventory_added", "stateful_retry",
       args_schema={"priority": "fortress|stronghold|village|general optional"},
       requires_world_state=["chest_nearby"],
       can_use_container=True),

    _s("deposit_items", "inventory", "implemented", "medium",
       "Put a specific list of items into a nearby chest. "
       "Critical items (pickaxes, diamonds, ender pearls) are rejected without explicit override.",
       "verify_action_result_ok", "stateful_retry",
       args_schema={"items": "list of item names to deposit (required)"},
       requires_world_state=["chest_nearby"],
       can_use_container=True),

    _s("withdraw_items", "inventory", "implemented", "medium",
       "Take specific items from a nearby chest.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"items": "list of item names to withdraw (required)"},
       requires_world_state=["chest_nearby"],
       can_use_container=True),

    # -----------------------------------------------------------------------
    # SURVIVAL
    # -----------------------------------------------------------------------
    _s("eat_food", "survival", "implemented", "low",
       "Eat available food if hunger recovery is needed.",
       "verify_action_result_ok", "safe_retry",
       preconditions=["has_food_in_inventory"],
       consumes=["food"]),

    _s("flee", "survival", "implemented", "medium",
       "Move away quickly from immediate danger.",
       "verify_position_changed", "safe_retry",
       moves_bot=True),

    _s("retreat_from_combat", "survival", "implemented", "medium",
       "Disengage from the nearest hostile and move ~18 blocks away. "
       "Unlike flee, does not prevent re-engagement — use when you need distance to heal or reposition. "
       "Returns distance_from_threat after retreat.",
       "verify_position_changed", "safe_retry",
       moves_bot=True),

    _s("sleep_if_possible", "survival", "implemented", "low",
       "Sleep through the night using a bed. Only works in the Overworld. "
       "Will place a bed from inventory if none is nearby. "
       "Fails immediately if not night or if a bed explodes (Nether/End).",
       "verify_action_result_ok", "stateful_retry",
       requires_world_state=["is_overworld", "is_night", "no_hostiles_nearby"]),

    _s("set_spawn_with_bed", "survival", "implemented", "low",
       "Set respawn point by interacting with a bed in the Overworld. "
       "Places a bed from inventory if none is nearby. "
       "Stores a 'spawn_bed' waypoint. Works even during daytime.",
       "verify_action_result_ok", "idempotent",
       requires_world_state=["is_overworld"]),

    _s("build_emergency_shelter", "survival", "planned", "high",
       "Quickly place dirt/cobblestone walls and a roof for overnight survival.",
       "verify_block_placed", "stateful_no_retry",
       preconditions=["has_shelter_material"],
       consumes=["dirt_or_cobblestone"],
       can_place=True),

    _s("avoid_hazard", "survival", "planned", "medium",
       "Detect and step away from nearby hazard (cactus, fire, lava edge).",
       "verify_position_changed", "safe_retry",
       moves_bot=True),

    _s("escape_liquid", "survival", "planned", "high",
       "Swim or jump out of water or lava immediately.",
       "verify_position_changed", "safe_retry",
       moves_bot=True),

    _s("handle_stuck", "survival", "planned", "medium",
       "Break the block the bot is inside or jump/strafe to unstick.",
       "verify_position_changed", "safe_retry",
       moves_bot=True, can_dig=True),

    # -----------------------------------------------------------------------
    # DEATH / RECOVERY
    # -----------------------------------------------------------------------
    _s("recover_death_items", "death_recovery", "implemented", "high",
       "Navigate to the last recorded death location and wait for auto-pickup of dropped items. "
       "Only attempts recent death locations, includes despawn warning, and refuses repeated lethal recovery after two failures. "
       "Reports time_remaining_s, visible drops, and recovered item counts.",
       "verify_inventory_added", "stateful_retry",
       preconditions=["death_location_known"],
       moves_bot=True),

    _s("abandon_death_recovery", "death_recovery", "implemented", "low",
       "Give up on recovering the latest death items and mark the recovery as abandoned.",
       "verify_action_result_ok", "idempotent"),

    _s("return_to_spawn_or_home", "death_recovery", "implemented", "medium",
       "Navigate to spawn_bed, home, surface waypoint, or the bridge spawn point after death recovery is unsafe or abandoned.",
       "verify_position_changed", "stateful_retry",
       moves_bot=True),

    # -----------------------------------------------------------------------
    # COMBAT
    # -----------------------------------------------------------------------
    _s("attack_mob", "combat", "implemented", "high",
       "Attack a nearby mob by type (mob_type) or nearest hostile if omitted. "
       "Never attacks players or named mobs. Equips best weapon automatically. "
       "Aborts if health ≤ 8 — use eat_food or retreat_from_combat first. "
       "Returns killed flag, drops gained, and health after.",
       "verify_entity_killed", "stateful_retry",
       args_schema={"mob_type": "entity type name optional", "radius": "4-64 optional (default 24)"},
       preconditions=["has_weapon_or_fists"],
       can_fight=True),

    _s("attack_nearest_hostile", "combat", "implemented", "high",
       "Equip best weapon and attack the nearest hostile. "
       "Refuses to engage a creeper within 5 blocks — use retreat_from_combat instead. "
       "Aborts if health ≤ 8.",
       "verify_entity_killed", "stateful_retry",
       preconditions=["hostile_nearby"],
       can_fight=True),

    _s("kill_passive_mob", "combat", "implemented", "medium",
       "Kill a passive mob (cow, pig, sheep, chicken, rabbit) to collect food and drops. "
       "Provide target to specify type, or omit to target nearest killable passive. "
       "Returns drops gained.",
       "verify_entity_killed", "stateful_retry",
       args_schema={"target": "mob type optional (cow|pig|sheep|chicken|rabbit)"},
       preconditions=["passive_mob_nearby"],
       produces=["food", "drops"],
       can_fight=True),

    _s("kill_blaze", "combat", "implemented", "critical",
       "Kill a Blaze and collect blaze rods. Uses bow if available (preferred), falls back to melee. "
       "Maintains safe distance when using bow. Aborts if health ≤ 8. "
       "Returns blaze_rods count and full drops.",
       "verify_entity_killed", "stateful_retry",
       preconditions=["has_ranged_or_melee_weapon"],
       produces=["blaze_rod"],
       can_fight=True),

    _s("kill_enderman", "combat", "implemented", "high",
       "Kill an Enderman and collect ender pearls. "
       "Looks at feet level to reduce eye-contact aggro. Aborts if health ≤ 8. "
       "Returns ender_pearls count and full drops.",
       "verify_entity_killed", "stateful_retry",
       preconditions=["has_sword"],
       produces=["ender_pearl"],
       can_fight=True),

    _s("block_with_shield", "combat", "implemented", "medium",
       "Equip shield to offhand and hold block stance for ~3 s. "
       "Effective against skeleton arrows, creeper blasts, and blaze fireballs.",
       "verify_action_result_ok", "safe_retry",
       preconditions=["has_shield"],
       can_fight=True),

    _s("shoot_bow", "combat", "implemented", "high",
       "Equip bow, fully charge (1.2 s), and release at target or nearest hostile. "
       "Use for end crystals, ghasts, caged blazes, or dragon. "
       "Returns target hit, drops gained, and health after.",
       "verify_entity_killed", "stateful_retry",
       args_schema={"target": "entity type name optional"},
       preconditions=["has_bow", "has_arrows"],
       consumes=["arrow"],
       can_fight=True),

    _s("charge_bow", "combat", "implemented", "medium",
       "Equip bow and begin drawing without releasing. "
       "Call shoot_bow afterward to aim and release, or deactivate manually.",
       "verify_action_result_ok", "idempotent",
       preconditions=["has_bow"],
       can_fight=True),

    _s("deflect_ghast_fireball", "combat", "partial", "critical",
       "Detect a nearby ghast fireball entity and swing at it to deflect it back. "
       "Best-effort: requires fireball to be within 16 blocks and detectable as an entity. "
       "Returns deflected flag.",
       "verify_action_result_ok", "stateful_no_retry",
       preconditions=["in_nether"],
       can_fight=True),

    _s("kite_mob", "combat", "implemented", "high",
       "Strafe away from a mob while attacking it for up to 10 s. "
       "Maintains 3-6 block distance and swings when in range. "
       "Good for endermen and blazes. Returns killed flag and drops.",
       "verify_entity_killed", "stateful_retry",
       preconditions=["has_weapon", "hostile_nearby"],
       can_fight=True, moves_bot=True),

    _s("throw_ender_pearl", "combat", "implemented", "high",
       "Equip and throw an ender pearl to teleport. "
       "Modes: forward (current look dir), escape (away from nearest threat), "
       "across_gap (current dir), toward_target (toward nearest hostile). "
       "Costs 2.5 hearts fall damage. Returns before/after positions.",
       "verify_position_changed", "stateful_no_retry",
       args_schema={"mode": "forward|escape|across_gap|toward_target optional (default forward)"},
       preconditions=["has_ender_pearl"],
       consumes=["ender_pearl"],
       moves_bot=True),

    # -----------------------------------------------------------------------
    # NETHER PORTAL
    # -----------------------------------------------------------------------
    _s("find_lava_pool", "nether_portal", "implemented", "high",
       "Locate a lava pool suitable for portal construction within a search radius (default 48, max 128). "
       "Navigates near the pool and stores a 'lava_pool' waypoint. Returns pool_position, pool_size, and y_level.",
       "verify_action_result_ok", "stateful_retry",
       args_schema={"radius": "16-128 optional"},
       moves_bot=True),

    _s("build_nether_portal", "nether_portal", "implemented", "high",
       "Place a 14-block obsidian frame (full corners) in the correct portal shape. "
       "Overworld only. Requires 14 obsidian. Marks a nether_portal_overworld waypoint.",
       "verify_block_placed", "stateful_no_retry",
       preconditions=["has_14_obsidian"],
       consumes=["obsidian"],
       can_place=True,
       requirements=[
           Requirement(kind=REQ_DIMENSION, dimension="overworld"),
           Requirement(kind=REQ_INVENTORY_ITEM, item="obsidian", count=14),
       ]),

    _s("cast_nether_portal", "nether_portal", "partial", "high",
       "Use water-on-lava casting to form obsidian for a portal. "
       "Overworld only. Current implementation converts the inner 2 blocks of the bottom row — "
       "always returns partial=true. Use build_nether_portal if you have 14 obsidian.",
       "verify_action_result_ok", "stateful_no_retry",
       preconditions=["has_water_bucket", "lava_pool_nearby"],
       consumes=["water_bucket"],
       can_place=True),

    _s("light_nether_portal", "nether_portal", "implemented", "high",
       "Light the nether portal obsidian frame with flint and steel. "
       "Succeeds early if a portal block is already nearby. Polls for portal blocks after activation.",
       "verify_portal_lit", "idempotent",
       preconditions=["has_flint_and_steel", "obsidian_frame_nearby"],
       consumes=["flint_and_steel"],
       can_place=True),

    _s("enter_nether", "nether_portal", "implemented", "critical",
       "Step into a lit nether portal to teleport to the Nether. "
       "Saves overworld and nether-side waypoints. Fails if already in the Nether.",
       "verify_dimension_changed", "stateful_no_retry",
       preconditions=["portal_lit_nearby"],
       moves_bot=True),

    _s("leave_nether", "nether_portal", "implemented", "critical",
       "Navigate to the nether_portal_nether waypoint and step through to return to the Overworld.",
       "verify_dimension_changed", "stateful_no_retry",
       requires_world_state=["in_nether", "nether_portal_waypoint_stored"],
       moves_bot=True),

    _s("return_to_portal", "nether_portal", "implemented", "high",
       "Navigate back to the known portal in the current dimension "
       "(nether_portal_nether in the Nether, nether_portal_overworld in the Overworld). "
       "Fails in the End where no portal waypoint is stored.",
       "verify_position_changed", "stateful_retry",
       requires_world_state=["portal_location_known"],
       moves_bot=True),

    # -----------------------------------------------------------------------
    # NETHER PROGRESSION
    # -----------------------------------------------------------------------
    _s("navigate_nether_safely", "nether_progression", "implemented", "critical",
       "Move 24 blocks in a cardinal direction through the Nether, scanning for lava ahead before moving. "
       "Returns lava_ahead=true if path is blocked.",
       "verify_position_changed", "stateful_retry",
       args_schema={"direction": "north|south|east|west optional (default: bot facing direction)"},
       requires_world_state=["in_nether"],
       moves_bot=True),

    _s("avoid_opening_chests_near_piglins", "nether_progression", "implemented", "high",
       "Sensing action: returns safe_to_loot=true if no Piglins or Piglin Brutes are within 16 blocks, "
       "otherwise safe_to_loot=false with piglins_nearby count and closest distance.",
       "verify_action_result_ok", "idempotent"),

    _s("find_nether_fortress", "nether_progression", "implemented", "critical",
       "Bounded Nether exploration (max radius 96) scanning for nether_bricks. "
       "Stores a 'fortress' waypoint when found. Returns partial_success+can_retry if radius exhausted without finding one.",
       "verify_milestone", "stateful_retry",
       args_schema={"radius": "32-96 optional (default: 96)"},
       requires_world_state=["in_nether"],
       moves_bot=True),

    _s("find_bastion_or_piglins", "nether_progression", "planned", "high",
       "Locate a Bastion Remnant or a group of Piglins for bartering.",
       "verify_milestone", "stateful_retry",
       requires_world_state=["in_nether"],
       moves_bot=True),

    _s("barter_with_piglins", "nether_progression", "implemented", "high",
       "Drop gold ingots to a nearby Piglin and wait 8 s for barter output. "
       "Returns gold_spent, items_received, and ender_pearls count. Requires wearing at least one gold armor piece.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-16 optional (default: 1)"},
       preconditions=["has_gold_ingot", "piglin_nearby"],
       requires_world_state=["in_nether"],
       consumes=["gold_ingot"],
       produces=["ender_pearl", "other_trade_items"]),

    _s("collect_blaze_rods", "nether_progression", "implemented", "critical",
       "Kill Blazes in a loop until the target rod count is reached (default 6, max 12). "
       "If no Blaze is nearby returns suggested_next_action=find_nether_fortress.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-12 optional (default: 6)"},
       preconditions=["has_weapon", "in_nether"],
       produces=["blaze_rod"],
       can_fight=True),

    _s("collect_ender_pearls", "nether_progression", "planned", "high",
       "Kill Endermen or barter with Piglins to obtain ender pearls.",
       "verify_inventory_added", "stateful_retry",
       args_schema={"count": "1-12 optional"},
       preconditions=["has_weapon_or_gold_ingots"],
       produces=["ender_pearl"],
       can_fight=True),

    _s("retreat_from_nether_danger", "nether_progression", "implemented", "critical",
       "Move 20 blocks away from the nearest Nether threat (ghast, blaze, piglin_brute, hoglin, zoglin, wither_skeleton, magma_cube).",
       "verify_position_changed", "safe_retry",
       moves_bot=True),

    # -----------------------------------------------------------------------
    # STRONGHOLD / END PORTAL
    # -----------------------------------------------------------------------
    _s("throw_eye_of_ender", "stronghold", "implemented", "medium",
       "Equip and throw an Eye of Ender. Tracks the projectile entity to derive travel direction "
       "and stores stronghold_search memory (direction_x, direction_z, throw_count) for locate_stronghold_step.",
       "verify_action_result_ok", "stateful_retry",
       preconditions=["has_ender_eye"],
       consumes=["ender_eye"]),

    _s("locate_stronghold_step", "stronghold", "implemented", "high",
       "Move 64 blocks in the stored eye-of-ender direction, scan for stronghold indicator blocks "
       "(end_portal_frame, stone_bricks, mossy/cracked_stone_bricks). Stores 'stronghold' waypoint if found. "
       "Returns stronghold_found=true and suggests next action.",
       "verify_milestone", "stateful_retry",
       requires_world_state=["stronghold_direction_stored"],
       moves_bot=True),

    _s("dig_staircase_to_stronghold", "stronghold", "implemented", "high",
       "Dig a safe diagonal staircase downward (never straight down) while scanning for stronghold blocks. "
       "Aborts on lava or bedrock. Returns partial_success+can_retry and stronghold_found flag. "
       "Stores 'stronghold' waypoint if indicator blocks are detected.",
       "verify_position_changed", "stateful_retry",
       preconditions=["has_pickaxe"],
       moves_bot=True, can_dig=True),

    _s("scan_for_end_portal_room", "stronghold", "implemented", "high",
       "Scan within 128 blocks for end_portal_frame blocks, navigate to the portal room, and store "
       "the 'end_portal_room' waypoint. Returns filled_frames, empty_frames, eyes_needed, and portal_ready flag.",
       "verify_milestone", "stateful_retry",
       moves_bot=True),

    _s("activate_end_portal", "stronghold", "implemented", "critical",
       "Find all end_portal_frame blocks within 8 blocks, insert ender_eye into each empty frame "
       "using bot.activateBlock. Returns eyes_placed, frames_remaining, and portal_active flag.",
       "verify_block_placed", "stateful_no_retry",
       preconditions=["has_ender_eye", "end_portal_room_found"],
       consumes=["ender_eye"],
       can_place=True,
       requirements=[
           Requirement(kind=REQ_INVENTORY_ITEM, item="ender_eye", count=1),
       ]),

    _s("enter_end", "stronghold", "implemented", "critical",
       "Navigate into an active end_portal block within 8 blocks and wait for dimension change to the_end. "
       "Fails if no end_portal block is present — use activate_end_portal first.",
       "verify_dimension_changed", "stateful_no_retry",
       preconditions=["end_portal_active"],
       moves_bot=True),

    # -----------------------------------------------------------------------
    # END FIGHT
    # -----------------------------------------------------------------------
    _s("end_safe_landing", "end_fight", "implemented", "critical",
       "Ensure the bot can safely leave the End obsidian platform. Bridges a detected gap only when bounded and avoids void movement.",
       "verify_action_result_ok", "stateful_no_retry",
       requires_world_state=["in_the_end"],
       moves_bot=True, can_place=True,
       requirements=[
           Requirement(kind=REQ_DIMENSION, dimension="the_end"),
       ]),

    _s("equip_pumpkin_head", "end_fight", "implemented", "high",
       "Equip a carved pumpkin as helmet to prevent Endermen from aggro-ing.",
       "verify_action_result_ok", "idempotent",
       preconditions=["has_carved_pumpkin"],
       requires_world_state=["in_the_end"]),

    _s("look_down_around_endermen", "end_fight", "implemented", "medium",
       "Look downward and stop movement when Endermen are nearby to reduce accidental aggro.",
       "verify_action_result_ok", "idempotent",
       requires_world_state=["in_the_end"]),

    _s("scan_end_crystals", "end_fight", "implemented", "high",
       "Locate visible End Crystal entities and report positions plus caged/unconfirmed cage status.",
       "verify_action_result_ok", "idempotent",
       requires_world_state=["in_the_end"]),

    _s("destroy_end_crystal", "end_fight", "partial", "high",
       "Destroy one uncaged End Crystal by bow when visible or careful melee when low and reachable. Avoids close explosion range.",
       "verify_entity_killed", "stateful_retry",
       preconditions=["has_ranged_or_melee_weapon"],
       requires_world_state=["in_the_end"],
       can_fight=True),

    _s("destroy_caged_end_crystal", "end_fight", "partial", "critical",
       "Bounded high-risk caged crystal step: break reachable iron bars or suggest pillar_up, then retry crystal destruction.",
       "verify_milestone", "stateful_retry",
       preconditions=["has_pickaxe", "has_ranged_weapon"],
       requires_world_state=["in_the_end"],
       can_dig=True, can_fight=True, moves_bot=True),

    _s("destroy_nearby_end_crystals", "end_fight", "partial", "high",
       "Bounded loop that destroys up to a few reachable End Crystals, returning remaining count and can_retry.",
       "verify_milestone", "stateful_retry",
       preconditions=["has_ranged_or_melee_weapon"],
       requires_world_state=["in_the_end"],
       can_fight=True),

    _s("attack_perched_dragon", "end_fight", "partial", "critical",
       "Bounded melee attack on a likely perched Ender Dragon near the exit portal.",
       "verify_entity_killed", "stateful_retry",
       preconditions=["has_sword", "dragon_is_perched"],
       requires_world_state=["in_the_end"],
       can_fight=True, moves_bot=True),

    _s("attack_dragon_with_bow", "end_fight", "partial", "critical",
       "Shoot the Ender Dragon with arrows while it flies or circles.",
       "verify_entity_killed", "stateful_retry",
       preconditions=["has_bow", "has_arrows"],
       requires_world_state=["in_the_end"],
       consumes=["arrow"],
       can_fight=True),

    _s("use_bed_bomb", "end_fight", "implemented", "critical",
       "Place a bed adjacent to the perched Ender Dragon and activate it to trigger an explosion. "
       "Retreats to safe distance before detonation. Only works in The End. "
       "NOT exposed to LLM — triggered by orchestration logic only.",
       "verify_action_result_ok", "stateful_no_retry",
       preconditions=["has_bed", "health_above_12"],
       requires_world_state=["in_the_end"],
       consumes=["bed"],
       can_fight=True, can_place=True, exposes_to_llm=False),

    _s("avoid_bed_explosion", "end_fight", "implemented", "critical",
       "Move away from a nearby bed before it explodes. "
       "Checks for bed blocks within 16 blocks and retreats to safe distance. "
       "NOT exposed to LLM — triggered by orchestration logic only.",
       "verify_position_changed", "stateful_no_retry",
       requires_world_state=["in_the_end"],
       moves_bot=True, exposes_to_llm=False),

    _s("dragon_phase_crystals", "end_fight", "partial", "critical",
       "Bounded phase: prioritize remaining End Crystals before engaging the dragon.",
       "verify_milestone", "stateful_retry",
       requires_world_state=["in_the_end", "crystals_remaining"]),

    _s("dragon_phase_circle", "end_fight", "partial", "critical",
       "Bounded phase: avoid hazards, eat if needed, and shoot the circling dragon when viable.",
       "verify_milestone", "stateful_retry",
       preconditions=["has_bow", "has_arrows"],
       requires_world_state=["in_the_end"],
       can_fight=True),

    _s("dragon_phase_perch", "end_fight", "partial", "critical",
       "Bounded phase: attack perched dragon with melee, optionally using a bed bomb only when explicitly enabled and safe.",
       "verify_milestone", "stateful_retry",
       preconditions=["has_sword_or_bed"],
       requires_world_state=["in_the_end", "dragon_is_perched"],
       can_fight=True, moves_bot=True),

    _s("fight_dragon_phase", "end_fight", "partial", "critical",
       "One bounded dragon fight controller: avoid hazards, handle Endermen, destroy crystals, attack vulnerable dragon, and return next action.",
       "verify_milestone", "stateful_retry",
       requires_world_state=["in_the_end"]),

    _s("return_to_overworld_via_end_portal", "end_fight", "implemented", "critical",
       "After dragon death, enter the End exit portal to return to the Overworld.",
       "verify_dimension_changed", "stateful_no_retry",
       preconditions=["dragon_dead"],
       requires_world_state=["in_the_end", "exit_portal_open"],
       moves_bot=True),

    _s("finish_dragon_fight", "end_fight", "planned", "critical",
       "Top-level: complete the full Ender Dragon fight sequence.",
       "verify_milestone", "stateful_retry",
       requires_world_state=["in_the_end"]),

    # -----------------------------------------------------------------------
    # META ACTIONS (Python-handled)
    # -----------------------------------------------------------------------
    _s("describe_actions", "core_control", "implemented", "low",
       "Request detailed documentation for one or more actions by name. "
       "Returns args schema, description, and preconditions. "
       "Use when uncertain what an action does or what args it requires.",
       "verify_action_result_ok", "idempotent",
       args_schema={"actions": "list of action names (required)"}),

    # -----------------------------------------------------------------------
    # LEGACY / EXTRA (implemented in Node, not in primary list above)
    # -----------------------------------------------------------------------
    _s("look_at_player", "core_control", "implemented", "low",
       "Look toward a player by username.",
       "verify_action_result_ok", "safe_retry",
       args_schema={"username": "player username optional"}),

    _s("follow_player", "core_control", "implemented", "low",
       "Follow a player by username.",
       "verify_position_changed", "safe_retry",
       args_schema={"username": "player username optional"},
       moves_bot=True),

    _s("come_here", "core_control", "implemented", "low",
       "Navigate to a nearby player.",
       "verify_position_changed", "safe_retry",
       args_schema={"username": "player username optional"},
       moves_bot=True),

    _s("set_vtuber_mood", "core_control", "implemented", "low",
       "Set the bot's displayed mood expression.",
       "verify_action_result_ok", "idempotent",
       args_schema={"mood": "neutral|happy|surprised|scared|focused|confused"},
       exposes_to_llm=False),
]

# ---------------------------------------------------------------------------
# Primary lookup dict
# ---------------------------------------------------------------------------

CATALOG: dict[str, ActionSpec] = {spec.name: spec for spec in _CATALOG_LIST}


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_llm_exposed_specs(bridge_action_names: set[str] | None = None) -> dict[str, ActionSpec]:
    """Return catalog entries eligible for LLM exposure.

    If bridge_action_names is provided, restrict to actions the bridge reports
    as available. Otherwise return all catalog entries with exposes_to_llm=True.
    """
    result: dict[str, ActionSpec] = {}
    for spec in _CATALOG_LIST:
        if not spec.exposes_to_llm:
            continue
        if bridge_action_names is not None and spec.name not in bridge_action_names:
            continue
        result[spec.name] = spec
    return result


def get_llm_action_specs_for_prompt(bridge_action_names: set[str] | None = None) -> dict[str, dict]:
    """Return action descriptions formatted for the LLM state packet.

    Format: {action_name: {"args": {...}, "description": "...", "status": "..."}}
    Only implemented/partial actions exposed to LLM are included.
    """
    exposed = get_llm_exposed_specs(bridge_action_names)
    result: dict[str, dict] = {}
    for name, spec in exposed.items():
        entry: dict = {
            "args": spec.args_schema,
            "description": spec.description,
        }
        if spec.status == "partial":
            entry["status"] = "partial"
            entry["preconditions"] = spec.preconditions
        elif spec.preconditions:
            entry["preconditions"] = spec.preconditions
        result[name] = entry
    return result


def allowed_from_catalog() -> frozenset[str]:
    """Return names of all actions eligible to be executed (implemented or partial + exposes_to_llm)."""
    return frozenset(spec.name for spec in _CATALOG_LIST if spec.exposes_to_llm)


def catalog_status(name: str) -> str | None:
    """Return the status string for an action, or None if not in catalog."""
    spec = CATALOG.get(name)
    return spec.status if spec is not None else None


_VALID_STATUSES = {"implemented", "partial", "stub", "planned"}
_VALID_RETRY_POLICIES = {
    "safe_retry",
    "idempotent",
    "stateful_retry",
    "stateful_no_retry",
    "destructive",
}


def _action_metadata_row(spec: ActionSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "status": spec.status,
        "category": spec.category,
        "implemented": spec.status in {"implemented", "partial"},
        "exposes_to_llm": spec.exposes_to_llm,
        "risk": spec.risk,
        "retry_policy": spec.retry_policy,
        "args_schema": spec.args_schema,
        "verifier_signature": spec.verifier_signature,
    }


def action_metadata_rows() -> list[dict[str, Any]]:
    """Return JSON-friendly metadata rows for every catalog entry."""
    return [_action_metadata_row(spec) for spec in _CATALOG_LIST]


def action_catalog_summary() -> dict[str, int]:
    """Return counts by action status."""
    summary = {"total": len(_CATALOG_LIST), "implemented": 0, "partial": 0, "stub": 0, "planned": 0}
    for spec in _CATALOG_LIST:
        if spec.status not in summary:
            summary[spec.status] = 0
        summary[spec.status] += 1
    return summary


def actions_by_status(status: str) -> list[dict[str, Any]]:
    """Return metadata rows for a status, sorted by action name."""
    return sorted(
        (_action_metadata_row(spec) for spec in _CATALOG_LIST if spec.status == status),
        key=lambda row: row["name"],
    )


CATEGORY_ORDER = [
    "core_control", "sensing", "movement", "placement", "crafting",
    "resource", "smelting", "inventory", "survival", "death_recovery",
    "combat", "nether_portal", "nether_progression", "stronghold", "end_fight",
]

# Short inline hints appended to compact signatures to reduce LLM alias confusion.
# Format: "[hint text]".
COMPACT_HINTS: dict[str, str] = {
    "collect_obsidian": "aka mine_obsidian",
    "collect_flint": "aka mine_flint",
    "collect_wood": "aka mine_logs",
    "craft_item": "only generic utility/iron; prefer specific craft_*",
    "mine_stone": "gets cobblestone",
    "mine_iron_ore": "gets raw_iron",
}


def get_compact_action_signature(spec: ActionSpec) -> str:
    """Return 'name(arg1,arg2?) [hint]' compact signature string for one action spec."""
    if not spec.args_schema:
        sig = f"{spec.name}()"
    else:
        parts = [
            f"{k}?" if "optional" in str(v).lower() else k
            for k, v in spec.args_schema.items()
        ]
        sig = f"{spec.name}({','.join(parts)})"
    hint = COMPACT_HINTS.get(spec.name)
    return f"{sig} [{hint}]" if hint else sig


def get_compact_action_list(
    bridge_action_names: set[str] | None = None,
    max_chars: int = 4000,
) -> str:
    """Return a category-grouped compact action list string.

    Each line: 'category: sig1; sig2; ...'
    Falls back to names-only if the full-args version exceeds max_chars.
    Hard-truncates to max_chars as last resort.
    """
    by_cat: dict[str, list[ActionSpec]] = {}
    for spec in _CATALOG_LIST:
        if not spec.exposes_to_llm:
            continue
        if bridge_action_names is not None and spec.name not in bridge_action_names:
            continue
        by_cat.setdefault(spec.category, []).append(spec)

    ordered = [c for c in CATEGORY_ORDER if c in by_cat]
    for cat in by_cat:
        if cat not in ordered:
            ordered.append(cat)

    def _build(strip_args: bool) -> str:
        lines = []
        for cat in ordered:
            specs = by_cat.get(cat, [])
            if not specs:
                continue
            if strip_args:
                sigs = "; ".join(s.name for s in specs)
            else:
                sigs = "; ".join(get_compact_action_signature(s) for s in specs)
            lines.append(f"{cat}: {sigs}")
        return "\n".join(lines)

    full = _build(strip_args=False)
    if len(full) <= max_chars:
        return full
    stripped = _build(strip_args=True)
    return stripped[:max_chars]


def get_detailed_action_docs(
    action_names: list[str] | tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Return full doc dicts for the requested action names.

    Only returns entries for catalog actions with exposes_to_llm=True.
    """
    result: dict[str, dict[str, Any]] = {}
    for name in action_names:
        spec = CATALOG.get(name)
        if spec is None or not spec.exposes_to_llm:
            continue
        entry: dict[str, Any] = {"args": spec.args_schema, "description": spec.description}
        if spec.status == "partial":
            entry["status"] = "partial"
        if spec.preconditions:
            entry["preconditions"] = spec.preconditions
        result[name] = entry
    return result


def llm_exposed_count(bridge_action_names: set[str] | None = None) -> int:
    """Return count of LLM-exposed actions, optionally filtered to bridge-available ones."""
    return sum(
        1 for spec in _CATALOG_LIST
        if spec.exposes_to_llm
        and (bridge_action_names is None or spec.name in bridge_action_names)
    )


def validate_action_catalog() -> dict[str, Any]:
    """Validate catalog invariants used by policy, prompts, and diagnostics."""
    errors: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for spec in _CATALOG_LIST:
        counts[spec.name] = counts.get(spec.name, 0) + 1

    duplicates = [
        {"name": name, "count": count}
        for name, count in sorted(counts.items())
        if count > 1
    ]
    for duplicate in duplicates:
        errors.append({
            "name": duplicate["name"],
            "field": "name",
            "error": f"duplicate action name appears {duplicate['count']} times",
        })

    for spec in _CATALOG_LIST:
        if not spec.status or spec.status not in _VALID_STATUSES:
            errors.append({
                "name": spec.name,
                "field": "status",
                "error": f"missing or invalid status: {spec.status!r}",
            })
        if spec.args_schema is None or not isinstance(spec.args_schema, dict):
            errors.append({
                "name": spec.name,
                "field": "args_schema",
                "error": "args_schema must be present and must be a dict",
            })
        if not spec.retry_policy or spec.retry_policy not in _VALID_RETRY_POLICIES:
            errors.append({
                "name": spec.name,
                "field": "retry_policy",
                "error": f"missing or invalid retry_policy: {spec.retry_policy!r}",
            })
        if spec.status in {"planned", "stub"} and spec.exposes_to_llm:
            errors.append({
                "name": spec.name,
                "field": "exposes_to_llm",
                "error": f"{spec.status} actions must not be exposed to the LLM",
            })
        if not spec.verifier_signature:
            errors.append({
                "name": spec.name,
                "field": "verifier_signature",
                "error": "verifier_signature is required",
            })

    return {
        "ok": not errors,
        "summary": action_catalog_summary(),
        "duplicates": duplicates,
        "errors": errors,
    }
