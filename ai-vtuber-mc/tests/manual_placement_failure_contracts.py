"""Manual smoke for placement failure contracts.

Run with a Mineflayer bridge listening on NODE_URL, for example:
    uv run python tests/manual_placement_failure_contracts.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


NODE_URL = os.environ.get("NODE_URL", "http://localhost:3001").rstrip("/")


def post_action(action: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps({"action": action, "args": args or {}}).encode("utf-8")
    request = urllib.request.Request(
        f"{NODE_URL}/action",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            raise RuntimeError(f"{action} HTTP {exc.code}: {payload}") from exc


def assert_failure_contract(action: str, response: dict[str, Any]) -> None:
    if response.get("ok") is True:
        return

    result = response.get("result")
    assert isinstance(result, dict), f"{action}: failure missing result object: {response}"
    for key in ("failure_type", "stop_reason", "suggested_next_action", "can_retry", "needed", "diagnostics"):
        assert key in result, f"{action}: failure missing {key}: {response}"
    assert isinstance(result["diagnostics"], dict), f"{action}: diagnostics must be an object"


def main() -> int:
    actions: list[tuple[str, dict[str, Any]]] = [
        ("place_crafting_table", {}),
        ("place_furnace", {}),
        ("place_chest", {}),
        ("place_torch", {}),
        ("place_block", {"item": "dirt", "mode": "nearby"}),
        ("place_water", {"mode": "nearby"}),
        ("place_lava", {"mode": "controlled_source"}),
    ]

    failures = 0
    for action, args in actions:
        response = post_action(action, args)
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        print(
            json.dumps(
                {
                    "action": action,
                    "ok": response.get("ok"),
                    "error": response.get("error"),
                    "failure_type": result.get("failure_type"),
                    "stop_reason": result.get("stop_reason"),
                    "suggested_next_action": result.get("suggested_next_action"),
                },
                separators=(",", ":"),
            )
        )
        try:
            assert_failure_contract(action, response)
        except AssertionError as exc:
            failures += 1
            print(str(exc), file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
