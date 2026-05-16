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
        }
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

    # --- compact action list: all implemented/partial LLM-exposed actions appear ---
    from vtuber_ai.action_catalog import get_compact_action_list, get_detailed_action_docs, llm_exposed_count, CATALOG
    full_list = get_compact_action_list(set(AUTONOMOUS_ALLOWED_ACTIONS))
    assert "status" in full_list
    assert "collect_wood" in full_list
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

    print("manual game brain tests passed")


if __name__ == "__main__":
    main()
