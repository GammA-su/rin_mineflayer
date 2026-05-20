"""
Generic action requirement and failure-explanation system.

Each action can declare typed requirements (inventory_item, station_usable,
accessible_block, dimension, …).  check_requirements() evaluates them against
live current_facts / state and returns a RequirementReport.

The report is used to build a factual failure packet for the LLM.  It does NOT
force next actions — the LLM decides what to do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Requirement type constants
# ---------------------------------------------------------------------------

REQ_INVENTORY_ITEM = "inventory_item"
REQ_INVENTORY_ANY = "inventory_any"
REQ_STATION_USABLE = "station_usable"
REQ_TOOL_TIER = "tool_tier"
REQ_DIMENSION = "dimension"
REQ_NEARBY_BLOCK = "nearby_block"
REQ_ACCESSIBLE_BLOCK = "accessible_block"
REQ_SAFE_WORKSPACE = "safe_workspace"
REQ_KNOWN_PLACE = "known_place"
REQ_HEALTH_MIN = "health_min"
REQ_FOOD_MIN = "food_min"
REQ_EQUIPMENT = "equipment"
REQ_WORLD_STRUCTURE = "world_structure"
REQ_ENTITY_NEARBY = "entity_nearby"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Requirement:
    kind: str
    # All fields are optional; each kind uses a subset.
    item: str | None = None            # inventory_item, equipment
    items: list[str] | None = None     # inventory_any
    count: int = 1                     # inventory_item / inventory_any
    station: str | None = None         # station_usable
    tier: str | None = None            # tool_tier  (wood/stone/iron/diamond)
    tool_type: str | None = None       # tool_tier  (pickaxe/sword/axe…)
    dimension: str | None = None       # dimension
    block: str | None = None           # nearby_block, accessible_block
    radius: int | None = None          # nearby_block, accessible_block, entity_nearby
    purpose: str | None = None         # safe_workspace
    kind_tag: str | None = None        # known_place
    value: float | None = None         # health_min, food_min
    slot: str | None = None            # equipment
    item_or_tag: str | None = None     # equipment
    structure: str | None = None       # world_structure
    entity_tag: str | None = None      # entity_nearby


@dataclass
class Effect:
    kind: str
    item: str | None = None
    count: int = 1
    station: str | None = None
    block: str | None = None
    fact: str | None = None
    dimension: str | None = None
    place_kind: str | None = None


@dataclass
class FailedRequirement:
    kind: str
    # Populated based on kind
    item: str | None = None
    items: list[str] | None = None
    need: int | None = None
    have: int | None = None
    station: str | None = None
    usable: bool | None = None
    visible: bool | None = None
    distance: float | None = None
    required_dimension: str | None = None
    current_dimension: str | None = None
    block: str | None = None
    accessible: bool | None = None
    nearest_distance: float | None = None
    tier: str | None = None
    tool_type: str | None = None
    health: float | None = None
    food: float | None = None
    min_value: float | None = None
    entity_tag: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class RequirementReport:
    ok: bool
    failed_requirements: list[FailedRequirement] = field(default_factory=list)
    repeatable_now: bool = True
    relevant_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "failed_requirements": [r.to_dict() for r in self.failed_requirements],
            "repeatable_now": self.repeatable_now,
            "relevant_state": self.relevant_state,
        }


# ---------------------------------------------------------------------------
# Helpers for reading current state
# ---------------------------------------------------------------------------

_TOOL_TIER_ORDER = ["wood", "stone", "iron", "diamond", "netherite"]

_TIER_ITEMS: dict[str, list[str]] = {
    "wood":      ["wooden_pickaxe", "wooden_sword", "wooden_axe", "wooden_shovel"],
    "stone":     ["stone_pickaxe", "stone_sword", "stone_axe", "stone_shovel"],
    "iron":      ["iron_pickaxe", "iron_sword", "iron_axe", "iron_shovel"],
    "diamond":   ["diamond_pickaxe", "diamond_sword", "diamond_axe", "diamond_shovel"],
    "netherite": ["netherite_pickaxe", "netherite_sword", "netherite_axe", "netherite_shovel"],
}


def _inv_count(counts: dict[str, int], item: str) -> int:
    return counts.get(item, 0)


def _has_tool_tier(counts: dict[str, int], min_tier: str, tool_type: str | None) -> bool:
    min_idx = _TOOL_TIER_ORDER.index(min_tier) if min_tier in _TOOL_TIER_ORDER else 0
    for idx in range(min_idx, len(_TOOL_TIER_ORDER)):
        tier = _TOOL_TIER_ORDER[idx]
        items = _TIER_ITEMS.get(tier, [])
        for item in items:
            if tool_type and not item.endswith(f"_{tool_type}"):
                continue
            if counts.get(item, 0) > 0:
                return True
    return False


def _best_tool_tier(counts: dict[str, int], tool_type: str | None) -> str | None:
    for tier in reversed(_TOOL_TIER_ORDER):
        items = _TIER_ITEMS.get(tier, [])
        for item in items:
            if tool_type and not item.endswith(f"_{tool_type}"):
                continue
            if counts.get(item, 0) > 0:
                return tier
    return None


def _station_usable(facts: dict[str, Any], station: str) -> tuple[bool, bool, float | None]:
    """Return (usable, visible, distance)."""
    if station == "crafting_table":
        usable = bool(facts.get("has_nearby_crafting_table_usable"))
        visible = bool(facts.get("has_visible_crafting_table"))
        dist = facts.get("nearest_crafting_table_distance")
    elif station == "furnace":
        usable = bool(facts.get("has_nearby_furnace_usable"))
        visible = bool(facts.get("has_visible_furnace"))
        dist = facts.get("nearest_furnace_distance")
    else:
        usable = False
        visible = False
        dist = None
    return usable, visible, dist if isinstance(dist, (int, float)) else None


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------

def check_requirements(
    requirements: list[Requirement],
    current_facts: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> RequirementReport:
    """Evaluate all requirements against live state.

    Args:
        requirements: list of Requirement objects from the action spec.
        current_facts: the current_facts dict built by game_brain._current_facts().
        state: raw state dict (used for health, food, dimension when not in facts).

    Returns:
        RequirementReport with ok=True if all pass, else failed_requirements list.
    """
    state = state or {}
    counts: dict[str, int] = {}
    if isinstance(current_facts.get("inventory_counts"), dict):
        counts = current_facts["inventory_counts"]
    elif isinstance(state.get("inventory_counts"), dict):
        counts = state["inventory_counts"]

    dimension: str | None = (
        current_facts.get("dimension")
        or state.get("dimension")
    )
    health: float | None = (
        state.get("health")
        or current_facts.get("health")
    )
    food: float | None = (
        state.get("food")
        or current_facts.get("food")
    )

    failed: list[FailedRequirement] = []
    repeatable = True

    for req in requirements:
        fr = _check_one(req, counts, current_facts, dimension, health, food)
        if fr is not None:
            failed.append(fr)
            # Non-retryable if a station or dimension gate is in the way
            if req.kind in (REQ_STATION_USABLE, REQ_DIMENSION, REQ_TOOL_TIER):
                repeatable = False

    relevant: dict[str, Any] = {}
    if failed:
        relevant = _build_relevant_state(failed, current_facts, counts, dimension, health, food)

    return RequirementReport(
        ok=not failed,
        failed_requirements=failed,
        repeatable_now=not failed and repeatable,
        relevant_state=relevant,
    )


def _check_one(
    req: Requirement,
    counts: dict[str, int],
    facts: dict[str, Any],
    dimension: str | None,
    health: float | None,
    food: float | None,
) -> FailedRequirement | None:
    """Return FailedRequirement if the requirement is not met, else None."""

    if req.kind == REQ_INVENTORY_ITEM:
        item = req.item or ""
        have = _inv_count(counts, item)
        need = req.count
        if have < need:
            return FailedRequirement(kind=req.kind, item=item, need=need, have=have)

    elif req.kind == REQ_INVENTORY_ANY:
        items = req.items or []
        need = req.count
        have = sum(_inv_count(counts, it) for it in items)
        if have < need:
            return FailedRequirement(kind=req.kind, items=list(items), need=need, have=have)

    elif req.kind == REQ_STATION_USABLE:
        station = req.station or ""
        usable, visible, dist = _station_usable(facts, station)
        if not usable:
            return FailedRequirement(
                kind=req.kind,
                station=station,
                usable=False,
                visible=visible,
                distance=dist,
            )

    elif req.kind == REQ_TOOL_TIER:
        tier = req.tier or "wood"
        tool_type = req.tool_type
        if not _has_tool_tier(counts, tier, tool_type):
            best = _best_tool_tier(counts, tool_type)
            return FailedRequirement(
                kind=req.kind,
                tier=tier,
                tool_type=tool_type,
                have=None,
                item=best,  # best available tier (None if none)
            )

    elif req.kind == REQ_DIMENSION:
        wanted = req.dimension or ""
        # normalise "overworld" / "minecraft:overworld" etc.
        current = _norm_dimension(dimension or "")
        wanted_norm = _norm_dimension(wanted)
        if current != wanted_norm:
            return FailedRequirement(
                kind=req.kind,
                required_dimension=wanted_norm,
                current_dimension=current,
            )

    elif req.kind == REQ_HEALTH_MIN:
        min_val = req.value or 0.0
        if health is None or health < min_val:
            return FailedRequirement(
                kind=req.kind,
                health=health,
                min_value=min_val,
            )

    elif req.kind == REQ_FOOD_MIN:
        min_val = req.value or 0.0
        if food is None or food < min_val:
            return FailedRequirement(
                kind=req.kind,
                food=food,
                min_value=min_val,
            )

    elif req.kind == REQ_NEARBY_BLOCK:
        # Check facts for block presence
        block = req.block or ""
        present = bool(facts.get(f"nearby_{block}") or facts.get(f"has_nearby_{block}"))
        if not present:
            return FailedRequirement(kind=req.kind, block=block, visible=False)

    elif req.kind == REQ_ACCESSIBLE_BLOCK:
        block = req.block or ""
        # We can't determine this precisely without Node data, so we mark accessible=None
        # when there is no positive signal.  Parsers from error text enrich this later.
        present = bool(facts.get(f"accessible_{block}") or facts.get(f"has_accessible_{block}"))
        if not present:
            return FailedRequirement(kind=req.kind, block=block, accessible=False, visible=None)

    elif req.kind == REQ_ENTITY_NEARBY:
        tag = req.entity_tag or ""
        present = bool(facts.get(f"nearby_{tag}") or facts.get(f"entity_{tag}_nearby"))
        if not present:
            return FailedRequirement(kind=req.kind, entity_tag=tag)

    elif req.kind == REQ_KNOWN_PLACE:
        kind_tag = req.kind_tag or req.kind
        known = bool(facts.get(f"known_{kind_tag}") or facts.get(f"has_{kind_tag}_waypoint"))
        if not known:
            return FailedRequirement(kind=req.kind, block=kind_tag)

    return None


def _norm_dimension(dim: str) -> str:
    dim = dim.lower().replace("minecraft:", "").strip()
    if dim in ("overworld", ""):
        return "overworld"
    if dim in ("the_nether", "nether"):
        return "the_nether"
    if dim in ("the_end", "end"):
        return "the_end"
    return dim


def _build_relevant_state(
    failed: list[FailedRequirement],
    facts: dict[str, Any],
    counts: dict[str, int],
    dimension: str | None,
    health: float | None,
    food: float | None,
) -> dict[str, Any]:
    relevant: dict[str, Any] = {}
    for fr in failed:
        if fr.kind == REQ_INVENTORY_ITEM and fr.item:
            relevant[f"inv_{fr.item}"] = counts.get(fr.item, 0)
        elif fr.kind == REQ_INVENTORY_ANY and fr.items:
            for it in fr.items:
                relevant[f"inv_{it}"] = counts.get(it, 0)
        elif fr.kind == REQ_STATION_USABLE and fr.station:
            s = fr.station
            relevant[f"{s}_usable"] = False
            relevant[f"{s}_visible"] = fr.visible
            if fr.distance is not None:
                relevant[f"{s}_distance"] = fr.distance
        elif fr.kind == REQ_DIMENSION:
            relevant["dimension"] = dimension
        elif fr.kind in (REQ_HEALTH_MIN, REQ_FOOD_MIN):
            if health is not None:
                relevant["health"] = health
            if food is not None:
                relevant["food"] = food
        elif fr.kind == REQ_TOOL_TIER:
            relevant["best_tool_tier"] = fr.item  # best available
    return relevant


# ---------------------------------------------------------------------------
# Error-string parser  (Node error → FailedRequirement list)
# ---------------------------------------------------------------------------

def parse_error_to_failed_requirements(
    error: str | None,
    action: str | None = None,
    result: dict[str, Any] | None = None,
    facts: dict[str, Any] | None = None,
) -> list[FailedRequirement]:
    """Convert Node error strings / result dicts into FailedRequirement items.

    This is the bridge between the untyped Node error text and the typed
    requirement system.  It does NOT replace the existing missing-materials
    parsing in verifier.py — it supplements it by producing FailedRequirement
    objects that the LLM packet can include.
    """
    reqs: list[FailedRequirement] = []
    facts = facts or {}
    result = result or {}

    # --- missing_materials from result dict (already structured) ---
    missing_mats = result.get("missing_materials")
    if isinstance(missing_mats, list):
        for m in missing_mats:
            name = m["name"] if isinstance(m, dict) else str(m)
            reqs.extend(_material_name_to_requirements(name, facts))

    # --- error string parsing ---
    if not isinstance(error, str) or not error:
        return reqs

    low = error.lower()

    # "Missing materials: stick x1, coal_or_charcoal x1"
    if "missing material" in low:
        reqs.extend(_parse_missing_materials_error(error, facts))

    # "No crafting table found within radius N"
    elif "no crafting table" in low or "crafting_table" in low and "no " in low:
        dist = _extract_number(error)
        usable, visible, actual_dist = _station_usable_from_facts(facts, "crafting_table")
        reqs.append(FailedRequirement(
            kind=REQ_STATION_USABLE,
            station="crafting_table",
            usable=False,
            visible=visible,
            distance=actual_dist,
        ))

    # "No furnace found within radius N" / "no furnace nearby"
    elif "no furnace" in low:
        usable, visible, actual_dist = _station_usable_from_facts(facts, "furnace")
        reqs.append(FailedRequirement(
            kind=REQ_STATION_USABLE,
            station="furnace",
            usable=False,
            visible=visible,
            distance=actual_dist,
        ))

    # "No accessible coal_ore found" / "no accessible X"
    elif "no accessible" in low:
        block = _extract_block_name(error)
        if block:
            reqs.append(FailedRequirement(
                kind=REQ_ACCESSIBLE_BLOCK,
                block=block,
                accessible=False,
                visible=None,
            ))

    # "wrong dimension" / "must be in the_nether" / "dimension_mismatch"
    elif "dimension" in low and ("wrong" in low or "mismatch" in low or "must be in" in low):
        required = _extract_dimension(error)
        current = facts.get("dimension")
        reqs.append(FailedRequirement(
            kind=REQ_DIMENSION,
            required_dimension=required,
            current_dimension=str(current) if current else None,
        ))

    return reqs


def _station_usable_from_facts(facts: dict[str, Any], station: str) -> tuple[bool, bool, float | None]:
    usable, visible, dist = _station_usable(facts, station)
    return usable, visible, dist


_LOG_STEM_ITEMS = [
    "oak_log", "spruce_log", "birch_log", "jungle_log", "acacia_log",
    "dark_oak_log", "mangrove_log", "cherry_log", "crimson_stem", "warped_stem",
]

_PLANK_ITEMS = [
    "oak_planks", "spruce_planks", "birch_planks", "jungle_planks",
    "acacia_planks", "dark_oak_planks", "mangrove_planks", "cherry_planks",
    "crimson_planks", "warped_planks",
]


def _is_log_stem_missing_phrase(name: str) -> bool:
    normalized = name.lower().strip(" .:_-").replace("-", "_").replace(" ", "_")
    return normalized in {
        "no_logs_or_stems_found_in_inventory",
        "no_log_or_stem_found_in_inventory",
        "logs_or_stems",
        "log_or_stem",
        "logs_or_stems_found_in_inventory",
    }


def _log_stem_failed_requirement(facts: dict[str, Any], need: int = 1, have_override: int | None = None) -> FailedRequirement:
    counts: dict[str, int] = facts.get("inventory_counts") or {}
    have = (sum(counts.get(it, 0) for it in _LOG_STEM_ITEMS)
            if have_override is None else have_override)
    return FailedRequirement(
        kind=REQ_INVENTORY_ANY,
        items=list(_LOG_STEM_ITEMS),
        need=need,
        have=have,
    )


def _parse_missing_materials_error(
    error: str,
    facts: dict[str, Any],
) -> list[FailedRequirement]:
    """Parse various 'Missing materials' error formats into FailedRequirements.

    Handles:
    - "stick x1"              → inventory_item item=stick need=1 have=0
    - "need 2 planks, have 1" → inventory_item item=planks need=2 have=1
    - "no logs or stems found in inventory" → inventory_any items=[log types] need=1 have=0
    - "coal_or_charcoal x1"  → inventory_any items=[coal,charcoal] need=1 have=0
    """
    _, _, tail = error.partition(":")
    text = tail.strip() or error
    reqs: list[FailedRequirement] = []
    counts: dict[str, int] = facts.get("inventory_counts") or {}

    # Special-case: "no logs or stems found in inventory"
    low = text.lower()
    if ("log" in low or "stem" in low) and ("no " in low or "not found" in low or "found" in low):
        reqs.append(_log_stem_failed_requirement(facts))
        return reqs

    for part in text.split(","):
        part = part.strip().rstrip(".")

        # Format: "need N name[, have M]" — verbose format from newer bot messages
        m_need = re.match(r"need\s+(\d+)\s+([a-z_]+)", part.lower())
        if m_need:
            need = int(m_need.group(1))
            raw_name = m_need.group(2)
            # Try to extract "have M" from the same part or the next token
            m_have = re.search(r"have\s+(\d+)", part.lower())
            have_count = int(m_have.group(1)) if m_have else counts.get(raw_name, 0)
            reqs.extend(_material_name_to_requirements(raw_name, facts, need=need, have_override=have_count))
            continue

        # Format: "name xN" or just "name" — skip standalone numbers ("have 1")
        m = re.match(r"([a-z_/]+)\s*(?:x(\d+))?", part.lower())
        if not m:
            continue
        raw_name = m.group(1).strip("_. ")
        need = int(m.group(2)) if m.group(2) else 1
        # Skip tokens that are pure words without an actual item name (e.g. "have")
        if not raw_name or raw_name in ("have", "need", "and", "or", "the", "a"):
            continue
        reqs.extend(_material_name_to_requirements(raw_name, facts, need=need))

    return reqs


def _material_name_to_requirements(
    name: str,
    facts: dict[str, Any],
    need: int = 1,
    have_override: int | None = None,
) -> list[FailedRequirement]:
    """Convert a material name to typed FailedRequirement(s).

    have_override: use this count instead of looking up from facts (for
    parsers that already extracted the count from the error string).
    """
    counts: dict[str, int] = facts.get("inventory_counts") or {}
    reqs: list[FailedRequirement] = []

    if name in ("coal_or_charcoal", "coal/charcoal"):
        coal = counts.get("coal", 0)
        charcoal = counts.get("charcoal", 0)
        have = coal + charcoal if have_override is None else have_override
        reqs.append(FailedRequirement(
            kind=REQ_INVENTORY_ANY,
            items=["coal", "charcoal"],
            need=need,
            have=have,
        ))
    elif name in ("log", "logs", "stem", "stems", "log_or_stem") or _is_log_stem_missing_phrase(name):
        reqs.append(_log_stem_failed_requirement(facts, need=need, have_override=have_override))
    elif name in ("planks", "plank"):
        have = (sum(counts.get(it, 0) for it in _PLANK_ITEMS)
                if have_override is None else have_override)
        reqs.append(FailedRequirement(
            kind=REQ_INVENTORY_ANY,
            items=list(_PLANK_ITEMS),
            need=need,
            have=have,
        ))
    elif name == "crafting_table":
        usable, visible, dist = _station_usable(facts, "crafting_table")
        reqs.append(FailedRequirement(
            kind=REQ_STATION_USABLE,
            station="crafting_table",
            usable=False,
            visible=visible,
            distance=dist,
        ))
    elif name == "furnace":
        usable, visible, dist = _station_usable(facts, "furnace")
        reqs.append(FailedRequirement(
            kind=REQ_STATION_USABLE,
            station="furnace",
            usable=False,
            visible=visible,
            distance=dist,
        ))
    else:
        have = counts.get(name, 0) if have_override is None else have_override
        reqs.append(FailedRequirement(kind=REQ_INVENTORY_ITEM, item=name, need=need, have=have))

    return reqs


def _extract_number(text: str) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def _extract_block_name(text: str) -> str | None:
    # "No accessible coal_ore found" → "coal_ore"
    m = re.search(r"no accessible\s+([a-z_]+)", text.lower())
    return m.group(1) if m else None


def _extract_dimension(text: str) -> str | None:
    for kw in ("the_end", "the_nether", "nether", "overworld"):
        if kw in text.lower():
            return _norm_dimension(kw)
    return None


# ---------------------------------------------------------------------------
# Build the LLM failure packet from a report
# ---------------------------------------------------------------------------

def build_requirement_failure_packet(
    action: str,
    report: RequirementReport,
    show_possible_next_actions: bool = False,
) -> dict[str, Any]:
    """Build the structured failure packet shown to the LLM.

    The packet contains factual failed_because entries and relevant_state.
    possible_next_actions is only included if show_possible_next_actions=True
    (controlled by VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM env var).
    """
    packet: dict[str, Any] = {
        "failed_action": action,
        "failure_type": "requirements_not_met",
        "repeatable_now": report.repeatable_now,
        "failed_because": [fr.to_dict() for fr in report.failed_requirements],
        "relevant_state": report.relevant_state,
        "repeat_condition": "Only retry after failed requirements changed.",
    }
    return packet


# ---------------------------------------------------------------------------
# Staleness detection for requirement-based failures
# ---------------------------------------------------------------------------

def requirement_changed(
    failed_req: FailedRequirement,
    old_facts: dict[str, Any],
    new_facts: dict[str, Any],
) -> bool:
    """Return True if the failed requirement's state changed meaningfully."""
    old_counts: dict[str, int] = old_facts.get("inventory_counts") or {}
    new_counts: dict[str, int] = new_facts.get("inventory_counts") or {}

    if failed_req.kind == REQ_INVENTORY_ITEM and failed_req.item:
        return new_counts.get(failed_req.item, 0) != old_counts.get(failed_req.item, 0)

    if failed_req.kind == REQ_INVENTORY_ANY and failed_req.items:
        old_sum = sum(old_counts.get(it, 0) for it in failed_req.items)
        new_sum = sum(new_counts.get(it, 0) for it in failed_req.items)
        return new_sum != old_sum

    if failed_req.kind == REQ_STATION_USABLE and failed_req.station:
        old_usable, _, _ = _station_usable(old_facts, failed_req.station)
        new_usable, _, _ = _station_usable(new_facts, failed_req.station)
        return old_usable != new_usable

    if failed_req.kind == REQ_DIMENSION:
        return old_facts.get("dimension") != new_facts.get("dimension")

    if failed_req.kind == REQ_HEALTH_MIN:
        old_h = old_facts.get("health", 0) or 0
        new_h = new_facts.get("health", 0) or 0
        return abs(new_h - old_h) >= 2.0

    if failed_req.kind == REQ_FOOD_MIN:
        old_f = old_facts.get("food", 0) or 0
        new_f = new_facts.get("food", 0) or 0
        return abs(new_f - old_f) >= 2.0

    if failed_req.kind == REQ_TOOL_TIER:
        # Check if any new tool appeared
        new_tool = _best_tool_tier(new_counts, failed_req.tool_type)
        old_tool = _best_tool_tier(old_counts, failed_req.tool_type)
        return new_tool != old_tool

    if failed_req.kind == REQ_ACCESSIBLE_BLOCK:
        new_pos = new_facts.get("position")
        old_pos = old_facts.get("position")
        if isinstance(new_pos, dict) and isinstance(old_pos, dict):
            dx = abs((new_pos.get("x") or 0) - (old_pos.get("x") or 0))
            dz = abs((new_pos.get("z") or 0) - (old_pos.get("z") or 0))
            return dx > 8 or dz > 8
        return False

    return False


def any_requirement_changed(
    failed_requirements: list[FailedRequirement],
    old_facts: dict[str, Any],
    new_facts: dict[str, Any],
) -> bool:
    """Return True if any failed requirement has changed."""
    return any(requirement_changed(fr, old_facts, new_facts) for fr in failed_requirements)
