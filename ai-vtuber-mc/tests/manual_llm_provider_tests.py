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
    captured_auth = None
    reject_param_once: str | None = None
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
        StubHandler.captured_auth = self.headers.get("Authorization")
        if StubHandler.reject_param_once and StubHandler.reject_param_once in StubHandler.captured_body:
            param = StubHandler.reject_param_once
            StubHandler.reject_param_once = None
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": f"Unsupported parameter: {param}"}}).encode("utf-8"))
            return
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
    env = with_env(VTUBER_LLM_PROVIDER="fake", VTUBER_LLM_BASE_URL=None)
    try:
        assert plan_action("follow me", "rin").action == "follow_player"
    finally:
        restore_env(env)

    server, base_url = start_stub()
    env = with_env(VTUBER_LLM_PROVIDER="local_openai_compatible", VTUBER_LLM_BASE_URL=base_url)
    try:
        planned = plan_action("please do something", "rin")
        assert planned.action == "jump"
        assert planned.reason == "stubbed model response"
    finally:
        restore_env(env)
        server.shutdown()

    server, base_url = start_stub()
    StubHandler.response_content = "not json"
    env = with_env(VTUBER_LLM_PROVIDER="local_openai_compatible", VTUBER_LLM_BASE_URL=base_url)
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
    env = with_env(VTUBER_LLM_PROVIDER="local_openai_compatible", VTUBER_LLM_BASE_URL=base_url, VTUBER_LLM_MODEL="stub-model", VTUBER_LLM_MAX_TOKENS="88")
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
        assert metadata["llm_provider"] == "local_openai_compatible"
        assert metadata["llm_model"] == "stub-model"
        assert metadata["llm_base_url_host"].startswith("127.0.0.1:")
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

    server, base_url = start_stub()
    StubHandler.reject_param_once = "max_tokens"
    StubHandler.response_content = json.dumps(
        {
            "action": "status",
            "args": {},
            "speech": "Checking.",
            "reason": "compat retry",
        }
    )
    env = with_env(
        VTUBER_LLM_PROVIDER="openai",
        VTUBER_OPENAI_BASE_URL=base_url,
        VTUBER_LLM_MODEL=None,
        VTUBER_OPENAI_MODEL="gpt-5.5",
        OPENAI_API_KEY="test-secret",
    )
    try:
        planned = plan_action("please do something", "rin")
        assert planned.action == "status"
        assert StubHandler.captured_body["max_completion_tokens"] == 160
        assert "max_tokens" not in StubHandler.captured_body
        assert StubHandler.captured_auth == "Bearer test-secret"
    finally:
        StubHandler.response_content = json.dumps(
            {
                "action": "jump",
                "args": {},
                "speech": "Jumping.",
                "reason": "stubbed model response",
            }
        )
        StubHandler.reject_param_once = None
        restore_env(env)
        server.shutdown()

    print("manual llm provider tests passed")


if __name__ == "__main__":
    main()
