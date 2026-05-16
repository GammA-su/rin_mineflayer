from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def request_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: float = 10.0) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _decode_response(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _decode_response(exc.read())


def _decode_response(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "action": "unknown", "result": {"failure_type": "invalid_json"}, "error": raw[:200].decode("utf-8", errors="replace")}
    if not isinstance(data, dict):
        return {"ok": False, "action": "unknown", "result": {"failure_type": "invalid_response"}, "error": "Response was not an object."}
    return data


def response_contract_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "ok" not in data or not isinstance(data.get("ok"), bool):
        errors.append("missing bool field: ok")
    if "action" not in data or not isinstance(data.get("action"), str):
        errors.append("missing string field: action")
    if "result" not in data or not isinstance(data.get("result"), dict):
        errors.append("missing object field: result")
    if "error" not in data:
        errors.append("missing nullable field: error")
    if data.get("ok") is False:
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        if not result.get("failure_type") and not result.get("stop_reason"):
            errors.append("failure response should include result.failure_type or result.stop_reason where possible")
    return errors


def implemented_actions(base_url: str) -> list[str]:
    try:
        _status, metadata = request_json("GET", f"{base_url}/actions_metadata")
        actions = metadata.get("actions")
        if isinstance(actions, list):
            names = [
                item.get("name")
                for item in actions
                if isinstance(item, dict) and item.get("implemented") is True and isinstance(item.get("name"), str)
            ]
            if names:
                return sorted(set(names))
    except Exception:
        pass

    _status, data = request_json("GET", f"{base_url}/actions")
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise AssertionError("/actions did not return an actions list")
    return sorted({action for action in actions if isinstance(action, str)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual response-contract probe for Mineflayer body skills.")
    parser.add_argument(
        "--bridge-url",
        default=os.getenv("MINEFLAYER_BRIDGE_URL", "http://localhost:3001").rstrip("/"),
        help="Node bridge base URL.",
    )
    parser.add_argument(
        "--require-bridge",
        action="store_true",
        help="Fail instead of skipping when the Node bridge is unavailable.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout seconds.",
    )
    args = parser.parse_args()
    base_url = args.bridge_url.rstrip("/")

    try:
        actions = implemented_actions(base_url)
    except Exception as exc:
        message = f"Mineflayer bridge unavailable at {base_url}: {exc}"
        if args.require_bridge:
            raise AssertionError(message) from exc
        print(f"SKIP: {message}")
        return

    failures: list[str] = []

    status_code, status_response = request_json("POST", f"{base_url}/action", {"action": "status", "args": {}}, timeout=args.timeout)
    status_errors = response_contract_errors(status_response)
    if status_code >= 500:
        status_errors.append(f"unexpected HTTP {status_code}")
    if status_errors:
        failures.append(f"status success probe: {status_errors}; response={status_response}")

    for action in actions:
        # Unknown args force validation failure before any body skill executes.
        status_code, response = request_json(
            "POST",
            f"{base_url}/action",
            {"action": action, "args": {"__contract_probe": True}},
            timeout=args.timeout,
        )
        errors = response_contract_errors(response)
        if status_code >= 500:
            errors.append(f"unexpected HTTP {status_code}")
        if response.get("action") != action:
            errors.append(f"response action mismatch: expected {action!r}, got {response.get('action')!r}")
        if errors:
            failures.append(f"{action}: {errors}; response={response}")

    if failures:
        raise AssertionError("\n".join(failures))

    print(f"manual body skill contracts passed for {len(actions)} implemented actions")


if __name__ == "__main__":
    main()
