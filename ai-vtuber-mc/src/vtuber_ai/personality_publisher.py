"""Best-effort personality engine publisher.

Sends a compact BrainTickEvent JSON payload to an optional personality
service after each /agent/tick completes.  Never raises — all failures
are swallowed and logged at DEBUG level so gameplay is never blocked.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SEC: float = 0.75
_MAX_STRING_LEN: int = 1000
_MAX_RAW_BYTES: int = 8192

_STATION_BLOCK_KEYS: frozenset[str] = frozenset({
    "crafting_table", "furnace", "chest", "barrel",
    "blast_furnace", "smoker", "anvil",
})


def _trunc(v: Any) -> Any:
    """Truncate strings that exceed _MAX_STRING_LEN; pass other types through."""
    if isinstance(v, str) and len(v) > _MAX_STRING_LEN:
        return v[:_MAX_STRING_LEN]
    return v


def _bounded_raw(obj: Any, max_bytes: int = _MAX_RAW_BYTES) -> Any:
    """Return obj when its JSON size fits within max_bytes; else a size marker."""
    try:
        serialized = json.dumps(obj, default=str)
    except Exception:
        return {"_error": "not_serializable"}
    size = len(serialized.encode())
    if size <= max_bytes:
        return obj
    return {"_truncated": True, "_size_bytes": size}


def _compact_verifier(verifier: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the fields the personality engine actually needs from the verifier.

    Always preserves ``success`` and ``failure_type`` regardless of size.
    Bounds ``evidence`` and ``failed_because`` individually so they don't
    crowd out the scalar fields.
    """
    if not verifier:
        return None
    return {
        "success": verifier.get("success"),
        "failure_type": verifier.get("failure_type"),
        "stop_reason": verifier.get("stop_reason"),
        "recommendation": verifier.get("recommendation"),
        "failed_because": _bounded_raw(verifier.get("failed_because") or [], max_bytes=512),
        "evidence": _bounded_raw(verifier.get("evidence") or {}, max_bytes=512),
    }


def _extract_failed_requirements(
    verifier: dict[str, Any],
    outer_result: dict[str, Any],
) -> list[Any]:
    """Return a list of failed requirement objects from verifier or result."""
    # verifier.failed_because is the canonical source
    fb = verifier.get("failed_because")
    if isinstance(fb, list) and fb:
        return fb

    # Fall back to inner result.failed_because
    inner = outer_result.get("result") or {}
    if isinstance(inner, dict):
        fb2 = inner.get("failed_because")
        if isinstance(fb2, list) and fb2:
            return fb2

    return []


def _extract_nearby_stations(after_status: dict[str, Any]) -> dict[str, Any] | None:
    """Extract station-relevant blocks from after_status.nearbyBlocks."""
    nearby = after_status.get("nearbyBlocks")
    if not isinstance(nearby, dict):
        return None
    result: dict[str, Any] = {}
    for key in _STATION_BLOCK_KEYS:
        block = nearby.get(key)
        if block is not None:
            if isinstance(block, dict):
                result[key] = {
                    k: v for k, v in block.items()
                    if k in {"name", "distance", "position"}
                }
            else:
                result[key] = block
    return result if result else None


def build_tick_event(
    tick_id: int,
    tick: dict[str, Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build a compact BrainTickEvent dict from an /agent/tick response."""
    # --- action / args / reason ---
    action_obj = tick.get("action") or {}
    if isinstance(action_obj, dict):
        action_name: str = str(action_obj.get("action") or "?")
        action_args: dict[str, Any] = action_obj.get("args") or {}
        reason: str = str(action_obj.get("reason") or "")
    else:
        action_name = str(action_obj) if action_obj else "?"
        action_args = {}
        reason = ""

    # --- result payload unwrapping ---
    # ActionResult serialises as {"ok":…, "action":…, "result":{…inner…}, "error":…}
    outer_result = tick.get("result") or {}
    if not isinstance(outer_result, dict):
        outer_result = {}
    inner_result = outer_result.get("result")
    payload: dict[str, Any] = inner_result if isinstance(inner_result, dict) else outer_result

    failure_type = payload.get("failure_type") or outer_result.get("failure_type")
    stop_reason = payload.get("stop_reason") or outer_result.get("stop_reason")
    error = outer_result.get("error") or payload.get("error")

    collected_raw = (
        payload.get("collected")
        if payload.get("collected") is not None
        else payload.get("count")
    )
    inventory = payload.get("inventory")
    position = payload.get("position")

    # --- verifier fills in missing failure/stop and provides evidence ---
    verifier_raw = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else {}
    failure_type = failure_type or verifier_raw.get("failure_type")
    stop_reason = stop_reason or verifier_raw.get("stop_reason")

    # --- after_status for health / hunger / fallback position / stations ---
    after_status = tick.get("after_status") if isinstance(tick.get("after_status"), dict) else {}
    health = after_status.get("health")
    hunger = after_status.get("food") or after_status.get("hunger")
    if position is None:
        position = after_status.get("position")

    # --- planner info ---
    planner_info = tick.get("planner") if isinstance(tick.get("planner"), dict) else {}

    # --- derived raw fields for personality engine ---
    fallback_reason: str | None = planner_info.get("fallback_reason")
    failed_requirements = _extract_failed_requirements(verifier_raw, outer_result)
    nearby_stations = _extract_nearby_stations(after_status)

    # Inventory summary: prefer after_status top-level inventory over result payload
    inventory_summary = after_status.get("inventory") or inventory

    return {
        "tick_id": tick_id,
        "run_id": run_id,
        "mission": _trunc(str(tick.get("mission") or "")),
        "objective": _trunc(str(tick.get("objective") or "")),
        "action": action_name,
        "args": action_args,
        "ok": bool(tick.get("ok")),
        "failure": _trunc(str(failure_type)) if failure_type else None,
        "stop": _trunc(str(stop_reason)) if stop_reason else None,
        "error": _trunc(str(error)) if error else None,
        "collected": int(collected_raw) if isinstance(collected_raw, (int, float)) else None,
        "reason": _trunc(reason),
        "verifier": _compact_verifier(verifier_raw),
        "inventory": _bounded_raw(inventory, max_bytes=2048) if inventory is not None else None,
        "position": position,
        "health": health,
        "hunger": hunger,
        "raw": {
            "planner": _bounded_raw(planner_info, max_bytes=4096),
            "result": _bounded_raw(outer_result, max_bytes=4096),
            "fallback_reason": _trunc(fallback_reason) if fallback_reason else None,
            "failed_requirements": _bounded_raw(failed_requirements, max_bytes=1024),
            "nearby_stations": _bounded_raw(nearby_stations, max_bytes=512) if nearby_stations else None,
            "inventory_summary": _bounded_raw(inventory_summary, max_bytes=1024) if inventory_summary is not None else None,
        },
    }


def publish_tick_event(
    event: dict[str, Any],
    url: str,
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> bool:
    """POST event JSON to url.  Returns True on success, False on any failure.

    Never raises.  The timeout enforces that a slow or absent personality
    service cannot block gameplay — keep it short (default 0.75 s).
    """
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(url, json=event)
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.debug("personality publish failed url=%s: %s", url, exc)
        return False
