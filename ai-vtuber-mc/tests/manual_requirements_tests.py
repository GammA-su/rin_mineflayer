"""Manual tests for the generic requirements system."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.requirements import (
    Requirement,
    FailedRequirement,
    RequirementReport,
    REQ_INVENTORY_ITEM,
    REQ_INVENTORY_ANY,
    REQ_STATION_USABLE,
    REQ_TOOL_TIER,
    REQ_DIMENSION,
    REQ_ACCESSIBLE_BLOCK,
    REQ_HEALTH_MIN,
    check_requirements,
    parse_error_to_failed_requirements,
    build_requirement_failure_packet,
    requirement_changed,
    any_requirement_changed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def facts(
    *,
    inventory_counts: dict | None = None,
    has_nearby_crafting_table_usable: bool = False,
    has_visible_crafting_table: bool = False,
    nearest_crafting_table_distance: float | None = None,
    has_nearby_furnace_usable: bool = False,
    has_visible_furnace: bool = False,
    nearest_furnace_distance: float | None = None,
    dimension: str | None = None,
    health: float | None = None,
    food: float | None = None,
    **extra,
) -> dict:
    f = {
        "inventory_counts": inventory_counts or {},
        "has_nearby_crafting_table_usable": has_nearby_crafting_table_usable,
        "has_visible_crafting_table": has_visible_crafting_table,
        "nearest_crafting_table_distance": nearest_crafting_table_distance,
        "has_nearby_furnace_usable": has_nearby_furnace_usable,
        "has_visible_furnace": has_visible_furnace,
        "nearest_furnace_distance": nearest_furnace_distance,
    }
    if dimension is not None:
        f["dimension"] = dimension
    if health is not None:
        f["health"] = health
    if food is not None:
        f["food"] = food
    f.update(extra)
    return f


# ---------------------------------------------------------------------------
# 1. check_requirements — inventory_item
# ---------------------------------------------------------------------------

def test_inventory_item_pass():
    reqs = [Requirement(kind=REQ_INVENTORY_ITEM, item="stick", count=2)]
    f = facts(inventory_counts={"stick": 4})
    report = check_requirements(reqs, f)
    assert report.ok
    assert report.failed_requirements == []


def test_inventory_item_fail():
    reqs = [Requirement(kind=REQ_INVENTORY_ITEM, item="stick", count=2)]
    f = facts(inventory_counts={"stick": 1})
    report = check_requirements(reqs, f)
    assert not report.ok
    assert len(report.failed_requirements) == 1
    fr = report.failed_requirements[0]
    assert fr.kind == REQ_INVENTORY_ITEM
    assert fr.item == "stick"
    assert fr.have == 1
    assert fr.need == 2


# ---------------------------------------------------------------------------
# 2. check_requirements — inventory_any
# ---------------------------------------------------------------------------

def test_inventory_any_coal_pass():
    reqs = [Requirement(kind=REQ_INVENTORY_ANY, items=["coal", "charcoal"], count=1)]
    f = facts(inventory_counts={"charcoal": 2})
    report = check_requirements(reqs, f)
    assert report.ok


def test_inventory_any_fail():
    reqs = [Requirement(kind=REQ_INVENTORY_ANY, items=["coal", "charcoal"], count=1)]
    f = facts(inventory_counts={})
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    assert fr.kind == REQ_INVENTORY_ANY
    assert fr.have == 0


# ---------------------------------------------------------------------------
# 3. check_requirements — station_usable
# ---------------------------------------------------------------------------

def test_station_usable_pass():
    reqs = [Requirement(kind=REQ_STATION_USABLE, station="crafting_table")]
    f = facts(has_nearby_crafting_table_usable=True, has_visible_crafting_table=True)
    report = check_requirements(reqs, f)
    assert report.ok


def test_station_usable_fail_not_visible():
    reqs = [Requirement(kind=REQ_STATION_USABLE, station="crafting_table")]
    f = facts()
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    assert fr.kind == REQ_STATION_USABLE
    assert fr.station == "crafting_table"
    assert fr.usable is False
    assert fr.visible is False
    # Station failures are non-retryable
    assert not report.repeatable_now


def test_station_usable_fail_visible_but_far():
    reqs = [Requirement(kind=REQ_STATION_USABLE, station="crafting_table")]
    f = facts(
        has_visible_crafting_table=True,
        has_nearby_crafting_table_usable=False,
        nearest_crafting_table_distance=12.0,
    )
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    assert fr.visible is True
    assert fr.distance == 12.0


# ---------------------------------------------------------------------------
# 4. check_requirements — tool_tier
# ---------------------------------------------------------------------------

def test_tool_tier_pass_exact():
    reqs = [Requirement(kind=REQ_TOOL_TIER, tier="wood", tool_type="pickaxe")]
    f = facts(inventory_counts={"wooden_pickaxe": 1})
    assert check_requirements(reqs, f).ok


def test_tool_tier_pass_higher():
    reqs = [Requirement(kind=REQ_TOOL_TIER, tier="stone", tool_type="pickaxe")]
    f = facts(inventory_counts={"iron_pickaxe": 1})
    assert check_requirements(reqs, f).ok


def test_tool_tier_fail_none():
    reqs = [Requirement(kind=REQ_TOOL_TIER, tier="stone", tool_type="pickaxe")]
    f = facts(inventory_counts={})
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    assert fr.kind == REQ_TOOL_TIER
    assert fr.tier == "stone"
    # item is None when no tool at all
    assert fr.item is None


def test_tool_tier_fail_with_lower_available():
    reqs = [Requirement(kind=REQ_TOOL_TIER, tier="stone", tool_type="pickaxe")]
    f = facts(inventory_counts={"wooden_pickaxe": 1})
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    # best available tier name reported in item field
    assert fr.item == "wood"


# ---------------------------------------------------------------------------
# 5. check_requirements — dimension
# ---------------------------------------------------------------------------

def test_dimension_pass():
    reqs = [Requirement(kind=REQ_DIMENSION, dimension="the_end")]
    f = facts(dimension="the_end")
    assert check_requirements(reqs, f).ok


def test_dimension_fail():
    reqs = [Requirement(kind=REQ_DIMENSION, dimension="the_end")]
    f = facts(dimension="overworld")
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    assert fr.required_dimension == "the_end"
    assert fr.current_dimension == "overworld"


def test_dimension_normalisation():
    reqs = [Requirement(kind=REQ_DIMENSION, dimension="nether")]
    f = facts(dimension="minecraft:the_nether")
    assert check_requirements(reqs, f).ok


# ---------------------------------------------------------------------------
# 6. check_requirements — health_min
# ---------------------------------------------------------------------------

def test_health_min_pass():
    reqs = [Requirement(kind=REQ_HEALTH_MIN, value=10.0)]
    f = facts(health=20.0)
    assert check_requirements(reqs, f).ok


def test_health_min_fail():
    reqs = [Requirement(kind=REQ_HEALTH_MIN, value=10.0)]
    f = facts(health=8.0)
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    assert fr.health == 8.0
    assert fr.min_value == 10.0


# ---------------------------------------------------------------------------
# 7. accessible_block requirement
# ---------------------------------------------------------------------------

def test_accessible_block_fail():
    reqs = [Requirement(kind=REQ_ACCESSIBLE_BLOCK, block="coal_ore")]
    f = facts()
    report = check_requirements(reqs, f)
    assert not report.ok
    fr = report.failed_requirements[0]
    assert fr.block == "coal_ore"
    assert fr.accessible is False


# ---------------------------------------------------------------------------
# 8. parse_error_to_failed_requirements
# ---------------------------------------------------------------------------

def test_parse_missing_materials_error():
    f = facts(inventory_counts={"stick": 0})
    result = parse_error_to_failed_requirements(
        error="Missing materials: stick x1, coal_or_charcoal x1.",
        facts=f,
    )
    kinds = {fr.kind for fr in result}
    assert REQ_INVENTORY_ITEM in kinds
    assert REQ_INVENTORY_ANY in kinds


def test_parse_missing_logs_or_stems_error():
    expected_items = [
        "oak_log", "spruce_log", "birch_log", "jungle_log", "acacia_log",
        "dark_oak_log", "mangrove_log", "cherry_log", "crimson_stem", "warped_stem",
    ]
    result = parse_error_to_failed_requirements(
        error="Missing materials: no logs or stems found in inventory.",
        facts=facts(inventory_counts={}),
    )
    assert len(result) == 1
    fr = result[0]
    assert fr.kind == REQ_INVENTORY_ANY
    assert fr.items == expected_items
    assert fr.need == 1
    assert fr.have == 0

    structured_result = parse_error_to_failed_requirements(
        error="Missing materials: no logs or stems found in inventory.",
        result={"missing_materials": ["no_logs_or_stems_found_in_inventory"]},
        facts=facts(inventory_counts={}),
    )
    assert all(fr.item != "no_logs_or_stems_found_in_inventory" for fr in structured_result)
    assert any(fr.kind == REQ_INVENTORY_ANY and fr.items == expected_items for fr in structured_result)


def test_parse_no_crafting_table_error():
    f = facts()
    result = parse_error_to_failed_requirements(
        error="No crafting table found within radius 4.",
        facts=f,
    )
    assert len(result) == 1
    fr = result[0]
    assert fr.kind == REQ_STATION_USABLE
    assert fr.station == "crafting_table"
    assert fr.usable is False


def test_parse_no_furnace_error():
    f = facts()
    result = parse_error_to_failed_requirements(
        error="No furnace found within radius 6.",
        facts=f,
    )
    assert len(result) == 1
    assert result[0].kind == REQ_STATION_USABLE
    assert result[0].station == "furnace"


def test_parse_no_accessible_block_error():
    f = facts()
    result = parse_error_to_failed_requirements(
        error="No accessible coal_ore found nearby.",
        facts=f,
    )
    assert len(result) == 1
    fr = result[0]
    assert fr.kind == REQ_ACCESSIBLE_BLOCK
    assert fr.block == "coal_ore"


def test_parse_dimension_error():
    f = facts(dimension="overworld")
    result = parse_error_to_failed_requirements(
        error="Wrong dimension: must be in the_end to activate portal.",
        facts=f,
    )
    assert len(result) == 1
    fr = result[0]
    assert fr.kind == REQ_DIMENSION
    assert fr.required_dimension == "the_end"


# ---------------------------------------------------------------------------
# 9. build_requirement_failure_packet
# ---------------------------------------------------------------------------

def test_build_packet_structure():
    reqs = [
        Requirement(kind=REQ_INVENTORY_ANY, items=["coal", "charcoal"], count=1),
        Requirement(kind=REQ_INVENTORY_ITEM, item="stick", count=1),
    ]
    f = facts(inventory_counts={})
    report = check_requirements(reqs, f)
    packet = build_requirement_failure_packet("craft_torches", report)
    assert packet["failed_action"] == "craft_torches"
    assert packet["failure_type"] == "requirements_not_met"
    assert "failed_because" in packet
    assert len(packet["failed_because"]) == 2
    assert "repeat_condition" in packet


def test_build_packet_hides_pna_by_default():
    reqs = [Requirement(kind=REQ_INVENTORY_ITEM, item="obsidian", count=14)]
    f = facts(inventory_counts={"obsidian": 3})
    report = check_requirements(reqs, f)
    packet = build_requirement_failure_packet("build_nether_portal", report)
    assert "possible_next_actions" not in packet


# ---------------------------------------------------------------------------
# 10. requirement_changed / any_requirement_changed
# ---------------------------------------------------------------------------

def test_requirement_changed_inventory_item():
    fr = FailedRequirement(kind=REQ_INVENTORY_ITEM, item="cobblestone")
    old = facts(inventory_counts={"cobblestone": 0})
    new = facts(inventory_counts={"cobblestone": 3})
    assert requirement_changed(fr, old, new) is True


def test_requirement_changed_inventory_item_unchanged():
    fr = FailedRequirement(kind=REQ_INVENTORY_ITEM, item="cobblestone")
    old = facts(inventory_counts={"cobblestone": 0})
    new = facts(inventory_counts={"cobblestone": 0})
    assert requirement_changed(fr, old, new) is False


def test_requirement_changed_station_becomes_usable():
    fr = FailedRequirement(kind=REQ_STATION_USABLE, station="crafting_table", usable=False)
    old = facts()
    new = facts(has_nearby_crafting_table_usable=True)
    assert requirement_changed(fr, old, new) is True


def test_requirement_changed_tool_tier():
    fr = FailedRequirement(kind=REQ_TOOL_TIER, tier="stone", tool_type="pickaxe")
    old = facts(inventory_counts={})
    new = facts(inventory_counts={"stone_pickaxe": 1})
    assert requirement_changed(fr, old, new) is True


def test_any_requirement_changed_mixed():
    frs = [
        FailedRequirement(kind=REQ_INVENTORY_ITEM, item="stick"),
        FailedRequirement(kind=REQ_INVENTORY_ANY, items=["coal", "charcoal"]),
    ]
    old = facts(inventory_counts={})
    new = facts(inventory_counts={"coal": 1})
    assert any_requirement_changed(frs, old, new) is True


def test_any_requirement_changed_none():
    frs = [
        FailedRequirement(kind=REQ_INVENTORY_ITEM, item="stick"),
        FailedRequirement(kind=REQ_INVENTORY_ANY, items=["coal", "charcoal"]),
    ]
    old = facts(inventory_counts={"wood": 3})
    new = facts(inventory_counts={"wood": 4})
    assert any_requirement_changed(frs, old, new) is False


# ---------------------------------------------------------------------------
# 11. Catalog integration — key action specs have requirements
# ---------------------------------------------------------------------------

def test_catalog_requirements_populated():
    from vtuber_ai.action_catalog import CATALOG
    actions_with_reqs = {
        name: spec
        for name, spec in CATALOG.items()
        if spec.requirements
    }
    required_actions = {
        "craft_wooden_pickaxe",
        "craft_stone_pickaxe",
        "craft_torches",
        "mine_stone",
        "mine_coal",
        "mine_iron_ore",
        "collect_obsidian",
        "build_nether_portal",
        "activate_end_portal",
        "end_safe_landing",
    }
    missing = required_actions - set(actions_with_reqs)
    assert not missing, f"These actions lack requirements: {missing}"


def test_catalog_craft_wooden_pickaxe_requirements():
    from vtuber_ai.action_catalog import CATALOG
    spec = CATALOG["craft_wooden_pickaxe"]
    kinds = {r.kind for r in spec.requirements}
    assert REQ_STATION_USABLE in kinds
    assert REQ_INVENTORY_ANY in kinds or REQ_INVENTORY_ITEM in kinds


def test_catalog_build_nether_portal_requires_overworld():
    from vtuber_ai.action_catalog import CATALOG
    spec = CATALOG["build_nether_portal"]
    dim_reqs = [r for r in spec.requirements if r.kind == REQ_DIMENSION]
    assert len(dim_reqs) == 1
    assert dim_reqs[0].dimension == "overworld"


def test_catalog_end_safe_landing_requires_the_end():
    from vtuber_ai.action_catalog import CATALOG
    spec = CATALOG["end_safe_landing"]
    dim_reqs = [r for r in spec.requirements if r.kind == REQ_DIMENSION]
    assert len(dim_reqs) == 1
    assert dim_reqs[0].dimension == "the_end"


# ---------------------------------------------------------------------------
# 12. _enrich_failure_with_requirements integration (via build_llm_state_packet)
# ---------------------------------------------------------------------------

def test_enrich_failure_craft_torches_no_materials():
    """Unresolved craft_torches failure should contain failed_because with inventory items."""
    from vtuber_ai.game_brain import build_llm_state_packet

    def state_dict(summary, **extra):
        v = {"summary": summary, "recent_ticks": [], "last_action": None,
             "last_result": None, "last_verifier": None}
        v.update(extra)
        return v

    summary = {
        "ok": True, "health": 20, "food": 20,
        "inventory_counts": {"spruce_planks": 2, "wooden_pickaxe": 1},
        "nearby_blocks": {}, "nearby_entities": [],
    }
    unchanged = {"inventory_counts": {"spruce_planks": 2, "wooden_pickaxe": 1}, "position": {"x": 0, "y": 64, "z": 0}}
    torch_fail_tick = {
        "action": "craft_torches", "ok": 0,
        "error": "Missing materials: stick x1, coal_or_charcoal x1.",
        "result": {},
        "verifier": {
            "failure_type": "missing_materials",
            "missing_materials": ["stick", "coal_or_charcoal"],
            "possible_next_actions": ["craft_sticks", "mine_coal"],
            "lesson": "need coal and sticks",
        },
        "before_state": unchanged, "after_state": unchanged,
    }
    status_ok = {
        "action": "status", "ok": 1, "error": None, "result": {},
        "verifier": {"failure_type": "none"},
        "before_state": unchanged, "after_state": unchanged,
    }
    packet = build_llm_state_packet(
        status=state_dict(summary, recent_ticks=[status_ok, torch_fail_tick]),
        recent_memory=[],
        last_result={"action": "status", "ok": True, "result": {}, "verifier": {"failure_type": "none"}},
        bridge_actions=("status", "craft_torches", "craft_sticks", "mine_coal", "collect_wood"),
        mission="make torches",
    )
    unresolved = packet["unresolved_failure"]
    assert unresolved is not None
    assert unresolved["action"] == "craft_torches"
    # possible_next_actions stripped by default
    assert "possible_next_actions" not in unresolved
    # failed_because populated
    assert "failed_because" in unresolved
    kinds = {fb["kind"] for fb in unresolved["failed_because"]}
    assert "inventory_any" in kinds or "inventory_item" in kinds
    assert "repeat_condition" in unresolved


def test_enrich_failure_craft_torches_with_pna_env_var():
    """When VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM=1, possible_next_actions is included."""
    import os
    from vtuber_ai.game_brain import build_llm_state_packet

    def state_dict(summary, **extra):
        v = {"summary": summary, "recent_ticks": [], "last_action": None,
             "last_result": None, "last_verifier": None}
        v.update(extra)
        return v

    summary = {
        "ok": True, "health": 20, "food": 20,
        "inventory_counts": {},
        "nearby_blocks": {}, "nearby_entities": [],
    }
    unchanged = {"inventory_counts": {}, "position": {"x": 0, "y": 64, "z": 0}}
    torch_fail_tick = {
        "action": "craft_torches", "ok": 0,
        "error": "Missing materials: stick x1, coal_or_charcoal x1.",
        "result": {},
        "verifier": {
            "failure_type": "missing_materials",
            "missing_materials": ["stick", "coal_or_charcoal"],
            "possible_next_actions": ["craft_sticks", "mine_coal"],
            "lesson": "need coal and sticks",
        },
        "before_state": unchanged, "after_state": unchanged,
    }
    status_ok = {
        "action": "status", "ok": 1, "error": None, "result": {},
        "verifier": {"failure_type": "none"},
        "before_state": unchanged, "after_state": unchanged,
    }
    old = os.environ.get("VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM")
    os.environ["VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM"] = "1"
    try:
        packet = build_llm_state_packet(
            status=state_dict(summary, recent_ticks=[status_ok, torch_fail_tick]),
            recent_memory=[],
            last_result=None,
            bridge_actions=("status", "craft_torches", "craft_sticks"),
            mission="make torches",
        )
        unresolved = packet["unresolved_failure"]
        assert unresolved is not None
        assert "possible_next_actions" in unresolved
    finally:
        if old is None:
            os.environ.pop("VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM", None)
        else:
            os.environ["VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM"] = old


def test_enrich_failure_mine_stone_no_pickaxe():
    """mine_stone failure should report tool_tier requirement if no pickaxe."""
    from vtuber_ai.game_brain import _enrich_failure_with_requirements
    current_facts = {
        "inventory_counts": {},
        "has_nearby_crafting_table_usable": False,
        "has_visible_crafting_table": False,
    }
    fake_failure = {
        "action": "mine_stone",
        "failure_type": "no_progress",
        "error": "No pickaxe.",
        "age_ticks": 1,
    }
    enriched = _enrich_failure_with_requirements(fake_failure, current_facts)
    assert enriched is not None
    assert "failed_because" in enriched
    kinds = {fb["kind"] for fb in enriched["failed_because"]}
    assert "tool_tier" in kinds


def test_enrich_failure_build_nether_portal_wrong_dimension():
    """build_nether_portal in the_nether should report dimension failure."""
    from vtuber_ai.game_brain import _enrich_failure_with_requirements
    current_facts = {
        "inventory_counts": {"obsidian": 14},
        "dimension": "the_nether",
        "has_nearby_crafting_table_usable": False,
        "has_visible_crafting_table": False,
    }
    fake_failure = {
        "action": "build_nether_portal",
        "failure_type": "no_progress",
        "error": "Wrong dimension.",
        "age_ticks": 1,
    }
    enriched = _enrich_failure_with_requirements(fake_failure, current_facts)
    assert enriched is not None
    assert "failed_because" in enriched
    kinds = {fb["kind"] for fb in enriched["failed_because"]}
    assert "dimension" in kinds


def test_enrich_failure_activate_end_portal_no_eyes():
    """activate_end_portal with no ender_eye should report inventory failure."""
    from vtuber_ai.game_brain import _enrich_failure_with_requirements
    current_facts = {
        "inventory_counts": {},
        "dimension": "the_end",
        "has_nearby_crafting_table_usable": False,
        "has_visible_crafting_table": False,
    }
    fake_failure = {
        "action": "activate_end_portal",
        "failure_type": "no_progress",
        "error": "No ender_eye in inventory.",
        "age_ticks": 1,
    }
    enriched = _enrich_failure_with_requirements(fake_failure, current_facts)
    assert enriched is not None
    assert "failed_because" in enriched
    kinds = {fb["kind"] for fb in enriched["failed_because"]}
    assert "inventory_item" in kinds


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    tests = [
        test_inventory_item_pass,
        test_inventory_item_fail,
        test_inventory_any_coal_pass,
        test_inventory_any_fail,
        test_station_usable_pass,
        test_station_usable_fail_not_visible,
        test_station_usable_fail_visible_but_far,
        test_tool_tier_pass_exact,
        test_tool_tier_pass_higher,
        test_tool_tier_fail_none,
        test_tool_tier_fail_with_lower_available,
        test_dimension_pass,
        test_dimension_fail,
        test_dimension_normalisation,
        test_health_min_pass,
        test_health_min_fail,
        test_accessible_block_fail,
        test_parse_missing_materials_error,
        test_parse_missing_logs_or_stems_error,
        test_parse_no_crafting_table_error,
        test_parse_no_furnace_error,
        test_parse_no_accessible_block_error,
        test_parse_dimension_error,
        test_build_packet_structure,
        test_build_packet_hides_pna_by_default,
        test_requirement_changed_inventory_item,
        test_requirement_changed_inventory_item_unchanged,
        test_requirement_changed_station_becomes_usable,
        test_requirement_changed_tool_tier,
        test_any_requirement_changed_mixed,
        test_any_requirement_changed_none,
        test_catalog_requirements_populated,
        test_catalog_craft_wooden_pickaxe_requirements,
        test_catalog_build_nether_portal_requires_overworld,
        test_catalog_end_safe_landing_requires_the_end,
        test_enrich_failure_craft_torches_no_materials,
        test_enrich_failure_craft_torches_with_pna_env_var,
        test_enrich_failure_mine_stone_no_pickaxe,
        test_enrich_failure_build_nether_portal_wrong_dimension,
        test_enrich_failure_activate_end_portal_no_eyes,
    ]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            failed.append((t.__name__, exc))

    if failed:
        for name, exc in failed:
            print(f"  FAIL {name}: {exc}")
        raise AssertionError(f"{len(failed)} test(s) failed.")

    print(f"manual_requirements_tests passed: {passed} tests ok")


if __name__ == "__main__":
    main()
