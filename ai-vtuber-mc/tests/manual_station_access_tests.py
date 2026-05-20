from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.action_catalog import get_compact_action_list  # noqa: E402
from vtuber_ai.game_brain import _compact_failure_summary, _current_facts  # noqa: E402
from vtuber_ai.schemas import ActionRequest, ActionResult  # noqa: E402
from vtuber_ai.verifier import verify_action  # noqa: E402


def main() -> None:
    facts = _current_facts(
        {
            "inventory_counts": {"cobblestone": 3, "stick": 2},
            "nearby_blocks": {
                "crafting_table": {
                    "name": "crafting_table",
                    "position": {"x": 6, "y": 64, "z": 0},
                    "distance": 6.5,
                }
            },
        }
    )
    assert facts["has_visible_crafting_table"] is True
    assert facts["has_nearby_crafting_table_usable"] is False
    assert facts["nearest_crafting_table_distance"] == 6.5
    assert facts["can_attempt_stone_pickaxe_materials"] is False

    failure_result = {
        "failure_type": "missing_station",
        "stop_reason": "station_visible_but_too_far",
        "station_needed": "crafting_table",
        "nearest_station_distance": 6.5,
        "usable_radius": 6,
        "possible_next_actions": ["approach_station", "return_to_workspace", "setup_workspace", "place_crafting_table"],
    }
    verifier = verify_action(
        before_status={"ok": True, "inventory": [], "nearbyBlocks": {}},
        after_status={"ok": True, "inventory": [], "nearbyBlocks": {}},
        action_request=ActionRequest(action="craft_stone_pickaxe"),
        action_result=ActionResult(ok=False, action="craft_stone_pickaxe", result=failure_result, error="No station usable."),
    )
    assert verifier["failure_type"] == "missing_station"
    assert verifier["stop_reason"] == "station_visible_but_too_far"
    assert verifier["nearest_station_distance"] == 6.5
    assert "approach_station" in verifier["possible_next_actions"]

    summary = _compact_failure_summary({
        "action": "craft_stone_pickaxe",
        "ok": False,
        "error": "No station usable.",
        "result": failure_result,
        "verifier": verifier,
    })
    assert summary["stop_reason"] == "station_visible_but_too_far"
    assert summary["nearest_station_distance"] == 6.5
    assert "approach_station" in summary["repair_hint"]

    compact_actions = get_compact_action_list({"approach_station"}, max_chars=500)
    assert "approach_station(station,radius)" in compact_actions

    approach_success = verify_action(
        before_status={"ok": True, "health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}, "inventory": []},
        after_status={"ok": True, "health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}, "inventory": []},
        action_request=ActionRequest(action="approach_station", args={"station": "crafting_table", "radius": 3}),
        action_result=ActionResult(
            ok=True,
            action="approach_station",
            result={
                "reached": True,
                "station": "crafting_table",
                "station_position": {"x": 2, "y": 64, "z": 0},
                "start_distance": 2.0,
                "final_distance": 2.0,
                "target_radius": 3,
                "usable": True,
                "usable_for_station": True,
            },
            error=None,
        ),
    )
    assert approach_success["success"] is True

    approach_partial = verify_action(
        before_status={"ok": True, "health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}, "inventory": []},
        after_status={"ok": True, "health": 20, "food": 20, "position": {"x": 3, "y": 64, "z": 0}, "inventory": []},
        action_request=ActionRequest(action="approach_station", args={"station": "crafting_table", "radius": 3}),
        action_result=ActionResult(
            ok=False,
            action="approach_station",
            result={
                "reached": False,
                "partial_success": True,
                "station": "crafting_table",
                "station_position": {"x": 6, "y": 64, "z": 0},
                "start_distance": 6.5,
                "final_distance": 3.56,
                "target_radius": 3,
                "usable_radius": 6,
                "usable_for_station": True,
                "distance_improved": True,
                "failure_type": "station_not_reached",
                "stop_reason": "still_outside_requested_radius",
                "possible_next_actions": ["approach_station", "craft_stone_pickaxe", "look_around"],
            },
            error="Approached station but did not reach requested radius.",
        ),
    )
    assert approach_partial["success"] is False
    assert approach_partial["partial_success"] is True
    assert approach_partial["usable_for_station"] is True
    assert approach_partial["distance_improved"] is True
    assert approach_partial["failure_type"] == "station_not_reached"
    assert approach_partial["recommendation"] != "Avoid repeating the same action blindly."

    print("manual station access tests passed")


if __name__ == "__main__":
    main()
