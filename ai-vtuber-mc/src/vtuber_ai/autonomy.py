import asyncio
from typing import Any

from httpx import HTTPError, TimeoutException

from vtuber_ai.agent_state import build_agent_state, summarize_status
from vtuber_ai.game_brain import AUTONOMOUS_ALLOWED_ACTIONS, choose_next_action
from vtuber_ai.memory import get_recent_agent_ticks, get_recent_events, log_agent_tick, log_event
from vtuber_ai.mineflayer_client import get_bot_status, get_bridge_actions, send_action
from vtuber_ai.policy import PolicyError, validate_action
from vtuber_ai.schemas import ActionRequest, ActionResult, AgentLiveRequest, AgentTickRequest
from vtuber_ai.tts import emit_speech_text
from vtuber_ai.verifier import verify_action


async def run_agent_tick(request: AgentTickRequest) -> dict[str, Any]:
    (before_status, status_error), (bridge_actions, bridge_fetch_error) = await asyncio.gather(
        _safe_get_status(),
        _safe_get_bridge_actions(),
    )
    recent_memory = get_recent_events(limit=30)
    recent_ticks = get_recent_agent_ticks(limit=20)
    state = build_agent_state(
        bot_status=before_status,
        recent_memory=recent_memory,
        recent_ticks=recent_ticks,
    )

    bridge_actions_set = frozenset(bridge_actions)
    if bridge_fetch_error or not bridge_actions_set:
        effective_allowed: tuple[str, ...] = AUTONOMOUS_ALLOWED_ACTIONS
        bridge_missing: list[str] = []
    else:
        effective_allowed = tuple(a for a in AUTONOMOUS_ALLOWED_ACTIONS if a in bridge_actions_set)
        bridge_missing = sorted(a for a in AUTONOMOUS_ALLOWED_ACTIONS if a not in bridge_actions_set)

    decision, planner_info = choose_next_action(
        state=state,
        memory=recent_memory,
        mission=request.mission,
        allowed_actions=effective_allowed,
        planner=request.planner,
    )

    planner_info["bridge_supported_actions_count"] = len(bridge_actions_set) if not bridge_fetch_error else None
    if bridge_missing:
        planner_info["bridge_missing_actions"] = bridge_missing

    if bridge_actions_set and decision.action not in bridge_actions_set:
        rejected_action = decision.action
        decision, fallback_info = choose_next_action(
            state=state,
            memory=recent_memory,
            mission=request.mission,
            allowed_actions=effective_allowed,
            planner="fallback",
        )
        planner_info = {
            **planner_info,
            **{k: v for k, v in fallback_info.items() if k not in planner_info},
            "fallback_used": True,
            "fallback_reason": f"LLM chose action not supported by bridge: {rejected_action}.",
        }

    action_request = ActionRequest(
        action=decision.action,
        args=decision.args,
        speech=decision.speech,
        reason=f"{decision.reason} Objective: {decision.objective}",
    )

    if status_error and action_request.action != "status":
        action_request = ActionRequest(
            action="status",
            args={},
            speech="I need to reconnect my view of the world.",
            reason=f"Bridge status was unavailable before planning: {status_error}",
        )
        planner_info = {
            **planner_info,
            "fallback_used": True,
            "fallback_reason": "Bridge status unavailable before action.",
        }

    try:
        action_request = validate_action(action_request)
    except PolicyError as exc:
        action_result = ActionResult(ok=False, action=action_request.action, error=str(exc))
        verifier = {
            "success": False,
            "evidence": {
                "policy_error": str(exc),
                "mineflayer_contacted": False,
            },
            "failure_type": "invalid_action",
            "recommendation": "Choose a whitelisted action with only supported args.",
        }
        after_status = before_status
        _remember_tick(request, decision.objective, action_request, action_result, before_status, after_status, verifier)
        return _tick_record(
            ok=False,
            request=request,
            decision=decision,
            planner_info=planner_info,
            action_request=action_request,
            action_result=action_result,
            before_status=before_status,
            after_status=after_status,
            verifier=verifier,
        )

    if action_request.speech:
        emit_speech_text(action_request.speech)

    try:
        action_result = await send_action(action_request)
    except TimeoutException:
        action_result = ActionResult(
            ok=False,
            action=action_request.action,
            error="Mineflayer bridge action timed out.",
        )
    except HTTPError:
        action_result = ActionResult(
            ok=False,
            action=action_request.action,
            error="Mineflayer bridge request failed.",
        )

    after_status, after_status_error = await _safe_get_status()
    if after_status_error:
        after_status = before_status

    verifier = verify_action(before_status, after_status, action_request, action_result)
    if after_status_error:
        verifier["failure_type"] = "bridge_error"
        verifier["recommendation"] = "Mineflayer bridge status was unreachable after the action."
        verifier["evidence"]["after_status_error"] = after_status_error

    _remember_tick(request, decision.objective, action_request, action_result, before_status, after_status, verifier)

    return _tick_record(
        ok=bool(action_result.ok and verifier["success"]),
        request=request,
        decision=decision,
        planner_info=planner_info,
        action_request=action_request,
        action_result=action_result,
        before_status=before_status,
        after_status=after_status,
        verifier=verifier,
    )


async def run_agent_live(request: AgentLiveRequest) -> dict[str, Any]:
    ticks: list[dict[str, Any]] = []
    repeated_failure_detected = False
    stopped_for_danger = False
    bridge_unreachable = False
    previous_failure_action: str | None = None
    repeated_failure_count = 0

    for index in range(request.max_ticks):
        tick_request = AgentTickRequest(
            mission=request.mission,
            user=request.user,
            planner=request.planner,
            allow_autonomy=True,
        )
        tick = await run_agent_tick(tick_request)
        tick["tick"] = index + 1
        ticks.append(tick)

        verifier = tick.get("verifier", {})
        action_model = tick.get("action")
        action = action_model.action if isinstance(action_model, ActionRequest) else None

        if verifier.get("failure_type") == "bridge_error":
            bridge_unreachable = True
            break

        after_summary = summarize_status(tick.get("after_status"))
        if _danger_without_recovery(after_summary):
            stopped_for_danger = True
            break

        if tick.get("ok"):
            repeated_failure_count = 0
            previous_failure_action = None
        elif action == previous_failure_action:
            repeated_failure_count += 1
        else:
            previous_failure_action = action
            repeated_failure_count = 1

        if repeated_failure_count >= 3:
            repeated_failure_detected = True
            break

        if index < request.max_ticks - 1 and request.tick_delay_sec > 0:
            await asyncio.sleep(request.tick_delay_sec)

    return {
        "ok": bool(ticks and ticks[-1].get("ok")),
        "mission": request.mission,
        "user": request.user,
        "planner": request.planner,
        "requested_max_ticks": request.max_ticks,
        "ticks_run": len(ticks),
        "stopped_for_danger": stopped_for_danger,
        "repeated_failure_detected": repeated_failure_detected,
        "bridge_unreachable": bridge_unreachable,
        "ticks": ticks,
    }


async def current_agent_state() -> dict[str, Any]:
    bot_status, status_error = await _safe_get_status()
    recent_memory = get_recent_events(limit=20)
    recent_ticks = get_recent_agent_ticks(limit=10)
    state = build_agent_state(
        bot_status=bot_status,
        recent_memory=recent_memory,
        recent_ticks=recent_ticks,
    )
    if status_error:
        state["status_error"] = status_error
    return state


async def _safe_get_status() -> tuple[dict[str, Any], str | None]:
    try:
        return await get_bot_status(), None
    except TimeoutException:
        return {"ok": False, "unavailable": True}, "Mineflayer bridge status timed out."
    except HTTPError:
        return {"ok": False, "unavailable": True}, "Mineflayer bridge status request failed."


async def _safe_get_bridge_actions() -> tuple[list[str], str | None]:
    try:
        return await get_bridge_actions(), None
    except TimeoutException:
        return [], "Bridge actions request timed out."
    except HTTPError:
        return [], "Bridge actions request failed."


def _remember_tick(
    request: AgentTickRequest,
    objective: str,
    action_request: ActionRequest,
    action_result: ActionResult,
    before_status: dict[str, Any],
    after_status: dict[str, Any],
    verifier: dict[str, Any],
) -> None:
    before_summary = summarize_status(before_status)
    after_summary = summarize_status(after_status)
    message = f"agent tick mission='{request.mission}' objective='{objective}' planner='{request.planner}'"

    log_event(request.user, message, action_request, action_result)
    log_agent_tick(
        user=request.user,
        mission=request.mission,
        objective=objective,
        action_request=action_request,
        action_result=action_result,
        before_state=before_summary,
        after_state=after_summary,
        verifier_result=verifier,
    )


def _tick_record(
    *,
    ok: bool,
    request: AgentTickRequest,
    decision: Any,
    planner_info: dict[str, Any],
    action_request: ActionRequest,
    action_result: ActionResult,
    before_status: dict[str, Any],
    after_status: dict[str, Any],
    verifier: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": ok,
        "mission": request.mission,
        "user": request.user,
        "planner": planner_info,
        "source": planner_info.get("source"),
        "fallback_used": planner_info.get("fallback_used", False),
        "args_sanitized": planner_info.get("args_sanitized", False),
        "removed_arg_keys": planner_info.get("removed_arg_keys", []),
        "last_failure_included": planner_info.get("last_failure_included", False),
        "available_actions_count": planner_info.get("available_actions_count"),
        "llm_latency_sec": planner_info.get("llm_latency_sec", 0.0),
        "prompt_size_chars": planner_info.get("prompt_size_chars", 0),
        "objective": decision.objective,
        "mood": decision.mood,
        "action": action_request,
        "result": action_result,
        "verifier": verifier,
        "before_status": before_status,
        "after_status": after_status,
    }


def _danger_without_recovery(summary: dict[str, Any]) -> bool:
    health = summary.get("health")
    return isinstance(health, (int, float)) and health <= 6 and not summary.get("has_food")
