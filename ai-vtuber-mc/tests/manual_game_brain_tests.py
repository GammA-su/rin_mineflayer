from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.autonomy import _is_fatal_live_failure, _is_recoverable_failure
from vtuber_ai.game_brain import (
    AUTONOMOUS_ALLOWED_ACTIONS,
    build_llm_state_packet,
    build_repetition_warning,
    choose_next_action,
    find_blocked_family,
    hard_block_repetitions_enabled,
)


class StubHandler(BaseHTTPRequestHandler):
    captured_body: dict | None = None
    response_action = "collect_wood"
    response_args = {"count": 4}
    response_compact = False  # if True, emit {"a":..., "args":...} format

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        StubHandler.captured_body = json.loads(raw)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if StubHandler.response_compact:
            inner = {"a": StubHandler.response_action, "args": StubHandler.response_args}
        else:
            inner = {
                "objective": "collect starter wood",
                "action": StubHandler.response_action,
                "args": StubHandler.response_args,
                "speech": "Wood first.",
                "mood": "focused",
                "reason": "Current state supports this.",
            }
        body = {
            "choices": [{"message": {"content": json.dumps(inner)}}],
            "usage": {"completion_tokens": 12},
        }
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def log_message(self, _format: str, *args: object) -> None:
        return


def state(summary: dict, **extra: object) -> dict:
    value = {
        "summary": summary,
        "recent_ticks": [],
        "last_action": None,
        "last_result": None,
        "last_verifier": None,
    }
    value.update(extra)
    return value


def start_stub() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def restore_env(old_env: dict[str, str | None]) -> None:
    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def main() -> None:
    os.environ.pop("VTUBER_LLM_BASE_URL", None)

    danger = state(
        {
            "ok": True,
            "health": 6,
            "food": 14,
            "hostile_nearby": True,
            "has_food": False,
            "inventory_counts": {},
            "nearby_blocks": {},
        }
    )
    decision, info = choose_next_action(danger, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "hybrid")
    assert decision.action == "flee"
    assert info["source"] == "emergency_reflex"

    hungry = state(
        {
            "ok": True,
            "health": 20,
            "food": 5,
            "hostile_nearby": False,
            "has_food": True,
            "inventory_counts": {"bread": 1},
            "nearby_blocks": {},
        }
    )
    decision, info = choose_next_action(hungry, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "hybrid")
    assert decision.action == "status"
    assert info["fallback_used"] is True

    lava = state(
        {
            "ok": True,
            "health": 20,
            "food": 20,
            "hostile_nearby": False,
            "movement": {"inLava": True},
            "inventory_counts": {},
            "nearby_blocks": {},
        }
    )
    decision, info = choose_next_action(lava, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "hybrid")
    assert decision.action == "flee"
    assert info["source"] == "emergency_reflex"

    starter = state(
        {
            "ok": True,
            "health": 20,
            "food": 20,
            "hostile_nearby": False,
            "has_food": False,
            "inventory_counts": {},
            "nearby_blocks": {},
        }
    )
    decision, info = choose_next_action(starter, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
    assert decision.action == "status"
    assert info["fallback_used"] is True
    assert "llm_state_packet_preview" in info

    server, base_url = start_stub()
    old_env = {
        "VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL"),
        "VTUBER_LLM_MAX_TOKENS": os.environ.get("VTUBER_LLM_MAX_TOKENS"),
    }
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    os.environ["VTUBER_LLM_MAX_TOKENS"] = "77"
    try:
        rich_state = state(
            {
                "ok": True,
                "health": 20,
                "food": 20,
                "dimension": "overworld",
                "time": {"timeOfDay": 1000, "isDay": True},
                "position": {"x": 1, "y": 64, "z": 2},
                "inventory_counts": {"oak_log": 1},
                "nearby_blocks": {
                    "crafting_table": {
                        "name": "crafting_table",
                        "position": {"x": 2, "y": 64, "z": 2},
                    }
                },
                "nearby_block_counts": {f"block_{index}": index for index in range(30)} | {"crafting_table": 1},
                "nearby_entities": [
                    {"name": f"entity_{index}", "type": "mob", "hostile": False, "distance": index}
                    for index in range(15)
                ],
            },
            recent_ticks=[{"action": "place_crafting_table", "ok": 1, "error": None}],
            last_action="place_crafting_table",
            last_result={"alreadyPresent": True},
            last_verifier={"failure_type": "no_progress", "recommendation": "Avoid repeating the same action blindly."},
        )
        memory = [
            {"id": index, "message": "x" * 100, "action": "status", "ok": 1, "error": None, "reason": "ok"}
            for index in range(6)
        ]
        decision, info = choose_next_action(rich_state, memory, "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision.action == "collect_wood"
        assert info["fallback_used"] is False
        assert info["llm_latency_sec"] >= 0
        assert info["prompt_size_chars"] > 0
        assert info["available_actions_count"] == len(AUTONOMOUS_ALLOWED_ACTIONS)
        assert info["last_failure_included"] is True
        assert info["unresolved_failure_included"] is False
        assert "llm_state_packet_preview" in info
        # compact-action diagnostics
        assert info["compact_action_count"] == len(AUTONOMOUS_ALLOWED_ACTIONS)
        assert info["compact_action_chars"] > 0
        assert info["detailed_action_docs_count"] <= int(os.environ.get("VTUBER_MAX_DETAILED_ACTION_DOCS", "12"))
        assert isinstance(info["detailed_action_names"], list)
        assert info["full_catalog_count"] >= len(AUTONOMOUS_ALLOWED_ACTIONS)
        assert "prompt_budget_exceeded" in info

        payload = StubHandler.captured_body
        assert payload is not None
        assert payload["max_tokens"] == 77
        user_content = json.loads(payload["messages"][1]["content"])
        assert set(user_content) == {
            "mission",
            "health",
            "food",
            "dimension",
            "time",
            "isDay",
            "position",
            "inventory_counts",
            "current_facts",
            "nearbyBlockCounts",
            "nearbyBlocks",
            "nearbyEntities",
            "memory",
            "memory_filter",
            "current_intent",
            "unresolved_failure",
            "station_affordances",
            "item_affordances",
            "inventory_efficiency",
            "navigation_stall",
            "repeated_failed_action_loop",
            "progress_monitor",
            "continuation_facts",
            "workspace_status",
            "station_access_status",
            "live_recovery_status",
            "observation_fresh",
            "repeated_sensing_count",
            "last_observation_tick",
            "last_observation_summary",
            "last_failure_summary",
            "last_relevant_failure",
            "last_action_result",
            "planner_instruction",
            "full_action_list",
            "detailed_action_docs",
            "known_waypoints",
            "known_places",
            "last_death",
            "death_state",
            "milestones",
            "recent_completed_intents",
            "blocked_action_families",
            "repetition_warnings",
            "recent_resource_successes",
            "resource_sufficiency",
        }
        # No missing-materials failures in this state → no current_intent
        assert user_content["current_intent"] is None
        assert user_content["observation_fresh"] is False
        assert user_content["repeated_sensing_count"] == 0
        assert user_content["last_observation_tick"] is None
        assert user_content["last_observation_summary"] is None
        assert user_content["inventory_counts"]["oak_log"] == 1
        assert user_content["current_facts"]["has_nearby_crafting_table"] is True
        assert user_content["nearbyBlocks"]["crafting_table"]["name"] == "crafting_table"
        assert user_content["last_action_result"]["result_flags"]["alreadyPresent"] is True
        assert isinstance(user_content["known_waypoints"], list)
        assert isinstance(user_content["known_places"], dict)
        assert user_content["last_death"] is None or isinstance(user_content["last_death"], dict)
        assert user_content["death_state"] is None or isinstance(user_content["death_state"], dict)
        assert isinstance(user_content["milestones"], dict)
        assert "next_possible_milestones" in user_content["milestones"]
        assert len(user_content["nearbyBlockCounts"]) == 20
        assert len(user_content["nearbyEntities"]) == 10
        assert len(user_content["memory"]) == 2
        assert user_content["memory"][0]["historical"] is True
        # compact action list
        full_action_list = user_content["full_action_list"]
        assert isinstance(full_action_list, str) and len(full_action_list) > 0

        torch_summary = {
            "ok": True,
            "health": 20,
            "food": 20,
            "inventory_counts": {"spruce_planks": 2, "wooden_pickaxe": 1},
            "nearby_blocks": {},
            "nearby_entities": [],
        }
        unchanged = {"inventory_counts": {"spruce_planks": 2, "wooden_pickaxe": 1}, "position": {"x": 0, "y": 64, "z": 0}}
        torch_failure_tick = {
            "action": "craft_torches",
            "ok": 0,
            "error": "Missing materials: stick x1, coal_or_charcoal x1.",
            "result": {},
            "verifier": {
                "failure_type": "missing_materials",
                "missing_materials": ["stick", "coal_or_charcoal"],
                "possible_next_actions": ["craft_sticks", "mine_coal", "collect_wood", "look_around"],
                "lesson": "Torches need sticks and coal or charcoal.",
            },
            "before_state": unchanged,
            "after_state": unchanged,
        }
        status_success_tick = {
            "action": "status",
            "ok": 1,
            "error": None,
            "result": {},
            "verifier": {"failure_type": "none"},
            "before_state": unchanged,
            "after_state": unchanged,
        }
        torch_packet = build_llm_state_packet(
            status=state(torch_summary, recent_ticks=[status_success_tick, torch_failure_tick]),
            recent_memory=[],
            last_result={"action": "status", "ok": True, "result": {}, "verifier": {"failure_type": "none"}},
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="make torches",
        )
        unresolved = torch_packet["unresolved_failure"]
        assert unresolved["action"] == "craft_torches"
        assert unresolved["failure_type"] == "missing_materials"
        assert unresolved["missing_materials"] == ["stick", "coal_or_charcoal"]
        # possible_next_actions is removed by default (VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM not set)
        assert "possible_next_actions" not in unresolved
        # failed_because should be populated from error-string parsing (catalog path: craft_torches has requirements)
        assert "failed_because" in unresolved
        assert any(fb.get("kind") in ("inventory_any", "inventory_item") for fb in unresolved["failed_because"])
        assert unresolved["lesson"] == "Torches need sticks and coal or charcoal."
        assert unresolved["age_ticks"] == 1
        assert torch_packet["last_failure_summary"] is None
        # current_intent: craft_torches is the goal, no repair attempts yet
        intent = torch_packet["current_intent"]
        assert intent is not None
        assert intent["goal_action"] == "craft_torches"
        assert "coal_or_charcoal" in intent["blocking_problem"]
        assert "stick" in intent["blocking_problem"]
        assert intent["repair_attempts_count"] == 0
        assert intent["repeated_repair_failure_count"] == 0

        torch_success_tick = dict(torch_failure_tick)
        torch_success_tick.update({"ok": 1, "error": None, "verifier": {"failure_type": "none"}})
        torch_success_tick["result"] = {"crafted": True}
        resolved_by_same_action = build_llm_state_packet(
            status=state(torch_summary, recent_ticks=[torch_success_tick, torch_failure_tick]),
            recent_memory=[],
            last_result=None,
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="make torches",
        )
        assert resolved_by_same_action["unresolved_failure"] is None
        # Goal succeeded → no current_intent
        assert resolved_by_same_action["current_intent"] is None

        resolved_material_summary = dict(torch_summary)
        resolved_material_summary["inventory_counts"] = {
            "stick": 1,
            "coal": 1,
            "spruce_planks": 2,
            "wooden_pickaxe": 1,
        }
        resolved_by_inventory = build_llm_state_packet(
            status=state(resolved_material_summary, recent_ticks=[status_success_tick, torch_failure_tick]),
            recent_memory=[],
            last_result=None,
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="make torches",
        )
        assert resolved_by_inventory["unresolved_failure"] is None
        # All materials in inventory → current_intent cleared
        assert resolved_by_inventory["current_intent"] is None

        craft_sticks_tick = {
            "action": "craft_sticks",
            "ok": 1,
            "error": None,
            "result": {},
            "verifier": {"failure_type": "none"},
            "before_state": {"inventory_counts": {"spruce_planks": 2, "wooden_pickaxe": 1}},
            "after_state": {"inventory_counts": {"spruce_planks": 1, "stick": 4, "wooden_pickaxe": 1}},
        }
        resolved_by_recovery = build_llm_state_packet(
            status=state(torch_summary, recent_ticks=[craft_sticks_tick, torch_failure_tick]),
            recent_memory=[],
            last_result=None,
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="make torches",
        )
        assert resolved_by_recovery["unresolved_failure"] is None
        # craft_sticks succeeded but coal_or_charcoal still missing →
        # current_intent preserves craft_torches with only coal blocking
        intent_after_sticks = resolved_by_recovery["current_intent"]
        assert intent_after_sticks is not None
        assert intent_after_sticks["goal_action"] == "craft_torches"
        assert "coal_or_charcoal" in intent_after_sticks["blocking_problem"]
        assert "stick" not in intent_after_sticks["blocking_problem"]
        assert intent_after_sticks["repair_attempts_count"] == 1  # craft_sticks

        # --- Full repair chain: craft_torches → craft_sticks (ok) → mine_coal (fail) ---
        mine_coal_fail_tick = {
            "action": "mine_coal",
            "ok": 0,
            "error": "No accessible coal found.",
            "result": {"failure_type": "no_progress"},
            "verifier": {"failure_type": "no_progress"},
            "before_state": unchanged,
            "after_state": unchanged,
        }
        repair_chain_packet = build_llm_state_packet(
            status=state(torch_summary, recent_ticks=[mine_coal_fail_tick, craft_sticks_tick, torch_failure_tick]),
            recent_memory=[],
            last_result=None,
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="make torches",
        )
        repair_intent = repair_chain_packet["current_intent"]
        assert repair_intent is not None, "current_intent must survive a repair failure"
        assert repair_intent["goal_action"] == "craft_torches", \
            f"original goal must be craft_torches, not overwritten by mine_coal; got {repair_intent['goal_action']}"
        assert "coal_or_charcoal" in repair_intent["blocking_problem"]
        assert repair_intent["repair_attempts_count"] == 2  # craft_sticks + mine_coal
        assert repair_intent["repeated_repair_failure_count"] == 0  # mine_coal failed once only
        assert "repair_attempts_summary" in repair_intent
        assert "craft_sticks" in repair_intent["repair_attempts_summary"]
        assert "mine_coal" in repair_intent["repair_attempts_summary"]

        # Repeated mine_coal failures should trigger the anti-loop lesson
        mine_coal_fail2 = dict(mine_coal_fail_tick)
        repeated_repair_packet = build_llm_state_packet(
            status=state(torch_summary, recent_ticks=[mine_coal_fail2, mine_coal_fail_tick, craft_sticks_tick, torch_failure_tick]),
            recent_memory=[],
            last_result=None,
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="make torches",
        )
        repeated_intent = repeated_repair_packet["current_intent"]
        assert repeated_intent is not None
        assert repeated_intent["goal_action"] == "craft_torches"
        assert repeated_intent["repeated_repair_failure_count"] >= 1
        assert "lesson" in repeated_intent
        assert "explore_nearby" in repeated_intent["lesson"] or "coal" in repeated_intent["lesson"].lower()

        StubHandler.response_action = "craft_sticks"
        StubHandler.response_args = {}
        decision, unresolved_info = choose_next_action(
            state(torch_summary, recent_ticks=[status_success_tick, torch_failure_tick]),
            [],
            "make torches",
            AUTONOMOUS_ALLOWED_ACTIONS,
            "llm",
        )
        assert decision.action == "craft_sticks"
        assert unresolved_info["unresolved_failure_included"] is True
        assert unresolved_info["unresolved_failure_action"] == "craft_torches"
        assert unresolved_info["unresolved_failure_age_ticks"] == 1
        # possible_next_actions is hidden by default; diagnostic is None
        assert unresolved_info["unresolved_failure_possible_next_actions"] is None
        assert unresolved_info["current_intent_included"] is True
        assert unresolved_info["current_intent_goal_action"] == "craft_torches"
        assert "coal_or_charcoal" in (unresolved_info["current_intent_blocking_problem"] or "")
        assert "repair_attempts_count" in unresolved_info
        assert "repeated_repair_failure_count" in unresolved_info

        observation_state_summary = {
            "ok": True,
            "health": 20,
            "food": 20,
            "inventory_counts": {"stick": 1},
            "nearby_blocks": {},
            "nearby_block_counts": {"stone": 4, "dirt": 2},
            "nearby_entities": [],
        }
        obs_before = {
            "inventory_counts": {"stick": 1},
            "position": {"x": 1, "y": 64, "z": 1},
            "nearby_block_counts": {"stone": 4, "dirt": 2},
            "nearby_entities": [],
        }
        look_tick = {
            "action": "look_around",
            "ok": 1,
            "error": None,
            "result": {"radius": 16, "nearbyBlockCounts": {"stone": 4, "dirt": 2}, "nearbyEntities": []},
            "verifier": {"failure_type": "none"},
            "before_state": obs_before,
            "after_state": obs_before,
        }
        check_inv_tick = {
            "action": "check_inventory",
            "ok": 1,
            "error": None,
            "result": {"counts": {"stick": 1}},
            "verifier": {"failure_type": "none"},
            "before_state": obs_before,
            "after_state": obs_before,
        }
        observation_packet = build_llm_state_packet(
            status=state(observation_state_summary, recent_ticks=[look_tick, check_inv_tick]),
            recent_memory=[],
            last_result={"action": "look_around", "ok": True, "result": look_tick["result"], "verifier": {"failure_type": "none"}},
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="observe without looping",
        )
        assert observation_packet["observation_fresh"] is True
        assert observation_packet["repeated_sensing_count"] == 2
        assert observation_packet["last_observation_tick"] == 0
        assert observation_packet["last_observation_summary"]["action"] == "look_around"
        assert observation_packet["last_observation_summary"]["radius"] == 16
        assert observation_packet["last_observation_summary"]["moved_since_observation"] is False
        assert "stone" in observation_packet["last_observation_summary"]["nearbyBlockCounts"]
        assert observation_packet["progress_monitor"]["world_observation_changed_recently"] is False

        StubHandler.response_action = "look_around"
        StubHandler.response_args = {"radius": 16}
        sensing_decision, sensing_info = choose_next_action(
            state(observation_state_summary, recent_ticks=[look_tick, check_inv_tick]),
            [],
            "observe without looping",
            AUTONOMOUS_ALLOWED_ACTIONS,
            "llm",
        )
        assert sensing_decision.action == "look_around"
        assert sensing_info["observation_fresh"] is True
        assert sensing_info["repeated_sensing_count"] == 2
        assert sensing_info["last_observation_tick"] == 0
        assert sensing_info["last_observation_action"] == "look_around"
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}

        def _status_tick() -> dict:
            return {
                "action": "status",
                "ok": 1,
                "error": None,
                "result": {},
                "verifier": {"failure_type": "none", "success": True},
                "before_state": obs_before,
                "after_state": obs_before,
            }

        stalled_packet = build_llm_state_packet(
            status=state(observation_state_summary, recent_ticks=[_status_tick() for _ in range(5)]),
            recent_memory=[],
            last_result={"action": "status", "ok": True, "result": {}, "verifier": {"failure_type": "none"}},
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="avoid status loop",
        )
        stalled_monitor = stalled_packet["progress_monitor"]
        assert stalled_monitor["low_information_loop"] is True
        assert stalled_packet["observation_fresh"] is True
        assert stalled_packet["repeated_sensing_count"] == 5
        assert stalled_monitor["state_changed_recently"] is False
        assert stalled_monitor["ticks_since_last_material_progress"] == 5
        assert stalled_monitor["ticks_since_last_position_progress"] == 5
        _, stalled_info = choose_next_action(
            state(observation_state_summary, recent_ticks=[_status_tick() for _ in range(5)]),
            [],
            "avoid status loop",
            AUTONOMOUS_ALLOWED_ACTIONS,
            "llm",
        )
        assert stalled_info["low_information_loop"] is True
        assert stalled_info["repeated_sensing_count"] == 5
        assert stalled_info["state_changed_recently"] is False
        assert stalled_info["ticks_since_last_material_progress"] == 5
        assert stalled_info["ticks_since_last_position_progress"] == 5
        # planner diagnostics: affordance + loop fields must be present
        assert "station_affordances" in stalled_info
        assert "item_affordances" in stalled_info
        assert "navigation_stall" in stalled_info
        assert "progress_monitor" in stalled_info
        assert isinstance(stalled_info["progress_monitor"], dict)
        assert "repeated_failed_action_loop" in stalled_info
        assert "invalid_action_loop" in stalled_info
        assert "recent_completed_intents" in stalled_info
        assert "blocked_action_families_count" in stalled_info
        assert "blocked_action_families" in stalled_info
        assert isinstance(stalled_info["blocked_action_families"], list)

        discovery_before = {**obs_before, "nearby_block_counts": {}}
        discovery_after = {**obs_before, "nearby_block_counts": {"stone": 4, "coal_ore": 1}}
        discovery_tick = {
            "action": "look_around",
            "ok": 1,
            "error": None,
            "result": {"radius": 16, "nearbyBlockCounts": {"stone": 4, "coal_ore": 1}},
            "verifier": {"failure_type": "none", "success": True},
            "before_state": discovery_before,
            "after_state": discovery_after,
        }
        discovery_packet = build_llm_state_packet(
            status=state({**observation_state_summary, "nearby_block_counts": {"stone": 4, "coal_ore": 1}}, recent_ticks=[discovery_tick]),
            recent_memory=[],
            last_result={"action": "look_around", "ok": True, "result": discovery_tick["result"], "verifier": {"failure_type": "none"}},
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="observe new blocks",
        )
        assert discovery_packet["progress_monitor"]["world_observation_changed_recently"] is True
        assert discovery_packet["progress_monitor"]["low_information_loop"] is False

        craft_before = {**obs_before, "inventory_counts": {"cobblestone": 3, "stick": 2}}
        craft_after = {**obs_before, "inventory_counts": {"stone_pickaxe": 1}}
        craft_tick = {
            "action": "craft_stone_pickaxe",
            "ok": 1,
            "error": None,
            "result": {"crafts": 1},
            "verifier": {"failure_type": "none", "success": True},
            "before_state": craft_before,
            "after_state": craft_after,
        }
        craft_packet = build_llm_state_packet(
            status=state({**observation_state_summary, "inventory_counts": {"stone_pickaxe": 1}}, recent_ticks=[craft_tick, _status_tick(), _status_tick()]),
            recent_memory=[],
            last_result={"action": "craft_stone_pickaxe", "ok": True, "result": {"crafts": 1}, "verifier": {"failure_type": "none"}},
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="crafting progress",
        )
        assert craft_packet["progress_monitor"]["low_information_loop"] is False
        assert craft_packet["progress_monitor"]["ticks_since_last_material_progress"] == 0
        assert craft_packet["progress_monitor"]["inventory_changed_recently"] is True

        move_before = {**obs_before, "position": {"x": 1, "y": 64, "z": 1}}
        move_after = {**obs_before, "position": {"x": 8, "y": 64, "z": 1}}
        move_tick = {
            "action": "explore_nearby",
            "ok": 1,
            "error": None,
            "result": {"moved": True},
            "verifier": {"failure_type": "none", "success": True},
            "before_state": move_before,
            "after_state": move_after,
        }
        move_packet = build_llm_state_packet(
            status=state({**observation_state_summary, "position": {"x": 8, "y": 64, "z": 1}}, recent_ticks=[move_tick, _status_tick()]),
            recent_memory=[],
            last_result={"action": "explore_nearby", "ok": True, "result": {"moved": True}, "verifier": {"failure_type": "none"}},
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="movement progress",
        )
        assert move_packet["progress_monitor"]["ticks_since_last_position_progress"] == 0
        assert move_packet["progress_monitor"]["position_changed_recently"] is True
        assert move_packet["progress_monitor"]["low_information_loop"] is False

        danger_state = {**obs_before, "hostile_nearby": True, "health": 6}
        danger_status_tick = {
            "action": "status",
            "ok": 1,
            "error": None,
            "result": {},
            "verifier": {"failure_type": "none", "success": True},
            "before_state": danger_state,
            "after_state": danger_state,
        }
        danger_packet = build_llm_state_packet(
            status=state({**observation_state_summary, "hostile_nearby": True, "health": 6}, recent_ticks=[danger_status_tick for _ in range(5)]),
            recent_memory=[],
            last_result={"action": "status", "ok": True, "result": {}, "verifier": {"failure_type": "none"}},
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="survive danger",
        )
        assert danger_packet["progress_monitor"]["low_information_loop"] is False
        assert "status" in full_action_list
        assert "collect_wood" in full_action_list
        assert "return_to_workspace" in full_action_list
        # detailed docs: should cover emergency + core actions
        detailed_docs = user_content["detailed_action_docs"]
        assert isinstance(detailed_docs, dict)
        assert len(detailed_docs) <= int(os.environ.get("VTUBER_MAX_DETAILED_ACTION_DOCS", "12"))
        assert "status" in detailed_docs
        # planned/stub must not appear in full_action_list
        assert "mine_diamond_ore" not in full_action_list
        assert "collect_ender_pearls" not in full_action_list
        assert "facts" not in user_content
        assert "progression_hints" not in user_content
        assert "before_status" not in payload["messages"][1]["content"]
        assert "after_status" not in payload["messages"][1]["content"]
    finally:
        restore_env(old_env)
        server.shutdown()

    packet = build_llm_state_packet(
        status=starter,
        recent_memory=[],
        last_result={"action": "mine_stone", "ok": False, "error": "Missing pickaxe.", "verifier": {"failure_type": "no_progress"}},
        bridge_actions=("status", "mine_stone"),
        mission="survive",
    )
    # mine_stone is in bridge_actions and core list → should appear in detailed_action_docs
    assert "mine_stone" in packet["detailed_action_docs"]
    assert packet["detailed_action_docs"]["mine_stone"]["args"] == {"count": "1-16"}
    assert packet["last_action_result"]["error"] == "Missing pickaxe."
    # compact list should contain both bridge actions
    assert "status" in packet["full_action_list"]
    assert "mine_stone" in packet["full_action_list"]

    solved_state = state(
        {
            "ok": True,
            "health": 20,
            "food": 20,
            "inventory_counts": {"wooden_pickaxe": 1, "cobblestone": 8, "crafting_table": 3, "stick": 2},
            "nearby_blocks": {"crafting_table": None},
            "nearby_block_counts": {},
            "nearby_entities": [],
        }
    )
    stale_memory = [
        {"id": 1, "message": "Need wooden pickaxe", "action": "craft_wooden_pickaxe", "ok": 0, "error": "No pickaxe.", "reason": "missing pickaxe"},
        {"id": 2, "message": "Missing cobblestone", "action": "mine_stone", "ok": 0, "error": "Need cobblestone.", "reason": "missing cobblestone"},
        {"id": 3, "message": "Recent neutral status", "action": "status", "ok": 1, "error": None, "reason": "ok"},
    ]
    stale_packet = build_llm_state_packet(
        status=solved_state,
        recent_memory=stale_memory,
        last_result={
            "action": "craft_wooden_pickaxe",
            "ok": False,
            "error": "No crafting table found within radius 4.",
            "verifier": {"failure_type": "no_progress", "recommendation": "Need crafting table nearby."},
        },
        bridge_actions=("status", "craft_stone_pickaxe"),
        mission="survive",
    )
    assert stale_packet["current_facts"]["has_wooden_pickaxe"] is True
    assert stale_packet["current_facts"]["cobblestone_count"] == 8
    assert stale_packet["current_facts"]["has_inventory_crafting_table"] is True
    assert stale_packet["current_facts"]["has_nearby_crafting_table"] is False
    assert stale_packet["current_facts"]["can_attempt_stone_pickaxe_materials"] is False
    assert stale_packet["memory_filter"]["stale_memory_removed_count"] == 2
    assert stale_packet["memory_filter"]["memory_filtered_count"] == 1
    assert stale_packet["memory"][0]["historical"] is True
    assert stale_packet["last_relevant_failure"]["action"] == "craft_wooden_pickaxe"

    retry_packet = build_llm_state_packet(
        status=starter,
        recent_memory=[],
        last_result={
            "action": "acquire_blocks",
            "ok": False,
            "result": {
                "partial_success": False,
                "can_retry": True,
                "suggested_next_action": "navigate_to_block_type",
                "stop_reason": "path_timeout_before_target",
            },
            "verifier": {"failure_type": "bridge_error", "recommendation": "Try navigation first."},
        },
        bridge_actions=("status", "acquire_blocks", "navigate_to_block_type"),
        mission="survive",
    )
    last_action_result = retry_packet["last_action_result"]
    assert last_action_result["partial_success"] is False
    assert last_action_result["can_retry"] is True
    # suggested_next_action is suppressed from LLM state packet by default (VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM=0)
    assert "suggested_next_action" not in last_action_result
    assert last_action_result["stop_reason"] == "path_timeout_before_target"

    server, base_url = start_stub()
    StubHandler.response_action = "place_crafting_table"
    StubHandler.response_args = {"count": 4}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        table_state = state(
            {
                "ok": True,
                "health": 20,
                "food": 20,
                "position": {"x": 1, "y": 64, "z": 2},
                "inventory_counts": {"oak_log": 1},
                "nearby_blocks": {
                    "crafting_table": {
                        "name": "crafting_table",
                        "position": {"x": 2, "y": 64, "z": 2},
                    }
                },
                "nearby_block_counts": {"crafting_table": 1},
                "nearby_entities": [],
            }
        )
        decision, info = choose_next_action(table_state, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "hybrid")
        assert decision.action == "place_crafting_table"
        assert decision.args == {}
        assert info["args_sanitized"] is True
        assert "llm_action_overridden" not in info
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    server, base_url = start_stub()
    StubHandler.response_action = "craft_wooden_pickaxe"
    StubHandler.response_args = {
        "status": "ready",
        "say": "Making pickaxe!",
        "look_around": {"radius": 16},
    }
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        tool_state = state(
            {
                "ok": True,
                "health": 20,
                "food": 20,
                "position": {"x": 1, "y": 64, "z": 2},
                "inventory_counts": {"oak_planks": 3, "stick": 2},
                "nearby_blocks": {
                    "crafting_table": {
                        "name": "crafting_table",
                        "position": {"x": 2, "y": 64, "z": 2},
                    }
                },
                "nearby_block_counts": {"crafting_table": 1},
                "nearby_entities": [],
            }
        )
        decision, info = choose_next_action(tool_state, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "hybrid")
        assert decision.action == "craft_wooden_pickaxe"
        assert decision.args == {}
        assert info["args_sanitized"] is True
        assert info["args_sanitization_reason"] == "no-arg action"
        assert info["removed_arg_keys"] == ["look_around", "say", "status"]
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    server, base_url = start_stub()
    StubHandler.response_action = "collect_wood"
    StubHandler.response_args = {"count": 4, "radius": 64, "status": "ready"}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        decision, info = choose_next_action(starter, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision.action == "collect_wood"
        assert decision.args == {"count": 4}
        assert info["args_sanitized"] is True
        assert info["removed_arg_keys"] == ["radius", "status"]
    finally:
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    # --- compact action list: all implemented/partial LLM-exposed actions appear ---
    from vtuber_ai.action_catalog import get_compact_action_list, get_detailed_action_docs, llm_exposed_count, CATALOG
    full_list = get_compact_action_list(set(AUTONOMOUS_ALLOWED_ACTIONS))
    assert "status" in full_list
    assert "collect_wood" in full_list
    assert "craft_item(item" in full_list
    assert "prefer specific craft_*" in full_list
    assert "setup_workspace" in full_list
    assert "return_to_workspace" in full_list
    assert "describe_actions" in full_list
    # planned/stub must not appear
    assert "mine_diamond_ore" not in full_list
    assert "collect_ender_pearls" not in full_list
    assert "craft_bow" not in full_list
    # total exposed count is >= AUTONOMOUS_ALLOWED_ACTIONS
    assert llm_exposed_count() >= len(AUTONOMOUS_ALLOWED_ACTIONS)
    # compact list stays within budget
    assert len(full_list) <= 5000  # well within any reasonable prompt budget

    # --- detailed action docs: count bounded, correct schemas ---
    docs_12 = get_detailed_action_docs(["status", "collect_wood", "mine_stone", "craft_planks",
                                        "smelt_iron", "setup_workspace", "return_to_workspace",
                                        "flee", "eat_food", "recover_position", "find_safe_workspace",
                                        "craft_iron_pickaxe"])
    assert len(docs_12) == 12
    assert "status" in docs_12
    assert docs_12["mine_stone"]["args"] == {"count": "1-16"}
    assert docs_12["smelt_iron"]["args"] == {"count": "1-32 optional"}
    # planned actions are excluded from detailed docs
    docs_planned = get_detailed_action_docs(["mine_diamond_ore", "craft_bow", "status"])
    assert "mine_diamond_ore" not in docs_planned  # planned
    assert "craft_bow" not in docs_planned         # planned
    assert "status" in docs_planned

    # --- prompt size: full packet with all actions stays under 9000 chars ---
    import json as _json
    from vtuber_ai.game_brain import BRAIN_SYSTEM_PROMPT
    budget_packet = build_llm_state_packet(
        status=starter,
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="survive",
    )
    budget_content = _json.dumps(budget_packet, separators=(",", ":"))
    total_chars = len(BRAIN_SYSTEM_PROMPT) + len(budget_content)
    assert total_chars < 20000, f"prompt too large: {total_chars} chars"
    # full_action_list is present and compact
    assert isinstance(budget_packet["full_action_list"], str)
    assert len(budget_packet["full_action_list"]) <= 5000
    # detailed_action_docs bounded
    assert len(budget_packet["detailed_action_docs"]) <= 12

    # --- describe_actions returns correct docs ---
    from vtuber_ai.action_catalog import get_detailed_action_docs as _gdd
    describe_result = _gdd(["setup_workspace", "return_to_workspace", "find_safe_workspace"])
    assert "setup_workspace" in describe_result
    assert "return_to_workspace" in describe_result
    assert "find_safe_workspace" in describe_result
    assert "description" in describe_result["setup_workspace"]
    assert "args" in describe_result["return_to_workspace"]

    # --- compact planner: _parse_llm_raw unit tests ---
    from vtuber_ai.game_brain import _parse_llm_raw
    # compact schema {"a":...}
    d, is_compact = _parse_llm_raw({"a": "mine_stone", "args": {"count": 3}})
    assert d.action == "mine_stone"
    assert d.args == {"count": 3}
    assert d.speech == ""
    assert d.mood == "focused"
    assert d.objective == "mine_stone"
    assert is_compact is True

    # compact schema with why
    d, is_compact = _parse_llm_raw({"a": "collect_wood", "args": {}, "why": "need wood"})
    assert d.action == "collect_wood"
    assert d.reason == "need wood"
    assert is_compact is True

    # full schema {"action":...}
    d, is_compact = _parse_llm_raw({
        "objective": "mine stone", "action": "mine_stone", "args": {"count": 3},
        "speech": "Mining!", "mood": "focused", "reason": "need cobblestone",
    })
    assert d.action == "mine_stone"
    assert d.speech == "Mining!"
    assert is_compact is False

    # compact schema: missing args defaults to {}
    d, is_compact = _parse_llm_raw({"a": "status"})
    assert d.action == "status"
    assert d.args == {}
    assert is_compact is True

    # --- compact planner: integration test (stub returns compact format) ---
    server, base_url = start_stub()
    StubHandler.response_action = "mine_stone"
    StubHandler.response_args = {"count": 3}
    StubHandler.response_compact = True
    old_env = {
        "VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL"),
        "VTUBER_PLANNER_OUTPUT_MODE": os.environ.get("VTUBER_PLANNER_OUTPUT_MODE"),
    }
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    os.environ["VTUBER_PLANNER_OUTPUT_MODE"] = "compact"
    try:
        compact_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {"wooden_pickaxe": 1},
            "nearby_blocks": {}, "nearby_entities": [],
        })
        decision, info = choose_next_action(compact_state, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision, got fallback: {info.get('fallback_reason')}"
        assert decision.action == "mine_stone"
        assert decision.speech == ""
        assert decision.mood == "focused"
        assert info.get("parsed_compact_output") is True
        assert info.get("planner_output_mode") == "compact"
        assert info.get("completion_tokens") == 12
        assert isinstance(info.get("raw_llm_output_chars"), int) and info["raw_llm_output_chars"] > 0
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        StubHandler.response_compact = False
        restore_env(old_env)
        server.shutdown()

    # --- compact planner: full-schema stub in compact mode still parses ---
    server, base_url = start_stub()
    StubHandler.response_action = "collect_wood"
    StubHandler.response_args = {"count": 4}
    StubHandler.response_compact = False
    old_env = {
        "VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL"),
        "VTUBER_PLANNER_OUTPUT_MODE": os.environ.get("VTUBER_PLANNER_OUTPUT_MODE"),
    }
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    os.environ["VTUBER_PLANNER_OUTPUT_MODE"] = "compact"
    try:
        decision, info = choose_next_action(starter, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision: {info.get('fallback_reason')}"
        assert decision.action == "collect_wood"
        assert info.get("parsed_compact_output") is False
        assert info.get("planner_output_mode") == "compact"
    finally:
        restore_env(old_env)
        server.shutdown()

    # --- compact planner: invalid/non-JSON response falls back safely ---
    server, base_url = start_stub()
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    # Override do_POST to return garbage JSON
    import http.server as _hs
    class BadStubHandler(_hs.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = {"choices": [{"message": {"content": "not json at all!!!"}}]}
            self.wfile.write(json.dumps(body).encode("utf-8"))
        def log_message(self, *_): return
    bad_server = __import__('http.server', fromlist=['HTTPServer']).HTTPServer(("127.0.0.1", 0), BadStubHandler)
    bad_thread = threading.Thread(target=bad_server.serve_forever, daemon=True)
    bad_thread.start()
    bad_url = f"http://127.0.0.1:{bad_server.server_address[1]}"
    os.environ["VTUBER_LLM_BASE_URL"] = bad_url
    try:
        decision, info = choose_next_action(starter, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is None or info.get("fallback_used") is True or info.get("fallback_reason")
    finally:
        restore_env(old_env)
        bad_server.shutdown()

    # --- planner_output_mode in diagnostics when no base_url ---
    os.environ.pop("VTUBER_LLM_BASE_URL", None)
    os.environ["VTUBER_PLANNER_OUTPUT_MODE"] = "full"
    try:
        decision, info = choose_next_action(starter, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert info.get("planner_output_mode") == "full"
    finally:
        os.environ.pop("VTUBER_PLANNER_OUTPUT_MODE", None)

    # --- ACTION_ALIASES: mine_obsidian → collect_obsidian ---
    server, base_url = start_stub()
    StubHandler.response_action = "mine_obsidian"
    StubHandler.response_args = {"count": 5}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        obsidian_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {"diamond_pickaxe": 1},
            "nearby_blocks": {}, "nearby_entities": [],
        })
        decision, info = choose_next_action(obsidian_state, [], "collect obsidian", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision, got fallback: {info.get('fallback_reason')}"
        assert decision.action == "collect_obsidian", f"Expected collect_obsidian, got {decision.action}"
        assert info.get("action_alias_applied") is True, "action_alias_applied should be True"
        assert info.get("original_action") == "mine_obsidian"
        assert info.get("canonical_action") == "collect_obsidian"
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    # --- list-valued args normalize compact string forms before policy validation ---
    server, base_url = start_stub()
    StubHandler.response_action = "navigate_to_block_type"
    StubHandler.response_args = {"targets": "spruce_log", "radius": 8}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        nav_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {},
            "nearby_blocks": {}, "nearby_entities": [],
            "nearby_block_counts": {"spruce_log": 4},
        })
        decision, info = choose_next_action(nav_state, [], "move to spruce log", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision, got fallback: {info.get('fallback_reason')}"
        assert decision.action == "navigate_to_block_type"
        assert decision.args == {"targets": ["spruce_log"], "radius": 8}
        assert info.get("args_normalized") is True
        assert info.get("normalized_arg_keys") == ["targets"]
        assert info.get("normalization_reason") == "string_to_singleton_list"
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    # --- boolean args normalize compact string forms before policy validation ---
    server, base_url = start_stub()
    StubHandler.response_action = "mine_coal"
    StubHandler.response_args = {"allowExcavate": "true", "radius": 32}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        coal_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {"wooden_pickaxe": 1},
            "nearby_blocks": {}, "nearby_entities": [],
            "nearby_block_counts": {"coal_ore": 4},
        })
        decision, info = choose_next_action(coal_state, [], "mine coal", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision, got fallback: {info.get('fallback_reason')}"
        assert decision.action == "mine_coal"
        assert decision.args == {"allowExcavate": True, "radius": 32}
        assert info.get("args_normalized") is True
        assert info.get("normalized_arg_keys") == ["allowExcavate"]
        assert info.get("normalization_reason") == "string_boolean_to_boolean"
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    # --- craft_item item aliases canonicalize to specific craft_* actions ---
    server, base_url = start_stub()
    StubHandler.response_action = "craft_item"
    StubHandler.response_args = {"item": "stone_pickaxe"}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        craft_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {"cobblestone": 3, "stick": 2},
            "nearby_blocks": {"crafting_table": {"distance": 2.0}},
            "nearby_entities": [],
        })
        decision, info = choose_next_action(craft_state, [], "craft stone pickaxe", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision, got fallback: {info.get('fallback_reason')}"
        assert decision.action == "craft_stone_pickaxe"
        assert decision.args == {}
        assert info.get("action_canonicalized") is True
        assert info.get("original_action") == "craft_item"
        assert info.get("original_args") == {"item": "stone_pickaxe"}
        assert info.get("canonical_action") == "craft_stone_pickaxe"
        assert info.get("canonicalization_reason") == "craft_item item alias"
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    server, base_url = start_stub()
    StubHandler.response_action = "craft_item"
    StubHandler.response_args = {"item": "sticks", "count": 4}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        stick_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {"spruce_planks": 2},
            "nearby_blocks": {}, "nearby_entities": [],
        })
        decision, info = choose_next_action(stick_state, [], "craft sticks", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision, got fallback: {info.get('fallback_reason')}"
        assert decision.action == "craft_sticks"
        assert decision.args == {"count": 4}
        assert info.get("action_canonicalized") is True
        assert info.get("canonical_action") == "craft_sticks"
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    # --- ACTION_ALIASES: make_furnace → craft_furnace ---
    server, base_url = start_stub()
    StubHandler.response_action = "make_furnace"
    StubHandler.response_args = {}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        furnace_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {"cobblestone": 8},
            "nearby_blocks": {}, "nearby_entities": [],
        })
        decision, info = choose_next_action(furnace_state, [], "make furnace", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is not None, f"Expected decision, got fallback: {info.get('fallback_reason')}"
        assert decision.action == "craft_furnace", f"Expected craft_furnace, got {decision.action}"
        assert info.get("action_alias_applied") is True
        assert info.get("original_action") == "make_furnace"
        assert info.get("canonical_action") == "craft_furnace"
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    # --- ACTION_ALIASES: truly unknown action still rejected ---
    server, base_url = start_stub()
    StubHandler.response_action = "fly_to_moon"
    StubHandler.response_args = {}
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        unknown_state = state({
            "ok": True, "health": 20, "food": 20,
            "inventory_counts": {}, "nearby_blocks": {}, "nearby_entities": [],
        })
        decision, info = choose_next_action(unknown_state, [], "survive", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert decision is None or decision.action != "fly_to_moon", "fly_to_moon must not be executed"
        assert "fallback_reason" in info
        assert "fly_to_moon" in info["fallback_reason"]
        assert info.get("action_alias_applied") is not True
    finally:
        StubHandler.response_action = "collect_wood"
        StubHandler.response_args = {"count": 4}
        restore_env(old_env)
        server.shutdown()

    # --- VERIFIER: failed_because and repeatable_now emitted at tick time ---
    from vtuber_ai.verifier import verify_action
    from vtuber_ai.schemas import ActionRequest, ActionResult

    def _make_req(action: str) -> ActionRequest:
        return ActionRequest(action=action, args={}, speech="", reason="")

    def _make_res(ok: bool, error: str | None = None, result: dict | None = None, action: str = "test") -> ActionResult:
        return ActionResult(ok=ok, action=action, error=error, result=result or {})

    unchanged_summary = {"inventory_counts": {}, "nearby_blocks": {}, "health": 20, "food": 20}
    empty_state = {"inventory_counts": {}, "nearby_blocks": {}, "nearby_entities": [], "health": 20, "food": 20}

    # craft_torches missing stick → verifier emits failed_because
    v_torch = verify_action(
        empty_state, empty_state,
        _make_req("craft_torches"),
        _make_res(False, "Missing materials: stick x1.", {"missing_materials": [{"name": "stick"}], "failure_type": "missing_materials"}),
    )
    assert isinstance(v_torch.get("failed_because"), list) and v_torch["failed_because"], \
        f"verifier must emit failed_because for craft_torches, got: {v_torch.get('failed_because')}"
    assert v_torch["repeatable_now"] is False, \
        f"repeatable_now must be False for missing_materials, got: {v_torch.get('repeatable_now')}"
    assert v_torch.get("repeat_condition") is not None

    # craft_sticks missing planks → verifier emits failed_because
    v_sticks = verify_action(
        empty_state, empty_state,
        _make_req("craft_sticks"),
        _make_res(False, "Missing materials: planks x2.", {"missing_materials": [{"name": "planks"}], "failure_type": "missing_materials"}),
    )
    assert isinstance(v_sticks.get("failed_because"), list) and v_sticks["failed_because"], \
        f"verifier must emit failed_because for craft_sticks, got: {v_sticks.get('failed_because')}"
    assert v_sticks["repeatable_now"] is False

    # Exact "need N item, have M" errors preserve quantities in failed_because.
    for error, expected in [
        ("Missing materials: need 2 planks, have 1.", {"kind": "inventory_item", "item": "planks", "need": 2, "have": 1}),
        ("Missing materials: need 3 cobblestone, have 0.", {"kind": "inventory_item", "item": "cobblestone", "need": 3, "have": 0}),
        ("Missing materials: need 8 cobblestone, have 4.", {"kind": "inventory_item", "item": "cobblestone", "need": 8, "have": 4}),
    ]:
        v_need_have = verify_action(
            empty_state, empty_state,
            _make_req("craft_sticks"),
            _make_res(False, error),
        )
        assert expected in (v_need_have.get("failed_because") or []), \
            f"expected exact failed_because {expected}, got: {v_need_have.get('failed_because')}"

    # craft_planks missing logs → verifier emits failed_because via error parsing
    v_planks = verify_action(
        empty_state, empty_state,
        _make_req("craft_planks"),
        _make_res(False, "Missing materials: oak_log x1.", {"missing_materials": [{"name": "oak_log"}], "failure_type": "missing_materials"}),
    )
    assert isinstance(v_planks.get("failed_because"), list) and v_planks["failed_because"], \
        f"verifier must emit failed_because for craft_planks, got: {v_planks.get('failed_because')}"

    # --- status success does NOT clear unresolved_failure ---
    torch_unchanged = {"inventory_counts": {"spruce_planks": 0, "wooden_pickaxe": 1}, "position": {"x": 0, "y": 64, "z": 0}}
    torch_fail_tick2 = {
        "action": "craft_torches", "ok": 0,
        "error": "Missing materials: stick x1, coal_or_charcoal x1.",
        "result": {},
        "verifier": {
            "failure_type": "missing_materials",
            "missing_materials": ["stick", "coal_or_charcoal"],
            "possible_next_actions": ["craft_sticks", "mine_coal"],
            "lesson": "Torches need sticks and coal or charcoal.",
        },
        "before_state": torch_unchanged, "after_state": torch_unchanged,
    }
    status_ok_tick2 = {
        "action": "status", "ok": 1, "error": None, "result": {},
        "verifier": {"failure_type": "none"},
        "before_state": torch_unchanged, "after_state": torch_unchanged,
    }
    torch_summary2 = {"ok": True, "health": 20, "food": 20, "inventory_counts": {"wooden_pickaxe": 1}, "nearby_blocks": {}, "nearby_entities": []}
    # status is newest tick, craft_torches failure is older
    pkt_after_status = build_llm_state_packet(
        status=state(torch_summary2, recent_ticks=[status_ok_tick2, torch_fail_tick2]),
        recent_memory=[],
        last_result={"action": "status", "ok": True, "result": {}, "verifier": {"failure_type": "none"}},
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="make torches",
    )
    assert pkt_after_status["unresolved_failure"] is not None, \
        "unresolved_failure must persist after a status success"
    assert pkt_after_status["unresolved_failure"]["action"] == "craft_torches"
    assert pkt_after_status["current_intent"] is not None, \
        "current_intent must persist after a status success"

    # --- dependency chain: craft_torches → craft_sticks → craft_planks ---
    planks_unchanged = {"inventory_counts": {}, "position": {"x": 0, "y": 64, "z": 0}}
    craft_planks_fail_tick = {
        "action": "craft_planks", "ok": 0,
        "error": "Missing materials: oak_log x1.",
        "result": {},
        "verifier": {
            "failure_type": "missing_materials",
            "missing_materials": ["oak_log"],
            "failed_because": [{"kind": "inventory_item", "item": "oak_log", "need": 1, "have": 0}],
            "repeatable_now": False,
        },
        "before_state": planks_unchanged, "after_state": planks_unchanged,
    }
    craft_sticks_fail_tick2 = {
        "action": "craft_sticks", "ok": 0,
        "error": "Missing materials: planks x2.",
        "result": {},
        "verifier": {
            "failure_type": "missing_materials",
            "missing_materials": ["planks"],
            "failed_because": [{"kind": "inventory_item", "item": "planks", "need": 2, "have": 0}],
            "repeatable_now": False,
        },
        "before_state": planks_unchanged, "after_state": planks_unchanged,
    }
    # Ticks newest-first: craft_planks (newest), craft_sticks, craft_torches (oldest)
    dep_chain_packet = build_llm_state_packet(
        status=state(torch_summary2, recent_ticks=[craft_planks_fail_tick, craft_sticks_fail_tick2, torch_fail_tick2]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="make torches",
    )
    dep_intent = dep_chain_packet["current_intent"]
    assert dep_intent is not None, "current_intent must survive a dependency failure chain"
    assert dep_intent["goal_action"] == "craft_torches", \
        f"goal_action must remain craft_torches, got {dep_intent.get('goal_action')}"
    dep_chain = dep_intent.get("dependency_chain")
    assert dep_chain is not None, "dependency_chain must be present after multi-step failures"
    assert "craft_torches" in dep_chain, f"craft_torches missing from dep chain: {dep_chain}"
    assert dep_intent.get("repair_attempts_count", 0) >= 2, \
        f"repair_attempts_count must be >= 2, got {dep_intent.get('repair_attempts_count')}"

    # --- run_agent_live stopping-logic helpers ---

    # Navigation failure → recoverable, not fatal.
    nav_verifier = {"failure_type": "navigation_failed"}
    assert _is_fatal_live_failure(nav_verifier) is False, \
        "navigation_failed must NOT be fatal so live loop continues"
    assert _is_recoverable_failure(nav_verifier) is True, \
        "navigation_failed must be recoverable"

    # Actual bridge crash → fatal.
    bridge_verifier = {"failure_type": "bridge_error"}
    assert _is_fatal_live_failure(bridge_verifier) is True, \
        "bridge_error must be fatal"
    assert _is_recoverable_failure(bridge_verifier) is False, \
        "bridge_error must not be recoverable"

    # Missing materials → recoverable.
    mat_verifier = {"failure_type": "missing_materials"}
    assert _is_fatal_live_failure(mat_verifier) is False
    assert _is_recoverable_failure(mat_verifier) is True

    # path_timeout (pre-normalisation) → recoverable.
    pt_verifier = {"failure_type": "path_timeout"}
    assert _is_fatal_live_failure(pt_verifier) is False
    assert _is_recoverable_failure(pt_verifier) is True

    # Resource acquisition timeout → recoverable, so /agent/live can continue.
    resource_verifier = {"failure_type": "resource_acquisition_failed"}
    assert _is_fatal_live_failure(resource_verifier) is False
    assert _is_recoverable_failure(resource_verifier) is True

    # --- station_affordances: furnace in inventory + no nearby furnace → gap fact ---
    from vtuber_ai.game_brain import (
        _station_affordances, _item_affordances, _inventory_efficiency,
        _navigation_stall_from_ticks, _repeated_failed_action_loop, _invalid_action_loop,
        _repeated_failed_action_family, _recent_completed_intents_from_ticks,
        _blocked_action_families, find_blocked_family,
        _recent_resource_successes_from_ticks, _resource_sufficiency,
        _is_timeout_tick,
    )
    from vtuber_ai.memory import action_family_key, schema_blocked_family_key
    from vtuber_ai.verifier import POSITION_MEANINGFUL_DELTA_BLOCKS

    furnace_inv_summary = {
        "inventory_counts": {"furnace": 1, "coal": 35, "raw_iron": 1},
        "nearby_blocks": {},  # furnace not deployed
    }
    sa = _station_affordances(furnace_inv_summary)
    assert sa["carried_stations"]["furnace"] == 1
    assert sa["usable_nearby_stations"]["furnace"] is False
    assert len(sa["station_gap_facts"]) > 0
    assert any(gf["station"] == "furnace" for gf in sa["station_gap_facts"])
    furnace_gap = next(gf for gf in sa["station_gap_facts"] if gf["station"] == "furnace")
    assert furnace_gap["in_inventory"] is True
    assert furnace_gap["usable_nearby"] is False
    assert "station is carried but not usable nearby" in furnace_gap["fact"]

    # station usable nearby → no gap fact
    furnace_nearby_summary = {
        "inventory_counts": {"furnace": 1},
        "nearby_blocks": {"furnace": {"name": "furnace", "distance": 3.0}},
    }
    sa_no_gap = _station_affordances(furnace_nearby_summary)
    assert sa_no_gap["usable_nearby_stations"]["furnace"] is True
    assert not any(gf["station"] == "furnace" for gf in sa_no_gap["station_gap_facts"])

    # --- item_affordances: raw_iron + coal → has_smeltable_items and has_fuel ---
    smelting_summary = {
        "inventory_counts": {"raw_iron": 1, "coal": 35},
        "nearby_blocks": {},
    }
    ia = _item_affordances(smelting_summary)
    assert ia["has_fuel"] is True
    assert ia["fuel_items"].get("coal") == 35
    assert ia["has_smeltable_items"] is True
    assert ia["smeltable_items"].get("raw_iron") == 1
    assert "tool_duplicates" in ia
    assert ia["low_consumables"]["food"] is True  # no food items
    assert ia["low_consumables"]["torches"] is True  # no torches

    # fuel with no smeltable → has_fuel True, has_smeltable_items False
    fuel_only = {"inventory_counts": {"coal": 10}, "nearby_blocks": {}}
    ia2 = _item_affordances(fuel_only)
    assert ia2["has_fuel"] is True
    assert ia2["has_smeltable_items"] is False

    # --- inventory_efficiency: many stone_pickaxe → duplicate_tools fact ---
    many_picks_summary = {
        "inventory_counts": {"stone_pickaxe": 7, "coal": 3, "oak_log": 2},
        "nearby_blocks": {},
    }
    eff = _inventory_efficiency(many_picks_summary)
    assert eff["duplicate_tools"].get("stone_pickaxe") == 7
    assert eff["inventory_slots_used"] == 3
    assert "note" in eff

    # 2 of same tool → not a duplicate (threshold > 2)
    two_picks = {"inventory_counts": {"stone_pickaxe": 2}, "nearby_blocks": {}}
    eff2 = _inventory_efficiency(two_picks)
    assert "stone_pickaxe" not in eff2["duplicate_tools"]
    assert "note" not in eff2

    # --- navigation_stall: repeated navigation failures create stall fact ---
    nav_fail_tick = {
        "action": "navigate_to_block_type",
        "ok": 0,
        "error": "navigation path failed: timed out pathing to iron_ore",
        "result": {"failure_type": "navigation_failed"},
        "verifier": {"failure_type": "navigation_failed"},
        "args": {"targets": ["iron_ore"], "radius": 64},
        "before_state": {"position": {"x": 0, "y": 64, "z": 0}},
        "after_state": {"position": {"x": 0, "y": 64, "z": 0}},
    }
    stall = _navigation_stall_from_ticks([nav_fail_tick, nav_fail_tick, nav_fail_tick], {})
    assert stall is not None
    assert stall["recent_navigation_failures"] == 3
    assert "iron_ore" in stall["last_failed_targets"]
    assert stall["position_changed_recently"] is False
    assert "Recent movement" in stall["fact"]

    # single nav failure → still a stall
    stall1 = _navigation_stall_from_ticks([nav_fail_tick], {})
    assert stall1 is not None
    assert stall1["recent_navigation_failures"] == 1

    # no failures → None
    success_tick = {
        "action": "navigate_to_block_type",
        "ok": 1,
        "error": None,
        "result": {},
        "verifier": {"failure_type": "none"},
        "before_state": {"position": {"x": 0, "y": 64, "z": 0}},
        "after_state": {"position": {"x": 10, "y": 64, "z": 0}},
    }
    assert _navigation_stall_from_ticks([success_tick], {}) is None

    # resource acquisition failure also detected
    resource_fail_tick = {
        "action": "mine_iron_ore",
        "ok": 0,
        "error": "block acquisition failed: timed out",
        "result": {"failure_type": "resource_acquisition_failed"},
        "verifier": {"failure_type": "resource_acquisition_failed"},
        "args": {},
        "before_state": {"position": {"x": 0, "y": 64, "z": 0}},
        "after_state": {"position": {"x": 0, "y": 64, "z": 0}},
    }
    stall_resource = _navigation_stall_from_ticks([resource_fail_tick, nav_fail_tick], {})
    assert stall_resource is not None
    assert stall_resource["recent_navigation_failures"] == 2

    # --- _repeated_failed_action_loop: same non-observation action fails ≥2 times ---
    _mine_fail_tick = {
        "action": "mine_iron_ore", "ok": 0, "error": "block not found",
        "result": {}, "verifier": {"failure_type": "no_progress"},
    }
    _pm_mine = {"recent_action_repetition": {"action": "mine_iron_ore", "count": 3}, "low_information_loop": False}
    rfa = _repeated_failed_action_loop([_mine_fail_tick, _mine_fail_tick, _mine_fail_tick], _pm_mine)
    assert rfa is not None, "must detect repeated failure of same action"
    assert rfa["action"] == "mine_iron_ore"
    assert rfa["count"] == 3
    assert rfa["failed_count"] >= 2
    assert "mine_iron_ore" in rfa["fact"]

    # same action only once (count < 2) → None
    _pm_once = {"recent_action_repetition": {"action": "mine_iron_ore", "count": 1}, "low_information_loop": False}
    assert _repeated_failed_action_loop([_mine_fail_tick], _pm_once) is None

    # observation action (status) → None even if repeated
    _status_fail_tick = {"action": "status", "ok": 0, "error": "bridge fail", "result": {}}
    _pm_status = {"recent_action_repetition": {"action": "status", "count": 3}, "low_information_loop": False}
    assert _repeated_failed_action_loop([_status_fail_tick, _status_fail_tick, _status_fail_tick], _pm_status) is None

    # no progress_monitor → None
    assert _repeated_failed_action_loop([], None) is None

    # --- _invalid_action_loop: ticks with invalid_action / invalid_action_args ---
    _inv_tick = {
        "action": "fly_to_moon", "ok": 0, "error": "unknown action",
        "verifier": {"failure_type": "invalid_action"},
    }
    _inv_args_tick = {
        "action": "navigate_to_block_type", "ok": 0, "error": "bad args",
        "verifier": {"failure_type": "invalid_action_args"},
    }
    ial = _invalid_action_loop([_inv_tick, _inv_args_tick])
    assert ial is not None, "must detect invalid action failures"
    assert ial["invalid_action_count"] == 2
    assert "fly_to_moon" in ial["actions"]
    assert "navigate_to_block_type" in ial["actions"]
    assert "2" in ial["fact"]

    # no invalid ticks → None
    assert _invalid_action_loop([_mine_fail_tick]) is None
    assert _invalid_action_loop([]) is None

    # --- _recent_completed_intents_from_ticks ---
    _smelt_ok_tick = {
        "action": "smelt_item",
        "ok": 1,
        "args": {"input": "raw_iron", "count": 1},
        "result": {},
        "verifier": {"failure_type": "none"},
    }
    _collect_ok_tick = {
        "action": "collect_wood",
        "ok": 1,
        "args": {"count": 5},
        "result": {},
        "verifier": {"failure_type": "none"},
    }
    _status_ok_tick = {
        "action": "status",
        "ok": 1,
        "args": {},
        "result": {},
        "verifier": {"failure_type": "none"},
    }
    _nav_ok_tick = {
        "action": "navigate_to_block_type",
        "ok": 1,
        "args": {"targets": ["iron_ore"], "radius": 32},
        "result": {},
        "verifier": {"failure_type": "none"},
    }

    # smelt_item success → appears with input= but not count=
    rci = _recent_completed_intents_from_ticks([_smelt_ok_tick])
    assert len(rci) == 1, rci
    assert rci[0]["action"] == "smelt_item"
    assert rci[0]["result"] == "succeeded"
    assert rci[0]["age_ticks"] == 0
    assert rci[0].get("input") == "raw_iron", rci[0]
    assert "count" not in rci[0], rci[0]

    # observation action → excluded
    rci_obs = _recent_completed_intents_from_ticks([_status_ok_tick])
    assert rci_obs == [], rci_obs

    # count + radius → excluded; targets → kept
    rci_nav = _recent_completed_intents_from_ticks([_nav_ok_tick])
    assert len(rci_nav) == 1, rci_nav
    assert "targets" in rci_nav[0], rci_nav[0]
    assert "radius" not in rci_nav[0], rci_nav[0]

    # collect_wood maps to resource_acquisition:wood → resource_family added; count filtered out
    rci_cw = _recent_completed_intents_from_ticks([_collect_ok_tick])
    assert len(rci_cw) == 1, rci_cw
    assert rci_cw[0]["action"] == "collect_wood", rci_cw[0]
    assert rci_cw[0]["result"] == "succeeded", rci_cw[0]
    assert rci_cw[0]["age_ticks"] == 0, rci_cw[0]
    assert rci_cw[0].get("resource_family") == "wood", rci_cw[0]
    assert "count" not in rci_cw[0], rci_cw[0]

    # failed tick → excluded
    rci_fail = _recent_completed_intents_from_ticks([_mine_fail_tick])
    assert rci_fail == [], rci_fail

    # age_ticks increments correctly; max_count=3 caps
    five_ticks = [_smelt_ok_tick, _collect_ok_tick, _smelt_ok_tick, _collect_ok_tick, _smelt_ok_tick]
    rci_cap = _recent_completed_intents_from_ticks(five_ticks, window=5, max_count=3)
    assert len(rci_cap) == 3, rci_cap
    assert rci_cap[0]["age_ticks"] == 0
    assert rci_cap[1]["age_ticks"] == 1
    assert rci_cap[2]["age_ticks"] == 2

    # empty → empty
    assert _recent_completed_intents_from_ticks([]) == []

    # --- action_family_key ---
    assert action_family_key("mine_iron_ore", {}) == "resource_acquisition:iron_ore"
    assert action_family_key("mine_stone", {}) == "resource_acquisition:stone"
    assert action_family_key("collect_wood", {}) == "resource_acquisition:wood"
    assert action_family_key("collect_obsidian", {}) == "resource_acquisition:obsidian"
    assert action_family_key("navigate_to_block_type", {"targets": ["iron_ore"]}) == "resource_acquisition:iron_ore"
    assert action_family_key("navigate_to_block_type", {"targets": ["oak_log", "spruce_log"]}) == "resource_acquisition:oak_log"
    assert action_family_key("navigate_to_block_type", {}) is None
    assert action_family_key("smelt_item", {}) == "action:smelt_item"
    assert action_family_key("scan_for_specific_block", {}) == "action:scan_for_specific_block"
    assert action_family_key("navigate_to_position", {}) == "navigation_target:position"
    assert action_family_key("status", {}) is None
    assert action_family_key("look_around", {}) is None
    assert action_family_key("check_inventory", {}) is None
    assert action_family_key("scan_for_hostiles", {}) is None
    assert action_family_key("acquire_blocks", {"targets": ["iron_ore"]}) == "resource_acquisition:iron_ore"
    assert action_family_key("acquire_blocks", {"targets": ["oak_log"]}) == "resource_acquisition:oak_log"
    assert action_family_key("acquire_blocks", {}) is None

    # --- _blocked_action_families: core detection ---
    _iron_pos = {"x": 10, "y": 64, "z": 10}
    _mine_iron_fail = {
        "action": "mine_iron_ore", "ok": 0,
        "args": {},
        "verifier": {"failure_type": "resource_acquisition_failed", "failed_because": [{"kind": "accessible_block", "block": "iron_ore", "accessible": False}]},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    _nav_iron_fail = {
        "action": "navigate_to_block_type", "ok": 0,
        "args": {"targets": ["iron_ore"], "radius": 32},
        "verifier": {"failure_type": "navigation_failed", "failed_because": [{"kind": "nearby_block", "block": "iron_ore", "accessible": False}]},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    _same_summary = {"position": _iron_pos, "inventory_counts": {}}

    # mine_iron_ore + navigate_to_block_type iron_ore → resource_acquisition:iron_ore blocked
    baf = _blocked_action_families([_mine_iron_fail, _nav_iron_fail], _same_summary)
    assert len(baf) == 1, baf
    assert baf[0]["family"] == "resource_acquisition:iron_ore", baf[0]
    assert baf[0]["blocked"] is True
    assert baf[0]["failure_count"] == 2
    assert baf[0]["repeatable_now"] is False
    assert "iron_ore" in baf[0]["unblock_condition"]
    assert isinstance(baf[0]["last_failures"], list) and len(baf[0]["last_failures"]) > 0

    # same action once → below threshold, not blocked
    baf_once = _blocked_action_families([_mine_iron_fail], _same_summary)
    assert baf_once == [], baf_once

    # moving > 8 blocks → family cleared
    _moved_summary = {"position": {"x": 60, "y": 64, "z": 60}, "inventory_counts": {}}
    baf_moved = _blocked_action_families([_mine_iron_fail, _nav_iron_fail], _moved_summary)
    assert baf_moved == [], baf_moved

    # inventory changed → family cleared
    _got_iron_summary = {"position": _iron_pos, "inventory_counts": {"raw_iron": 3}}
    baf_inv = _blocked_action_families([_mine_iron_fail, _nav_iron_fail], _got_iron_summary)
    assert baf_inv == [], baf_inv

    # smelt_item repeated invalid args → action:smelt_item blocked
    _smelt_fail = {
        "action": "smelt_item", "ok": 0,
        "args": {"count": 64},
        "verifier": {"failure_type": "invalid_args", "failed_because": [{"kind": "invalid_args", "action": "smelt_item", "missing_arg": "input"}]},
        "after_state": {"inventory_counts": {"coal": 10}},
    }
    _smelt_summary = {"position": _iron_pos, "inventory_counts": {"coal": 10}}
    baf_smelt = _blocked_action_families([_smelt_fail, _smelt_fail], _smelt_summary)
    assert any(bf["family"] == "action:smelt_item" for bf in baf_smelt), baf_smelt
    smelt_blocked = next(bf for bf in baf_smelt if bf["family"] == "action:smelt_item")
    assert smelt_blocked["failure_count"] == 2
    assert "invalid_args" in smelt_blocked["last_failures"]

    # successful smelt_item tick doesn't count as failure → only 1 failure tick → not blocked
    _smelt_ok = {
        "action": "smelt_item", "ok": 1,
        "args": {"input": "raw_iron", "count": 1},
        "verifier": {"failure_type": "none"},
        "after_state": {"inventory_counts": {"iron_ingot": 1}},
    }
    _after_smelt_summary = {"position": _iron_pos, "inventory_counts": {"iron_ingot": 1}}
    baf_smelt_cleared = _blocked_action_families([_smelt_ok, _smelt_fail], _after_smelt_summary)
    assert not any(bf["family"] == "action:smelt_item" for bf in baf_smelt_cleared), baf_smelt_cleared

    # observation ticks never contribute to any family
    _status_fail = {
        "action": "status", "ok": 0, "args": {},
        "verifier": {"failure_type": "bridge_error"},
        "after_state": {"inventory_counts": {}},
    }
    baf_obs = _blocked_action_families([_status_fail, _status_fail, _status_fail], {"inventory_counts": {}})
    assert baf_obs == [], baf_obs

    # smelt_item missing_materials 2x without inventory change → blocked (req 3)
    _smelt_miss_fail = {
        "action": "smelt_item", "ok": 0,
        "args": {"input": "raw_iron"},
        "verifier": {"failure_type": "missing_materials", "failed_because": [{"kind": "inventory_item", "item": "raw_iron", "need": 1, "have": 0}]},
        "after_state": {"inventory_counts": {"coal": 10}},
    }
    _miss_summary = {"position": _iron_pos, "inventory_counts": {"coal": 10}}
    baf_miss = _blocked_action_families([_smelt_miss_fail, _smelt_miss_fail], _miss_summary)
    assert any(bf["family"] == "action:smelt_item" for bf in baf_miss), baf_miss
    miss_blocked = next(bf for bf in baf_miss if bf["family"] == "action:smelt_item")
    assert miss_blocked["failure_count"] == 2
    assert "missing_materials" in miss_blocked["last_failures"]

    # --- POSITION_MEANINGFUL_DELTA_BLOCKS constant ---
    assert POSITION_MEANINGFUL_DELTA_BLOCKS == 8, \
        f"default threshold must be 8 blocks, got {POSITION_MEANINGFUL_DELTA_BLOCKS}"

    # --- _is_timeout_tick helper ---
    _timeout_verifier_tick = {
        "action": "mine_iron_ore", "ok": 0,
        "error": "Block acquisition failed: timed out after 12000ms.",
        "verifier": {"failure_type": "resource_acquisition_failed",
                     "failed_because": [{"kind": "action_timeout", "action": "mine_iron_ore", "timeout_ms": 12000}]},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    _timeout_ft_tick = {
        "action": "explore_nearby", "ok": 0,
        "error": "Timed out after 15000ms.",
        "verifier": {"failure_type": "action_timeout", "failed_because": []},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    _non_timeout_tick = {
        "action": "mine_iron_ore", "ok": 0,
        "error": "block not found",
        "verifier": {"failure_type": "resource_acquisition_failed", "failed_because": []},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    assert _is_timeout_tick(_timeout_verifier_tick) is True, "action_timeout in failed_because must be detected"
    assert _is_timeout_tick(_timeout_ft_tick) is True, "action_timeout failure_type must be detected"
    assert _is_timeout_tick(_non_timeout_tick) is False, "non-timeout must not be flagged"
    _error_only_tick = dict(_non_timeout_tick, error="timed out after 10s",
                            verifier={"failure_type": "resource_acquisition_failed", "failed_because": []})
    assert _is_timeout_tick(_error_only_tick) is True, "timeout in error text must be detected"
    # partial_progress_timeout must NOT be treated as a hard timeout (bot made real progress)
    _partial_progress_tick = {
        "action": "mine_coal", "ok": 0,
        "error": "Block acquisition timed out.",
        "verifier": {
            "failure_type": "partial_progress_timeout",
            "failed_because": [{"kind": "partial_progress_timeout", "action": "mine_coal",
                                 "progress_signals": ["excavated_blocks:3"], "continuation_relevant": True}],
        },
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    assert _is_timeout_tick(_partial_progress_tick) is False, (
        "partial_progress_timeout must not count as a hard timeout tick for block purposes"
    )
    _partial_progress_ft_only_tick = dict(_partial_progress_tick,
                                          verifier={"failure_type": "partial_progress_timeout", "failed_because": []})
    assert _is_timeout_tick(_partial_progress_ft_only_tick) is False, (
        "partial_progress_timeout failure_type must not be a hard timeout"
    )
    _mined_no_drop_tick = {
        "action": "mine_coal", "ok": 0,
        "error": "Mined coal_ore but drop was not collected",
        "stop_reason": "mined_target_but_drop_not_collected",
        "verifier": {"failure_type": "partial_progress_timeout", "failed_because": [
            {"kind": "mined_target_but_drop_not_collected", "minedTargetBlocks": 1}
        ]},
        "args": {},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    assert _is_timeout_tick(_mined_no_drop_tick) is False, (
        "mined_target_but_drop_not_collected is progress, must not be a hard timeout"
    )
    _close_range_failed_tick = {
        "action": "mine_coal", "ok": 0,
        "stop_reason": "close_range_access_timeout",
        "verifier": {"failure_type": "close_range_access_failed", "failed_because": []},
        "args": {},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    assert _is_timeout_tick(_close_range_failed_tick) is False, (
        "close_range_access_failed must not be a hard timeout tick"
    )

    # --- _blocked_action_families: fast-block diagnostics fields ---
    # All existing blocks now carry expensive_action_family, blocked_created_tick, blocked_created_reason
    baf_existing = _blocked_action_families([_mine_iron_fail, _nav_iron_fail], _same_summary)
    assert len(baf_existing) == 1, baf_existing
    baf_rec = baf_existing[0]
    assert "expensive_action_family" in baf_rec, baf_rec
    assert "blocked_created_tick" in baf_rec, baf_rec
    assert "blocked_created_reason" in baf_rec, baf_rec
    # mine_iron_ore is expensive; navigate_to_block_type is expensive
    assert baf_rec["expensive_action_family"] is True, baf_rec
    # smelt_item is NOT expensive
    _smelt_not_expensive = _blocked_action_families([_smelt_fail, _smelt_fail], _smelt_summary)
    if _smelt_not_expensive:
        assert _smelt_not_expensive[0]["expensive_action_family"] is False, _smelt_not_expensive[0]

    # --- _blocked_action_families: fast-block triggers on 2 timeouts in 4 ticks ---
    _iron_timeout_tick = {
        "action": "mine_iron_ore", "ok": 0,
        "error": "Block acquisition failed: timed out after 12000ms.",
        "verifier": {
            "failure_type": "resource_acquisition_failed",
            "failed_because": [{"kind": "action_timeout", "action": "mine_iron_ore", "timeout_ms": 12000}],
        },
        "args": {},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    _same_pos_summary = {"position": _iron_pos, "inventory_counts": {}}

    # 2 timeouts at age 0 and 1 (within 4-tick fast window) → fast-blocked
    baf_fast = _blocked_action_families([_iron_timeout_tick, _iron_timeout_tick], _same_pos_summary)
    assert len(baf_fast) == 1, f"2 timeouts in 4 ticks must fast-block: {baf_fast}"
    fast_rec = baf_fast[0]
    assert fast_rec["family"] == "resource_acquisition:iron_ore", fast_rec
    assert fast_rec["blocked"] is True, fast_rec
    assert fast_rec["expensive_action_family"] is True, fast_rec
    assert "timeouts" in fast_rec["blocked_created_reason"], fast_rec
    assert isinstance(fast_rec["blocked_created_tick"], int), fast_rec

    # Single timeout → not fast-blocked (still below threshold)
    baf_one_timeout = _blocked_action_families([_iron_timeout_tick], _same_pos_summary)
    assert baf_one_timeout == [], f"single timeout must not fast-block: {baf_one_timeout}"

    # position moved exactly POSITION_MEANINGFUL_DELTA_BLOCKS → fast-block suppressed
    _moved_exact_summary = {
        "position": {"x": _iron_pos["x"] + POSITION_MEANINGFUL_DELTA_BLOCKS + 1, "y": _iron_pos["y"], "z": _iron_pos["z"]},
        "inventory_counts": {},
    }
    baf_moved_exact = _blocked_action_families([_iron_timeout_tick, _iron_timeout_tick], _moved_exact_summary)
    assert baf_moved_exact == [], f"move > threshold must suppress fast-block: {baf_moved_exact}"

    # position moved < threshold (7 blocks) → fast-block still active
    _moved_below_summary = {
        "position": {"x": _iron_pos["x"] + POSITION_MEANINGFUL_DELTA_BLOCKS - 1, "y": _iron_pos["y"], "z": _iron_pos["z"]},
        "inventory_counts": {},
    }
    baf_below = _blocked_action_families([_iron_timeout_tick, _iron_timeout_tick], _moved_below_summary)
    assert len(baf_below) == 1, f"move below threshold must keep fast-block: {baf_below}"

    # position changed > 8 blocks (well above threshold) → fast-block suppressed
    _moved_far_summary = {"position": {"x": 100, "y": 64, "z": 100}, "inventory_counts": {}}
    baf_moved = _blocked_action_families([_iron_timeout_tick, _iron_timeout_tick], _moved_far_summary)
    assert baf_moved == [], f"large position change must suppress fast-block: {baf_moved}"

    # 2 non-timeout failures at age 0,1 → not fast-blocked (no timeouts), falls to standard check
    # with 2 non-timeout failures same pos → standard block
    _iron_nontimeout = {
        "action": "mine_iron_ore", "ok": 0,
        "error": "block not found",
        "verifier": {"failure_type": "resource_acquisition_failed", "failed_because": []},
        "args": {},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    baf_standard = _blocked_action_families([_iron_nontimeout, _iron_nontimeout], _same_pos_summary)
    assert len(baf_standard) == 1, f"2 non-timeout failures must still standard-block: {baf_standard}"
    std_rec = baf_standard[0]
    assert "timeouts" not in std_rec["blocked_created_reason"], std_rec
    assert "_failures_" in std_rec["blocked_created_reason"], std_rec
    assert std_rec["expensive_action_family"] is True, std_rec

    # mine_coal timeout → expensive_action_family=True (different expensive action)
    _coal_timeout_tick = {
        "action": "mine_coal", "ok": 0,
        "error": "Block acquisition failed: timed out after 10000ms.",
        "verifier": {
            "failure_type": "resource_acquisition_failed",
            "failed_because": [{"kind": "action_timeout", "action": "mine_coal", "timeout_ms": 10000}],
        },
        "args": {},
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    baf_coal = _blocked_action_families([_coal_timeout_tick, _coal_timeout_tick], _same_pos_summary)
    assert len(baf_coal) == 1, f"2 mine_coal timeouts must fast-block: {baf_coal}"
    assert baf_coal[0]["expensive_action_family"] is True, baf_coal[0]
    assert baf_coal[0]["family"] == "resource_acquisition:coal", baf_coal[0]

    # fast-block triggered with 3 timeouts: blocked_created_reason reflects count
    baf_three = _blocked_action_families(
        [_iron_timeout_tick, _iron_timeout_tick, _iron_timeout_tick], _same_pos_summary
    )
    assert len(baf_three) == 1, baf_three
    assert "timeouts" in baf_three[0]["blocked_created_reason"], baf_three[0]

    # --- schema_blocked_family_key ---
    _smelt_inv_args_fb = [{"kind": "invalid_args", "action": "smelt_item", "missing_arg": "input"}]
    assert schema_blocked_family_key("smelt_item", _smelt_inv_args_fb) == "action_schema:smelt_item:missing_input"
    _nav_inv_args_fb = [{"kind": "invalid_args", "action": "navigate_to_block_type", "missing_arg": "targets"}]
    assert schema_blocked_family_key("navigate_to_block_type", _nav_inv_args_fb) == "action_schema:navigate_to_block_type:missing_targets"
    # No invalid_args entry → None
    assert schema_blocked_family_key("smelt_item", []) is None
    assert schema_blocked_family_key("smelt_item", [{"kind": "inventory_item", "item": "raw_iron"}]) is None
    # missing_arg not a string → None
    assert schema_blocked_family_key("smelt_item", [{"kind": "invalid_args", "missing_arg": 42}]) is None

    # --- _blocked_action_families: schema family detection ---
    _smelt_missing_input_tick = {
        "action": "smelt_item", "ok": 0,
        "args": {},
        "verifier": {
            "failure_type": "invalid_args",
            "failed_because": [{"kind": "invalid_args", "action": "smelt_item", "missing_arg": "input",
                                 "expected": "non-empty string"}],
        },
        "after_state": {"position": _iron_pos, "inventory_counts": {"coal": 5}},
    }
    _schema_summary = {"position": _iron_pos, "inventory_counts": {"coal": 5}}

    # Single invalid_args failure → schema family blocked immediately (threshold=1)
    baf_schema = _blocked_action_families([_smelt_missing_input_tick], _schema_summary)
    assert any(bf["family"] == "action_schema:smelt_item:missing_input" for bf in baf_schema), \
        f"schema family must appear after 1 failure: {baf_schema}"
    schema_rec = next(bf for bf in baf_schema if bf["family"] == "action_schema:smelt_item:missing_input")
    assert schema_rec["blocked"] is True
    assert schema_rec["repeatable_now"] is False
    assert schema_rec["expensive_action_family"] is False
    assert schema_rec["blocked_created_reason"] == "invalid_args_schema_violation"
    assert "input" in schema_rec["unblock_condition"]
    assert "smelt_item" in schema_rec["unblock_condition"]
    assert isinstance(schema_rec["failed_because"], list) and len(schema_rec["failed_because"]) > 0

    # Standard action:smelt_item family ALSO present when 2 failures
    baf_schema2 = _blocked_action_families([_smelt_missing_input_tick, _smelt_missing_input_tick], _schema_summary)
    assert any(bf["family"] == "action_schema:smelt_item:missing_input" for bf in baf_schema2)
    assert any(bf["family"] == "action:smelt_item" for bf in baf_schema2)

    # Successful smelt_item clears the schema family
    _smelt_success_tick = {
        "action": "smelt_item", "ok": 1,
        "args": {"input": "raw_iron", "count": 1},
        "verifier": {"failure_type": "none"},
        "after_state": {"position": _iron_pos, "inventory_counts": {"iron_ingot": 1}},
    }
    baf_schema_cleared = _blocked_action_families(
        [_smelt_success_tick, _smelt_missing_input_tick], _schema_summary
    )
    assert not any(bf["family"] == "action_schema:smelt_item:missing_input" for bf in baf_schema_cleared), \
        f"success must clear schema family: {baf_schema_cleared}"

    # navigate_to_block_type missing targets → schema family (action_family_key returns None for {})
    _nav_missing_targets_tick = {
        "action": "navigate_to_block_type", "ok": 0,
        "args": {},
        "verifier": {
            "failure_type": "invalid_args",
            "failed_because": [{"kind": "invalid_args", "action": "navigate_to_block_type",
                                 "missing_arg": "targets", "expected": "non-empty list"}],
        },
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    baf_nav_schema = _blocked_action_families([_nav_missing_targets_tick], _schema_summary)
    assert any(bf["family"] == "action_schema:navigate_to_block_type:missing_targets" for bf in baf_nav_schema), \
        f"missing targets schema family must be detected: {baf_nav_schema}"

    # scan_for_specific_block missing targets → schema family
    _scan_missing_targets_tick = {
        "action": "scan_for_specific_block", "ok": 0,
        "args": {},
        "verifier": {
            "failure_type": "invalid_args",
            "failed_because": [{"kind": "invalid_args", "action": "scan_for_specific_block",
                                 "missing_arg": "targets", "expected": "non-empty list"}],
        },
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    baf_scan_schema = _blocked_action_families([_scan_missing_targets_tick], _schema_summary)
    assert any(bf["family"] == "action_schema:scan_for_specific_block:missing_targets" for bf in baf_scan_schema), \
        f"scan schema family: {baf_scan_schema}"

    # acquire_blocks missing targets → schema family
    _acq_missing_targets_tick = {
        "action": "acquire_blocks", "ok": 0,
        "args": {},
        "verifier": {
            "failure_type": "invalid_args",
            "failed_because": [{"kind": "invalid_args", "action": "acquire_blocks",
                                 "missing_arg": "targets", "expected": "non-empty list"}],
        },
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    baf_acq_schema = _blocked_action_families([_acq_missing_targets_tick], _schema_summary)
    assert any(bf["family"] == "action_schema:acquire_blocks:missing_targets" for bf in baf_acq_schema), \
        f"acquire_blocks schema family: {baf_acq_schema}"

    # missing_materials failure does NOT create a schema family
    _smelt_miss_mat_tick = {
        "action": "smelt_item", "ok": 0,
        "args": {"input": "raw_iron"},
        "verifier": {
            "failure_type": "missing_materials",
            "failed_because": [{"kind": "inventory_item", "item": "raw_iron", "need": 1, "have": 0}],
        },
        "after_state": {"position": _iron_pos, "inventory_counts": {}},
    }
    baf_miss_mat = _blocked_action_families([_smelt_miss_mat_tick], _schema_summary)
    assert not any(bf["family"].startswith("action_schema:smelt_item:") for bf in baf_miss_mat), \
        f"missing_materials must not create schema family: {baf_miss_mat}"

    # --- find_blocked_family: schema family pre-execution skip ---
    _fbf_schema_summary = {"position": _iron_pos, "inventory_counts": {"coal": 5}}

    # smelt_item {} → blocked (input missing)
    fbf_schema = find_blocked_family("smelt_item", {}, [_smelt_missing_input_tick], _fbf_schema_summary)
    assert fbf_schema is not None, "smelt_item {} must be blocked by schema"
    assert fbf_schema["family"] == "action_schema:smelt_item:missing_input", fbf_schema
    assert fbf_schema["repeatable_now"] is False
    assert "input" in fbf_schema["unblock_condition"]

    # smelt_item {"input": "raw_iron"} → NOT blocked (arg provided)
    fbf_schema_ok = find_blocked_family(
        "smelt_item", {"input": "raw_iron"}, [_smelt_missing_input_tick], _fbf_schema_summary
    )
    assert fbf_schema_ok is None, "providing input must unblock schema family"

    # smelt_item {"input": ""} → still blocked (empty string = still missing)
    fbf_schema_empty = find_blocked_family(
        "smelt_item", {"input": ""}, [_smelt_missing_input_tick], _fbf_schema_summary
    )
    assert fbf_schema_empty is not None, "empty string for input must remain blocked"

    # navigate_to_block_type {} → blocked even though action_family_key returns None
    fbf_nav_schema = find_blocked_family(
        "navigate_to_block_type", {}, [_nav_missing_targets_tick], _fbf_schema_summary
    )
    assert fbf_nav_schema is not None, "navigate_to_block_type {} must be blocked"
    assert fbf_nav_schema["family"] == "action_schema:navigate_to_block_type:missing_targets"

    # navigate_to_block_type {"targets": ["iron_ore"]} → NOT blocked
    fbf_nav_ok = find_blocked_family(
        "navigate_to_block_type", {"targets": ["iron_ore"]}, [_nav_missing_targets_tick], _fbf_schema_summary
    )
    assert fbf_nav_ok is None, "providing targets must unblock"

    # navigate_to_block_type {"targets": []} → still blocked (empty list)
    fbf_nav_empty = find_blocked_family(
        "navigate_to_block_type", {"targets": []}, [_nav_missing_targets_tick], _fbf_schema_summary
    )
    assert fbf_nav_empty is not None, "empty targets list must remain blocked"

    # unrelated action → not blocked by schema family
    fbf_unrelated = find_blocked_family(
        "mine_iron_ore", {}, [_smelt_missing_input_tick], _fbf_schema_summary
    )
    assert fbf_unrelated is None, "mine_iron_ore not affected by smelt_item schema block"

    # --- find_blocked_family: pre-execution skip logic ---
    # Two mine_iron_ore failures → find_blocked_family returns blocked record
    fbf = find_blocked_family("mine_iron_ore", {}, [_mine_iron_fail, _nav_iron_fail], _same_summary)
    assert fbf is not None, "mine_iron_ore should be blocked after 2 failures"
    assert fbf["family"] == "resource_acquisition:iron_ore", fbf
    assert fbf["blocked"] is True
    assert fbf["repeatable_now"] is False
    assert "unblock_condition" in fbf

    # navigate_to_block_type iron_ore is also blocked (same resource family)
    fbf_nav = find_blocked_family(
        "navigate_to_block_type", {"targets": ["iron_ore"]}, [_mine_iron_fail, _nav_iron_fail], _same_summary
    )
    assert fbf_nav is not None, "navigate_to_block_type iron_ore should share the blocked family"
    assert fbf_nav["family"] == "resource_acquisition:iron_ore"

    # acquire_blocks iron_ore is also blocked
    fbf_acq = find_blocked_family(
        "acquire_blocks", {"targets": ["iron_ore"]}, [_mine_iron_fail, _nav_iron_fail], _same_summary
    )
    assert fbf_acq is not None, "acquire_blocks iron_ore should share the blocked family"

    # After position changes > 8 blocks → find_blocked_family returns None (unblocked)
    _explore_moved_summary = {"position": {"x": 60, "y": 64, "z": 60}, "inventory_counts": {}}
    fbf_moved = find_blocked_family("mine_iron_ore", {}, [_mine_iron_fail, _nav_iron_fail], _explore_moved_summary)
    assert fbf_moved is None, "mine_iron_ore should be unblocked after position changes"

    # Single failure → below threshold → not blocked
    fbf_once = find_blocked_family("mine_iron_ore", {}, [_mine_iron_fail], _same_summary)
    assert fbf_once is None, "single failure should not trigger block"

    # Observation action → None (never blocked)
    fbf_obs = find_blocked_family("status", {}, [_mine_iron_fail, _mine_iron_fail], _same_summary)
    assert fbf_obs is None, "observation actions must never be blocked"

    # Unrelated action (coal mining) → None
    _coal_fail = dict(_mine_iron_fail, action="mine_coal_ore")
    fbf_coal = find_blocked_family("mine_iron_ore", {}, [_coal_fail, _coal_fail], _same_summary)
    assert fbf_coal is None, "mine_iron_ore should not be blocked by mine_coal_ore failures"

    # item_affordances uses SMELT_INPUTS — raw_beef should appear, sand should not
    from vtuber_ai.game_brain import _item_affordances
    ia_smeltable = _item_affordances({
        "inventory_counts": {"raw_beef": 2, "sand": 5, "coal": 10},
    })
    assert ia_smeltable["has_smeltable_items"] is True, ia_smeltable
    assert "raw_beef" in ia_smeltable["smeltable_items"], ia_smeltable  # in SMELT_INPUTS
    assert "sand" not in ia_smeltable["smeltable_items"], ia_smeltable  # NOT in SMELT_INPUTS
    assert ia_smeltable["has_fuel"] is True, ia_smeltable
    assert "coal" in ia_smeltable["fuel_items"], ia_smeltable

    # item_affordances keys always present even with empty inventory
    ia_empty = _item_affordances({"inventory_counts": {}})
    assert ia_empty["has_smeltable_items"] is False
    assert ia_empty["smeltable_items"] == {}
    assert ia_empty["has_fuel"] is False
    assert ia_empty["fuel_items"] == {}

    # build_llm_state_packet includes blocked_action_families
    iron_fail_state = state(
        {"ok": True, "health": 20, "food": 20, "inventory_counts": {}, "nearby_blocks": {}},
        recent_ticks=[_mine_iron_fail, _nav_iron_fail],
    )
    iron_packet = build_llm_state_packet(
        status=iron_fail_state,
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="mine iron",
    )
    assert "blocked_action_families" in iron_packet
    assert isinstance(iron_packet["blocked_action_families"], list)

    # --- build_llm_state_packet includes all new affordance fields ---
    affordance_summary = {
        "ok": True, "health": 20, "food": 20,
        "inventory_counts": {"furnace": 1, "raw_iron": 1, "coal": 35, "stone_pickaxe": 7},
        "nearby_blocks": {},  # furnace not placed
        "nearby_entities": [],
    }
    aff_packet = build_llm_state_packet(
        status=state(affordance_summary, recent_ticks=[nav_fail_tick, nav_fail_tick]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="smelt iron",
    )
    assert "station_affordances" in aff_packet
    assert "item_affordances" in aff_packet
    assert "inventory_efficiency" in aff_packet
    assert "navigation_stall" in aff_packet
    # furnace gap
    aff_sa = aff_packet["station_affordances"]
    assert any(gf["station"] == "furnace" for gf in aff_sa["station_gap_facts"])
    # smeltable + fuel
    aff_ia = aff_packet["item_affordances"]
    assert aff_ia["has_smeltable_items"] is True
    assert aff_ia["has_fuel"] is True
    # duplicate tools
    aff_eff = aff_packet["inventory_efficiency"]
    assert aff_eff["duplicate_tools"].get("stone_pickaxe") == 7
    # nav stall from ticks
    aff_ns = aff_packet["navigation_stall"]
    assert aff_ns is not None
    assert aff_ns["recent_navigation_failures"] == 2

    # --- progress_monitor includes repeated_sensing_count and last_meaningful_change ---
    pm = aff_packet["progress_monitor"]
    assert "repeated_sensing_count" in pm
    assert "last_meaningful_change" in pm  # may be None if no meaningful changes

    # --- explore_nearby action_timeout: position-aware verifier feedback ---
    _explore_req = _make_req("explore_nearby")
    _timeout_err = "Timed out explore_nearby after 15000ms."
    _timeout_result = {
        "failure_type": "action_timeout",
        "stop_reason": "action_timeout",
        "repeatable_now": True,
        "can_retry": True,
        "failed_because": [{"kind": "action_timeout", "action": "explore_nearby", "timeout_ms": 15000}],
        "diagnostics": {"timeout_ms": 15000},
    }

    _pos_before = {"inventory_counts": {}, "nearby_blocks": {}, "health": 20, "food": 20,
                   "position": {"x": 0, "y": 64, "z": 0}}
    _pos_same   = {"inventory_counts": {}, "nearby_blocks": {}, "health": 20, "food": 20,
                   "position": {"x": 0, "y": 64, "z": 0}}
    _pos_moved  = {"inventory_counts": {}, "nearby_blocks": {}, "health": 20, "food": 20,
                   "position": {"x": 10, "y": 64, "z": 0}}
    _pos_moved_nearby = {"inventory_counts": {}, "nearby_blocks": {},
                         "nearbyBlockCounts": {"stone": 4, "coal_ore": 1},
                         "health": 20, "food": 20,
                         "position": {"x": 10, "y": 64, "z": 0}}

    # No position change → navigation_failed, repeatable_now=False
    v_no_move = verify_action(
        _pos_before, _pos_same,
        _explore_req,
        _make_res(False, _timeout_err, _timeout_result),
    )
    assert v_no_move["failure_type"] == "navigation_failed", \
        f"expected navigation_failed, got {v_no_move['failure_type']}"
    assert v_no_move["repeatable_now"] is False, \
        f"expected repeatable_now=False, got {v_no_move.get('repeatable_now')}"
    assert v_no_move["partial_success"] is False, \
        f"expected partial_success=False"
    _fb = v_no_move.get("failed_because") or []
    assert any(f.get("kind") == "action_timeout" for f in _fb), \
        f"failed_because missing action_timeout entry: {_fb}"
    _at_entry = next(f for f in _fb if f.get("kind") == "action_timeout")
    assert _at_entry["action"] == "explore_nearby"
    assert _at_entry["timeout_ms"] == 15000
    assert _at_entry["position_changed"] is False
    assert _at_entry["distance_moved"] == 0.0
    assert _at_entry["recoverable"] is True
    assert v_no_move["failure_type"] != "bridge_error", "must NOT be bridge_error"
    assert v_no_move["failure_type"] != "action_timeout", "must be reclassified from action_timeout"
    _rs_no_move = v_no_move.get("relevant_state") or {}
    assert "position" in _rs_no_move, "relevant_state must include position"
    assert v_no_move.get("repeat_condition") is not None

    # With position change → partial_progress, repeatable_now=True, partial_success=True
    v_moved = verify_action(
        _pos_before, _pos_moved,
        _explore_req,
        _make_res(False, _timeout_err, _timeout_result),
    )
    assert v_moved["failure_type"] == "partial_progress", \
        f"expected partial_progress, got {v_moved['failure_type']}"
    assert v_moved["repeatable_now"] is True, \
        f"expected repeatable_now=True, got {v_moved.get('repeatable_now')}"
    assert v_moved["partial_success"] is True
    _fb_moved = v_moved.get("failed_because") or []
    _at_moved = next((f for f in _fb_moved if f.get("kind") == "action_timeout"), None)
    assert _at_moved is not None
    assert _at_moved["position_changed"] is True
    assert _at_moved["distance_moved"] > 0, f"expected distance_moved > 0, got {_at_moved.get('distance_moved')}"
    assert _at_moved["recoverable"] is True

    # relevant_state includes nearbyBlockCounts when present
    v_nearby = verify_action(
        _pos_before, _pos_moved_nearby,
        _explore_req,
        _make_res(False, _timeout_err, _timeout_result),
    )
    _rs_nearby = v_nearby.get("relevant_state") or {}
    assert "nearbyBlockCounts" in _rs_nearby, "relevant_state must include nearbyBlockCounts when available"
    assert _rs_nearby["nearbyBlockCounts"].get("coal_ore") == 1

    # Error without MS number — still produces action_timeout entry (no timeout_ms)
    v_no_ms = verify_action(
        _pos_before, _pos_same,
        _explore_req,
        _make_res(False, "Timed out explore_nearby.", {"failure_type": "action_timeout", "failed_because": []}),
    )
    _fb_no_ms = v_no_ms.get("failed_because") or []
    assert any(f.get("kind") == "action_timeout" for f in _fb_no_ms)
    _at_no_ms = next(f for f in _fb_no_ms if f.get("kind") == "action_timeout")
    assert "timeout_ms" not in _at_no_ms or _at_no_ms["timeout_ms"] is None

    # Exploration path failure (not action_timeout) still goes through nav path unchanged
    v_path_fail = verify_action(
        _pos_before, _pos_same,
        _explore_req,
        _make_res(False, "Exploration path failed: no safe path.", {}),
    )
    assert v_path_fail["failure_type"] in {"navigation_failed", "no_progress"}, \
        f"path failure should remain nav/no_progress: {v_path_fail['failure_type']}"

    # --- _repeated_failed_action_family: smelt_item repeated invalid args ---
    def _smelt_fail(error: str, failure_type: str, failed_because: list | None = None, inv: dict | None = None) -> dict:
        state_snap = {"inventory_counts": inv or {}}
        return {
            "action": "smelt_item",
            "ok": 0,
            "error": error,
            "result": {"failure_type": failure_type},
            "verifier": {"failure_type": failure_type, "failed_because": failed_because or []},
            "before_state": state_snap,
            "after_state": state_snap,
        }

    smelt_ticks = [
        _smelt_fail("Missing raw_iron", "missing_materials", [{"kind": "inventory_item", "item": "raw_iron", "need": 1, "have": 0}]),
        _smelt_fail("invalid input: cobblestone", "invalid_action_args"),
        _smelt_fail("invalid input: cobblestone", "invalid_action_args"),
        _smelt_fail("missing input arg", "invalid_action_args"),
    ]
    current_inv_empty = {}
    rfaf = _repeated_failed_action_family(smelt_ticks, {"inventory_counts": current_inv_empty})
    assert rfaf is not None, "must detect repeated smelt_item failures"
    assert rfaf["active"] is True
    assert rfaf["action"] == "smelt_item"
    assert rfaf["count"] == 4
    assert isinstance(rfaf["failure_types"], list) and len(rfaf["failure_types"]) > 0
    assert rfaf["state_changed_since_first_failure"] is False  # inventory unchanged
    assert isinstance(rfaf["last_failed_because"], list)
    assert "lesson" in rfaf
    assert "repeatedly" in rfaf["lesson"]

    # state changed between first failure and now → state_changed_since_first_failure=True
    rfaf_changed = _repeated_failed_action_family(smelt_ticks, {"inventory_counts": {"raw_iron": 2}})
    assert rfaf_changed is not None
    assert rfaf_changed["state_changed_since_first_failure"] is True

    # successful state-changing action interspersed resets the window — no loop in last 5 ticks
    craft_ok_tick = {
        "action": "craft_sticks", "ok": 1, "error": None,
        "result": {}, "verifier": {"failure_type": "none"},
        "before_state": {}, "after_state": {},
    }
    ticks_with_success = [craft_ok_tick] + smelt_ticks[:2]  # only 2 smelt fails in short window
    rfaf_cleared = _repeated_failed_action_family(ticks_with_success, {"inventory_counts": {}})
    # only 2 smelt_item fails AND they are not in the 3+ related category → active
    # 2 in short window (indices 1 and 2) → SHORT_THRESHOLD=2 is met → still active
    assert rfaf_cleared is not None
    assert rfaf_cleared["action"] == "smelt_item"
    # But 1 smelt fail only after clearing → not active
    rfaf_one = _repeated_failed_action_family([craft_ok_tick, smelt_ticks[0]], {"inventory_counts": {}})
    assert rfaf_one is None, "single smelt failure after success must not trigger loop"

    # observation actions never trigger repeated_failed_action_family
    status_fail_ticks = [{"action": "status", "ok": 0, "error": "x", "result": {}, "verifier": {"failure_type": "bridge_error"}, "before_state": {}, "after_state": {}} for _ in range(4)]
    assert _repeated_failed_action_family(status_fail_ticks, {}) is None

    # different actions each failing once → no loop
    different_fails = [
        {"action": "mine_coal", "ok": 0, "error": "x", "result": {}, "verifier": {"failure_type": "no_progress"}, "before_state": {}, "after_state": {}},
        {"action": "mine_iron_ore", "ok": 0, "error": "x", "result": {}, "verifier": {"failure_type": "no_progress"}, "before_state": {}, "after_state": {}},
    ]
    assert _repeated_failed_action_family(different_fails, {}) is None

    # build_llm_state_packet exposes repeated_failed_action_loop when smelt_item loops
    smelt_loop_state = state(
        {"ok": True, "health": 20, "food": 20, "inventory_counts": {}, "nearby_blocks": {}, "nearby_entities": []},
        recent_ticks=smelt_ticks,
    )
    smelt_packet = build_llm_state_packet(
        status=smelt_loop_state,
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="smelt iron",
    )
    pkt_rfal = smelt_packet.get("repeated_failed_action_loop")
    assert pkt_rfal is not None, "repeated_failed_action_loop must be present in LLM packet"
    assert pkt_rfal["active"] is True
    assert pkt_rfal["action"] == "smelt_item"

    # planner diagnostics expose the new sub-fields
    server, base_url = start_stub()
    old_env = {"VTUBER_LLM_BASE_URL": os.environ.get("VTUBER_LLM_BASE_URL")}
    os.environ["VTUBER_LLM_BASE_URL"] = base_url
    try:
        _, smelt_info = choose_next_action(smelt_loop_state, [], "smelt iron", AUTONOMOUS_ALLOWED_ACTIONS, "llm")
        assert "repeated_failed_action_loop" in smelt_info
        assert smelt_info.get("repeated_failed_action_name") == "smelt_item"
        assert isinstance(smelt_info.get("repeated_failed_action_count"), int) and smelt_info["repeated_failed_action_count"] == 4
        assert smelt_info.get("repeated_failed_state_changed") is False
    finally:
        restore_env(old_env)
        server.shutdown()

    # --- no possible_next_actions in LLM prompt when VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM=0 ---
    # (already verified earlier via torch_packet assertion; confirming default env behaviour)
    assert os.environ.get("VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM", "0") != "1", \
        "env var must default to 0 in test environment"

    # --- _recent_completed_intents_from_ticks: mine_coal success gets resource_family + inventory_delta ---
    _coal_pos = {"x": 5, "y": 60, "z": 5}
    _mine_coal_ok_tick = {
        "action": "mine_coal",
        "ok": 1,
        "args": {},
        "result": {},
        "verifier": {"failure_type": "none"},
        "before_state": {"position": _coal_pos, "inventory_counts": {"coal": 2}},
        "after_state": {"position": _coal_pos, "inventory_counts": {"coal": 7}},
    }
    rci_coal = _recent_completed_intents_from_ticks([_mine_coal_ok_tick])
    assert len(rci_coal) == 1, rci_coal
    assert rci_coal[0]["action"] == "mine_coal", rci_coal[0]
    assert rci_coal[0]["result"] == "succeeded", rci_coal[0]
    assert rci_coal[0].get("resource_family") == "coal", rci_coal[0]
    assert "inventory_delta" in rci_coal[0], rci_coal[0]
    assert rci_coal[0]["inventory_delta"].get("coal") == 5, rci_coal[0]

    # --- _recent_resource_successes_from_ticks: mine_coal success produces entry ---
    _coal_summary = {"position": _coal_pos, "inventory_counts": {"coal": 7}}
    rrs = _recent_resource_successes_from_ticks([_mine_coal_ok_tick], _coal_summary)
    assert "coal" in rrs, rrs
    assert rrs["coal"]["action"] == "mine_coal", rrs["coal"]
    assert rrs["coal"]["ticks_ago"] == 0, rrs["coal"]
    assert rrs["coal"]["inventory_count"] == 7, rrs["coal"]
    assert "fact" in rrs["coal"], rrs["coal"]

    # most-recent (lowest age) wins when multiple successes for same family
    _mine_coal_older_tick = dict(_mine_coal_ok_tick, before_state={"inventory_counts": {"coal": 0}},
                                 after_state={"inventory_counts": {"coal": 2}})
    rrs_two = _recent_resource_successes_from_ticks([_mine_coal_ok_tick, _mine_coal_older_tick], _coal_summary)
    assert rrs_two["coal"]["ticks_ago"] == 0, "most recent must win"
    assert rrs_two["coal"]["inventory_count"] == 7, "most recent after_state used"

    # no success ticks → empty
    _coal_fail_tick = dict(_mine_coal_ok_tick, ok=0)
    rrs_empty = _recent_resource_successes_from_ticks([_coal_fail_tick], _coal_summary)
    assert rrs_empty == {}, rrs_empty

    # observation action → not included
    rrs_obs = _recent_resource_successes_from_ticks([_status_ok_tick], _coal_summary)
    assert rrs_obs == {}, rrs_obs

    # --- _resource_sufficiency: coal ≥ 8 → sufficient_for_basic_needs=True ---
    rs_enough = _resource_sufficiency({"inventory_counts": {"coal": 8}})
    assert "coal" in rs_enough, rs_enough
    assert rs_enough["coal"]["count"] == 8, rs_enough
    assert rs_enough["coal"]["sufficient_for_basic_needs"] is True, rs_enough

    rs_low = _resource_sufficiency({"inventory_counts": {"coal": 3}})
    assert "coal" in rs_low, rs_low
    assert rs_low["coal"]["sufficient_for_basic_needs"] is False, rs_low

    # coal=0 → not included
    rs_none = _resource_sufficiency({"inventory_counts": {"coal": 0}})
    assert "coal" not in rs_none, rs_none

    # raw_iron threshold=3: exactly 3 → sufficient
    rs_iron = _resource_sufficiency({"inventory_counts": {"raw_iron": 3}})
    assert rs_iron["raw_iron"]["sufficient_for_basic_needs"] is True, rs_iron

    # empty inventory → empty dict
    assert _resource_sufficiency({"inventory_counts": {}}) == {}, "empty inventory must give empty result"

    # --- _blocked_action_families: mine_coal success clears resource_acquisition:coal block ---
    _coal_fail_tick_baf = {
        "action": "mine_coal", "ok": 0,
        "args": {},
        "verifier": {"failure_type": "resource_acquisition_failed", "failed_because": [
            {"kind": "accessible_block", "block": "coal_ore", "accessible": False}
        ]},
        "after_state": {"position": _coal_pos, "inventory_counts": {}},
    }
    _mine_coal_ok_baf = {
        "action": "mine_coal", "ok": 1,
        "args": {},
        "verifier": {"failure_type": "none"},
        "after_state": {"position": _coal_pos, "inventory_counts": {"coal": 5}},
    }
    _coal_baf_summary = {"position": _coal_pos, "inventory_counts": {"coal": 5}}

    # two failures alone → blocked
    baf_coal_blocked = _blocked_action_families([_coal_fail_tick_baf, _coal_fail_tick_baf], _coal_baf_summary)
    # inventory changed already clears it; use empty summary to test pure success-clearing
    _coal_empty_summary = {"position": _coal_pos, "inventory_counts": {}}
    baf_coal_blocked2 = _blocked_action_families([_coal_fail_tick_baf, _coal_fail_tick_baf], _coal_empty_summary)
    assert any(bf["family"] == "resource_acquisition:coal" for bf in baf_coal_blocked2), \
        f"two coal failures must block: {baf_coal_blocked2}"

    # success followed by failures → not blocked (success clears the family)
    baf_coal_cleared = _blocked_action_families(
        [_coal_fail_tick_baf, _coal_fail_tick_baf, _mine_coal_ok_baf], _coal_empty_summary
    )
    assert not any(bf["family"] == "resource_acquisition:coal" for bf in baf_coal_cleared), \
        f"mine_coal success must clear resource_acquisition:coal block: {baf_coal_cleared}"

    # partial progress should continue/clear, not strengthen a resource block
    _coal_partial_mined_baf = {
        "action": "mine_coal", "ok": 0,
        "args": {},
        "result": {
            "failure_type": "partial_progress_timeout",
            "stop_reason": "mined_target_but_drop_not_collected",
            "partial_success": True,
            "minedTargetBlocks": 1,
        },
        "verifier": {
            "failure_type": "partial_progress_timeout",
            "diagnostics": {"continuation_relevant": True, "minedTargetBlocks": 1},
            "failed_because": [{"kind": "partial_progress_timeout", "minedTargetBlocks": 1}],
        },
        "after_state": {"position": _coal_pos, "inventory_counts": {}},
    }
    _coal_partial_drop_baf = {
        "action": "mine_coal", "ok": 0,
        "args": {},
        "result": {
            "failure_type": "partial_progress_timeout",
            "stop_reason": "drop_collection_partial_progress",
            "partial_success": True,
            "dropDistanceImproved": True,
        },
        "verifier": {
            "failure_type": "partial_progress_timeout",
            "diagnostics": {"continuation_relevant": True, "dropDistanceImproved": True},
            "failed_because": [{"kind": "drop_collection_failed", "dropDistanceImproved": True}],
        },
        "after_state": {"position": _coal_pos, "inventory_counts": {}},
    }
    baf_partial_mined = _blocked_action_families([_coal_partial_mined_baf, _coal_fail_tick_baf], _coal_empty_summary)
    assert not any(bf["family"] == "resource_acquisition:coal" for bf in baf_partial_mined), \
        f"partial mined target must not block coal family: {baf_partial_mined}"
    baf_partial_drop = _blocked_action_families([_coal_partial_drop_baf, _coal_fail_tick_baf], _coal_empty_summary)
    assert not any(bf["family"] == "resource_acquisition:coal" for bf in baf_partial_drop), \
        f"drop_collection_partial_progress must not block coal family: {baf_partial_drop}"
    baf_partial_clears_old = _blocked_action_families(
        [_coal_partial_mined_baf, _coal_fail_tick_baf, _coal_fail_tick_baf],
        _coal_empty_summary,
    )
    assert not any(bf["family"] == "resource_acquisition:coal" for bf in baf_partial_clears_old), \
        f"new partial progress must clear older coal block: {baf_partial_clears_old}"
    fbf_partial = find_blocked_family(
        "mine_coal", {}, [_coal_partial_mined_baf, _coal_fail_tick_baf, _coal_fail_tick_baf], _coal_empty_summary
    )
    assert fbf_partial is None, f"partial-progress mine_coal must not be pre-execution blocked: {fbf_partial}"

    # --- recent_resource_successes + resource_sufficiency appear in build_llm_state_packet ---
    coal_ok_state = state(
        {"ok": True, "health": 20, "food": 20, "inventory_counts": {"coal": 10}, "nearby_blocks": {}},
        recent_ticks=[_mine_coal_ok_tick],
    )
    coal_packet = build_llm_state_packet(
        status=coal_ok_state,
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="gather resources",
    )
    assert "recent_resource_successes" in coal_packet, "recent_resource_successes must be in LLM packet"
    assert "coal" in coal_packet["recent_resource_successes"], coal_packet["recent_resource_successes"]
    assert "resource_sufficiency" in coal_packet, "resource_sufficiency must be in LLM packet"
    assert "coal" in coal_packet["resource_sufficiency"], coal_packet["resource_sufficiency"]
    assert coal_packet["resource_sufficiency"]["coal"]["sufficient_for_basic_needs"] is True
    partial_continuation_state = state(
        {"ok": True, "health": 20, "food": 20, "inventory_counts": {}, "nearby_blocks": {}},
        recent_ticks=[_coal_partial_mined_baf],
    )
    partial_continuation_packet = build_llm_state_packet(
        status=partial_continuation_state,
        recent_memory=[],
        last_result=_coal_partial_mined_baf,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="gather coal",
    )
    continuation_facts = partial_continuation_packet.get("continuation_facts") or []
    assert any(cf.get("continuation_family") == "resource_acquisition:coal" for cf in continuation_facts), (
        f"partial progress must create continuation fact: {continuation_facts}"
    )

    # --- suggested_next_action suppression in LLM state packet ---
    _pna_status = {
        "ok": True, "health": 20, "food": 20, "inventory_counts": {"wooden_pickaxe": 1},
        "nearby_blocks": {}, "hostile_nearby": False,
        "position": {"x": 0, "y": 64, "z": 0},
    }
    _nav_fail_result = {
        "action": "mine_coal",
        "ok": False,
        "error": "Navigation path failed.",
        "result": {
            "failure_type": "navigation_failed",
            "stop_reason": "path_timeout_before_target",
            "suggested_next_action": "navigate_to_block_type",
            "possible_next_actions": ["navigate_to_block_type", "look_around"],
            "can_retry": True,
        },
        "verifier": {
            "failure_type": "navigation_failed",
            "suggested_next_action": "navigate_to_block_type",
            "recommendation": "Try a different path.",
        },
    }
    _nav_pkt = build_llm_state_packet(
        status=_pna_status, recent_memory=[], last_result=_nav_fail_result,
        bridge_actions=("status", "mine_coal", "navigate_to_block_type"), mission="survive",
    )
    # By default (env var=0): suggested_next_action must not appear in last_action_result or last_failure_summary
    _lar = _nav_pkt.get("last_action_result") or {}
    _lfs = _nav_pkt.get("last_failure_summary") or {}
    assert "suggested_next_action" not in _lar, f"suggested_next_action must be suppressed by default: {_lar}"
    assert "possible_next_actions" not in _lar, f"possible_next_actions must be suppressed by default: {_lar}"
    assert "suggested_next_action" not in _lfs, f"suggested_next_action must be suppressed in failure_summary: {_lfs}"

    # With env var=1: suggested_next_action should appear in last_action_result
    _old_env = os.environ.get("VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM")
    os.environ["VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM"] = "1"
    try:
        _nav_pkt_show = build_llm_state_packet(
            status=_pna_status, recent_memory=[], last_result=_nav_fail_result,
            bridge_actions=("status", "mine_coal", "navigate_to_block_type"), mission="survive",
        )
    finally:
        if _old_env is None:
            os.environ.pop("VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM", None)
        else:
            os.environ["VTUBER_SHOW_POSSIBLE_NEXT_ACTIONS_TO_LLM"] = _old_env
    _lar_show = _nav_pkt_show.get("last_action_result") or {}
    assert _lar_show.get("suggested_next_action") == "navigate_to_block_type", (
        f"suggested_next_action should appear when env var=1: {_lar_show}"
    )

    # partial_progress_timeout: factual fields appear in failure_summary; no suggested_next_action
    _partial_result = {
        "action": "mine_coal",
        "ok": False,
        "error": "Block acquisition timed out.",
        "result": {
            "failure_type": "partial_progress_timeout",
            "stop_reason": "path_timeout_after_progress",
            "partial_success": True,
            "suggested_next_action": "mine_coal",  # must be stripped
            "can_retry": True,
            "failed_because": [{
                "kind": "partial_progress_timeout",
                "action": "mine_coal",
                "stop_reason": "path_timeout_before_target",
                "progress_signals": {"excavatedBlocks": 1, "inventory_delta": {"dirt": -1}},
                "continuation_relevant": True,
            }],
        },
        "verifier": {
            "failure_type": "partial_progress_timeout",
            "suggested_next_action": None,
            "repeatable_now": True,
            "diagnostics": {"continuation_relevant": True, "progress_made": True, "excavatedBlocks": 1, "inventory_delta": {"dirt": -1}},
            "recommendation": "Partial progress means continuing may be reasonable, but you may choose any valid action.",
        },
    }
    _partial_pkt = build_llm_state_packet(
        status=_pna_status, recent_memory=[], last_result=_partial_result,
        bridge_actions=("status", "mine_coal"), mission="survive",
    )
    _partial_lfs = _partial_pkt.get("last_failure_summary") or {}
    assert _partial_lfs.get("failure_type") == "partial_progress_timeout", _partial_lfs
    assert _partial_lfs.get("partial_success") is True, f"partial_success must be in failure_summary: {_partial_lfs}"
    assert "suggested_next_action" not in _partial_lfs, (
        f"suggested_next_action must not appear for partial_progress_timeout: {_partial_lfs}"
    )
    _partial_lar = _partial_pkt.get("last_action_result") or {}
    assert "suggested_next_action" not in _partial_lar, (
        f"suggested_next_action must be stripped from last_action_result for partial_progress_timeout: {_partial_lar}"
    )

    # -------------------------------------------------------------------------
    # blocked_action_families: partial progress must not block resource acquisition
    # -------------------------------------------------------------------------
    from vtuber_ai.game_brain import _blocked_action_families

    _bare_pos = {"x": 10, "y": 60, "z": 10}
    _coal_summary = {
        "ok": True, "health": 20, "food": 20,
        "position": _bare_pos,
        "inventory_counts": {},
        "dimension": "overworld",
    }

    def _make_partial_progress_coal_tick(age_pos_offset: int = 0) -> dict:
        """Tick matching the exact scenario from the bug report."""
        return {
            "action": "mine_coal",
            "ok": 0,
            "error": "Block acquisition timed out.",
            "result": {
                "failure_type": "partial_progress_timeout",
                "partial_success": True,
                "minedTargetBlocks": 1,
                "dropDistanceImproved": True,
                "botPositionChanged": True,
                "continuation_relevant": True,
                "stop_reason": "drop_collection_partial_progress",
                "failed_because": [{
                    "kind": "partial_progress_timeout",
                    "action": "mine_coal",
                    "continuation_relevant": True,
                    "minedTargetBlocks": 1,
                    "dropDistanceImproved": True,
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": True,
                "partial_success": True,
                "diagnostics": {
                    "continuation_relevant": True,
                    "minedTargetBlocks": 1,
                    "dropDistanceImproved": True,
                },
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {
                "inventory_counts": {},
                "position": {"x": 10 + age_pos_offset, "y": 60, "z": 10},
            },
        }

    def _make_pure_timeout_coal_tick() -> dict:
        """No-progress mine_coal action_timeout tick."""
        return {
            "action": "mine_coal",
            "ok": 0,
            "error": "Block acquisition failed: timed out after 60000ms.",
            "result": {"failure_type": "action_timeout"},
            "verifier": {
                "failure_type": "resource_acquisition_failed",
                "repeatable_now": False,
                "failed_because": [{"kind": "action_timeout", "action": "mine_coal", "timeout_ms": 60000}],
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    # --- Test A: two partial_progress_timeout mine_coal ticks → NO block ---
    _ticks_a = [_make_partial_progress_coal_tick(), _make_partial_progress_coal_tick()]
    _blocked_a = _blocked_action_families(_ticks_a, _coal_summary)
    _coal_block_a = [bf for bf in _blocked_a if bf.get("family") == "resource_acquisition:coal"]
    assert not _coal_block_a, (
        f"Test A FAILED: two partial_progress_timeout mine_coal ticks must NOT create "
        f"resource_acquisition:coal block; got: {_coal_block_a}"
    )

    # --- Test B: two pure action_timeout mine_coal ticks (no progress) → block IS created ---
    _ticks_b = [_make_pure_timeout_coal_tick(), _make_pure_timeout_coal_tick()]
    _blocked_b = _blocked_action_families(_ticks_b, _coal_summary)
    _coal_block_b = [bf for bf in _blocked_b if bf.get("family") == "resource_acquisition:coal"]
    assert _coal_block_b, (
        f"Test B FAILED: two pure action_timeout mine_coal ticks (no progress) must create "
        f"resource_acquisition:coal block; got blocked_families={_blocked_b}"
    )
    assert _coal_block_b[0].get("blocked") is True, _coal_block_b[0]
    # The block must NOT be softened (no progress ticks)
    assert _coal_block_b[0].get("repeatable_now") is False, (
        f"Test B: pure-timeout block must have repeatable_now=False; got {_coal_block_b[0]}"
    )

    # --- Test C: action_timeout then partial_progress_timeout → block absent or softened ---
    # Order: recent tick first (age 0), older tick last (age 1)
    _ticks_c = [_make_partial_progress_coal_tick(), _make_pure_timeout_coal_tick()]
    _blocked_c = _blocked_action_families(_ticks_c, _coal_summary)
    _coal_block_c = [bf for bf in _blocked_c if bf.get("family") == "resource_acquisition:coal"]
    if _coal_block_c:
        # If a block exists it must be softened (repeatable_now=True, reason set)
        assert _coal_block_c[0].get("repeatable_now") is True, (
            f"Test C FAILED: partial_progress tick must soften existing block to repeatable_now=True; "
            f"got {_coal_block_c[0]}"
        )
        assert _coal_block_c[0].get("unblock_condition_change_reason") == "partial_progress_made", (
            f"Test C FAILED: unblock_condition_change_reason must be 'partial_progress_made'; "
            f"got {_coal_block_c[0]}"
        )
    # else: block absent entirely — also correct

    # -------------------------------------------------------------------------
    # drop_collection:* blocking — narrow family for DC failures
    # -------------------------------------------------------------------------
    from vtuber_ai.game_brain import _is_drop_collection_failure_tick, find_blocked_family

    def _make_dc_blocker_tick() -> dict:
        """mine_coal tick: mined 1 block but drop blocked by undiggable blocker."""
        return {
            "action": "mine_coal", "ok": 0,
            "args": {},
            "error": "Mined coal_ore but drop collection failed: drop_collection_partial_progress",
            "result": {
                "failure_type": "partial_progress_timeout",
                "stop_reason": "drop_collection_partial_progress",
                "partial_success": True,
                "minedTargetBlocks": 1,
                "dropRecoveryFailureReason": "drop_blocker_not_diggable",
                "dropEntityPosition": {"x": 10, "y": 59, "z": 10},
                "dropBlockedBy": "stone",
                "failed_because": [{
                    "kind": "mined_target_but_drop_not_collected",
                    "action": "mine_coal",
                    "minedTargetBlocks": 1,
                    "dropRecoveryFailureReason": "drop_blocker_not_diggable",
                    "dropEntityPosition": {"x": 10, "y": 59, "z": 10},
                    "dropBlockedBy": "stone",
                    "stop_reason": "drop_collection_partial_progress",
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": True,
                "diagnostics": {"continuation_relevant": True, "minedTargetBlocks": 1},
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    # Helper: is_drop_collection_failure_tick must recognise this tick
    _dc_tick = _make_dc_blocker_tick()
    assert _is_drop_collection_failure_tick(_dc_tick), (
        "DC tick with stop_reason=drop_collection_partial_progress + minedTargetBlocks=1 "
        "must be recognised as a drop_collection failure"
    )
    # Pure timeout tick must NOT be recognised as DC failure
    assert not _is_drop_collection_failure_tick(_make_pure_timeout_coal_tick()), (
        "Pure action_timeout tick must NOT be a drop_collection failure"
    )

    # --- DC-1: single DC failure → no block at all ---
    _dc_only = _blocked_action_families([_make_dc_blocker_tick()], _coal_summary)
    assert not any(bf["family"] in {"resource_acquisition:coal", "drop_collection:coal"}
                   for bf in _dc_only), (
        "DC-1: single DC failure must not create any block"
    )

    # --- DC-2: DC failure + 2 pure timeouts (the reported bug scenario) ---
    # resource_acquisition:coal must NOT be blocked; drop_collection:coal MUST be blocked.
    _dc_then_pure = [
        _make_pure_timeout_coal_tick(),   # age 0 — most recent
        _make_pure_timeout_coal_tick(),   # age 1
        _make_dc_blocker_tick(),          # age 2 — oldest, DC failure
    ]
    _blocked_dc2 = _blocked_action_families(_dc_then_pure, _coal_summary)
    _ra_block_dc2 = [bf for bf in _blocked_dc2 if bf["family"] == "resource_acquisition:coal"]
    _dc_block_dc2 = [bf for bf in _blocked_dc2 if bf["family"] == "drop_collection:coal"]
    assert not _ra_block_dc2, (
        f"DC-2: resource_acquisition:coal must NOT be blocked when DC failure exists; "
        f"got: {_ra_block_dc2}"
    )
    assert _dc_block_dc2, (
        f"DC-2: drop_collection:coal MUST be blocked instead; got blocked={_blocked_dc2}"
    )
    assert _dc_block_dc2[0].get("blocked_family_type") == "drop_collection", _dc_block_dc2[0]
    assert _dc_block_dc2[0].get("recovery_failure_reason") == "drop_blocker_not_diggable", _dc_block_dc2[0]
    assert _dc_block_dc2[0].get("drop_position") is not None, (
        f"DC-2: drop_position must be present in block record; got: {_dc_block_dc2[0]}"
    )
    assert _dc_block_dc2[0].get("blocker") == "stone", _dc_block_dc2[0]

    # --- DC-3: find_blocked_family returns drop_collection:coal for mine_coal ---
    _fbf_dc = find_blocked_family("mine_coal", {}, _dc_then_pure, _coal_summary)
    assert _fbf_dc is not None, "DC-3: find_blocked_family must return a block for mine_coal"
    assert _fbf_dc["family"] == "drop_collection:coal", (
        f"DC-3: must return drop_collection:coal, got {_fbf_dc['family']}"
    )

    # --- DC-4: must not block after position changes significantly ---
    _coal_new_pos = dict(_coal_summary)
    _coal_new_pos["position"] = {"x": 50, "y": 60, "z": 50}   # > 8 blocks away
    _fbf_dc_moved = find_blocked_family("mine_coal", {}, _dc_then_pure, _coal_new_pos)
    assert _fbf_dc_moved is None, (
        f"DC-4: drop_collection:coal must clear when position changed; "
        f"got: {_fbf_dc_moved}"
    )

    # --- DC-5: must not block after coal collected (inventory changed) ---
    _coal_inv = dict(_coal_summary)
    _coal_inv["inventory_counts"] = {"coal": 3}
    _fbf_dc_inv = find_blocked_family("mine_coal", {}, _dc_then_pure, _coal_inv)
    assert _fbf_dc_inv is None, (
        f"DC-5: drop_collection:coal must clear when coal collected; got: {_fbf_dc_inv}"
    )

    # --- DC-6: two pure timeouts WITHOUT any DC failure → still blocks resource_acquisition ---
    _pure_only = [_make_pure_timeout_coal_tick(), _make_pure_timeout_coal_tick()]
    _blocked_pure = _blocked_action_families(_pure_only, _coal_summary)
    _ra_pure = [bf for bf in _blocked_pure if bf["family"] == "resource_acquisition:coal"]
    _dc_pure = [bf for bf in _blocked_pure if bf["family"] == "drop_collection:coal"]
    assert _ra_pure, (
        f"DC-6: two pure timeouts without DC failure must still block resource_acquisition:coal; "
        f"got: {_blocked_pure}"
    )
    assert not _dc_pure, (
        f"DC-6: drop_collection:coal must NOT be blocked when no DC failure exists; "
        f"got: {_dc_pure}"
    )

    # --- DC-7: mine_coal success clears both resource_acquisition AND drop_collection ---
    _mine_coal_ok_dc = {
        "action": "mine_coal", "ok": 1,
        "args": {},
        "result": {"collected": 3},
        "verifier": {"failure_type": "none"},
        "before_state": {"inventory_counts": {}, "position": _bare_pos},
        "after_state": {"inventory_counts": {"coal": 3}, "position": _bare_pos},
    }
    _success_then_dc = [
        _mine_coal_ok_dc,          # age 0
        _make_pure_timeout_coal_tick(),   # age 1
        _make_dc_blocker_tick(),          # age 2
    ]
    _blocked_ok = _blocked_action_families(_success_then_dc, _coal_summary)
    assert not any(bf["family"] in {"resource_acquisition:coal", "drop_collection:coal"}
                   for bf in _blocked_ok), (
        f"DC-7: mine_coal success must clear both families; got: {_blocked_ok}"
    )

    # --- DC-8: above_route_ignored block → blockerReason/blockerIntersects extracted, no blocker ---
    def _make_dc_above_route_tick() -> dict:
        """DC failure tick where the candidate blocker was above the movement volume."""
        return {
            "action": "mine_coal", "ok": 0,
            "args": {},
            "error": "Mined coal_ore but drop collection failed: drop_collection_partial_progress",
            "result": {
                "failure_type": "partial_progress_timeout",
                "stop_reason": "drop_collection_partial_progress",
                "partial_success": True,
                "minedTargetBlocks": 1,
                "dropRecoveryFailureReason": "drop_no_safe_stand",
                "dropEntityPosition": {"x": 10, "y": 78, "z": 10},
                "dropBlockedBy": None,
                "blockerReason": "above_route_ignored",
                "blockerIntersectsMovementVolume": False,
                "failed_because": [{
                    "kind": "mined_target_but_drop_not_collected",
                    "action": "mine_coal",
                    "minedTargetBlocks": 1,
                    "dropRecoveryFailureReason": "drop_no_safe_stand",
                    "dropEntityPosition": {"x": 10, "y": 78, "z": 10},
                    "dropBlockedBy": None,
                    "blockerReason": "above_route_ignored",
                    "blockerIntersectsMovementVolume": False,
                    "stop_reason": "drop_collection_partial_progress",
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": True,
                "diagnostics": {"continuation_relevant": True, "minedTargetBlocks": 1},
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    _dc_above = _make_dc_above_route_tick()
    assert _is_drop_collection_failure_tick(_dc_above), (
        "DC-8: tick with above_route_ignored blocker must still be recognized as DC failure"
    )
    from vtuber_ai.game_brain import _extract_drop_collection_diagnostics
    _dc_above_diag = _extract_drop_collection_diagnostics(_dc_above)
    assert _dc_above_diag.get("blocker_reason") == "above_route_ignored", (
        f"DC-8: blocker_reason must be 'above_route_ignored'; got: {_dc_above_diag}"
    )
    assert _dc_above_diag.get("blocker_intersects_movement_volume") is False, (
        f"DC-8: blocker_intersects_movement_volume must be False; got: {_dc_above_diag}"
    )
    assert _dc_above_diag.get("blocker") is None, (
        f"DC-8: blocker must be None when block is above route; got: {_dc_above_diag}"
    )

    # --- DC-9: head_space blocker → blockerReason/blockerIntersects extracted with blocker ---
    def _make_dc_head_space_tick() -> dict:
        """DC failure tick where the candidate blocker is in the player's head space."""
        return {
            "action": "mine_coal", "ok": 0,
            "args": {},
            "error": "Mined coal_ore but drop collection failed: drop_collection_partial_progress",
            "result": {
                "failure_type": "partial_progress_timeout",
                "stop_reason": "drop_collection_partial_progress",
                "partial_success": True,
                "minedTargetBlocks": 1,
                "dropRecoveryFailureReason": "drop_blocker_not_diggable",
                "dropEntityPosition": {"x": 10, "y": 79, "z": 10},
                "dropBlockedBy": {"name": "granite", "position": {"x": 10, "y": 80, "z": 10}},
                "blockerReason": "head_space",
                "blockerIntersectsMovementVolume": True,
                "failed_because": [{
                    "kind": "mined_target_but_drop_not_collected",
                    "action": "mine_coal",
                    "minedTargetBlocks": 1,
                    "dropRecoveryFailureReason": "drop_blocker_not_diggable",
                    "dropEntityPosition": {"x": 10, "y": 79, "z": 10},
                    "dropBlockedBy": {"name": "granite", "position": {"x": 10, "y": 80, "z": 10}},
                    "blockerReason": "head_space",
                    "blockerIntersectsMovementVolume": True,
                    "stop_reason": "drop_collection_partial_progress",
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": True,
                "diagnostics": {"continuation_relevant": True, "minedTargetBlocks": 1},
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    _dc_head = _make_dc_head_space_tick()
    assert _is_drop_collection_failure_tick(_dc_head), (
        "DC-9: tick with head_space blocker must be recognized as DC failure"
    )
    _dc_head_diag = _extract_drop_collection_diagnostics(_dc_head)
    assert _dc_head_diag.get("blocker_reason") == "head_space", (
        f"DC-9: blocker_reason must be 'head_space'; got: {_dc_head_diag}"
    )
    assert _dc_head_diag.get("blocker_intersects_movement_volume") is True, (
        f"DC-9: blocker_intersects_movement_volume must be True; got: {_dc_head_diag}"
    )
    assert _dc_head_diag.get("blocker") is not None, (
        f"DC-9: blocker must be present for head_space block; got: {_dc_head_diag}"
    )

    # --- DC-10: drop_collection_timeout with minedTargetBlocks=1 is recognised as DC failure ---
    # buildDropCollectionFailure maps drop_collection_timeout → stop_reason=mined_target_but_drop_not_collected
    def _make_dc_timeout_tick() -> dict:
        """mine_coal tick: block mined, drop collection timed out with 2 passes."""
        return {
            "action": "mine_coal", "ok": 0,
            "args": {},
            "error": "Mined coal_ore but drop collection failed: drop_collection_timeout",
            "result": {
                "failure_type": "partial_progress_timeout",
                "stop_reason": "mined_target_but_drop_not_collected",
                "partial_success": True,
                "minedTargetBlocks": 1,
                "dropEntityStillExists": True,
                "nearbyDropsFound": 1,
                "relevantDropsFound": 1,
                "nearestDropDistance": 2.4,
                "dropCollectionPasses": 2,
                "dropsCollectedThisAction": 0,
                "targetInventoryDelta": 0,
                "inventoryDeltaAfterDropCollection": 0,
                "failed_because": [{
                    "kind": "mined_target_but_drop_not_collected",
                    "action": "mine_coal",
                    "stop_reason": "mined_target_but_drop_not_collected",
                    "drop_collection_reason": "drop_collection_timeout",
                    "minedTargetBlocks": 1,
                    "nearbyDropsFound": 1,
                    "nearestDropDistance": 2.4,
                    "dropCollectionPasses": 2,
                    "dropsCollectedThisAction": 0,
                    "targetInventoryDelta": 0,
                    "inventoryDeltaAfterDropCollection": 0,
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": True,
                "diagnostics": {"continuation_relevant": True, "minedTargetBlocks": 1},
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    _dc_timeout = _make_dc_timeout_tick()
    assert _is_drop_collection_failure_tick(_dc_timeout), (
        "DC-10: drop_collection_timeout with minedTargetBlocks=1 must be recognized as DC failure"
    )
    _dc_timeout_diag = _extract_drop_collection_diagnostics(_dc_timeout)
    assert _dc_timeout_diag.get("blocked_family_type") == "drop_collection", _dc_timeout_diag

    # DC-10b: drop_collection:coal is blocked by the timeout scenario
    _timeout_ticks = [
        _make_pure_timeout_coal_tick(),    # age 0
        _make_pure_timeout_coal_tick(),    # age 1
        _dc_timeout_tick(),                # age 2 — DC failure
    ] if False else [
        _make_pure_timeout_coal_tick(),
        _make_pure_timeout_coal_tick(),
        _make_dc_timeout_tick(),
    ]
    _blocked_timeout = _blocked_action_families(_timeout_ticks, _coal_summary)
    _dc_timeout_block = [bf for bf in _blocked_timeout if bf["family"] == "drop_collection:coal"]
    assert _dc_timeout_block, (
        f"DC-10b: drop_collection:coal must be blocked for timeout scenario; got: {_blocked_timeout}"
    )

    # --- DC-11: ok=true tick with targetInventoryDelta>0 is NOT a DC failure ---
    _success_tick = {
        "action": "mine_coal", "ok": 1,
        "args": {},
        "result": {
            "collected": 2,
            "dropsCollectedThisAction": 2,
            "targetInventoryDelta": 2,
            "dropCollectionPasses": 1,
        },
        "verifier": {"failure_type": "none"},
        "before_state": {"inventory_counts": {}, "position": _bare_pos},
        "after_state": {"inventory_counts": {"coal": 2}, "position": _bare_pos},
    }
    assert not _is_drop_collection_failure_tick(_success_tick), (
        "DC-11: ok=true tick with targetInventoryDelta>0 must NOT be a DC failure"
    )

    # --- DC-12: close drop with no pickup attempt triggers bug failure, recognised as DC ---
    def _make_dc_bug_tick() -> dict:
        """mine_coal: drop within 1.5 blocks, no pickup was attempted (old code bug)."""
        return {
            "action": "mine_coal", "ok": 0,
            "args": {},
            "error": "Drop close but no pickup attempted (dist=1.3, vertDelta=-1.0)",
            "result": {
                "failure_type": "internal_drop_collection_bug",
                "stop_reason": "drop_close_but_no_pickup_attempt",
                "partial_success": True,
                "minedTargetBlocks": 1,
                "dropEntityStillExists": True,
                "nearestDropDistance": 1.3,
                "dropVerticalDelta": -1.0,
                "closeDropPickupAttempted": False,
                "dropDirectWalkAttempted": False,
                "failed_because": [{
                    "kind": "internal_drop_collection_bug",
                    "action": "mine_coal",
                    "stop_reason": "drop_close_but_no_pickup_attempt",
                    "drop_distance": 1.3,
                    "dropVerticalDelta": -1.0,
                    "minedTargetBlocks": 1,
                    "continuation_relevant": True,
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": True,
                "diagnostics": {"continuation_relevant": True, "minedTargetBlocks": 1},
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    _dc_bug = _make_dc_bug_tick()
    # Bug tick must be recognised as a drop_collection failure (routes to drop_collection:coal)
    assert _is_drop_collection_failure_tick(_dc_bug), (
        "DC-12: internal_drop_collection_bug tick must be recognised as a DC failure"
    )
    # The block should carry drop_collection:coal, not resource_acquisition:coal
    _bug_ticks = [
        _make_pure_timeout_coal_tick(),
        _make_pure_timeout_coal_tick(),
        _dc_bug,
    ]
    _blocked_bug = _blocked_action_families(_bug_ticks, _coal_summary)
    _dc_bug_block = [bf for bf in _blocked_bug if bf["family"] == "drop_collection:coal"]
    _ra_bug_block = [bf for bf in _blocked_bug if bf["family"] == "resource_acquisition:coal"]
    assert _dc_bug_block, (
        f"DC-12: drop_collection:coal must be blocked for bug tick scenario; got: {_blocked_bug}"
    )
    assert not _ra_bug_block, (
        f"DC-12: resource_acquisition:coal must NOT be blocked; got: {_ra_bug_block}"
    )
    # Diagnostics extraction includes dropVerticalDelta via drop_position path isn't required,
    # but blocked_family_type must be 'drop_collection'
    assert _dc_bug_block[0].get("blocked_family_type") == "drop_collection", _dc_bug_block[0]

    # DC-12b: close drop tick with closeDropPickupAttempted=true and vertDelta=-1
    #   must still be recognised as a DC failure (new code path)
    def _make_dc_close_pickup_tick() -> dict:
        return {
            "action": "mine_coal", "ok": 0,
            "args": {},
            "error": "Mined coal_ore but drop collection failed: drop_collection_timeout",
            "result": {
                "failure_type": "partial_progress_timeout",
                "stop_reason": "mined_target_but_drop_not_collected",
                "partial_success": True,
                "minedTargetBlocks": 1,
                "closeDropPickupAttempted": True,
                "closeDropPickupTicks": 12,
                "dropCollectionMethod": "close_pickup",
                "dropDirectWalkAttempted": False,
                "nearestDropDistance": 1.4,
                "dropVerticalDelta": -1.0,
                "dropEntityStillExists": True,
                "inventoryDeltaAfterDropCollection": 0,
                "botPositionChanged": True,
                "failed_because": [{
                    "kind": "mined_target_but_drop_not_collected",
                    "action": "mine_coal",
                    "stop_reason": "mined_target_but_drop_not_collected",
                    "drop_collection_reason": "drop_collection_timeout",
                    "minedTargetBlocks": 1,
                    "closeDropPickupAttempted": True,
                    "closeDropPickupTicks": 12,
                    "dropCollectionMethod": "close_pickup",
                    "nearestDropDistance": 1.4,
                    "dropVerticalDelta": -1.0,
                    "inventoryDeltaAfterDropCollection": 0,
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": True,
                "diagnostics": {"continuation_relevant": True, "minedTargetBlocks": 1},
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    _dc_close = _make_dc_close_pickup_tick()
    assert _is_drop_collection_failure_tick(_dc_close), (
        "DC-12b: close_pickup attempt tick must be recognised as a DC failure"
    )
    from vtuber_ai.game_brain import _extract_drop_collection_diagnostics as _edc
    _dc_close_diag = _edc(_dc_close)
    # dropCollectionMethod is not null — extracting from failed_because
    assert _dc_close_diag.get("blocked_family_type") == "drop_collection", _dc_close_diag

    # --- DC-13: drop_deep_unreachable tick is recognised as DC failure ---
    # JS emits stop_reason=drop_deep_unreachable when dropVerticalDelta<=-3 and noSafeStand.
    _deep_drop_pos = {"x": 100.5, "y": 68.0, "z": 200.3}
    _deep_dc_family = "drop_collection:coal:100_68_200"

    def _make_dc_deep_unreachable_tick() -> dict:
        return {
            "action": "mine_coal", "ok": 0,
            "args": {},
            "error": "Mined coal but drop fell deep and unreachable (vertDelta=-4, noSafeStand): abandoning this drop",
            "result": {
                "failure_type": "partial_progress_timeout",
                "stop_reason": "drop_deep_unreachable",
                "partial_success": True,
                "continuation_relevant": False,
                "resource_action_still_valid": True,
                "dropCollectionAbandoned": True,
                "abandonedDropReason": "deep_no_safe_stand",
                "minedTargetBlocks": 1,
                "dropVerticalDelta": -4.0,
                "dropSafeStandCandidatesFound": 0,
                "dropEntityPosition": _deep_drop_pos,
                "failed_because": [{
                    "kind": "drop_deep_unreachable",
                    "action": "mine_coal",
                    "item": "coal",
                    "dropVerticalDelta": -4.0,
                    "dropSafeStandCandidatesFound": 0,
                    "dropEntityPosition": _deep_drop_pos,
                    "same_drop_retry_not_recommended": True,
                    "continuation_relevant": False,
                    "resource_action_still_valid": True,
                    "drop_collection_family": _deep_dc_family,
                    "minedTargetBlocks": 1,
                }],
            },
            "verifier": {
                "failure_type": "partial_progress_timeout",
                "repeatable_now": False,
                "diagnostics": {"continuation_relevant": False, "minedTargetBlocks": 1},
            },
            "before_state": {"inventory_counts": {}, "position": _bare_pos},
            "after_state": {"inventory_counts": {}, "position": _bare_pos},
        }

    _dc_deep = _make_dc_deep_unreachable_tick()
    assert _is_drop_collection_failure_tick(_dc_deep), (
        "DC-13: drop_deep_unreachable tick must be recognised as a DC failure"
    )

    _dc_deep_diag = _extract_drop_collection_diagnostics(_dc_deep)
    assert _dc_deep_diag.get("drop_collection_family") == _deep_dc_family, (
        f"DC-13: drop_collection_family must be position-specific; got: {_dc_deep_diag}"
    )
    assert _dc_deep_diag.get("same_drop_retry_not_recommended") is True, (
        f"DC-13: same_drop_retry_not_recommended must be True; got: {_dc_deep_diag}"
    )
    assert _dc_deep_diag.get("abandoned_drop_reason") == "deep_no_safe_stand", (
        f"DC-13: abandoned_drop_reason must be deep_no_safe_stand; got: {_dc_deep_diag}"
    )

    # DC-13b: position-specific family is emitted; resource_acquisition:coal is NOT blocked
    _deep_pkt = build_llm_state_packet(
        status=state(_coal_summary, recent_ticks=[_dc_deep]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="mine coal",
    )
    _deep_blocked = _deep_pkt.get("blocked_action_families") or []
    _deep_families = [bf.get("family") for bf in _deep_blocked]
    assert _deep_dc_family in _deep_families, (
        f"DC-13b: position-specific drop_collection family must appear in blocked; got: {_deep_families}"
    )
    assert "resource_acquisition:coal" not in _deep_families, (
        f"DC-13b: resource_acquisition:coal must NOT be blocked by deep drop; got: {_deep_families}"
    )
    assert "drop_collection:coal" not in _deep_families, (
        f"DC-13b: generic drop_collection:coal must NOT appear; got: {_deep_families}"
    )

    # DC-13c: unblock_condition for position-specific family mentions mining a different block
    _dc13_bf = next(bf for bf in _deep_blocked if bf.get("family") == _deep_dc_family)
    _unblock = _dc13_bf.get("unblock_condition") or ""
    assert "coal" in _unblock.lower(), (
        f"DC-13c: unblock_condition must mention coal; got: {_unblock!r}"
    )
    assert "different" in _unblock.lower() or "new" in _unblock.lower() or "mine" in _unblock.lower(), (
        f"DC-13c: unblock_condition must suggest mining a different block; got: {_unblock!r}"
    )

    # DC-13d: repeatable_now must NOT be True for position-specific family
    assert _dc13_bf.get("repeatable_now") is not True, (
        f"DC-13d: position-specific deep-drop block must not be softened to repeatable_now=True; got: {_dc13_bf}"
    )

    # DC-13e: after a successful mine_coal, the position-specific block is cleared
    _success_coal_tick = {
        "action": "mine_coal", "ok": 1,
        "args": {},
        "result": {"collected": 1, "minedTargetBlocks": 1},
        "before_state": {"inventory_counts": {}, "position": _bare_pos},
        "after_state": {"inventory_counts": {"coal": 1}, "position": _bare_pos},
    }
    _success_pkt = build_llm_state_packet(
        status=state(_coal_summary, recent_ticks=[_dc_deep, _success_coal_tick]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="mine coal",
    )
    _success_blocked_families = [bf.get("family") for bf in (_success_pkt.get("blocked_action_families") or [])]
    assert _deep_dc_family not in _success_blocked_families, (
        f"DC-13e: position-specific block must be cleared after successful mine_coal; "
        f"got: {_success_blocked_families}"
    )

    # DC-13f: drop_deep_unreachable tick must NOT appear in continuation_facts
    # (continuation_relevant=False means this specific drop is not worth retrying,
    # even though mining itself succeeded).
    _deep_cont_pkt = build_llm_state_packet(
        status=state(_coal_summary, recent_ticks=[_dc_deep]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="mine coal",
    )
    _deep_cont_facts = _deep_cont_pkt.get("continuation_facts") or []
    assert not any(cf.get("continuation_family") == "resource_acquisition:coal" for cf in _deep_cont_facts), (
        f"DC-13f: drop_deep_unreachable tick must NOT produce continuation_fact for coal; "
        f"got continuation_facts={_deep_cont_facts}"
    )

    # --- Sanity: continuation_facts emits fact for partial_progress_timeout families ---
    _cont_pkt = build_llm_state_packet(
        status=state(_coal_summary, recent_ticks=[_make_partial_progress_coal_tick()]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="mine coal",
    )
    _cont_facts = _cont_pkt.get("continuation_facts") or []
    assert any(cf.get("continuation_family") == "resource_acquisition:coal" for cf in _cont_facts), (
        f"Sanity: partial_progress_timeout tick must produce continuation_fact for coal; "
        f"got continuation_facts={_cont_facts}"
    )

    # --- WS-1: two return_to_workspace path_timeout failures → workspace_status ---
    def _make_ws_timeout_tick(station=None):
        result = {
            "failure_type": "path_timeout",
            "stop_reason": "path_timeout",
            "reached": False,
            "maybe_stale": False,
            "target_workspace_position": {"x": 0, "y": 64, "z": 0},
            "failed_because": [{"kind": "path_timeout", "action": "return_to_workspace"}],
        }
        if station:
            result["station_needed"] = station
        return {
            "action": "return_to_workspace",
            "ok": 0,
            "args": {},
            "result": result,
            "verifier": {"failure_type": "navigation_failed", "success": False},
            "before_state": {"inventory_counts": {}, "position": {"x": 0, "y": 64, "z": 0}},
            "after_state": {"inventory_counts": {}, "position": {"x": 0, "y": 64, "z": 0}},
        }

    _ws1_pkt = build_llm_state_packet(
        status=state(_coal_summary, recent_ticks=[
            _make_ws_timeout_tick("crafting_table"),
            _make_ws_timeout_tick(),
        ]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="craft stone pickaxe",
    )
    _ws1_status = _ws1_pkt.get("workspace_status")
    assert _ws1_status is not None, (
        f"WS-1: two path_timeout failures must produce workspace_status; got None"
    )
    assert _ws1_status.get("remembered_workspace_reachable") is False, (
        f"WS-1: remembered_workspace_reachable must be False; got: {_ws1_status}"
    )
    assert _ws1_status.get("failure_count") >= 2, (
        f"WS-1: failure_count must be >= 2; got: {_ws1_status}"
    )
    assert "crafting_table" in (_ws1_status.get("station_missing_near_current_position") or []), (
        f"WS-1: crafting_table must appear in station_missing list; got: {_ws1_status}"
    )

    # WS-1b: single failure must NOT produce workspace_status
    _ws1b_pkt = build_llm_state_packet(
        status=state(_coal_summary, recent_ticks=[_make_ws_timeout_tick()]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="craft stone pickaxe",
    )
    assert _ws1b_pkt.get("workspace_status") is None, (
        f"WS-1b: single failure must NOT produce workspace_status; got: {_ws1b_pkt.get('workspace_status')}"
    )

    # WS-1c: success between failures resets the count
    _ws1c_pkt = build_llm_state_packet(
        status=state(_coal_summary, recent_ticks=[
            _make_ws_timeout_tick(),
            {"action": "return_to_workspace", "ok": 1, "args": {}, "result": {}, "verifier": {}},
            _make_ws_timeout_tick(),
        ]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="craft stone pickaxe",
    )
    assert _ws1c_pkt.get("workspace_status") is None, (
        f"WS-1c: success between failures must reset count and NOT produce workspace_status; "
        f"got: {_ws1c_pkt.get('workspace_status')}"
    )

    # --- SAS-1: station_access_status reflects current nearby blocks ---
    _sas_summary_no_station = {
        "inventory_counts": {},
        "position": {"x": 0, "y": 64, "z": 0},
        "nearby_blocks": {},
    }
    _sas_pkt_empty = build_llm_state_packet(
        status=state(_sas_summary_no_station, recent_ticks=[]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="craft",
    )
    _sas = _sas_pkt_empty.get("station_access_status")
    assert isinstance(_sas, dict), f"SAS-1: station_access_status must be a dict; got {_sas!r}"
    assert "crafting_table" in _sas, "SAS-1: crafting_table key must exist"
    assert _sas["crafting_table"]["visible"] is False, "SAS-1: no nearby station → visible=False"
    assert _sas["crafting_table"]["usable"] is False, "SAS-1: no nearby station → usable=False"
    assert "last_approach_success_tick" not in _sas["crafting_table"], "SAS-1: no approach history → no last_approach_success_tick"

    # SAS-2: approach_station success appears as last_approach_success_tick
    _approach_success_tick = {
        "action": "approach_station",
        "ok": 1,
        "args": {"station": "crafting_table"},
        "result": {"station": "crafting_table", "reached": True, "usable": True},
        "verifier": {"success": True, "failure_type": "none"},
        "before_state": {"inventory_counts": {}, "position": {"x": 0, "y": 64, "z": 0}},
        "after_state": {"inventory_counts": {}, "position": {"x": 1, "y": 64, "z": 1}},
    }
    _sas_summary_with_ct = dict(_sas_summary_no_station)
    _sas_summary_with_ct["nearby_blocks"] = {
        "crafting_table": {"name": "crafting_table", "distance": 2, "position": {"x": 1, "y": 64, "z": 1}}
    }
    _sas_pkt_approach = build_llm_state_packet(
        status=state(_sas_summary_with_ct, recent_ticks=[_approach_success_tick]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="craft",
    )
    _sas2 = _sas_pkt_approach.get("station_access_status", {})
    _ct2 = _sas2.get("crafting_table", {})
    assert _ct2.get("visible") is True, f"SAS-2: crafting_table visible after approach; got {_ct2}"
    assert _ct2.get("usable") is True, f"SAS-2: crafting_table usable at distance 2; got {_ct2}"
    assert _ct2.get("last_approach_success_tick") == 0, (
        f"SAS-2: last_approach_success_tick must be 0 (age 0 = most recent tick); got {_ct2}"
    )
    assert _ct2.get("repeated_approach_warning") is True, (
        f"SAS-2: repeated_approach_warning must be True when usable and just approached; got {_ct2}"
    )

    # SAS-3: without recent approach, repeated_approach_warning is absent
    _sas_pkt_no_recent = build_llm_state_packet(
        status=state(_sas_summary_with_ct, recent_ticks=[]),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="craft",
    )
    _ct3 = _sas_pkt_no_recent.get("station_access_status", {}).get("crafting_table", {})
    assert _ct3.get("usable") is True, f"SAS-3: crafting_table usable from nearby_blocks; got {_ct3}"
    assert "repeated_approach_warning" not in _ct3, (
        f"SAS-3: repeated_approach_warning must be absent when no recent approach; got {_ct3}"
    )

    # --- LRS-1: live_recovery_status from consecutive failures ---
    from vtuber_ai.game_brain import _live_recovery_status_from_ticks

    def _make_failed_tick(action: str, failure_type: str = "no_progress") -> dict:
        return {
            "action": action,
            "ok": False,
            "result": {"ok": False, "failure_type": failure_type},
            "verifier": {"ok": False, "failure_type": failure_type},
        }

    def _make_ok_tick(action: str) -> dict:
        return {"action": action, "ok": True, "result": {"ok": True}, "verifier": {"ok": True}}

    # 3 consecutive failures → returns live_recovery_status
    _lrs_ticks_3 = [
        _make_failed_tick("collect_wood", "path_timeout"),
        _make_failed_tick("collect_wood", "path_timeout"),
        _make_failed_tick("collect_stone", "no_progress"),
    ]
    _lrs1 = _live_recovery_status_from_ticks(_lrs_ticks_3)
    assert _lrs1 is not None, "LRS-1: 3 consecutive failures must produce live_recovery_status"
    assert _lrs1["live_recovery_mode"] is True, f"LRS-1: live_recovery_mode must be True; got {_lrs1}"
    assert _lrs1["consecutive_failure_count"] == 3, (
        f"LRS-1: consecutive_failure_count must be 3; got {_lrs1}"
    )
    assert _lrs1["must_change_conditions"] is True, f"LRS-1: must_change_conditions must be True; got {_lrs1}"
    assert isinstance(_lrs1["recent_failure_pattern"], str) and _lrs1["recent_failure_pattern"], (
        f"LRS-1: recent_failure_pattern must be a non-empty string; got {_lrs1}"
    )

    # < 3 consecutive failures → returns None
    _lrs_ticks_2 = [
        _make_failed_tick("collect_wood"),
        _make_failed_tick("collect_stone"),
    ]
    _lrs2 = _live_recovery_status_from_ticks(_lrs_ticks_2)
    assert _lrs2 is None, f"LRS-1b: 2 consecutive failures must NOT produce live_recovery_status; got {_lrs2}"

    # success resets the consecutive count
    _lrs_ticks_reset = [
        _make_failed_tick("collect_wood"),
        _make_failed_tick("collect_stone"),
        _make_ok_tick("look_around"),
        _make_failed_tick("collect_wood"),
    ]
    _lrs3 = _live_recovery_status_from_ticks(_lrs_ticks_reset)
    assert _lrs3 is None, (
        f"LRS-1c: success between failures must reset count and NOT produce live_recovery_status; got {_lrs3}"
    )

    # live_recovery_status appears in build_llm_state_packet output
    _lrs_state = state(
        {"health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}, "dimension": "overworld"},
        recent_ticks=[
            _make_failed_tick("collect_wood"),
            _make_failed_tick("collect_wood"),
            _make_failed_tick("collect_wood"),
        ],
    )
    _lrs_pkt = build_llm_state_packet(
        status=_lrs_state,
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="survive",
    )
    _lrs_val = _lrs_pkt.get("live_recovery_status")
    assert _lrs_val is not None, "LRS-1d: 3 consecutive failure ticks must yield live_recovery_status in packet"
    assert _lrs_val["live_recovery_mode"] is True, f"LRS-1d: live_recovery_mode must be True in packet; got {_lrs_val}"

    # --- ADVISORY MODE: hard_block_repetitions_enabled reads env var ---
    _old_hbr = os.environ.pop("VTUBER_HARD_BLOCK_REPETITIONS", None)
    try:
        assert hard_block_repetitions_enabled() is False, "default must be advisory mode (False)"
        os.environ["VTUBER_HARD_BLOCK_REPETITIONS"] = "0"
        assert hard_block_repetitions_enabled() is False, "0 must be advisory mode"
        os.environ["VTUBER_HARD_BLOCK_REPETITIONS"] = "1"
        assert hard_block_repetitions_enabled() is True, "1 must be hard-block mode"
    finally:
        if _old_hbr is None:
            os.environ.pop("VTUBER_HARD_BLOCK_REPETITIONS", None)
        else:
            os.environ["VTUBER_HARD_BLOCK_REPETITIONS"] = _old_hbr

    # --- ADVISORY MODE: build_repetition_warning produces expected payload ---
    _blocked_sample = {
        "family": "resource_acquisition:iron_ore",
        "failure_count": 3,
        "failed_because": [{"kind": "action_timeout", "action": "mine_iron_ore"}],
        "unblock_condition": "Move ≥8 blocks or change inventory.",
    }
    _warn = build_repetition_warning(_blocked_sample)
    assert _warn["repetition_warning"] is True, _warn
    assert _warn["repetition_family"] == "resource_acquisition:iron_ore", _warn
    assert isinstance(_warn["recent_failures"], list) and len(_warn["recent_failures"]) == 1, _warn
    assert "iron_ore" in _warn["why_repeating_may_be_low_value"], _warn
    assert isinstance(_warn["state_change_needed"], list) and _warn["state_change_needed"], _warn
    assert _warn["warning_severity"] == "medium", f"3 failures must be medium severity; got {_warn}"

    _warn_low = build_repetition_warning({**_blocked_sample, "failure_count": 1})
    assert _warn_low["warning_severity"] == "low", _warn_low
    _warn_high = build_repetition_warning({**_blocked_sample, "failure_count": 5})
    assert _warn_high["warning_severity"] == "high", _warn_high

    # --- ADVISORY MODE: build_llm_state_packet in advisory mode shows repetition_warnings ---
    def _make_iron_fail_tick(pos: dict) -> dict:
        return {
            "action": "mine_iron_ore",
            "ok": 0,
            "args": {},
            "error": "Block acquisition failed: timed out after 12000ms.",
            "result": {"failure_type": "resource_acquisition_failed"},
            "verifier": {
                "failure_type": "resource_acquisition_failed",
                "failed_because": [
                    {"kind": "action_timeout", "action": "mine_iron_ore", "timeout_ms": 12000, "recoverable": True},
                    {"kind": "resource_acquisition_attempt", "resource_family": "iron_ore",
                     "position_changed_since_last_attempt": False, "distance_moved_since_last_attempt": 0.0,
                     "position_change_meaningful": False},
                ],
            },
            "before_state": {"position": pos, "inventory_counts": {}},
            "after_state": {"position": pos, "inventory_counts": {}},
        }

    _iron_pos = {"x": 10, "y": 60, "z": 10}
    _iron_fail_ticks = [_make_iron_fail_tick(_iron_pos), _make_iron_fail_tick(_iron_pos)]
    _iron_summary = {
        "ok": True, "health": 20, "food": 20, "dimension": "overworld",
        "position": _iron_pos, "inventory_counts": {}, "nearby_blocks": {},
    }

    os.environ.pop("VTUBER_HARD_BLOCK_REPETITIONS", None)  # advisory mode (default 0)
    _adv_pkt = build_llm_state_packet(
        status=state(_iron_summary, recent_ticks=_iron_fail_ticks),
        recent_memory=[],
        last_result=None,
        bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
        mission="get iron",
    )
    assert _adv_pkt["blocked_action_families"] == [], (
        f"advisory mode must have empty blocked_action_families; got {_adv_pkt['blocked_action_families']}"
    )
    assert isinstance(_adv_pkt["repetition_warnings"], list), _adv_pkt["repetition_warnings"]
    assert len(_adv_pkt["repetition_warnings"]) >= 1, (
        f"advisory mode must have repetition_warnings for repeated mine_iron_ore; got {_adv_pkt['repetition_warnings']}"
    )
    _rw = _adv_pkt["repetition_warnings"][0]
    assert _rw["repetition_warning"] is True, _rw
    assert "iron_ore" in _rw["repetition_family"], _rw

    # --- ADVISORY MODE: find_blocked_family still returns a record (used by autonomy.py) ---
    _fbf_rec = find_blocked_family("mine_iron_ore", {}, _iron_fail_ticks, _iron_summary)
    assert _fbf_rec is not None, (
        "find_blocked_family must return a record for repeated mine_iron_ore even in advisory mode"
    )
    assert "iron_ore" in _fbf_rec.get("family", ""), _fbf_rec

    # --- HARD-BLOCK MODE: blocked_action_families is populated, repetition_warnings is empty ---
    try:
        os.environ["VTUBER_HARD_BLOCK_REPETITIONS"] = "1"
        _hard_pkt = build_llm_state_packet(
            status=state(_iron_summary, recent_ticks=_iron_fail_ticks),
            recent_memory=[],
            last_result=None,
            bridge_actions=AUTONOMOUS_ALLOWED_ACTIONS,
            mission="get iron",
        )
        assert isinstance(_hard_pkt["blocked_action_families"], list), _hard_pkt["blocked_action_families"]
        assert len(_hard_pkt["blocked_action_families"]) >= 1, (
            f"hard-block mode must populate blocked_action_families; got {_hard_pkt['blocked_action_families']}"
        )
        assert _hard_pkt["repetition_warnings"] == [], (
            f"hard-block mode must have empty repetition_warnings; got {_hard_pkt['repetition_warnings']}"
        )
        _hbf = _hard_pkt["blocked_action_families"][0]
        assert _hbf.get("blocked") is True, _hbf
        assert "iron_ore" in _hbf.get("family", ""), _hbf
    finally:
        os.environ.pop("VTUBER_HARD_BLOCK_REPETITIONS", None)

    print("manual game brain tests passed")


if __name__ == "__main__":
    main()
