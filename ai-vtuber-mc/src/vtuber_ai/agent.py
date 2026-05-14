import os
from typing import Any

from vtuber_ai.curriculum import inventory_counts, recommend_objective
from vtuber_ai.llm import plan_agent_action
from vtuber_ai.memory import get_recent_events, log_event
from vtuber_ai.mineflayer_client import get_bot_status, send_action
from vtuber_ai.policy import PolicyError, validate_action
from vtuber_ai.schemas import ActionRequest, ActionResult, AgentRunRequest
from vtuber_ai.tts import emit_speech_text
from vtuber_ai.verifier import verify_step


def plan_objective_action(objective: str, mission: str, user: str) -> ActionRequest:
    reason = f"Curriculum objective '{objective}' for mission: {mission}"

    plans = {
        "collect_wood": ActionRequest(
            action="collect_wood",
            args={},
            speech="I will try to gather wood.",
            reason=reason,
        ),
        "craft_planks": ActionRequest(
            action="craft_planks",
            args={},
            speech="I will try to craft planks.",
            reason=reason,
        ),
        "craft_sticks": ActionRequest(
            action="craft_sticks",
            args={},
            speech="I will try to craft sticks.",
            reason=reason,
        ),
        "craft_crafting_table": ActionRequest(
            action="craft_crafting_table",
            args={},
            speech="I will try to craft a table.",
            reason=reason,
        ),
        "place_crafting_table": ActionRequest(
            action="place_crafting_table",
            args={},
            speech="I will place one crafting table.",
            reason=reason,
        ),
        "craft_wooden_pickaxe": ActionRequest(
            action="craft_wooden_pickaxe",
            args={},
            speech="I will try to craft a wooden pickaxe.",
            reason=reason,
        ),
        "mine_stone": ActionRequest(
            action="mine_stone",
            args={},
            speech="I will try to mine stone.",
            reason=reason,
        ),
        "craft_stone_pickaxe": ActionRequest(
            action="craft_stone_pickaxe",
            args={},
            speech="I will try to craft a stone pickaxe.",
            reason=reason,
        ),
        "tier1_complete": ActionRequest(
            action="status",
            args={},
            speech="Tier one looks complete.",
            reason=reason,
        ),
    }

    return plans.get(
        objective,
        ActionRequest(
            action="status",
            args={},
            speech="I will check status first.",
            reason=f"Unknown objective '{objective}', choosing status safely for user {user}.",
        ),
    )


async def run_agent_once(request: AgentRunRequest) -> dict[str, Any]:
    before_status = await get_bot_status()
    recent_memory = get_recent_events(limit=20)
    objective = recommend_objective(before_status, recent_memory)
    curriculum_action = plan_objective_action(objective, request.mission, request.user)
    action_request, planner_info = _plan_agent_action(
        request=request,
        objective=objective,
        before_status=before_status,
        recent_memory=recent_memory,
        curriculum_action=curriculum_action,
    )

    try:
        action_request = validate_action(action_request)
    except PolicyError as exc:
        fallback_result = _fallback_after_policy_rejection(
            action_request=action_request,
            curriculum_action=curriculum_action,
            planner_info=planner_info,
            error=str(exc),
        )
        action_request = fallback_result["action_request"]
        planner_info = fallback_result["planner_info"]

        try:
            action_request = validate_action(action_request)
        except PolicyError as fallback_exc:
            rejected = ActionResult(ok=False, action=action_request.action, error=str(fallback_exc))
            log_event(request.user, _agent_message(request, objective, planner_info), action_request, rejected)
            return {
                "ok": False,
                "user": request.user,
                "mission": request.mission,
                "objective": objective,
                "planner": planner_info,
                "planned_action": action_request,
                "mineflayer_result": rejected,
                "verification": {
                    "objective": objective,
                    "success": False,
                    "evidence": {
                        "policy_error": str(fallback_exc),
                        "mineflayer_contacted": False,
                    },
                    "next_recommended_objective": objective,
                },
                "observations": {
                    "before_status": before_status,
                    "after_status": before_status,
                    "recent_memory_count": len(recent_memory),
                },
            }

    if action_request.speech:
        emit_speech_text(action_request.speech)

    mineflayer_result = await send_action(action_request)
    after_status = await get_bot_status()
    verification = verify_step(
        objective=objective,
        before_status=before_status,
        after_status=after_status,
        action_request=action_request,
        action_result=mineflayer_result,
    )

    log_event(request.user, _agent_message(request, objective, planner_info), action_request, mineflayer_result)

    return {
        "ok": bool(mineflayer_result.ok and verification["success"]),
        "user": request.user,
        "mission": request.mission,
        "objective": objective,
        "planner": planner_info,
        "planned_action": action_request,
        "mineflayer_result": mineflayer_result,
        "verification": verification,
        "observations": {
            "before_status": before_status,
            "after_status": after_status,
            "recent_memory_count": len(recent_memory),
        },
    }


async def run_agent_loop(request: AgentRunRequest) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    consecutive_failures = 0
    previous_failure_signature: tuple[str, str, str | None] | None = None
    repeated_failure_detected = False
    objective_complete = False

    for index in range(request.max_steps):
        step = await run_agent_once(request)
        step["step"] = index + 1
        steps.append(step)

        verification = step["verification"]
        next_objective = verification.get("next_recommended_objective")

        if verification.get("success") and next_objective == "tier1_complete":
            objective_complete = True
            break

        if step["ok"]:
            consecutive_failures = 0
            previous_failure_signature = None
            continue

        consecutive_failures += 1
        failure_signature = (
            step.get("objective", ""),
            step.get("planned_action", {}).action if isinstance(step.get("planned_action"), ActionRequest) else "",
            step.get("mineflayer_result", {}).error
            if isinstance(step.get("mineflayer_result"), ActionResult)
            else None,
        )

        if consecutive_failures >= 3 or failure_signature == previous_failure_signature:
            repeated_failure_detected = True
            break

        previous_failure_signature = failure_signature

    return {
        "ok": bool(steps and steps[-1]["ok"]),
        "mission": request.mission,
        "user": request.user,
        "requested_max_steps": request.max_steps,
        "steps_run": len(steps),
        "objective_complete": objective_complete,
        "repeated_failure_detected": repeated_failure_detected,
        "steps": steps,
    }


def _plan_agent_action(
    *,
    request: AgentRunRequest,
    objective: str,
    before_status: dict[str, Any],
    recent_memory: list[dict[str, Any]],
    curriculum_action: ActionRequest,
) -> tuple[ActionRequest, dict[str, Any]]:
    mode = os.getenv("VTUBER_AGENT_PLANNER", "curriculum").strip().lower() or "curriculum"

    if mode != "llm":
        return curriculum_action, {
            "mode": "curriculum",
            "fallback_used": False,
            "requested_mode": mode,
            "curriculum_action": curriculum_action.action,
            "deviated_from_curriculum": False,
        }

    action_request, provider_info = plan_agent_action(
        mission=request.mission,
        current_objective=objective,
        bot_status=before_status,
        inventory_summary=inventory_counts(before_status),
        recent_memory=recent_memory,
        last_failure=_last_failure(recent_memory),
        fallback_action=curriculum_action,
    )
    deviated = action_request.action != curriculum_action.action

    if deviated:
        action_request.reason = (
            f"{action_request.reason} Deviation from curriculum objective '{objective}' "
            f"(curriculum action '{curriculum_action.action}')."
        ).strip()

    return action_request, {
        "mode": "llm",
        "provider": provider_info.get("provider"),
        "model": provider_info.get("model"),
        "fallback_used": bool(provider_info.get("fallback_used")),
        "fallback_reason": provider_info.get("fallback_reason"),
        "curriculum_action": curriculum_action.action,
        "deviated_from_curriculum": deviated,
    }


def _fallback_after_policy_rejection(
    *,
    action_request: ActionRequest,
    curriculum_action: ActionRequest,
    planner_info: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    if planner_info.get("mode") != "llm":
        return {
            "action_request": action_request,
            "planner_info": planner_info,
        }

    fallback = ActionRequest.model_validate(curriculum_action)
    fallback.reason = (
        f"{fallback.reason} LLM proposal '{action_request.action}' was rejected by policy: {error}"
    )
    updated_info = dict(planner_info)
    updated_info["fallback_used"] = True
    updated_info["fallback_reason"] = f"LLM proposal rejected by policy: {error}"
    updated_info["rejected_llm_action"] = action_request.action
    updated_info["deviated_from_curriculum"] = False
    return {
        "action_request": fallback,
        "planner_info": updated_info,
    }


def _last_failure(recent_memory: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in recent_memory:
        if event.get("ok") in (0, False):
            return {
                "id": event.get("id"),
                "ts": event.get("ts"),
                "action": event.get("action"),
                "message": event.get("message"),
                "error": event.get("error"),
                "reason": event.get("reason"),
            }
    return None


def _agent_message(request: AgentRunRequest, objective: str, planner_info: dict[str, Any]) -> str:
    return (
        f"agent mission='{request.mission}' objective='{objective}' "
        f"planner='{planner_info.get('mode')}' deviation='{planner_info.get('deviated_from_curriculum')}'"
    )
