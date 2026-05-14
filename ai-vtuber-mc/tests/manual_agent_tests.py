from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.agent import plan_objective_action
from vtuber_ai.curriculum import inventory_counts, recommend_objective
from vtuber_ai.schemas import ActionRequest, ActionResult
from vtuber_ai.verifier import verify_step


def status_with_inventory(items: list[dict]) -> dict:
    return {
        "ok": True,
        "connected": True,
        "entityReady": True,
        "inventory": items,
        "nearbyBlocks": {},
    }


def with_nearby_crafting_table(status: dict) -> dict:
    status = dict(status)
    status["nearbyBlocks"] = {
        "crafting_table": {
            "name": "crafting_table",
            "position": {"x": 1, "y": 64, "z": 1},
            "distance": 2,
        }
    }
    return status


def main() -> None:
    empty = status_with_inventory([])
    assert recommend_objective(empty) == "collect_wood"

    logs = status_with_inventory([{"name": "oak_log", "count": 1}])
    assert recommend_objective(logs) == "craft_planks"

    planks = status_with_inventory([{"name": "oak_planks", "count": 4}])
    assert recommend_objective(planks) == "craft_sticks"

    sticks = status_with_inventory(
        [
            {"name": "oak_planks", "count": 4},
            {"name": "stick", "count": 2},
        ]
    )
    assert recommend_objective(sticks) == "craft_crafting_table"

    table = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "oak_planks", "count": 3},
        ]
    )
    assert recommend_objective(table) == "place_crafting_table"
    assert recommend_objective(with_nearby_crafting_table(table)) == "craft_wooden_pickaxe"

    wooden_pick = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "wooden_pickaxe", "count": 1},
        ]
    )
    assert recommend_objective(wooden_pick) == "mine_stone"

    stone_ready = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "wooden_pickaxe", "count": 1},
            {"name": "cobblestone", "count": 3},
        ]
    )
    assert recommend_objective(stone_ready) == "craft_stone_pickaxe"

    complete = status_with_inventory(
        [
            {"name": "crafting_table", "count": 1},
            {"name": "stick", "count": 2},
            {"name": "wooden_pickaxe", "count": 1},
            {"name": "cobblestone", "count": 3},
            {"name": "stone_pickaxe", "count": 1},
        ]
    )
    assert recommend_objective(complete) == "tier1_complete"

    assert inventory_counts(status_with_inventory([{"name": "stick", "count": 1}, {"name": "stick", "count": 2}]))[
        "stick"
    ] == 3

    action = plan_objective_action("collect_wood", "test mission", "agent")
    assert action.action == "collect_wood"
    assert plan_objective_action("place_crafting_table", "test mission", "agent").action == "place_crafting_table"

    verification = verify_step(
        objective="collect_wood",
        before_status=empty,
        after_status=logs,
        action_request=action,
        action_result=ActionResult(ok=True, action="collect_wood"),
    )
    assert verification["success"] is True
    assert verification["next_recommended_objective"] == "craft_planks"

    failed = verify_step(
        objective="collect_wood",
        before_status=empty,
        after_status=empty,
        action_request=action,
        action_result=ActionResult(ok=False, action="collect_wood", error="not implemented"),
    )
    assert failed["success"] is False

    print("manual agent tests passed")


if __name__ == "__main__":
    main()
