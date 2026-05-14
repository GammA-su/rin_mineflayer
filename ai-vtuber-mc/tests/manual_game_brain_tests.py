from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.game_brain import AUTONOMOUS_ALLOWED_ACTIONS, build_llm_state_packet, choose_next_action


class StubHandler(BaseHTTPRequestHandler):
    captured_body: dict | None = None
    response_action = "collect_wood"
    response_args = {"count": 4}

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        StubHandler.captured_body = json.loads(raw)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "objective": "collect starter wood",
                                "action": StubHandler.response_action,
                                "args": StubHandler.response_args,
                                "speech": "Wood first.",
                                "mood": "focused",
                                "reason": "Current state supports this.",
                            }
                        )
                    }
                }
            ]
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
        assert "llm_state_packet_preview" in info

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
                "last_relevant_failure",
                "last_action_result",
                "planner_instruction",
                "available_actions",
            }
        assert user_content["inventory_counts"]["oak_log"] == 1
        assert user_content["current_facts"]["has_nearby_crafting_table"] is True
        assert user_content["nearbyBlocks"]["crafting_table"]["name"] == "crafting_table"
        assert user_content["last_action_result"]["result_flags"]["alreadyPresent"] is True
        assert len(user_content["nearbyBlockCounts"]) == 20
        assert len(user_content["nearbyEntities"]) == 10
        assert len(user_content["memory"]) == 2
        assert user_content["memory"][0]["historical"] is True
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
    assert packet["available_actions"]["mine_stone"]["args"] == {"count": "1-16"}
    assert packet["last_action_result"]["error"] == "Missing pickaxe."

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
    assert last_action_result["suggested_next_action"] == "navigate_to_block_type"
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

    print("manual game brain tests passed")


if __name__ == "__main__":
    main()
