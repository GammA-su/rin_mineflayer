from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.policy import PolicyError, validate_action
from vtuber_ai.schemas import ActionRequest


def expect_valid(request: ActionRequest) -> None:
    assert validate_action(request) == request


def expect_error(request: ActionRequest, expected: str) -> None:
    try:
        validate_action(request)
    except PolicyError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected PolicyError containing: {expected}")


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
    expect_valid(ActionRequest(action="navigate_to_block_type", args={"targets": ["stone"]}))
    expect_valid(ActionRequest(action="navigate_to_block_type", args={"targets": ["coal_ore"], "radius": 48}))
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
    expect_valid(ActionRequest(action="craft_wooden_pickaxe"))
    expect_valid(ActionRequest(action="mine_stone"))
    expect_valid(ActionRequest(action="mine_stone", args={"count": 3}))
    expect_valid(ActionRequest(action="craft_stone_pickaxe"))
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
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": []}), "non-empty list")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["diamond_block"]}), "target is not allowed")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "count": 33}), "between 1 and 32")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "radius": 7}), "between 8 and 96")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "allowExcavate": "yes"}), "must be a boolean")
    expect_error(ActionRequest(action="acquire_blocks", args={"targets": ["stone"], "accessMode": "unsafe"}), "must be one of")
    expect_error(ActionRequest(action="navigate_to_block_type"), "requires args.targets")
    expect_error(ActionRequest(action="navigate_to_block_type", args={"targets": ["diamond_block"]}), "target is not allowed")
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
    expect_error(ActionRequest(action="craft_wooden_pickaxe", args={"count": 1}), "does not accept args")
    expect_error(ActionRequest(action="mine_stone", args={"depth": 3}), "unknown args")
    expect_error(ActionRequest(action="mine_stone", args={"count": 17}), "between 1 and 16")
    expect_error(ActionRequest(action="mine_stone", args={"count": False}), "must be an integer")
    expect_error(ActionRequest(action="craft_stone_pickaxe", args={"count": 1}), "does not accept args")
    expect_error(ActionRequest(action="follow_player", args={"username": ""}), "non-empty string")
    expect_error(ActionRequest(action="set_vtuber_mood", args={"mood": "angry"}), "one of")

    print("manual policy tests passed")


if __name__ == "__main__":
    main()
