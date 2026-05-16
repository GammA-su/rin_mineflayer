from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from httpx import HTTPError, TimeoutException

from vtuber_ai.agent import run_agent_loop, run_agent_once
from vtuber_ai.action_catalog import actions_by_status, validate_action_catalog
from vtuber_ai.autonomy import current_agent_state, run_agent_live, run_agent_tick
from vtuber_ai.curriculum import inventory_counts, recommend_objective
from vtuber_ai.llm import plan_action
from vtuber_ai.memory import get_recent_agent_ticks, get_recent_events, init_db, log_death_event, log_event
from vtuber_ai.milestones import build_milestone_state
from vtuber_ai.world_memory import (
    get_death_state,
    get_relevant_known_places,
    init_world_memory,
    list_known_places,
    list_waypoints,
    nearest_known_place,
    record_death_if_new,
    remember_known_place,
    update_death_recovery_state,
    upsert_waypoint,
)
from vtuber_ai.mineflayer_client import get_bot_status, send_action
from vtuber_ai.policy import PolicyError, validate_action
from vtuber_ai.schemas import ActionResult, AgentLiveRequest, AgentRunRequest, AgentTickRequest, ChatGoalRequest
from vtuber_ai.tts import emit_speech_text

load_dotenv()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    init_world_memory()
    yield


app = FastAPI(title="AI VTuber Minecraft Controller", lifespan=lifespan)


@app.get("/")
async def root() -> dict[str, Any]:
    return {"name": "ai-vtuber-mc", "ok": True}


@app.get("/status")
async def status() -> dict[str, Any]:
    try:
        bot_status = await get_bot_status()
        _maybe_record_death_from_status(bot_status)
        return bot_status
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Mineflayer bridge status request failed.") from exc


@app.get("/actions/summary")
async def actions_summary() -> dict[str, Any]:
    return validate_action_catalog()


@app.get("/actions/planned")
async def actions_planned() -> dict[str, Any]:
    return {"ok": True, "actions": actions_by_status("planned")}


@app.get("/actions/implemented")
async def actions_implemented() -> dict[str, Any]:
    return {"ok": True, "actions": actions_by_status("implemented")}


@app.post("/chat_goal")
async def chat_goal(goal: ChatGoalRequest) -> dict[str, Any]:
    user = goal.user or "local_user"
    action_request = plan_action(goal.message, user)
    if action_request.speech:
        emit_speech_text(action_request.speech)

    try:
        action_request = validate_action(action_request)
    except PolicyError as exc:
        rejected = ActionResult(
            ok=False,
            action=action_request.action,
            error=str(exc),
        )
        log_event(user, goal.message, action_request, rejected)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        mineflayer_result = await send_action(action_request)
    except TimeoutException as exc:
        failed = ActionResult(
            ok=False,
            action=action_request.action,
            error="Mineflayer bridge action timed out.",
        )
        log_event(user, goal.message, action_request, failed)
        raise HTTPException(status_code=504, detail=failed.error) from exc
    except HTTPError as exc:
        failed = ActionResult(
            ok=False,
            action=action_request.action,
            error="Mineflayer bridge request failed.",
        )
        log_event(user, goal.message, action_request, failed)
        raise HTTPException(status_code=502, detail=failed.error) from exc

    log_event(user, goal.message, action_request, mineflayer_result)
    _persist_death_recovery_result(action_request.action, mineflayer_result.result or {}, mineflayer_result.ok)

    return {
        "ok": mineflayer_result.ok,
        "user": user,
        "message": goal.message,
        "planned_action": action_request,
        "mineflayer_result": mineflayer_result,
    }


@app.get("/waypoints")
async def waypoints_list() -> list[dict]:
    return list_waypoints()


@app.get("/known_places")
async def known_places_list(limit: int = Query(default=50, ge=0, le=200)) -> dict[str, Any]:
    return {"ok": True, "known_places": list_known_places(limit=limit)}


@app.get("/known_places/relevant")
async def known_places_relevant() -> dict[str, Any]:
    try:
        bot_status = await get_bot_status()
        _maybe_record_death_from_status(bot_status)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Mineflayer bridge status request failed.") from exc
    return {"ok": True, "known_places": get_relevant_known_places(bot_status)}


@app.get("/world/places")
async def world_places_list(
    kind: str | None = Query(default=None),
    dimension: str | None = Query(default=None),
    limit: int = Query(default=50, ge=0, le=500),
) -> dict[str, Any]:
    places = list_known_places(kind=kind, dimension=dimension, limit=limit)
    return {"ok": True, "places": places, "count": len(places)}


@app.get("/world/places/nearest")
async def world_places_nearest(
    kind: str = Query(...),
    x: float = Query(...),
    y: float = Query(...),
    z: float = Query(...),
    dimension: str = Query(default="overworld"),
) -> dict[str, Any]:
    place = nearest_known_place(kind, {"x": x, "y": y, "z": z}, dimension)
    if place is None:
        return {"ok": False, "place": None, "error": f"No known place of kind '{kind}' in {dimension}."}
    return {"ok": True, "place": place}


@app.post("/world/places")
async def world_places_store(body: dict) -> dict[str, Any]:
    name = body.get("name")
    kind = str(body.get("kind") or "general")
    dimension = str(body.get("dimension") or "overworld")
    x = body.get("x")
    y = body.get("y")
    z = body.get("z")
    if not name or x is None or y is None or z is None:
        raise HTTPException(status_code=400, detail="name, x, y, z are required.")
    confidence = float(body.get("confidence") or 0.7)
    notes = str(body.get("notes")) if body.get("notes") else None
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else None
    place = remember_known_place(
        name=str(name),
        kind=kind,
        position={"x": float(x), "y": float(y), "z": float(z)},
        dimension=dimension,
        confidence=confidence,
        notes=notes,
        metadata=metadata,
    )
    return {"ok": True, "place": place}


@app.post("/waypoints")
async def waypoints_upsert(body: dict) -> dict:
    label = body.get("label")
    kind  = body.get("kind", "general")
    x     = body.get("x")
    y     = body.get("y")
    z     = body.get("z")
    dim   = body.get("dimension", "overworld")
    if not label or x is None or y is None or z is None:
        raise HTTPException(status_code=400, detail="label, x, y, z are required.")
    upsert_waypoint(str(label), str(kind), float(x), float(y), float(z), str(dim))
    return {"ok": True, "label": label}


@app.get("/memory/recent")
async def memory_recent(limit: int = Query(default=20, ge=0, le=200)) -> list[dict[str, Any]]:
    return get_recent_events(limit=limit)


@app.get("/agent/objective")
async def agent_objective() -> dict[str, Any]:
    try:
        bot_status = await get_bot_status()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Mineflayer bridge status request failed.") from exc

    recent_memory = get_recent_events(limit=20)
    objective = recommend_objective(bot_status, recent_memory)
    return {
        "objective": objective,
        "inventory_counts": inventory_counts(bot_status),
        "recent_memory_count": len(recent_memory),
    }


@app.post("/agent/run_once")
async def agent_run_once(request: AgentRunRequest | None = None) -> dict[str, Any]:
    request = request or AgentRunRequest()
    try:
        return await run_agent_once(request)
    except TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Mineflayer bridge action timed out.") from exc
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Mineflayer bridge request failed.") from exc


@app.post("/agent/run_loop")
async def agent_run_loop(request: AgentRunRequest | None = None) -> dict[str, Any]:
    request = request or AgentRunRequest()
    if not request.allow_autonomy:
        raise HTTPException(
            status_code=400,
            detail="/agent/run_loop requires allow_autonomy=true.",
        )

    try:
        return await run_agent_loop(request)
    except TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Mineflayer bridge action timed out.") from exc
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Mineflayer bridge request failed.") from exc


@app.post("/agent/tick")
async def agent_tick(request: AgentTickRequest | None = None) -> dict[str, Any]:
    request = request or AgentTickRequest()
    if not request.allow_autonomy:
        raise HTTPException(
            status_code=400,
            detail="/agent/tick requires allow_autonomy=true.",
        )

    return await run_agent_tick(request)


@app.post("/agent/live")
async def agent_live(request: AgentLiveRequest | None = None) -> dict[str, Any]:
    request = request or AgentLiveRequest()
    if not request.allow_autonomy:
        raise HTTPException(
            status_code=400,
            detail="/agent/live requires allow_autonomy=true.",
        )

    return await run_agent_live(request)


@app.get("/agent/state")
async def agent_state() -> dict[str, Any]:
    return await current_agent_state()


@app.get("/agent/milestones")
async def agent_milestones() -> dict[str, Any]:
    bot_status: dict[str, Any]
    try:
        bot_status = await get_bot_status()
        _maybe_record_death_from_status(bot_status)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Mineflayer bridge status request failed.") from exc

    return build_milestone_state(
        status=bot_status,
        recent_memory=get_recent_events(limit=100),
        recent_ticks=get_recent_agent_ticks(limit=100),
        waypoints=list_waypoints(),
        death_state=get_death_state(),
    )


@app.get("/agent/death_state")
async def agent_death_state() -> dict[str, Any]:
    bot_status: dict[str, Any] | None = None
    status_error: str | None = None
    try:
        bot_status = await get_bot_status()
        _maybe_record_death_from_status(bot_status)
    except HTTPError:
        status_error = "Mineflayer bridge status request failed."

    state = get_death_state()
    if isinstance(bot_status, dict):
        state["bridge_last_death"] = bot_status.get("last_death") or bot_status.get("lastDeath")
        state["respawned_recently"] = bool(bot_status.get("respawned_recently"))
        state["bridge_death_recovery"] = bot_status.get("death_recovery")
    if status_error:
        state["status_error"] = status_error
    return state


@app.get("/speech/latest")
async def speech_latest() -> dict[str, Any]:
    path = Path("data/latest_speech.txt")
    if not path.exists():
        return {"ok": False, "text": ""}

    return {"ok": True, "text": path.read_text(encoding="utf-8")}


def _maybe_record_death_from_status(bot_status: dict[str, Any] | None) -> None:
    if not isinstance(bot_status, dict):
        return
    last_death = bot_status.get("last_death") or bot_status.get("lastDeath")
    if not isinstance(last_death, dict):
        return
    x = last_death.get("x")
    y = last_death.get("y")
    z = last_death.get("z")
    ts = last_death.get("ts")
    if x is None or y is None or z is None or ts is None:
        return
    dim = str(last_death.get("dimension", "overworld"))
    cause = last_death.get("cause")
    inventory = last_death.get("inventory") if isinstance(last_death.get("inventory"), list) else []
    try:
        recorded = record_death_if_new(
            float(x),
            float(y),
            float(z),
            dim,
            int(ts),
            str(cause) if cause else None,
            inventory,
        )
        if recorded:
            log_death_event(
                x=float(x),
                y=float(y),
                z=float(z),
                dimension=dim,
                source_ts_ms=int(ts),
                cause=str(cause) if cause else None,
                inventory=inventory,
            )
    except Exception:
        return


def _persist_death_recovery_result(action: str, result: dict[str, Any], ok: bool) -> None:
    if action == "abandon_death_recovery" and ok:
        update_death_recovery_state(abandoned=True)
        return
    if action != "recover_death_items" or not isinstance(result, dict):
        return
    death_state = result.get("death_state")
    failures = result.get("recovery_failures")
    if failures is None and isinstance(death_state, dict):
        failures = death_state.get("failures") or death_state.get("recovery_failures")
    if isinstance(failures, int):
        update_death_recovery_state(failures=failures)
