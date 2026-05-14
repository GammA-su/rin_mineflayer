import os
from typing import Any

import httpx

from vtuber_ai.schemas import ActionRequest, ActionResult


class MineflayerBridgeClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("MINEFLAYER_BRIDGE_URL") or "http://localhost:3001").rstrip("/")
        self.action_timeout_seconds = _float_env("MINEFLAYER_ACTION_TIMEOUT_SECONDS", 180.0)
        self.status_timeout_seconds = _float_env("MINEFLAYER_STATUS_TIMEOUT_SECONDS", 10.0)

    async def send_action(self, action: ActionRequest) -> ActionResult:
        timeout = httpx.Timeout(self.action_timeout_seconds, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/action",
                json=action.model_dump(),
            )
            data = _json_response(response)

        return ActionResult(
            ok=bool(data.get("ok")),
            action=action.action,
            result=data.get("result") or {},
            error=data.get("error"),
        )

    async def get_bot_status(self) -> dict:
        timeout = httpx.Timeout(self.status_timeout_seconds, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{self.base_url}/status")
            response.raise_for_status()
            return _json_response(response)

    async def get_bridge_actions(self) -> list[str]:
        timeout = httpx.Timeout(self.status_timeout_seconds, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{self.base_url}/actions")
            response.raise_for_status()
            data = _json_response(response)
        actions = data.get("actions")
        if not isinstance(actions, list):
            return []
        return [a for a in actions if isinstance(a, str)]


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default

    try:
        value = float(raw)
    except ValueError:
        return default

    return value if value > 0 else default


_default_client = MineflayerBridgeClient()


async def send_action(action: ActionRequest) -> ActionResult:
    return await _default_client.send_action(action)


async def get_bot_status() -> dict:
    return await _default_client.get_bot_status()


async def get_bridge_actions() -> list[str]:
    return await _default_client.get_bridge_actions()


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        return {"ok": False, "error": "Mineflayer bridge returned an invalid JSON response."}

    if not isinstance(data, dict):
        return {"ok": False, "error": "Mineflayer bridge returned an invalid response."}

    return data
