from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from httpx import HTTPError, TimeoutException

from vtuber_ai.agent import run_agent_loop, run_agent_once
from vtuber_ai.autonomy import current_agent_state, run_agent_live, run_agent_tick
from vtuber_ai.curriculum import inventory_counts, recommend_objective
from vtuber_ai.llm import plan_action
from vtuber_ai.memory import get_recent_events, init_db, log_event
from vtuber_ai.mineflayer_client import get_bot_status, send_action
from vtuber_ai.policy import PolicyError, validate_action
from vtuber_ai.schemas import ActionResult, AgentLiveRequest, AgentRunRequest, AgentTickRequest, ChatGoalRequest
from vtuber_ai.tts import emit_speech_text

load_dotenv()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI VTuber Minecraft Controller", lifespan=lifespan)


@app.get("/")
async def root() -> dict[str, Any]:
    return {"name": "ai-vtuber-mc", "ok": True}


@app.get("/status")
async def status() -> dict[str, Any]:
    try:
        return await get_bot_status()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Mineflayer bridge status request failed.") from exc


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

    return {
        "ok": mineflayer_result.ok,
        "user": user,
        "message": goal.message,
        "planned_action": action_request,
        "mineflayer_result": mineflayer_result,
    }


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


@app.get("/speech/latest")
async def speech_latest() -> dict[str, Any]:
    path = Path("data/latest_speech.txt")
    if not path.exists():
        return {"ok": False, "text": ""}

    return {"ok": True, "text": path.read_text(encoding="utf-8")}
