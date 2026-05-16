import asyncio
from typing import Any

from httpx import HTTPError, TimeoutException

from vtuber_ai.agent_state import build_agent_state, summarize_status
from vtuber_ai.world_memory import (
    get_death_state,
    get_relevant_known_places,
    get_waypoint,
    list_known_places,
    list_waypoints,
    nearest_workspace,
    record_death_if_new,
    remember_workspace,
    update_death_recovery_state,
    update_workspace_station,
    upsert_waypoint,
)
from vtuber_ai.game_brain import AUTONOMOUS_ALLOWED_ACTIONS, choose_next_action
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
    metadata = workspace.get("metadata") if isinstance(workspace.get("metadata"), dict) else {}
    return ActionResult(
        ok=nav_result.ok,
        action=action_request.action,
        error=nav_result.error,
        result={
            **(nav_result.result if isinstance(nav_result.result, dict) else {}),
            "workspace_name": workspace.get("name"),
            "has_crafting_table": bool(metadata.get("has_crafting_table")),
            "has_furnace": bool(metadata.get("has_furnace")),
            "has_chest": bool(metadata.get("has_chest")),
        },
    )


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
