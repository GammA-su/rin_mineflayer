from typing import Any

from vtuber_ai.llm_provider import FALLBACK_SPEECH, plan_agent_openai_compatible, plan_with_configured_provider
from vtuber_ai.schemas import ActionRequest


def plan_action(message: str, user: str = "local_user") -> ActionRequest:
    """Plan an action with the configured provider.

    The default provider is deterministic fake planning. Real model output is
    still only a proposal; main.py validates every ActionRequest before sending
    anything to Mineflayer.
    """

    return plan_with_configured_provider(message, user)


def plan_agent_action(
    *,
    mission: str,
    current_objective: str,
    bot_status: dict[str, Any],
    inventory_summary: dict[str, int],
    recent_memory: list[dict[str, Any]],
    last_failure: dict[str, Any] | None,
    fallback_action: ActionRequest,
) -> tuple[ActionRequest, dict[str, Any]]:
    """Plan one autonomous agent action with the configured agent LLM provider."""

    return plan_agent_openai_compatible(
        mission=mission,
        current_objective=current_objective,
        bot_status=bot_status,
        inventory_summary=inventory_summary,
        recent_memory=recent_memory,
        last_failure=last_failure,
        fallback_action=fallback_action,
    )
