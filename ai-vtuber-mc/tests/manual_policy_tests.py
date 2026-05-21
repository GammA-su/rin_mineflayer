from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.policy import PolicyError, normalize_action_args, validate_action
from vtuber_ai.schemas import ActionRequest


def expect_valid(request: ActionRequest) -> None:
    assert validate_action(request) == request


def expect_valid_sanitized(request: ActionRequest, expected_args: dict) -> None:
    sanitized = validate_action(request)
    assert sanitized.action == request.action
    assert sanitized.args == expected_args


def expect_valid_normalized(
    request: ActionRequest,
    expected_args: dict,
    expected_reason: str = "string_to_singleton_list",
) -> None:
    normalized = validate_action(request)
    assert normalized.action == request.action
    assert normalized.args == expected_args
    _, info = normalize_action_args(request)
    assert info.get("args_normalized") is True
    assert info.get("normalized_arg_keys")
    assert info.get("normalization_reason") == expected_reason


def expect_valid_clamped_radius(request: ActionRequest, expected_radius: int, from_radius: int) -> None:
    normalized = validate_action(request)
    expected_args = dict(request.args or {})
    expected_args["radius"] = expected_radius
    assert normalized.action == request.action
    assert normalized.args == expected_args
    _, info = normalize_action_args(request)
    assert info.get("args_normalized") is True
    assert info.get("normalized_arg_keys") == ["radius"]
    assert info.get("normalization_reason") == "arg_clamped"
    assert info.get("clampedArgs") == {"radius": {"from": from_radius, "to": expected_radius}}


def expect_canonical(request: ActionRequest, expected_action: str, expected_args: dict | None = None) -> None:
    canonical = validate_action(request)
    assert canonical.action == expected_action
    if expected_args is not None:
        assert canonical.args == expected_args


def expect_error(request: ActionRequest, expected: str) -> None:
    try:
        validate_action(request)
    except PolicyError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected PolicyError containing: {expected}")


def expect_error_details(request: ActionRequest, expected: dict) -> None:
    try:
        validate_action(request)
    except PolicyError as exc:
        details = exc.details
        for key, value in expected.items():
            assert details.get(key) == value, details
        assert details.get("possible_next_actions"), details
    else:
        raise AssertionError(f"Expected PolicyError with details: {expected}")


def main() -> None:
    expect_valid(ActionRequest(action="status"))
    expect_valid(ActionRequest(action="say", args={"message": "hello"}))
    expect_valid(ActionRequest(action="look_around"))
    expect_valid(ActionRequest(action="look_around", args={"radius": 12}))
    expect_valid(ActionRequest(action="explore_nearby", args={"radius": 16}))
    expect_valid(ActionRequest(action="look_at_player", args={"username": "Steve"}))
    expect_valid(ActionRequest(action="follow_player"))
    expect_valid(ActionRequest(action="follow_player", args={"username": "Steve"}))
    expect_valid(ActionRequest(action="come_here", args={"username": "Alex"}))
    expect_valid(ActionRequest(action="set_vtuber_mood", args={"mood": "focused"}))
    expect_valid(ActionRequest(action="acquire_blocks", args={"targets": ["stone"]}))
    expect_valid_normalized(ActionRequest(action="acquire_blocks", args={"targets": "coal_ore"}), {"targets": ["coal_ore"]})
    expect_valid_clamped_radius(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "radius": 4}), 8, 4)
    expect_valid_clamped_radius(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "radius": 97}), 96, 97)
    expect_valid(ActionRequest(action="navigate_to_block_type", args={"targets": ["stone"]}))
    expect_valid_normalized(ActionRequest(action="navigate_to_block_type", args={"targets": "spruce_log"}), {"targets": ["spruce_log"]})
    expect_valid(ActionRequest(action="navigate_to_block_type", args={"targets": ["coal_ore"], "radius": 48}))
    expect_valid_normalized(ActionRequest(action="scan_for_specific_block", args={"targets": "spruce_log"}), {"targets": ["spruce_log"]})
    expect_valid(
        ActionRequest(
            action="acquire_blocks",
            args={"targets": ["coal_ore"], "count": 3, "radius": 48, "allowExcavate": True, "accessMode": "safe_staircase"},
        )
    )
    expect_valid(ActionRequest(action="collect_wood"))
    expect_valid(ActionRequest(action="collect_wood", args={"count": 4}))
    expect_valid(ActionRequest(action="craft_planks"))
    expect_valid(ActionRequest(action="craft_planks", args={"count": 64}))
    expect_valid(ActionRequest(action="craft_sticks", args={"count": 2}))
    expect_valid(ActionRequest(action="craft_crafting_table", args={"count": 1}))
    expect_valid(ActionRequest(action="place_crafting_table"))
    expect_canonical(ActionRequest(action="craft_item", args={"item": "stone_pickaxe"}), "craft_stone_pickaxe", {})
    expect_canonical(ActionRequest(action="craft_item", args={"item": "crafting_table"}), "craft_crafting_table", {})
    expect_canonical(ActionRequest(action="craft_item", args={"item": "sticks", "count": 4}), "craft_sticks", {"count": 4})
    expect_canonical(ActionRequest(action="craft_item", args={"item": "iron_pickaxe"}), "craft_iron_pickaxe", {})
    expect_canonical(ActionRequest(action="craft_item", args={"item": "furnace", "count": 1}), "craft_furnace", {})
    expect_canonical(ActionRequest(action="craft_item", args={"item": "torch", "count": 64}), "craft_torches", {"count": 64})
    expect_valid(ActionRequest(action="craft_furnace"))
    expect_valid_sanitized(ActionRequest(action="craft_furnace", args={"count": 1}), {})
    expect_valid(ActionRequest(action="craft_torches", args={"count": 4}))
    expect_valid(ActionRequest(action="craft_chest"))
    expect_valid(ActionRequest(action="craft_shield"))
    expect_valid(ActionRequest(action="craft_bucket"))
    expect_valid(ActionRequest(action="craft_iron_pickaxe"))
    expect_valid(ActionRequest(action="craft_iron_sword"))
    expect_valid(ActionRequest(action="craft_iron_armor"))
    expect_valid(ActionRequest(action="craft_wooden_pickaxe"))
    expect_valid(ActionRequest(action="mine_stone"))
    expect_valid(ActionRequest(action="mine_stone", args={"count": 3}))
    expect_valid_clamped_radius(ActionRequest(action="mine_stone", args={"radius": 4}), 8, 4)
    expect_valid_clamped_radius(ActionRequest(action="mine_stone", args={"radius": 97}), 96, 97)
    expect_valid(ActionRequest(action="mine_coal", args={"count": 32}))
    expect_valid(ActionRequest(action="mine_coal", args={"radius": 32}))
    expect_valid_clamped_radius(ActionRequest(action="mine_coal", args={"radius": 4}), 8, 4)
    expect_valid_clamped_radius(ActionRequest(action="mine_coal", args={"radius": 97}), 96, 97)
    expect_valid(ActionRequest(action="mine_coal", args={"count": 4, "radius": 16, "allowExcavate": True, "accessMode": "safe_staircase"}))
    expect_valid(ActionRequest(action="mine_coal", args={"allowExcavate": False, "accessMode": "surface_first"}))
    expect_valid_normalized(
        ActionRequest(action="mine_coal", args={"allowExcavate": "true", "accessMode": "surface_first"}),
        {"allowExcavate": True, "accessMode": "surface_first"},
        "string_boolean_to_boolean",
    )
    expect_valid_normalized(
        ActionRequest(action="mine_coal", args={"allowExcavate": "False"}),
        {"allowExcavate": False},
        "string_boolean_to_boolean",
    )
    expect_valid(ActionRequest(action="mine_coal", args={"accessMode": "exposed"}))
    expect_valid(ActionRequest(action="mine_iron_ore", args={"count": 3}))
    expect_valid_clamped_radius(ActionRequest(action="mine_iron_ore", args={"radius": 4}), 8, 4)
    expect_valid_clamped_radius(ActionRequest(action="mine_iron_ore", args={"radius": 97}), 96, 97)
    expect_valid(ActionRequest(action="craft_stone_pickaxe"))
    expect_valid_sanitized(ActionRequest(action="craft_stone_pickaxe", args={"count": 1}), {})
    expect_valid(ActionRequest(action="smelt_item", args={"input": "raw_iron", "fuel": "coal", "count": 3}))
    expect_valid(ActionRequest(action="smelt_iron", args={"count": 3}))
    expect_valid_normalized(
        ActionRequest(action="drop_item", args={"item": "dirt", "force": "True"}),
        {"item": "dirt", "force": True},
        "string_boolean_to_boolean",
    )
    expect_valid_normalized(
        ActionRequest(action="set_sneak", args={"enabled": "false"}),
        {"enabled": False},
        "string_boolean_to_boolean",
    )
    expect_valid(ActionRequest(action="flee"))
    expect_valid(ActionRequest(action="eat_food"))

    expect_error(ActionRequest(action="dig"), "is not allowed")
    expect_error(ActionRequest(action="say"), "requires args.message")
    expect_error(ActionRequest(action="say", args={"message": "   "}), "non-empty string")
    expect_error(ActionRequest(action="say", args={"message": "x" * 241}), "at most 240")
    expect_error(ActionRequest(action="say", args={"message": "/kill @e"}), "slash commands")
    expect_error(ActionRequest(action="jump", args={"height": 2}), "does not accept args")
    expect_error(ActionRequest(action="look_around", args={"radius": 7}), "between 8 and 32")
    expect_error(ActionRequest(action="look_around", args={"radius": 33}), "between 8 and 32")
    expect_error(ActionRequest(action="explore_nearby", args={"radius": 65}), "between 8 and 64")
    expect_error(ActionRequest(action="explore_nearby", args={"radius": "16"}), "must be an integer")
    expect_error(ActionRequest(action="flee", args={"radius": 12}), "does not accept args")
    expect_error(ActionRequest(action="eat_food", args={"item": "apple"}), "does not accept args")
    expect_error(ActionRequest(action="acquire_blocks"), "requires args.targets")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ""}), "non-empty list")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": []}), "non-empty list")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["diamond_block"]}), "target is not allowed")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "count": 33}), "between 1 and 32")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "allowExcavate": "yes"}), "must be a boolean")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "accessMode": "unsafe"}), "must be one of")
    expect_error(ActionRequest(action="navigate_to_block_type"), "requires args.targets")
    expect_error(ActionRequest(action="navigate_to_block_type", args={"targets": ""}), "non-empty list")
    expect_error(ActionRequest(action="navigate_to_block_type", args={"targets": ["diamond_block"]}), "target is not allowed")
    expect_error(ActionRequest(action="navigate_to_block_type", args={"targets": ["crafting_table"]}), "stations use approach_station")
    expect_error(ActionRequest(action="navigate_to_block_type", args={"targets": ["stone"], "radius": 7}), "between 8 and 96")
    expect_error(ActionRequest(action="navigate_to_block_type", args={"targets": ["stone"], "allowExcavate": True}), "unknown args")
    expect_error(ActionRequest(action="collect_wood", args={"tool": "axe"}), "unknown args")
    expect_error(ActionRequest(action="collect_wood", args={"count": 17}), "between 1 and 16")
    expect_error(ActionRequest(action="collect_wood", args={"count": "4"}), "must be an integer")
    expect_error(ActionRequest(action="craft_planks", args={"tool": "axe"}), "unknown args")
    expect_error(ActionRequest(action="craft_planks", args={"count": 65}), "between 1 and 64")
    expect_error(ActionRequest(action="craft_sticks", args={"count": 0}), "between 1 and 64")
    expect_error(ActionRequest(action="craft_crafting_table", args={"count": "1"}), "must be an integer")
    expect_error(ActionRequest(action="place_crafting_table", args={"position": "here"}), "does not accept args")

    # --- place_furnace: accepts radius and allowPrepareArea ---
    expect_valid(ActionRequest(action="place_furnace"))
    expect_valid(ActionRequest(action="place_furnace", args={"radius": 4, "allowPrepareArea": True}))
    expect_valid(ActionRequest(action="place_furnace", args={"radius": 1}))
    expect_valid(ActionRequest(action="place_furnace", args={"radius": 8}))
    expect_valid(ActionRequest(action="place_furnace", args={"allowPrepareArea": False}))
    expect_valid_normalized(
        ActionRequest(action="place_furnace", args={"allowPrepareArea": "true"}),
        {"allowPrepareArea": True},
        "string_boolean_to_boolean",
    )
    expect_valid_normalized(
        ActionRequest(action="place_furnace", args={"allowPrepareArea": "false", "radius": 6}),
        {"allowPrepareArea": False, "radius": 6},
        "string_boolean_to_boolean",
    )
    expect_error(ActionRequest(action="place_furnace", args={"radius": 0}), "between 1 and 8")
    expect_error(ActionRequest(action="place_furnace", args={"radius": 9}), "between 1 and 8")
    expect_error(ActionRequest(action="place_furnace", args={"radius": "4"}), "must be an integer")
    expect_error(ActionRequest(action="place_furnace", args={"allowPrepareArea": "yes"}), "must be a boolean")
    expect_error(ActionRequest(action="place_furnace", args={"speed": 5}), "unknown args")
    expect_canonical(ActionRequest(action="craft_item", args={"item": "diamond_pickaxe"}), "craft_diamond_pickaxe", {})
    expect_canonical(ActionRequest(action="craft_item", args={"item": "shield", "count": 2}), "craft_shield", {})
    expect_error(ActionRequest(action="craft_item", args={"item": "ladder"}), "unsupported_craft_item")
    expect_error_details(
        ActionRequest(action="craft_item", args={"item": "ladder"}),
        {
            "failure_type": "invalid_action_args",
            "stop_reason": "unsupported_craft_item",
            "invalid_item": "ladder",
        },
    )
    expect_error(ActionRequest(action="craft_torches", args={"count": 65}), "between 1 and 64")
    expect_valid_sanitized(ActionRequest(action="craft_shield", args={"count": 1}), {})
    expect_valid_sanitized(ActionRequest(action="craft_wooden_pickaxe", args={"count": 1}), {})
    expect_error(ActionRequest(action="mine_stone", args={"depth": 3}), "unknown args")
    expect_error(ActionRequest(action="mine_stone", args={"count": 17}), "between 1 and 16")
    expect_error(ActionRequest(action="mine_stone", args={"count": False}), "must be an integer")
    expect_error(ActionRequest(action="mine_coal", args={"count": 33}), "between 1 and 32")
    expect_error(ActionRequest(action="mine_coal", args={"allowExcavate": "yes"}), "must be a boolean")
    expect_error(ActionRequest(action="mine_coal", args={"accessMode": "underground"}), "must be one of")
    expect_error(ActionRequest(action="mine_coal", args={"targets": ["coal_ore"]}), "unknown args")
    expect_error(ActionRequest(action="mine_iron_ore", args={"count": "3"}), "must be an integer")
    expect_error(ActionRequest(action="smelt_item", args={"item": "raw_iron"}), "unknown args")
    expect_error(ActionRequest(action="smelt_item", args={"input": "cobblestone"}), "must be one of")
    expect_error(ActionRequest(action="smelt_item", args={"input": "raw_iron", "fuel": "lava_bucket"}), "must be one of")

    # --- smelt_item: machine-readable details on invalid args ---
    # Missing input → invalid_args details with missing_arg
    try:
        validate_action(ActionRequest(action="smelt_item", args={"count": 64}))
        raise AssertionError("Expected PolicyError for smelt_item missing input")
    except PolicyError as exc:
        assert exc.details.get("failure_type") == "invalid_args", exc.details
        assert exc.details.get("repeatable_now") is False, exc.details
        fb = exc.details.get("failed_because") or []
        assert len(fb) == 1, fb
        assert fb[0]["kind"] == "invalid_args", fb[0]
        assert fb[0]["action"] == "smelt_item", fb[0]
        assert fb[0]["missing_arg"] == "input", fb[0]
        assert "allowed smeltable" in fb[0]["expected"], fb[0]
        assert "possible_next_actions" not in exc.details, "must not include possible_next_actions"

    # Invalid input (cobblestone) → invalid_enum_value details
    try:
        validate_action(ActionRequest(action="smelt_item", args={"input": "cobblestone"}))
        raise AssertionError("Expected PolicyError for smelt_item cobblestone input")
    except PolicyError as exc:
        assert exc.details.get("failure_type") == "invalid_args", exc.details
        assert exc.details.get("repeatable_now") is False, exc.details
        fb = exc.details.get("failed_because") or []
        assert len(fb) == 1, fb
        assert fb[0]["kind"] == "invalid_enum_value", fb[0]
        assert fb[0]["action"] == "smelt_item", fb[0]
        assert fb[0]["arg"] == "input", fb[0]
        assert fb[0]["received"] == "cobblestone", fb[0]
        allowed_vals = fb[0].get("allowed_values") or []
        assert "raw_iron" in allowed_vals, allowed_vals
        assert "raw_gold" in allowed_vals, allowed_vals
        assert "cobblestone" not in allowed_vals, "cobblestone must not be in allowed_values"
        assert "possible_next_actions" not in exc.details, "must not include possible_next_actions"
    # --- scan_for_specific_block: machine-readable details on invalid args ---
    # Missing targets → invalid_args details with missing_arg
    try:
        validate_action(ActionRequest(action="scan_for_specific_block", args={}))
        raise AssertionError("Expected PolicyError for scan_for_specific_block missing targets")
    except PolicyError as exc:
        assert exc.details.get("failure_type") == "invalid_args", exc.details
        assert exc.details.get("repeatable_now") is False, exc.details
        fb = exc.details.get("failed_because") or []
        assert len(fb) == 1, fb
        assert fb[0]["kind"] == "invalid_args", fb[0]
        assert fb[0]["action"] == "scan_for_specific_block", fb[0]
        assert fb[0]["missing_arg"] == "targets", fb[0]
        assert "possible_next_actions" not in exc.details, "must not include possible_next_actions"

    # Empty targets list → same invalid_args
    try:
        validate_action(ActionRequest(action="scan_for_specific_block", args={"targets": []}))
        raise AssertionError("Expected PolicyError for scan_for_specific_block empty targets")
    except PolicyError as exc:
        assert exc.details.get("failure_type") == "invalid_args", exc.details
        assert exc.details.get("failed_because", [{}])[0].get("missing_arg") == "targets"

    # String target normalized to list → valid
    expect_valid_normalized(
        ActionRequest(action="scan_for_specific_block", args={"targets": "iron_ore"}),
        {"targets": ["iron_ore"]},
    )

    expect_error(ActionRequest(action="smelt_iron", args={"count": 33}), "between 1 and 32")
    expect_error(ActionRequest(action="follow_player", args={"username": ""}), "non-empty string")
    expect_error(ActionRequest(action="set_vtuber_mood", args={"mood": "angry"}), "one of")

    # --- return_to_workspace ---
    expect_valid(ActionRequest(action="return_to_workspace"))
    expect_valid(ActionRequest(action="return_to_workspace", args={"purpose": "crafting"}))
    expect_valid(ActionRequest(action="return_to_workspace", args={"purpose": "smelting"}))
    expect_valid(ActionRequest(action="return_to_workspace", args={"purpose": "storage"}))
    expect_valid(ActionRequest(action="return_to_workspace", args={"purpose": "general"}))
    expect_error(ActionRequest(action="return_to_workspace", args={"purpose": "mining"}), "must be one of")
    expect_error(ActionRequest(action="return_to_workspace", args={"radius": 10}), "unknown args")
    expect_valid_normalized(
        ActionRequest(action="setup_workspace", args={"need_crafting_table": "True", "need_furnace": "false", "radius": 16}),
        {"need_crafting_table": True, "need_furnace": False, "radius": 16},
        "string_boolean_to_boolean",
    )
    expect_valid(ActionRequest(action="approach_station", args={"station": "crafting_table"}))
    expect_valid(ActionRequest(action="approach_station", args={"station": "furnace", "radius": 3}))
    expect_error(ActionRequest(action="approach_station"), "must be one of")
    expect_error(ActionRequest(action="approach_station", args={"station": "anvil"}), "must be one of")
    expect_error(ActionRequest(action="approach_station", args={"station": "crafting_table", "radius": 1}), "between 2 and 6")

    # --- return_to_position ---
    expect_valid(ActionRequest(action="return_to_position", args={"x": 10.0, "y": 64.0, "z": 20.0}))
    expect_valid(ActionRequest(action="return_to_position", args={"x": 10, "y": 64, "z": 20, "dimension": "overworld"}))
    expect_valid(ActionRequest(action="return_to_position", args={"x": 10.0, "y": 64.0, "z": 20.0, "radius": 5}))
    expect_valid(ActionRequest(action="return_to_position", args={"x": 0, "y": 64, "z": 0, "dimension": "the_nether", "radius": 3}))
    expect_error(ActionRequest(action="return_to_position", args={"y": 64.0, "z": 20.0}), "requires args.x")
    expect_error(ActionRequest(action="return_to_position", args={"x": 10.0, "z": 20.0}), "requires args.y")
    expect_error(ActionRequest(action="return_to_position", args={"x": 10.0, "y": 64.0}), "requires args.z")
    expect_error(ActionRequest(action="return_to_position", args={"x": 10.0, "y": 64.0, "z": 20.0, "dimension": "nether"}), "must be one of")
    expect_error(ActionRequest(action="return_to_position", args={"x": 10.0, "y": 64.0, "z": 20.0, "radius": 0}), "1-16")
    expect_error(ActionRequest(action="return_to_position", args={"x": 10.0, "y": 64.0, "z": 20.0, "radius": 17}), "1-16")
    expect_error(ActionRequest(action="return_to_position", args={"x": 10.0, "y": 64.0, "z": 20.0, "speed": 5}), "unknown args")

    # --- return_to_known_position ---
    expect_valid(ActionRequest(action="return_to_known_position"))
    expect_valid(ActionRequest(action="return_to_known_position", args={"label": "home"}))
    expect_valid(ActionRequest(action="return_to_known_position", args={"label": "workspace"}))
    expect_error(ActionRequest(action="return_to_known_position", args={"label": ""}), "non-empty string")
    expect_error(ActionRequest(action="return_to_known_position", args={"label": "x" * 65}), "non-empty string")
    expect_error(ActionRequest(action="return_to_known_position", args={"radius": 10}), "unknown args")

    # --- collect_obsidian: canonical name passes policy ---
    expect_valid(ActionRequest(action="collect_obsidian", args={"count": 5}))
    expect_valid(ActionRequest(action="collect_obsidian", args={"count": 1}))
    # --- mine_obsidian: alias not known to policy, correctly rejected ---
    expect_error(ActionRequest(action="mine_obsidian"), "is not allowed")

    print("manual policy tests passed")


if __name__ == "__main__":
    main()
