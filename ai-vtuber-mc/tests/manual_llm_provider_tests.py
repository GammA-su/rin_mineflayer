from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import os
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.llm import plan_action, plan_agent_action
from vtuber_ai.schemas import ActionRequest


class StubHandler(BaseHTTPRequestHandler):
    captured_body = None
    response_content = json.dumps(
        {
            "action": "jump",
            "args": {},
            "speech": "Jumping.",
            "reason": "stubbed model response",
        }
    )

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
                        "content": self.response_content,
                    }
                }
            ]
        }
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def log_message(self, _format: str, *args: object) -> None:
        return


def with_env(**values: str | None):
    previous = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return previous


def restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def start_stub() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def main() -> None:
    env = with_env(VTUBER_LLM_PROVIDER=None, VTUBER_LLM_BASE_URL=None)
    try:
        assert plan_action("follow me", "rin").action == "follow_player"
    finally:
        restore_env(env)

    server, base_url = start_stub()
    env = with_env(VTUBER_LLM_PROVIDER="openai_compatible", VTUBER_LLM_BASE_URL=base_url)
    try:
        planned = plan_action("please do something", "rin")
        assert planned.action == "jump"
        assert planned.reason == "stubbed model response"
    finally:
        restore_env(env)
        server.shutdown()

    server, base_url = start_stub()
    StubHandler.response_content = "not json"
    env = with_env(VTUBER_LLM_PROVIDER="openai_compatible", VTUBER_LLM_BASE_URL=base_url)
    try:
        planned = plan_action("status please", "rin")
        assert planned.action == "status"
    finally:
        StubHandler.response_content = json.dumps(
            {
                "action": "jump",
                "args": {},
                "speech": "Jumping.",
                "reason": "stubbed model response",
            }
        )
        restore_env(env)
        server.shutdown()

    server, base_url = start_stub()
    StubHandler.response_content = json.dumps(
        {
            "action": "collect_wood",
            "args": {"count": 4},
            "speech": "I need wood first, chat!",
            "reason": "No logs in inventory.",
        }
    )
    env = with_env(VTUBER_LLM_BASE_URL=base_url, VTUBER_LLM_MODEL="stub-model", VTUBER_LLM_MAX_TOKENS="88")
    try:
        fallback = ActionRequest(action="status", args={}, speech="Checking status.", reason="fallback")
        planned, metadata = plan_agent_action(
            mission="survive and progress",
            current_objective="collect_wood",
            bot_status={"ok": True, "inventory": []},
            inventory_summary={},
            recent_memory=[],
            last_failure=None,
            fallback_action=fallback,
        )
        assert planned.action == "collect_wood"
        assert planned.args == {"count": 4}
        assert metadata["fallback_used"] is False
        assert metadata["model"] == "stub-model"
        assert metadata["prompt_size_chars"] > 0
        assert metadata["llm_latency_sec"] >= 0
        assert StubHandler.captured_body["max_tokens"] == 88
        user_content = json.loads(StubHandler.captured_body["messages"][1]["content"])
        assert "bot_status" not in user_content
        assert len(user_content["memory"]) == 0
    finally:
        StubHandler.response_content = json.dumps(
            {
                "action": "jump",
                "args": {},
                "speech": "Jumping.",
                "reason": "stubbed model response",
            }
        )
        restore_env(env)
        server.shutdown()

    print("manual llm provider tests passed")


if __name__ == "__main__":
    main()
