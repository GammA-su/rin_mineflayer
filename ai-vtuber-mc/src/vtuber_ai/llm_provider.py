import json
import os
import time
from typing import Any

from vtuber_ai.schemas import ActionRequest

FALLBACK_SPEECH = "I heard you! For now I can talk, follow, stop, jump, and check status."

ALLOWED_PLANNER_ACTIONS = (
    "status",
    "say",
    "look_at_player",
    "follow_player",
    "come_here",
    "stop",
    "jump",
    "set_vtuber_mood",
    "collect_wood",
    "craft_planks",
    "craft_sticks",
    "craft_crafting_table",
    "place_crafting_table",
    "craft_wooden_pickaxe",
    "mine_stone",
    "craft_stone_pickaxe",
)

SYSTEM_PROMPT = (
    "Minecraft VTuber planner. Pick one allowed action only. No code, no invented actions, no slash commands. "
    'Return strict JSON only: {"action":"","args":{},"speech":"","reason":""}. '
    "Keep every string short. Never write long explanations. The full response must fit under 80 tokens. "
    "Fields: speech max 12 words, reason max 12 words. "
    "Do not provide x/y/z coordinates. For place_crafting_table use args {}."
)

AGENT_SYSTEM_PROMPT = (
    "Minecraft VTuber agent planner. Prefer the objective, pick one allowed action, act cautiously. "
    "No code, no invented actions, no slash commands. "
    'Return strict JSON only: {"action":"","args":{},"speech":"","reason":""}. '
    "Keep every string short. Never write long explanations. The full response must fit under 80 tokens. "
    "Fields: speech max 12 words, reason max 12 words. "
    "Do not provide x/y/z coordinates unless the allowed action schema says so. For place_crafting_table use args {}. "
    'Action args schema: status:{} say:{"message":"short msg"} look_at_player:{} follow_player:{"username":"name"} '
    'come_here:{"username":"name"} stop:{} jump:{} set_vtuber_mood:{"mood":"mood"} '
    'collect_wood:{"count":4} craft_planks:{} craft_sticks:{} craft_crafting_table:{} place_crafting_table:{} '
    'craft_wooden_pickaxe:{} mine_stone:{"count":3} craft_stone_pickaxe:{} '
    "collect_wood count 1-16. mine_stone count 1-16."
)


def plan_with_configured_provider(message: str, user: str = "local_user") -> ActionRequest:
    provider = os.getenv("VTUBER_LLM_PROVIDER", "fake").strip().lower() or "fake"

    if provider == "openai_compatible":
        return plan_openai_compatible(message, user)

    return fake_plan_action(message, user)


def fake_plan_action(message: str, user: str = "local_user") -> ActionRequest:
    text = message.strip()
    lower_text = text.lower()
    username = user or "local_user"

    if lower_text.startswith("say "):
        speech = text[4:].strip()
        return ActionRequest(
            action="say",
            args={"message": speech},
            speech=speech,
            reason='Message started with "say ".',
        )

    if "status" in lower_text:
        return ActionRequest(
            action="status",
            args={},
            speech="Checking status.",
            reason='Message contained "status".',
        )

    if "follow me" in lower_text:
        return ActionRequest(
            action="follow_player",
            args={"username": username},
            speech="I'll follow you.",
            reason='Message contained "follow me".',
        )

    if "come here" in lower_text:
        return ActionRequest(
            action="come_here",
            args={"username": username},
            speech="Coming over.",
            reason='Message contained "come here".',
        )

    if "stop" in lower_text:
        return ActionRequest(
            action="stop",
            args={},
            speech="Stopping.",
            reason='Message contained "stop".',
        )

    if "jump" in lower_text:
        return ActionRequest(
            action="jump",
            args={},
            speech="Jumping.",
            reason='Message contained "jump".',
        )

    if "happy" in lower_text:
        return ActionRequest(
            action="set_vtuber_mood",
            args={"mood": "happy"},
            speech="Feeling happy.",
            reason='Message contained "happy".',
        )

    if "collect wood" in lower_text:
        return ActionRequest(
            action="collect_wood",
            args={},
            speech="I'll mark wood collection as a goal.",
            reason='Message contained "collect wood".',
        )

    if "craft planks" in lower_text or "make planks" in lower_text:
        return ActionRequest(
            action="craft_planks",
            args={},
            speech="I'll craft planks.",
            reason='Message contained "craft planks" or "make planks".',
        )

    if "craft sticks" in lower_text or "make sticks" in lower_text:
        return ActionRequest(
            action="craft_sticks",
            args={},
            speech="I'll craft sticks.",
            reason='Message contained "craft sticks" or "make sticks".',
        )

    if "craft crafting table" in lower_text or "make crafting table" in lower_text:
        return ActionRequest(
            action="craft_crafting_table",
            args={},
            speech="I'll craft a crafting table.",
            reason='Message contained "craft crafting table" or "make crafting table".',
        )

    if "place crafting table" in lower_text:
        return ActionRequest(
            action="place_crafting_table",
            args={},
            speech="I'll place a crafting table.",
            reason='Message contained "place crafting table".',
        )

    if "craft wooden pickaxe" in lower_text or "make wooden pickaxe" in lower_text:
        return ActionRequest(
            action="craft_wooden_pickaxe",
            args={},
            speech="I'll craft a wooden pickaxe.",
            reason='Message contained "craft wooden pickaxe" or "make wooden pickaxe".',
        )

    if "mine stone" in lower_text or "collect stone" in lower_text:
        return ActionRequest(
            action="mine_stone",
            args={},
            speech="I'll try to mine stone.",
            reason='Message contained "mine stone" or "collect stone".',
        )

    if "craft stone pickaxe" in lower_text or "make stone pickaxe" in lower_text:
        return ActionRequest(
            action="craft_stone_pickaxe",
            args={},
            speech="I'll craft a stone pickaxe.",
            reason='Message contained "craft stone pickaxe" or "make stone pickaxe".',
        )

    return ActionRequest(
        action="say",
        args={"message": FALLBACK_SPEECH},
        speech=FALLBACK_SPEECH,
        reason="No deterministic planner rule matched.",
    )


def plan_openai_compatible(message: str, user: str = "local_user") -> ActionRequest:
    base_url = (os.getenv("VTUBER_LLM_BASE_URL") or "").rstrip("/")
    if not base_url:
        return fake_plan_action(message, user)

    api_key = os.getenv("VTUBER_LLM_API_KEY")
    model = os.getenv("VTUBER_LLM_MODEL") or "local-model"
    max_tokens = _int_env("VTUBER_LLM_MAX_TOKENS", 160)
    timeout_sec = _float_env("VTUBER_LLM_TIMEOUT_SEC", 120.0)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user": user or "local_user",
                        "message": message,
                    }
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    raw_content: str | None = None
    try:
        import httpx

        response = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_sec,
        )
        response.raise_for_status()
        data = response.json()
        raw_content = data["choices"][0]["message"]["content"]
        parsed = json.loads(raw_content)
        return ActionRequest.model_validate(parsed)
    except Exception as exc:
        if isinstance(exc, json.JSONDecodeError) and raw_content is not None and os.getenv("VTUBER_DEBUG_LLM") == "1":
            print(f"[VTUBER_DEBUG_LLM] JSONDecodeError raw preview:\n{raw_content[:1000]}", flush=True)
        return fake_plan_action(message, user)


def plan_agent_openai_compatible(
    *,
    mission: str,
    current_objective: str,
    bot_status: dict[str, Any],
    inventory_summary: dict[str, int],
    recent_memory: list[dict[str, Any]],
    last_failure: dict[str, Any] | None,
    fallback_action: ActionRequest,
) -> tuple[ActionRequest, dict[str, Any]]:
    """Plan one autonomous agent action with an OpenAI-compatible model.

    This only returns a proposal. The caller must still validate the action
    through vtuber_ai.policy and then through the Mineflayer bridge whitelist.
    """

    base_url = (os.getenv("VTUBER_LLM_BASE_URL") or "").rstrip("/")
    if not base_url:
        return fallback_action, {
            "provider": "openai_compatible",
            "fallback_used": True,
            "fallback_reason": "VTUBER_LLM_BASE_URL is not set.",
            "llm_latency_sec": 0.0,
            "prompt_size_chars": 0,
        }

    api_key = os.getenv("VTUBER_LLM_API_KEY")
    model = os.getenv("VTUBER_LLM_MODEL") or "local-model"
    max_tokens = _int_env("VTUBER_LLM_MAX_TOKENS", 160)
    timeout_sec = _float_env("VTUBER_LLM_TIMEOUT_SEC", 120.0)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    context = _compact_agent_context(
        mission=mission,
        current_objective=current_objective,
        bot_status=bot_status,
        inventory_summary=inventory_summary,
        recent_memory=recent_memory,
        last_failure=last_failure,
    )
    user_content = json.dumps(context, separators=(",", ":"))
    prompt_size_chars = len(AGENT_SYSTEM_PROMPT) + len(user_content)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    started = time.perf_counter()
    raw_content: str | None = None
    try:
        import httpx

        response = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_sec,
        )
        llm_latency_sec = round(time.perf_counter() - started, 3)
        response.raise_for_status()
        data = response.json()
        raw_content = data["choices"][0]["message"]["content"]
        parsed = json.loads(raw_content)
        action = ActionRequest.model_validate(parsed)
        return action, {
            "provider": "openai_compatible",
            "fallback_used": False,
            "model": model,
            "llm_latency_sec": llm_latency_sec,
            "prompt_size_chars": prompt_size_chars,
        }
    except Exception as exc:
        info: dict[str, Any] = {
            "provider": "openai_compatible",
            "fallback_used": True,
            "fallback_reason": f"LLM planner failed: {type(exc).__name__}.",
            "llm_latency_sec": round(time.perf_counter() - started, 3),
            "prompt_size_chars": prompt_size_chars,
        }
        if isinstance(exc, json.JSONDecodeError) and raw_content is not None:
            info["json_extraction_success"] = False
            info["raw_llm_text_len"] = len(raw_content)
            info["raw_llm_text_preview"] = raw_content[:1000]
            if os.getenv("VTUBER_DEBUG_LLM") == "1":
                print(f"[VTUBER_DEBUG_LLM] JSONDecodeError raw preview:\n{raw_content[:1000]}", flush=True)
        return fallback_action, info


def _compact_agent_context(
    *,
    mission: str,
    current_objective: str,
    bot_status: dict[str, Any],
    inventory_summary: dict[str, int],
    recent_memory: list[dict[str, Any]],
    last_failure: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "mission": mission,
        "objective": current_objective,
        "health": bot_status.get("health"),
        "food": bot_status.get("food"),
        "position": bot_status.get("position"),
        "inventory": inventory_summary,
        "nearby_blocks": _top_counts(bot_status.get("nearbyBlockCounts"), limit=20),
        "nearby_entities": _compact_entities(bot_status.get("nearbyEntities"), limit=10),
        "memory": _compact_memory(recent_memory, limit=3),
        "last_failure": _compact_failure(last_failure),
        "allowed_actions": list(ALLOWED_PLANNER_ACTIONS),
    }


def _compact_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": status.get("ok"),
        "connected": status.get("connected"),
        "entityReady": status.get("entityReady"),
        "position": status.get("position"),
        "health": status.get("health"),
        "food": status.get("food"),
        "nearbyBlocks": status.get("nearbyBlocks") or {},
    }


def _compact_memory(memory: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    compacted = []
    for event in memory[:limit]:
        compacted.append(
            {
                "id": event.get("id"),
                "ts": event.get("ts"),
                "user": event.get("user"),
                "message": _short(event.get("message")),
                "action": event.get("action"),
                "ok": event.get("ok"),
                "error": _short(event.get("error")),
                "reason": _short(event.get("reason")),
            }
        )
    return compacted


def _compact_failure(failure: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(failure, dict):
        return None

    return {
        "action": failure.get("action"),
        "message": _short(failure.get("message")),
        "error": _short(failure.get("error")),
        "reason": _short(failure.get("reason")),
    }


def _compact_entities(entities: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(entities, list):
        return []

    compacted = []
    for entity in entities[:limit]:
        if not isinstance(entity, dict):
            continue
        compacted.append(
            {
                "name": entity.get("name"),
                "type": entity.get("type"),
                "hostile": entity.get("hostile"),
                "distance": entity.get("distance"),
            }
        )
    return compacted


def _top_counts(counts: Any, limit: int) -> dict[str, int]:
    if not isinstance(counts, dict):
        return {}

    items = sorted(
        ((name, count) for name, count in counts.items() if isinstance(name, str) and isinstance(count, int)),
        key=lambda item: item[1],
        reverse=True,
    )
    return dict(items[:limit])


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _short(value: Any, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."
