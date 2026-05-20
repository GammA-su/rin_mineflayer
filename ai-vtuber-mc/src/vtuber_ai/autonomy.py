import asyncio
import os
from typing import Any

from httpx import HTTPError, TimeoutException

from vtuber_ai.agent_state import build_agent_state, summarize_status
from vtuber_ai.world_memory import (
    STALE_WORKSPACE_CONFIDENCE_THRESHOLD,
    get_death_state,
    get_relevant_known_places,
    get_waypoint,
    list_known_places,
    list_waypoints,
    mark_workspace_unreachable,
    nearest_workspace,
    record_death_if_new,
    remember_workspace,
    update_death_recovery_state,
    update_workspace_station,
    upsert_waypoint,
)
from vtuber_ai.game_brain import (
    AUTONOMOUS_ALLOWED_ACTIONS,
    build_repetition_warning,
    choose_next_action,
    find_blocked_family,
    hard_block_repetitions_enabled,
)
from vtuber_ai.memory import get_recent_agent_ticks, get_recent_events, log_agent_tick, log_death_event, log_event
from vtuber_ai.milestones import build_milestone_state, newly_completed
from vtuber_ai.mineflayer_client import get_bot_status, get_bridge_actions, send_action
from vtuber_ai.policy import PolicyError, validate_action
from vtuber_ai.schemas import ActionRequest, ActionResult, AgentLiveRequest, AgentTickRequest
from vtuber_ai.tts import emit_speech_text
from vtuber_ai.verifier import verify_action

# Actions handled entirely in Python — not forwarded to the Node bridge.
# These are always available regardless of bridge action list.
PYTHON_SIDE_ACTIONS = frozenset({"return_to_workspace", "return_to_known_position", "describe_actions"})


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
    before_milestones = _build_milestones(before_status, recent_memory, recent_ticks)

    bridge_actions_set = frozenset(bridge_actions)
    if bridge_fetch_error or not bridge_actions_set:
        effective_allowed: tuple[str, ...] = AUTONOMOUS_ALLOWED_ACTIONS
        bridge_missing: list[str] = []
    else:
        # Python-side actions don't require Node bridge support — always include them.
        effective_allowed = tuple(
            a for a in AUTONOMOUS_ALLOWED_ACTIONS
            if a in bridge_actions_set or a in PYTHON_SIDE_ACTIONS
        )
        bridge_missing = sorted(
            a for a in AUTONOMOUS_ALLOWED_ACTIONS
            if a not in bridge_actions_set and a not in PYTHON_SIDE_ACTIONS
        )

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

    if bridge_actions_set and decision.action not in bridge_actions_set and decision.action not in PYTHON_SIDE_ACTIONS:
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
        error_details = dict(getattr(exc, "details", {}) or {})
        action_result = ActionResult(ok=False, action=action_request.action, result=error_details, error=str(exc))
        failure_type = error_details.get("failure_type", "invalid_action")
        verifier = {
            "success": False,
            "evidence": {
                "policy_error": str(exc),
                "mineflayer_contacted": False,
                **error_details,
            },
            "failure_type": failure_type,
            "stop_reason": error_details.get("stop_reason"),
            "possible_next_actions": error_details.get("possible_next_actions"),
            "failed_because": error_details.get("failed_because") or [],
            "repeatable_now": error_details.get("repeatable_now", False),
            "repeat_condition": error_details.get("repeat_condition"),
            "recommendation": "Choose a supported craft alias or one of the suggested canonical actions."
            if failure_type == "invalid_action_args"
            else "Choose a whitelisted action with only supported args.",
        }
        after_status = before_status
        after_milestones = before_milestones
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
            milestones=after_milestones,
            newly_completed_milestones=[],
        )

    # --- Pre-execution blocked-family check ---
    # If the LLM chose an action in a blocked family and state has not changed,
    # synthesize a blocked_repetition failure without touching the Node bridge.
    _blocked_rec = find_blocked_family(
        action_request.action,
        action_request.args if isinstance(action_request.args, dict) else {},
        recent_ticks,
        state.get("summary") if isinstance(state.get("summary"), dict) else {},
    )
    if _blocked_rec is not None:
        if hard_block_repetitions_enabled():
            # Hard-block mode: synthesize blocked_repetition without touching the Node bridge.
            _baf_result: dict[str, Any] = {
                "failure_type": "blocked_repetition",
                "blocked_family": _blocked_rec["family"],
                "unblock_condition": _blocked_rec.get("unblock_condition"),
                "failed_because": _blocked_rec.get("failed_because") or [],
                "repeatable_now": False,
                "skipped_execution": True,
                **({"blocked_key": _blocked_rec["blocked_key"]} if _blocked_rec.get("blocked_key") else {}),
                **({"blocked_scope": _blocked_rec["blocked_scope"]} if _blocked_rec.get("blocked_scope") else {}),
                **({"blocked_expires_in_ticks": _blocked_rec["blocked_expires_in_ticks"]} if _blocked_rec.get("blocked_expires_in_ticks") is not None else {}),
                **({"unblock_conditions": _blocked_rec["unblock_conditions"]} if _blocked_rec.get("unblock_conditions") else {}),
            }
            action_result = ActionResult(
                ok=False,
                action=action_request.action,
                result=_baf_result,
                error="Skipped blocked repeated action because requirements/environment have not changed.",
            )
            _baf_verifier: dict[str, Any] = {
                "success": False,
                "failure_type": "blocked_repetition",
                "failed_because": _baf_result["failed_because"],
                "repeatable_now": False,
                "repeat_condition": _baf_result.get("unblock_condition"),
                "evidence": {
                    "action": action_request.action,
                    "mineflayer_contacted": False,
                    "skipped_execution": True,
                    "blocked_family": _blocked_rec["family"],
                    "unblock_condition": _blocked_rec.get("unblock_condition"),
                },
                "recommendation": (
                    f"Action family '{_blocked_rec['family']}' is blocked. "
                    f"Choose a different action or satisfy: {_blocked_rec.get('unblock_condition')}"
                ),
            }
            after_status = before_status
            after_milestones = before_milestones
            planner_info["action_execution_skipped"] = True
            planner_info["skipped_reason"] = "blocked_action_family"
            planner_info["blocked_family"] = _blocked_rec["family"]
            planner_info["unblock_condition"] = _blocked_rec.get("unblock_condition")
            planner_info["blocked_family_failure_count"] = _blocked_rec.get("failure_count")
            if _blocked_rec.get("blocked_key"):
                planner_info["blocked_key"] = _blocked_rec["blocked_key"]
            if _blocked_rec.get("blocked_expires_in_ticks") is not None:
                planner_info["blocked_expires_in_ticks"] = _blocked_rec["blocked_expires_in_ticks"]
            _remember_tick(request, decision.objective, action_request, action_result, before_status, after_status, _baf_verifier)
            return _tick_record(
                ok=False,
                request=request,
                decision=decision,
                planner_info=planner_info,
                action_request=action_request,
                action_result=action_result,
                before_status=before_status,
                after_status=after_status,
                verifier=_baf_verifier,
                milestones=after_milestones,
                newly_completed_milestones=[],
            )
        else:
            # Advisory mode (VTUBER_HARD_BLOCK_REPETITIONS=0): expose warning to planner
            # but do NOT skip execution. The LLM may still choose the action.
            _warn_payload = build_repetition_warning(_blocked_rec)
            planner_info["repetition_warning"] = True
            planner_info["repetition_family"] = _blocked_rec["family"]
            planner_info["repetition_warning_payload"] = _warn_payload
            planner_info["repetition_failure_count"] = _blocked_rec.get("failure_count")

    if action_request.speech:
        emit_speech_text(action_request.speech)

    try:
        action_result = await _execute_action(action_request, before_status)
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

    # Persist mark_waypoint / set_home_position results to world_memory
    if action_request.action == "mark_waypoint" and action_result.ok:
        _persist_waypoint(action_request.args, action_result.result or {})
    if action_request.action == "set_home_position" and action_result.ok:
        _persist_home(action_result.result or {})
    if action_request.action == "recover_death_items" and isinstance(action_result.result, dict):
        death_state = action_result.result.get("death_state")
        failures = action_result.result.get("recovery_failures")
        if failures is None and isinstance(death_state, dict):
            failures = death_state.get("failures") or death_state.get("recovery_failures")
        if isinstance(failures, int):
            update_death_recovery_state(failures=failures)
    if action_request.action == "abandon_death_recovery" and action_result.ok:
        update_death_recovery_state(abandoned=True)

    after_status, after_status_error = await _safe_get_status()
    if after_status_error:
        after_status = before_status

    # Record death if bot_status reports a new death
    _maybe_record_death(after_status)
    _update_workspace_memory(action_request, action_result, after_status)
    try:
        _position = after_status.get("position") if isinstance(after_status, dict) else None
        _dimension = str(after_status.get("dimension") or "overworld") if isinstance(after_status, dict) else "overworld"
        _ws = nearest_workspace(_position, _dimension)
        planner_info["nearest_workspace_included"] = _ws is not None
        planner_info["workspace_memory_count"] = len(list_known_places(kind="workspace"))
    except Exception:
        pass
    after_milestones = _build_milestones(
        after_status,
        recent_memory,
        [_tick_as_history(action_request, action_result), *recent_ticks],
    )
    completed_now = newly_completed(before_milestones, after_milestones)

    verifier = verify_action(before_status, after_status, action_request, action_result)
    if after_status_error:
        verifier["failure_type"] = "bridge_error"
        verifier["recommendation"] = "Mineflayer bridge status was unreachable after the action."
        verifier["evidence"]["after_status_error"] = after_status_error

    # Advisory mode: if the action was in a warned family and still failed with no progress,
    # escalate the severity in planner_info so the next tick's LLM sees increased urgency.
    # Success clears naturally — the success tick removes the family from blocked detection.
    if _blocked_rec is not None and not hard_block_repetitions_enabled():
        if not verifier.get("success") and verifier.get("failure_type") not in {"", "none"}:
            planner_info["advisory_warning_escalated"] = True
            planner_info["advisory_warning_escalation_reason"] = (
                f"Action failed again with failure_type={verifier.get('failure_type')}; "
                "world state unchanged — consider a different approach."
            )

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
        milestones=after_milestones,
        newly_completed_milestones=completed_now,
    )


def _is_fatal_live_failure(verifier: dict[str, Any]) -> bool:
    """True only for actual bridge disconnections — not game-world failures."""
    ft = verifier.get("failure_type")
    return ft == "bridge_error"


def _is_recoverable_failure(verifier: dict[str, Any]) -> bool:
    """True for failures the bot can recover from without human intervention."""
    ft = verifier.get("failure_type")
    return ft not in {"bridge_error", "danger", "invalid_action", "not_ready"}


def _is_stale_workspace_loop(ticks: list[dict[str, Any]], window: int = 5, min_count: int = 2) -> bool:
    """True when recent ticks show repeated return_to_workspace path_timeout failures."""
    count = 0
    for tick in ticks[-window:]:
        if not isinstance(tick, dict):
            continue
        action = tick.get("action")
        action_name = action.action if hasattr(action, "action") else (action if isinstance(action, str) else None)
        if action_name != "return_to_workspace":
            continue
        if tick.get("ok"):
            count = 0  # success resets the streak
            continue
        result = tick.get("result")
        result_dict = result.result if hasattr(result, "result") else (result if isinstance(result, dict) else {})
        verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else {}
        ft = str(verifier.get("failure_type") or (result_dict or {}).get("failure_type") or "")
        stop_reason = str((result_dict or {}).get("stop_reason") or verifier.get("stop_reason") or "")
        if "path_timeout" in ft or "path_timeout" in stop_reason or "navigation_failed" in ft:
            count += 1
    return count >= min_count


async def run_agent_live(request: AgentLiveRequest) -> dict[str, Any]:
    max_consecutive = int(os.getenv("VTUBER_LIVE_MAX_CONSECUTIVE_FAILURES", "5"))
    stop_on_failure = request.stop_on_failure  # False by default → continuous mode

    ticks: list[dict[str, Any]] = []
    stopped_for_danger = False
    bridge_unreachable = False
    consecutive_failures = 0
    max_consecutive_failures_seen = 0
    live_stopped_reason: str | None = None
    early_stop_triggered_by: str | None = None
    stale_workspace_grace_used = False
    would_have_stopped = False
    would_have_stopped_reason: str | None = None

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

        verifier = tick.get("verifier") if isinstance(tick.get("verifier"), dict) else {}
        ok = bool(tick.get("ok"))

        # Fatal: actual bridge disconnection — stop immediately regardless of mode.
        if _is_fatal_live_failure(verifier):
            bridge_unreachable = True
            live_stopped_reason = "bridge_error"
            break

        # Fatal: bot in danger with no recovery path.
        after_summary = summarize_status(tick.get("after_status"))
        if _danger_without_recovery(after_summary):
            stopped_for_danger = True
            live_stopped_reason = "danger"
            break

        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            max_consecutive_failures_seen = max(max_consecutive_failures_seen, consecutive_failures)

        # Track whether old logic would have stopped here (for diagnostics).
        if not would_have_stopped and consecutive_failures >= max_consecutive:
            would_have_stopped = True
            would_have_stopped_reason = "max_consecutive_failures"

        # Stale workspace: mark unreachable once when the pattern is detected.
        if not stale_workspace_grace_used and _is_stale_workspace_loop(ticks):
            stale_workspace_grace_used = True
            try:
                after_st = tick.get("after_status") if isinstance(tick.get("after_status"), dict) else {}
                mark_workspace_unreachable(
                    after_st.get("position"),
                    str(after_st.get("dimension") or "overworld"),
                )
            except Exception:
                pass
            if stop_on_failure:
                consecutive_failures = 0  # legacy grace tick

        # Early stop only when explicitly requested (legacy / stop_on_failure=True mode).
        if stop_on_failure and consecutive_failures >= max_consecutive:
            early_stop_triggered_by = "stale_workspace_loop" if stale_workspace_grace_used else None
            live_stopped_reason = "max_consecutive_failures"
            break

        if index < request.max_ticks - 1 and request.tick_delay_sec > 0:
            await asyncio.sleep(request.tick_delay_sec)
    else:
        # Loop ran to completion — all max_ticks ticks executed.
        live_stopped_reason = "max_ticks_reached"

    last_verifier = ticks[-1].get("verifier") if ticks else {}
    if not isinstance(last_verifier, dict):
        last_verifier = {}
    failure_is_recoverable = _is_recoverable_failure(last_verifier) if ticks and not ticks[-1].get("ok") else True
    live_recovery_mode_active = max_consecutive_failures_seen >= max_consecutive and not stop_on_failure

    return {
        "ok": bool(ticks and ticks[-1].get("ok")),
        "mission": request.mission,
        "user": request.user,
        "planner": request.planner,
        "requested_max_ticks": request.max_ticks,
        "ticks_run": len(ticks),
        "stopped_for_danger": stopped_for_danger,
        "bridge_unreachable": bridge_unreachable,
        "consecutive_failures": consecutive_failures,
        "consecutive_failure_count": consecutive_failures,
        "max_consecutive_failures_seen": max_consecutive_failures_seen,
        "live_stopped_reason": live_stopped_reason,
        "stopped_reason": live_stopped_reason,
        "early_stop_triggered_by": early_stop_triggered_by,
        "stale_workspace_grace_used": stale_workspace_grace_used,
        "fatal_error": bridge_unreachable,
        "failure_is_recoverable": failure_is_recoverable,
        "early_stop_disabled": not stop_on_failure,
        "would_have_stopped": would_have_stopped,
        "would_have_stopped_reason": would_have_stopped_reason,
        "live_recovery_mode": live_recovery_mode_active,
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
    try:
        known_places = get_relevant_known_places(bot_status)
        state["known_places"] = known_places
        state["nearest_workspace"] = known_places.get("nearest_workspace")
    except Exception:
        pass
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
    milestones: dict[str, Any],
    newly_completed_milestones: list[str],
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
        "milestones": milestones,
        "newly_completed_milestones": newly_completed_milestones,
        "next_possible_milestones": milestones.get("next_possible_milestones", []),
    }


def _build_milestones(
    status: dict[str, Any],
    recent_memory: list[dict[str, Any]],
    recent_ticks: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_milestone_state(
        status=status,
        recent_memory=recent_memory,
        recent_ticks=recent_ticks,
        waypoints=list_waypoints(),
        death_state=get_death_state(),
    )


def _tick_as_history(action_request: ActionRequest, action_result: ActionResult) -> dict[str, Any]:
    return {
        "action": action_request.action,
        "ok": 1 if action_result.ok else 0,
        "result_json": action_result.result,
    }


def _persist_waypoint(args: dict[str, Any], result: dict[str, Any]) -> None:
    """Write a mark_waypoint action result into the persistent world_memory store."""
    label = args.get("label") or result.get("label")
    kind  = args.get("kind")  or result.get("kind", "general")
    x     = result.get("x")
    y     = result.get("y")
    z     = result.get("z")
    dim   = result.get("dimension", "overworld")
    if label and x is not None and y is not None and z is not None:
        try:
            upsert_waypoint(str(label), str(kind), float(x), float(y), float(z), str(dim))
        except Exception:
            pass


def _update_workspace_memory(
    action_request: ActionRequest,
    action_result: ActionResult,
    status: dict[str, Any] | None,
) -> None:
    if not isinstance(status, dict):
        return
    position = _position_from_result(action_result.result) or status.get("position")
    if not isinstance(position, dict):
        return
    dimension = str(status.get("dimension") or "overworld")
    nearby = status.get("nearbyBlocks") if isinstance(status.get("nearbyBlocks"), dict) else {}
    scan = action_result.result if action_request.action == "scan_workspace" and isinstance(action_result.result, dict) else {}

    has_crafting_table = _nearby_block_present(nearby, "crafting_table") or bool(scan.get("has_crafting_table"))
    has_furnace = _nearby_block_present(nearby, "furnace") or bool(scan.get("has_furnace"))
    has_chest = (
        _nearby_block_present(nearby, "chest")
        or _nearby_block_present(nearby, "barrel")
        or bool(scan.get("has_chest"))
    )
    safe = not bool(status.get("inLava")) and not _hostile_nearby(status)
    open_space_score = scan.get("open_space_score") if isinstance(scan.get("open_space_score"), (int, float)) else None

    try:
        if action_request.action in {"find_safe_workspace", "setup_workspace"} and action_result.ok:
            # setup_workspace result may have richer station metadata
            result = action_result.result if isinstance(action_result.result, dict) else {}
            ws_pos_raw = result.get("workspace_position")
            eff_position = ws_pos_raw if isinstance(ws_pos_raw, dict) else position
            remember_workspace(
                eff_position,
                dimension,
                has_crafting_table=bool(result.get("has_crafting_table")) or has_crafting_table,
                has_furnace=bool(result.get("has_furnace")) or has_furnace,
                has_chest=bool(result.get("has_chest")) or has_chest,
                safe=bool(result.get("safe", True)),
                notes="workspace established",
                open_space_score=open_space_score,
            )
        elif has_crafting_table or has_furnace or has_chest:
            remember_workspace(
                position,
                dimension,
                has_crafting_table=has_crafting_table,
                has_furnace=has_furnace,
                has_chest=has_chest,
                safe=safe,
                notes="stations observed nearby",
                open_space_score=open_space_score,
            )

        if action_result.ok and action_request.action in {"place_crafting_table", "place_furnace", "place_chest"}:
            update_workspace_station(action_request.action, position=position, dimension=dimension)
    except Exception:
        pass


def _position_from_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    position = result.get("position")
    return position if isinstance(position, dict) else None


def _nearby_block_present(nearby: dict[str, Any], key: str) -> bool:
    value = nearby.get(key)
    if isinstance(value, dict):
        return bool(value.get("name") or value.get("position"))
    return value is not None


def _hostile_nearby(status: dict[str, Any]) -> bool:
    entities = status.get("nearbyEntities")
    if not isinstance(entities, list):
        return False
    return any(isinstance(entity, dict) and entity.get("hostile") for entity in entities)


def _maybe_record_death(bot_status: dict[str, Any] | None) -> None:
    """Persist a death location reported by Node's getStatus.lastDeath."""
    if not isinstance(bot_status, dict):
        return
    last_death = bot_status.get("last_death") or bot_status.get("lastDeath")
    if not isinstance(last_death, dict):
        return
    x   = last_death.get("x")
    y   = last_death.get("y")
    z   = last_death.get("z")
    dim = last_death.get("dimension", "overworld")
    ts  = last_death.get("ts")
    cause = last_death.get("cause")
    inventory = last_death.get("inventory") if isinstance(last_death.get("inventory"), list) else []
    if x is not None and y is not None and z is not None and ts is not None:
        try:
            recorded = record_death_if_new(
                float(x),
                float(y),
                float(z),
                str(dim),
                int(ts),
                str(cause) if cause else None,
                inventory,
            )
            if recorded:
                log_death_event(
                    x=float(x),
                    y=float(y),
                    z=float(z),
                    dimension=str(dim),
                    source_ts_ms=int(ts),
                    cause=str(cause) if cause else None,
                    inventory=inventory,
                )
        except Exception:
            pass


def _danger_without_recovery(summary: dict[str, Any]) -> bool:
    health = summary.get("health")
    return isinstance(health, (int, float)) and health <= 6 and not summary.get("has_food")


# ---------------------------------------------------------------------------
# Python-side action dispatch
# ---------------------------------------------------------------------------

async def _execute_action(action_request: ActionRequest, before_status: dict[str, Any]) -> ActionResult:
    """Dispatch action to Node or handle Python-side before forwarding."""
    if action_request.action == "describe_actions":
        return _execute_describe_actions(action_request)
    if action_request.action == "return_to_workspace":
        return await _execute_return_to_workspace(action_request, before_status)
    if action_request.action == "return_to_known_position":
        return await _execute_return_to_known_position(action_request, before_status)
    return await send_action(action_request)


def _execute_describe_actions(action_request: ActionRequest) -> ActionResult:
    """Return detailed docs for the requested action names without calling Node."""
    from vtuber_ai.action_catalog import get_detailed_action_docs
    names = (action_request.args or {}).get("actions", [])
    if not isinstance(names, list):
        names = [str(names)]
    docs = get_detailed_action_docs(names)
    return ActionResult(
        ok=True,
        action="describe_actions",
        result={"actions_docs": docs, "count": len(docs), "requested": names},
    )


async def _execute_return_to_workspace(
    action_request: ActionRequest,
    before_status: dict[str, Any],
) -> ActionResult:
    """Look up nearest persistent workspace and translate to return_to_position."""
    position = before_status.get("position") if isinstance(before_status.get("position"), dict) else None
    dimension = str(before_status.get("dimension") or "overworld")

    workspace = nearest_workspace(position, dimension)

    if workspace is None:
        return ActionResult(
            ok=False,
            action=action_request.action,
            error="No known workspace in current dimension.",
            result={
                "failure_type": "no_known_workspace",
                "suggested_next_action": "setup_workspace",
                "can_retry": False,
            },
        )

    ws_dim = str(workspace.get("dimension") or "overworld")
    if ws_dim.replace("minecraft:", "") != dimension.replace("minecraft:", ""):
        return ActionResult(
            ok=False,
            action=action_request.action,
            error=f"Known workspace is in {ws_dim}, bot is in {dimension}.",
            result={
                "failure_type": "dimension_mismatch",
                "workspace_dimension": ws_dim,
                "current_dimension": dimension,
                "suggested_next_action": "setup_workspace",
                "can_retry": False,
            },
        )

    ws_position = {"x": int(workspace["x"]), "y": int(workspace["y"]), "z": int(workspace["z"])}
    ws_distance: float | None = None
    if position is not None:
        try:
            dx = float(workspace["x"]) - float(position.get("x", 0))
            dy = float(workspace["y"]) - float(position.get("y", 0))
            dz = float(workspace["z"]) - float(position.get("z", 0))
            ws_distance = round((dx * dx + dy * dy + dz * dz) ** 0.5, 1)
        except (TypeError, ValueError, KeyError):
            pass
    ws_confidence = float(workspace.get("confidence") or 0.5)
    maybe_stale = ws_confidence < STALE_WORKSPACE_CONFIDENCE_THRESHOLD

    # Already within usable workspace radius — navigation is a no-op.
    _WORKSPACE_USABLE_RADIUS = 6
    if ws_distance is not None and ws_distance <= _WORKSPACE_USABLE_RADIUS:
        metadata = workspace.get("metadata") if isinstance(workspace.get("metadata"), dict) else {}
        station_needed = _workspace_station_for_purpose(
            action_request.args.get("purpose") if isinstance(action_request.args, dict) else None
        )
        station_state = _station_state(before_status, station_needed) if station_needed else {}
        station_usable = bool(station_state.get("usable")) if station_needed else True
        base_already: dict[str, Any] = {
            "workspace_name": workspace.get("name"),
            "target_workspace_position": ws_position,
            "distance_to_workspace": ws_distance,
            "reached": True,
            "already_at_workspace": True,
            "maybe_stale": maybe_stale,
            "has_crafting_table": bool(metadata.get("has_crafting_table")),
            "has_furnace": bool(metadata.get("has_furnace")),
            "has_chest": bool(metadata.get("has_chest")),
            "station_needed": station_needed,
            "nearest_station_distance": station_state.get("distance"),
            "nearest_station_position": station_state.get("position"),
            "usable_radius": _WORKSPACE_USABLE_RADIUS,
            "failed_because": [],
        }
        if station_needed is not None and not station_usable:
            return ActionResult(
                ok=False,
                action=action_request.action,
                error=f"At workspace, but {station_needed} is not within usable range.",
                result={
                    **base_already,
                    "partial_success": True,
                    "failure_type": "station_not_reached",
                    "stop_reason": "workspace_reached_but_station_not_usable",
                    "possible_next_actions": ["approach_station", "setup_workspace", "look_around"],
                    "suggested_next_action": "approach_station",
                    "can_retry": True,
                },
            )
        return ActionResult(ok=True, action=action_request.action, result=base_already)

    translated = ActionRequest(
        action="return_to_position",
        args={
            "x": int(workspace["x"]),
            "y": int(workspace["y"]),
            "z": int(workspace["z"]),
            "dimension": ws_dim,
            "radius": 3,
        },
        speech=action_request.speech,
        reason=f"return_to_workspace → return_to_position at {workspace.get('name', 'workspace')}",
    )
    nav_result = await send_action(translated)
    station_needed = _workspace_station_for_purpose(action_request.args.get("purpose") if isinstance(action_request.args, dict) else None)
    station_state: dict[str, Any] = {}
    station_usable = True
    if station_needed is not None:
        try:
            after_nav_status = await get_bot_status()
        except Exception:
            after_nav_status = {}
        station_state = _station_state(after_nav_status, station_needed)
        station_usable = bool(station_state.get("usable"))
    metadata = workspace.get("metadata") if isinstance(workspace.get("metadata"), dict) else {}

    nav_result_dict = nav_result.result if isinstance(nav_result.result, dict) else {}
    nav_failed_because = list(nav_result_dict.get("failed_because") or [])
    if not nav_result.ok:
        stop_reason = str(nav_result_dict.get("stop_reason") or nav_result_dict.get("failure_type") or "")
        if "path_timeout" in stop_reason or nav_result_dict.get("failure_type") == "path_timeout":
            if not any(isinstance(fb, dict) and fb.get("kind") == "path_timeout" for fb in nav_failed_because):
                nav_failed_because.append({
                    "kind": "path_timeout",
                    "action": "return_to_workspace",
                    "target": workspace.get("name"),
                    "target_position": ws_position,
                })

    base_result = {
        **nav_result_dict,
        "workspace_name": workspace.get("name"),
        "target_workspace_position": ws_position,
        "distance_to_workspace": ws_distance,
        "reached": nav_result.ok,
        "maybe_stale": maybe_stale,
        "has_crafting_table": bool(metadata.get("has_crafting_table")),
        "has_furnace": bool(metadata.get("has_furnace")),
        "has_chest": bool(metadata.get("has_chest")),
        "station_needed": station_needed,
        "nearest_station_distance": station_state.get("distance"),
        "nearest_station_position": station_state.get("position"),
        "usable_radius": 6,
        "failed_because": nav_failed_because,
    }
    if nav_result.ok and station_needed is not None and not station_usable:
        return ActionResult(
            ok=False,
            action=action_request.action,
            error=f"Workspace reached, but {station_needed} is not within usable range.",
            result={
                **base_result,
                "partial_success": True,
                "failure_type": "station_not_reached",
                "stop_reason": "workspace_reached_but_station_not_usable",
                "possible_next_actions": ["approach_station", "setup_workspace", "look_around"],
                "suggested_next_action": "approach_station",
                "can_retry": True,
            },
        )

    return ActionResult(
        ok=nav_result.ok,
        action=action_request.action,
        error=nav_result.error,
        result=base_result,
    )


def _workspace_station_for_purpose(purpose: Any) -> str | None:
    if purpose == "crafting":
        return "crafting_table"
    if purpose == "smelting":
        return "furnace"
    if purpose == "storage":
        return "chest"
    return None


def _station_state(status: dict[str, Any], station: str) -> dict[str, Any]:
    nearby_blocks = status.get("nearbyBlocks") if isinstance(status.get("nearbyBlocks"), dict) else {}
    block = nearby_blocks.get(station)
    if not isinstance(block, dict):
        return {"visible": False, "usable": False, "distance": None, "position": None}
    distance = block.get("distance")
    return {
        "visible": True,
        "usable": isinstance(distance, (int, float)) and distance <= 6,
        "distance": distance if isinstance(distance, (int, float)) else None,
        "position": block.get("position") if isinstance(block.get("position"), dict) else None,
    }


async def _execute_return_to_known_position(
    action_request: ActionRequest,
    before_status: dict[str, Any],
) -> ActionResult:
    """Look up a persistent waypoint by label (or nearest home/workspace) and navigate there."""
    label = (action_request.args or {}).get("label")
    position = before_status.get("position") if isinstance(before_status.get("position"), dict) else None
    dimension = str(before_status.get("dimension") or "overworld")

    wp: dict[str, Any] | None = None
    if label:
        wp = get_waypoint(str(label))

    if wp is None:
        # Fall back to nearest workspace/home in current dimension
        workspace = nearest_workspace(position, dimension)
        if workspace:
            wp = {
                "label": workspace.get("name", "workspace"),
                "x": workspace["x"],
                "y": workspace["y"],
                "z": workspace["z"],
                "dimension": workspace.get("dimension", "overworld"),
            }

    if wp is None:
        return ActionResult(
            ok=False,
            action=action_request.action,
            error="No known position found" + (f" for label '{label}'" if label else "") + ".",
            result={
                "failure_type": "no_known_position",
                "suggested_next_action": "mark_waypoint",
                "can_retry": False,
            },
        )

    wp_dim = str(wp.get("dimension") or "overworld")
    if wp_dim.replace("minecraft:", "") != dimension.replace("minecraft:", ""):
        return ActionResult(
            ok=False,
            action=action_request.action,
            error=f"Target '{wp.get('label')}' is in {wp_dim} but bot is in {dimension}.",
            result={
                "failure_type": "dimension_mismatch",
                "suggested_next_action": "status",
                "can_retry": False,
            },
        )

    translated = ActionRequest(
        action="return_to_position",
        args={
            "x": int(float(wp["x"])),
            "y": int(float(wp["y"])),
            "z": int(float(wp["z"])),
            "dimension": wp_dim,
            "radius": 3,
        },
        speech=action_request.speech,
        reason=f"return_to_known_position at {wp.get('label')}",
    )
    nav_result = await send_action(translated)
    return ActionResult(
        ok=nav_result.ok,
        action=action_request.action,
        error=nav_result.error,
        result={
            **(nav_result.result if isinstance(nav_result.result, dict) else {}),
            "label": wp.get("label"),
        },
    )


def _persist_home(result: dict[str, Any]) -> None:
    """Write a set_home_position result into the persistent waypoint store."""
    x = result.get("x")
    y = result.get("y")
    z = result.get("z")
    dim = str(result.get("dimension") or "overworld")
    if x is not None and y is not None and z is not None:
        try:
            upsert_waypoint("home", "home", float(x), float(y), float(z), dim)
        except Exception:
            pass
