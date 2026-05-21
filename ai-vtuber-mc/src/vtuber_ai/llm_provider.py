import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from vtuber_ai.schemas import ActionRequest

# Lazily imported: httpx (only needed when making real HTTP calls)
_HTTPX_HTTPStatusError: type | None = None


def _get_httpx_status_error_cls() -> type:
    global _HTTPX_HTTPStatusError
    if _HTTPX_HTTPStatusError is None:
        import httpx  # noqa: PLC0415
        _HTTPX_HTTPStatusError = httpx.HTTPStatusError
    return _HTTPX_HTTPStatusError

FALLBACK_SPEECH = "I heard you! For now I can talk, follow, stop, jump, and check status."
LOCAL_OPENAI_COMPATIBLE_PROVIDER = "local_openai_compatible"
OPENAI_PROVIDER = "openai"
LOCAL_DEFAULT_BASE_URL = "http://127.0.0.1:8087/v1"
LOCAL_DEFAULT_MODEL = "Qwen3.5-9B-Q4_K_M.gguf"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "gpt-5.5"
DEFAULT_LLM_TIMEOUT_SEC = 180.0
DEFAULT_LLM_TEMPERATURE = 0.0
DEFAULT_LLM_REASONING_EFFORT = "none"

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


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key_env: str
    api_key: str
    timeout_sec: float
    temperature: float | None
    max_tokens: int
    reasoning_effort: str | None = None


def resolve_llm_config(
    overrides: dict[str, Any] | None = None,
    *,
    default_max_tokens: int = 160,
) -> LLMConfig:
    """Resolve env + per-request LLM settings without exposing API keys."""

    overrides = {k: v for k, v in (overrides or {}).items() if v is not None and v != ""}
    provider = str(
        overrides.get("provider")
        or os.getenv("VTUBER_LLM_PROVIDER")
        or LOCAL_OPENAI_COMPATIBLE_PROVIDER
    ).strip().lower()
    if provider == "openai_compatible":
        provider = LOCAL_OPENAI_COMPATIBLE_PROVIDER

    if provider == OPENAI_PROVIDER:
        model = str(
            overrides.get("model")
            or os.getenv("VTUBER_OPENAI_MODEL")
            or os.getenv("VTUBER_LLM_MODEL")
            or OPENAI_DEFAULT_MODEL
        ).strip()
        base_url = str(
            overrides.get("base_url")
            or os.getenv("VTUBER_OPENAI_BASE_URL")
            or OPENAI_DEFAULT_BASE_URL
        ).rstrip("/")
        api_key_env = str(overrides.get("api_key_env") or "OPENAI_API_KEY").strip()
        api_key = os.getenv(api_key_env, "")
        reasoning_effort = str(os.getenv("VTUBER_LLM_REASONING_EFFORT") or DEFAULT_LLM_REASONING_EFFORT).strip() or None
    else:
        provider = LOCAL_OPENAI_COMPATIBLE_PROVIDER
        model = str(overrides.get("model") or os.getenv("VTUBER_LLM_MODEL") or LOCAL_DEFAULT_MODEL).strip()
        base_url = str(overrides.get("base_url") or os.getenv("VTUBER_LLM_BASE_URL") or LOCAL_DEFAULT_BASE_URL).rstrip("/")
        api_key_env = str(overrides.get("api_key_env") or "VTUBER_LLM_API_KEY").strip()
        api_key = os.getenv(api_key_env, "dummy")
        reasoning_effort = None

    if provider == OPENAI_PROVIDER:
        # Default max tokens for openai provider is 256, or 512 for debug
        is_debug = (os.getenv("VTUBER_DEBUG_LLM") == "1")
        default_tokens = 512 if is_debug else 256
    else:
        default_tokens = default_max_tokens

    timeout_sec = _float_env("VTUBER_LLM_TIMEOUT_SEC", DEFAULT_LLM_TIMEOUT_SEC)
    temperature = _float_env("VTUBER_LLM_TEMPERATURE", DEFAULT_LLM_TEMPERATURE)
    max_tokens = _int_env("VTUBER_LLM_MAX_TOKENS", default_tokens)

    return LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        api_key=api_key,
        timeout_sec=timeout_sec,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )


def llm_diagnostics_base(config: LLMConfig) -> dict[str, Any]:
    return {
        "llm_provider": config.provider,
        "llm_model": config.model,
        "llm_base_url_host": _url_host(config.base_url),
        "llm_request_api_mode": "responses" if config.provider == OPENAI_PROVIDER else "chat_completions",
    }


def _http_error_diagnostics(exc: Any, endpoint: str = "", api_mode: str = "") -> dict[str, Any]:
    """Extract actionable diagnostics from an httpx.HTTPStatusError without exposing the API key."""
    diag: dict[str, Any] = {}
    try:
        response = exc.response
        diag["llm_http_status_code"] = response.status_code
        body_text: str = ""
        try:
            body_text = response.text or ""
        except Exception:  # noqa: BLE001
            body_text = ""
        diag["llm_http_error_body_preview"] = body_text[:1000]
        # Try to parse JSON error fields
        try:
            err_json = json.loads(body_text)
            err_obj = err_json.get("error") if isinstance(err_json, dict) else None
            if isinstance(err_obj, dict):
                diag["llm_http_error_type"] = err_obj.get("type")
                diag["llm_http_error_code"] = err_obj.get("code")
        except Exception:  # noqa: BLE001
            pass
        # Endpoint from the failed request (safe — no key in URL)
        try:
            req_url = str(exc.request.url) if exc.request is not None else endpoint
        except Exception:  # noqa: BLE001
            req_url = endpoint
        diag["llm_request_endpoint"] = req_url
    except Exception:  # noqa: BLE001
        if endpoint:
            diag["llm_request_endpoint"] = endpoint
    if api_mode:
        diag["llm_request_api_mode"] = api_mode
    return diag


def _url_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path.split("/")[0]


def _headers_for_config(config: LLMConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


# JSON schema used for the Responses API structured output.
# Non-strict so additionalProperties:true on nested 'args' object is accepted.
_RESPONSES_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "minecraft_action",
    "strict": False,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "a": {"type": "string"},
            "args": {"type": "object"},
            "reason": {"type": "string"},
        },
        "required": ["a", "args"],
    },
}

# Phrase appended to input when the format requires the word "json".
_JSON_KEYWORD_SUFFIX = "\nReturn only JSON."


def _ensure_json_keyword(text: str) -> str:
    """Return text with _JSON_KEYWORD_SUFFIX appended if 'json' not already present."""
    if "json" in text.lower():
        return text
    return text + _JSON_KEYWORD_SUFFIX


def extract_responses_text(resp: dict[str, Any]) -> str:
    """Extract the generated text from an OpenAI Responses API response.

    Priority:
    1. resp["output_text"] if present and non-empty
    2. Iterate resp["output"]:
       For each item:
         - if item.type == "message":
           iterate item.content:
             - if content.type in ["output_text", "text"]:
               append content.text
             - if content has "text", append it
         - if item.type == "output_text" and item.text exists, append
         - if item.type == "reasoning", ignore for visible output but count it
         - if item.type == "function_call", record diagnostics
    """
    if resp.get("output_text") and isinstance(resp["output_text"], str):
        return resp["output_text"]

    output_list = resp.get("output")
    parts: list[str] = []

    if isinstance(output_list, list):
        for item in output_list:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "message":
                content_list = item.get("content")
                if isinstance(content_list, list):
                    for content in content_list:
                        if not isinstance(content, dict):
                            continue
                        content_type = content.get("type")
                        if content_type in ["output_text", "text"] and content.get("text"):
                            parts.append(content["text"])
                        elif "text" in content and content["text"]:
                            parts.append(content["text"])
            elif item_type == "output_text" and "text" in item and item["text"]:
                parts.append(item["text"])

    text = "".join(parts)
    if text:
        return text

    exc = ValueError("OpenAI Responses API returned no output text")
    setattr(exc, "llm_empty_output", True)
    raise exc


def _extract_responses_output_text(response_json: dict[str, Any]) -> str:
    return extract_responses_text(response_json)


def _extract_responses_diagnostics(response_json: dict[str, Any]) -> dict[str, Any]:
    """Safely extract OpenAI Responses API JSON diagnostics."""
    diag: dict[str, Any] = {}
    diag["llm_response_id"] = response_json.get("id")
    diag["llm_response_status"] = response_json.get("status")

    output_list = response_json.get("output")
    diag["llm_response_output_count"] = len(output_list) if isinstance(output_list, list) else 0

    output_types = []
    output_statuses = []
    output_incomplete_reasons = []

    if isinstance(output_list, list):
        for item in output_list:
            if isinstance(item, dict):
                if "type" in item:
                    output_types.append(item["type"])
                output_statuses.append(item.get("status"))
                inc = item.get("incomplete_details")
                if isinstance(inc, dict):
                    output_incomplete_reasons.append(inc.get("reason"))
                else:
                    output_incomplete_reasons.append(inc)

    diag["llm_response_output_types"] = output_types
    diag["llm_response_output_statuses"] = output_statuses
    diag["llm_response_output_incomplete_reasons"] = output_incomplete_reasons

    inc_details = response_json.get("incomplete_details")
    if isinstance(inc_details, dict):
        diag["llm_response_incomplete_reason"] = inc_details.get("reason")
    else:
        diag["llm_response_incomplete_reason"] = inc_details

    diag["llm_response_error"] = response_json.get("error")
    diag["llm_usage"] = response_json.get("usage")

    if os.getenv("VTUBER_DEBUG_LLM") == "1":
        diag["llm_raw_response_preview"] = json.dumps(response_json)[:3000]

    return diag


def _lower_reasoning_effort(current: str | None) -> str:
    """Return next lower/minimal reasoning effort value."""
    if current == "high":
        return "medium"
    if current == "medium":
        return "low"
    return "none"


def _responses_compat_issue(response: Any, payload: dict[str, Any], attempted: set[str]) -> str | None:
    """Detect a known removable param from a Responses API 400/422 response.

    Returns a string key identifying the issue, or None if the error is not
    a known compat problem (in which case the caller should raise_for_status).
    """
    if response.status_code not in {400, 422}:
        return None
    text = (response.text or "").lower()
    # Try JSON for precise param/code detection
    param_field = ""
    code_field = ""
    msg_field = ""
    try:
        err_json = json.loads(response.text or "")
        err_obj = err_json.get("error") if isinstance(err_json, dict) else None
        if isinstance(err_obj, dict):
            param_field = str(err_obj.get("param") or "").lower()
            code_field = str(err_obj.get("code") or "").lower()
            msg_field = str(err_obj.get("message") or "").lower()
    except Exception:  # noqa: BLE001
        pass

    # reasoning.effort value not supported by this model — drop the reasoning key
    if "reasoning" in payload and "reasoning" not in attempted:
        if (
            param_field == "reasoning.effort"
            or (code_field == "unsupported_value" and "reasoning" in text)
            or ("reasoning" in text and "unsupported" in text)
        ):
            return "reasoning"

    # json_schema format not accepted — fall back to json_object
    if "text" in payload and "json_schema" not in attempted:
        fmt_type = (payload.get("text") or {}).get("format", {}).get("type", "")
        if fmt_type == "json_schema":
            schema_keywords = ("json_schema", "additionalproperties", "json schema", "schema", "strict")
            if any(kw in text for kw in schema_keywords):
                return "json_schema"

    # json_object requires the word "json" in input — inject it, then retry
    if "text" in payload and "json_word" not in attempted:
        fmt_type = (payload.get("text") or {}).get("format", {}).get("type", "")
        if fmt_type == "json_object":
            json_word_phrases = (
                "contain the word 'json'",
                "contain the word \"json\"",
                "must contain 'json'",
                "must include 'json'",
                "word 'json'",
            )
            if any(ph in msg_field for ph in json_word_phrases) or "contain the word" in text:
                return "json_word"

    return None


def _post_openai_responses(
    config: LLMConfig,
    system_text: str,
    user_text: str,
) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    """POST to the OpenAI Responses API with per-param compat retries.

    Returns (response_json, retried, extra_diag).
    Raises httpx.HTTPStatusError on unrecoverable HTTP errors.

    Retry order (each issue at most once):
    1. reasoning.effort unsupported → remove 'reasoning' key
    2. json_schema rejected        → switch to json_object format
    3. json_word missing           → inject 'Return only JSON.' into input
    """
    import httpx  # noqa: PLC0415

    endpoint = f"{config.base_url.rstrip('/')}/responses"
    headers = _headers_for_config(config)

    payload: dict[str, Any] = {
        "model": config.model,
        "instructions": system_text,
        "input": user_text,
        "max_output_tokens": config.max_tokens,
        "text": {"format": dict(_RESPONSES_JSON_SCHEMA)},
    }
    if config.reasoning_effort:
        payload["reasoning"] = {"effort": config.reasoning_effort}

    attempted: set[str] = set()
    retried = False
    attempt_count = 0
    retry_format: str | None = None
    attempt_error_previews: list[str] = []
    retried_due_to_incomplete = False
    retried_due_to_empty_output = False

    while True:
        attempt_count += 1
        response = httpx.post(endpoint, headers=headers, json=payload, timeout=config.timeout_sec)
        if response.status_code < 400:
            response_json = response.json()

            # Check for Requirement 4: If response status is incomplete
            status = response_json.get("status")
            if status == "incomplete" and "incomplete_retry" not in attempted:
                attempted.add("incomplete_retry")
                retried = True
                retried_due_to_incomplete = True
                payload["max_output_tokens"] = max(payload.get("max_output_tokens", 256), 512)
                print(f"[VTUBER_LLM_WARN] Responses API response incomplete: {response_json.get('incomplete_details')}. Retrying with max_output_tokens={payload['max_output_tokens']}.", flush=True)
                continue

            # Check if output is empty
            has_text = False
            try:
                extracted_text = extract_responses_text(response_json)
                if extracted_text.strip():
                    has_text = True
            except ValueError:
                pass

            # Check for Requirement 6: JSON format fallback - Schema empty -> retry json_object
            if not has_text and "json_object_retry" not in attempted:
                current_format_type = (payload.get("text") or {}).get("format", {}).get("type")
                if current_format_type == "json_schema":
                    attempted.add("json_object_retry")
                    retried = True
                    payload["text"] = {"format": {"type": "json_object"}}
                    retry_format = "json_object"
                    payload["input"] = _ensure_json_keyword(str(payload["input"]))
                    payload["instructions"] = _ensure_json_keyword(str(payload["instructions"]))
                    print("[VTUBER_LLM_WARN] Responses API returned empty output with json_schema. Retrying with json_object format.", flush=True)
                    continue

            # Check for Requirement 5: Empty output but reasoning items present
            if not has_text and "empty_output_retry" not in attempted:
                output_list = response_json.get("output", [])
                has_reasoning = False
                if isinstance(output_list, list):
                    for item in output_list:
                        if isinstance(item, dict) and item.get("type") == "reasoning":
                            has_reasoning = True
                            break
                if has_reasoning:
                    attempted.add("empty_output_retry")
                    retried = True
                    retried_due_to_empty_output = True
                    current_effort = None
                    if "reasoning" in payload and isinstance(payload["reasoning"], dict):
                        current_effort = payload["reasoning"].get("effort")
                    new_effort = _lower_reasoning_effort(current_effort)
                    payload["reasoning"] = {"effort": new_effort}
                    payload["max_output_tokens"] = max(payload.get("max_output_tokens", 256), 512)
                    print(f"[VTUBER_LLM_WARN] Responses API returned empty output but reasoning was present. Retrying with reasoning.effort={new_effort} and max_output_tokens={payload['max_output_tokens']}.", flush=True)
                    continue

            extra_diag: dict[str, Any] = {
                "llm_attempt_count": attempt_count,
                "llm_retry_format": retry_format,
                "llm_request_contains_json_word": "json" in str(payload.get("input", "")).lower()
                    or "json" in str(payload.get("instructions", "")).lower(),
                "llm_attempt_error_previews": attempt_error_previews or None,
                "llm_retried_due_to_incomplete": retried_due_to_incomplete,
                "llm_retried_due_to_empty_output": retried_due_to_empty_output,
            }
            return response_json, retried, extra_diag

        # Record this attempt's error body before deciding what to do
        attempt_error_previews.append((response.text or "")[:500])

        issue = _responses_compat_issue(response, payload, attempted)
        if issue is None:
            # Non-retryable: attach attempt diagnostics to the exception
            exc = httpx.HTTPStatusError(
                message=str(response.status_code),
                request=response.request,
                response=response,
            )
            setattr(exc, "_llm_attempt_count", attempt_count)
            setattr(exc, "_llm_attempt_error_previews", attempt_error_previews)
            setattr(exc, "_llm_retry_format", retry_format)
            raise exc

        attempted.add(issue)
        retried = True

        if issue == "reasoning":
            print(
                f"[VTUBER_LLM_WARN] Responses API rejected reasoning.effort={config.reasoning_effort!r}; "
                "retrying without reasoning.",
                flush=True,
            )
            payload.pop("reasoning", None)

        elif issue == "json_schema":
            print(
                "[VTUBER_LLM_WARN] Responses API rejected json_schema format; retrying with json_object.",
                flush=True,
            )
            payload["text"] = {"format": {"type": "json_object"}}
            retry_format = "json_object"
            # Guarantee the word 'json' is present in input for json_object mode
            payload["input"] = _ensure_json_keyword(str(payload["input"]))

        elif issue == "json_word":
            print(
                "[VTUBER_LLM_WARN] Responses API requires word 'json' in input; appending suffix.",
                flush=True,
            )
            payload["input"] = _ensure_json_keyword(str(payload["input"]))





def chat_completion_json(
    *,
    config: LLMConfig,
    messages: list[dict[str, str]],
    use_response_format: bool = True,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """Call the appropriate LLM endpoint and parse the JSON response.

    For provider=openai: uses the Responses API (POST /v1/responses).
    For local_openai_compatible: uses Chat Completions (POST /chat/completions).

    Returns (parsed_message_json, raw_text, response_json, diagnostics).
    """

    if config.provider == OPENAI_PROVIDER:
        # Extract system and user content from messages list
        system_text = ""
        user_text = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system" and not system_text:
                system_text = content
            elif role in {"user", "developer"} and not user_text:
                user_text = content
        if not user_text and messages:
            user_text = messages[-1].get("content", "")

        # Ensure both instructions and input contain the word "json".
        # The Responses API json_object format requires it in input;
        # adding it upfront avoids the need for a retry.
        JSON_HINT_INSTRUCTIONS = "You must return only valid JSON. No markdown, no prose."
        JSON_HINT_INPUT = (
            'Return a JSON object exactly like: {"a":"action_name","args":{},"reason":"short reason"}'
        )
        if "json" not in system_text.lower():
            system_text = system_text + "\n" + JSON_HINT_INSTRUCTIONS
        if "json" not in user_text.lower():
            user_text = user_text + "\n" + JSON_HINT_INPUT

        started = time.perf_counter()
        endpoint = f"{config.base_url.rstrip('/')}/responses"
        response_json = None
        extra_diag = {}
        retried = False
        try:
            response_json, retried, extra_diag = _post_openai_responses(config, system_text, user_text)
            request_ms = int(round((time.perf_counter() - started) * 1000))
            try:
                raw_text = _extract_responses_output_text(response_json)
                parsed = json.loads(raw_text)
            except Exception as exc:
                setattr(exc, "response_json", response_json)
                for k, v in _extract_responses_diagnostics(response_json).items():
                    setattr(exc, k, v)
                if extra_diag:
                    for k, v in extra_diag.items():
                        setattr(exc, f"_{k}", v)
                raise

            resp_diags = _extract_responses_diagnostics(response_json)
            diagnostics = {
                **llm_diagnostics_base(config),
                "llm_request_ms": request_ms,
                "llm_retried_due_to_param_compat": retried,
                "llm_request_endpoint": endpoint,
                "llm_request_param_keys": ["model", "instructions", "input", "max_output_tokens", "text"],
                **extra_diag,
                **resp_diags,
            }
            if config.reasoning_effort:
                diagnostics["llm_request_param_keys"] = diagnostics["llm_request_param_keys"] + ["reasoning"]
            if os.getenv("VTUBER_DEBUG_LLM") == "1":
                diagnostics["raw_text_preview"] = raw_text[:1000]
            return parsed, raw_text, response_json, diagnostics
        except Exception as exc:
            request_ms = int(round((time.perf_counter() - started) * 1000))
            # Propagate per-attempt diagnostics attached by _post_openai_responses
            setattr(exc, "_llm_attempt_count", getattr(exc, "_llm_attempt_count", extra_diag.get("llm_attempt_count") if extra_diag else None))
            setattr(exc, "_llm_attempt_error_previews", getattr(exc, "_llm_attempt_error_previews", extra_diag.get("llm_attempt_error_previews") if extra_diag else None))
            setattr(exc, "_llm_retry_format", getattr(exc, "_llm_retry_format", extra_diag.get("llm_retry_format") if extra_diag else None))
            setattr(exc, "_llm_retried_due_to_incomplete", getattr(exc, "_llm_retried_due_to_incomplete", extra_diag.get("llm_retried_due_to_incomplete") if extra_diag else None))
            setattr(exc, "_llm_retried_due_to_empty_output", getattr(exc, "_llm_retried_due_to_empty_output", extra_diag.get("llm_retried_due_to_empty_output") if extra_diag else None))
            if response_json is not None:
                setattr(exc, "response_json", response_json)
                for k, v in _extract_responses_diagnostics(response_json).items():
                    if getattr(exc, k, None) is None:
                        setattr(exc, k, v)
            # Store for chat_failure_diagnostics
            setattr(_post_chat_with_compat_retries, "_last_request_ms", request_ms)
            setattr(_post_chat_with_compat_retries, "_last_retried", False)
            raise

    # Local / OpenAI-compatible path (Chat Completions)
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}

    started = time.perf_counter()
    setattr(_post_chat_with_compat_retries, "_last_request_ms", 0)
    setattr(_post_chat_with_compat_retries, "_last_retried", False)
    try:
        response_json = _post_chat_with_compat_retries(config, payload)
        request_ms = int(round((time.perf_counter() - started) * 1000))
        raw_text = response_json["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            setattr(exc, "raw_text", raw_text)
            raise
        diagnostics = {
            **llm_diagnostics_base(config),
            "llm_request_ms": request_ms,
            "llm_retried_due_to_param_compat": bool(payload.pop("_compat_retried", False)),
            "llm_request_endpoint": f"{config.base_url.rstrip('/')}/chat/completions",
            "llm_request_param_keys": [k for k in payload if not k.startswith("_")],
        }
        if os.getenv("VTUBER_DEBUG_LLM") == "1":
            diagnostics["raw_text_preview"] = raw_text[:1000]
        return parsed, raw_text, response_json, diagnostics
    except Exception:
        # Preserve elapsed/retry diagnostics for callers that will build a fallback response.
        retried = bool(payload.pop("_compat_retried", False))
        request_ms = int(round((time.perf_counter() - started) * 1000))
        setattr(_post_chat_with_compat_retries, "_last_request_ms", request_ms)
        setattr(_post_chat_with_compat_retries, "_last_retried", retried)
        raise


def chat_failure_diagnostics(
    config: LLMConfig,
    started: float,
    raw_text: str | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    api_mode = "responses" if config.provider == OPENAI_PROVIDER else "chat_completions"
    endpoint = (
        f"{config.base_url.rstrip('/')}/responses"
        if config.provider == OPENAI_PROVIDER
        else f"{config.base_url.rstrip('/')}/chat/completions"
    )
    info: dict[str, Any] = {
        **llm_diagnostics_base(config),
        "llm_request_ms": int(round((time.perf_counter() - started) * 1000)),
        "llm_retried_due_to_param_compat": bool(getattr(_post_chat_with_compat_retries, "_last_retried", False)),
        "llm_request_endpoint": endpoint,
        "llm_request_api_mode": api_mode,
    }
    if raw_text is not None and os.getenv("VTUBER_DEBUG_LLM") == "1":
        info["raw_text_preview"] = raw_text[:1000]
    # Merge HTTP error diagnostics if available
    http_err_cls = _get_httpx_status_error_cls()
    if exc is not None and isinstance(exc, http_err_cls):
        info.update(_http_error_diagnostics(exc, endpoint=endpoint, api_mode=api_mode))
    # Merge per-attempt diagnostics attached by _post_openai_responses
    if exc is not None:
        attempt_count = getattr(exc, "_llm_attempt_count", None)
        if attempt_count is not None:
            info["llm_attempt_count"] = attempt_count
        retry_format = getattr(exc, "_llm_retry_format", None)
        if retry_format is not None:
            info["llm_retry_format"] = retry_format
        attempt_errors = getattr(exc, "_llm_attempt_error_previews", None)
        if attempt_errors:
            info["llm_attempt_error_previews"] = attempt_errors

        # Merge newer Responses API diagnostics
        for attr in [
            "llm_empty_output",
            "llm_response_id",
            "llm_response_status",
            "llm_response_output_count",
            "llm_response_output_types",
            "llm_response_output_statuses",
            "llm_response_output_incomplete_reasons",
            "llm_response_incomplete_reason",
            "llm_response_error",
            "llm_usage",
            "llm_raw_response_preview",
            "llm_retried_due_to_incomplete",
            "_llm_retried_due_to_incomplete",
            "llm_retried_due_to_empty_output",
            "_llm_retried_due_to_empty_output",
        ]:
            val = getattr(exc, attr, None)
            if val is not None:
                key = attr[1:] if attr.startswith("_") else attr
                info[key] = val

    return info



def _post_chat_with_compat_retries(config: LLMConfig, payload: dict[str, Any]) -> dict[str, Any]:
    import httpx

    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    headers = _headers_for_config(config)
    attempted: set[str] = set()

    while True:
        response = httpx.post(endpoint, headers=headers, json={k: v for k, v in payload.items() if not k.startswith("_")}, timeout=config.timeout_sec)
        if response.status_code < 400:
            return response.json()

        issue = _compat_issue(response, payload, attempted)
        if issue is None:
            response.raise_for_status()

        attempted.add(issue)
        payload["_compat_retried"] = True
        print(f"[VTUBER_LLM_WARN] retrying chat completion after unsupported parameter: {issue}", flush=True)
        if issue == "max_tokens":
            payload["max_completion_tokens"] = payload.pop("max_tokens")
        elif issue == "temperature":
            payload.pop("temperature", None)
        elif issue == "response_format":
            payload.pop("response_format", None)
        elif issue == "reasoning_effort":
            payload.pop("reasoning_effort", None)


def _compat_issue(response: Any, payload: dict[str, Any], attempted: set[str]) -> str | None:
    if response.status_code not in {400, 422}:
        return None
    text = (response.text or "").lower()
    if "max_tokens" in payload and "max_tokens" in text and "max_tokens" not in attempted:
        return "max_tokens"
    if "temperature" in payload and "temperature" in text and "temperature" not in attempted:
        return "temperature"
    if "response_format" in payload and "response_format" in text and "response_format" not in attempted:
        return "response_format"
    if "reasoning_effort" in payload and "reasoning_effort" in text and "reasoning_effort" not in attempted:
        return "reasoning_effort"
    return None

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
    provider = os.getenv("VTUBER_LLM_PROVIDER", LOCAL_OPENAI_COMPATIBLE_PROVIDER).strip().lower() or LOCAL_OPENAI_COMPATIBLE_PROVIDER

    if provider in {"openai_compatible", LOCAL_OPENAI_COMPATIBLE_PROVIDER, OPENAI_PROVIDER}:
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
    config = resolve_llm_config(default_max_tokens=160)
    raw_content: str | None = None
    try:
        parsed, raw_content, _response_json, _diagnostics = chat_completion_json(
            config=config,
            messages=[
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
        )
        return ActionRequest.model_validate(parsed)
    except Exception as exc:
        raw_content = getattr(exc, "raw_text", raw_content)
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

    config = resolve_llm_config(default_max_tokens=160)
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

    messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
    ]

    started = time.perf_counter()
    raw_content: str | None = None
    try:
        parsed, raw_content, _response_json, llm_diag = chat_completion_json(config=config, messages=messages)
        llm_latency_sec = round(llm_diag["llm_request_ms"] / 1000, 3)
        action = ActionRequest.model_validate(parsed)
        return action, {
            "provider": config.provider,
            "fallback_used": False,
            "model": config.model,
            "llm_latency_sec": llm_latency_sec,
            "prompt_size_chars": prompt_size_chars,
            "_raw_response_json": _response_json,
            **llm_diag,
        }
    except Exception as exc:
        raw_content = getattr(exc, "raw_text", raw_content)
        llm_diag = chat_failure_diagnostics(config, started, raw_content, exc=exc)

        fallback_reason = f"LLM planner failed: {type(exc).__name__}."
        if isinstance(exc, ValueError):
            if getattr(exc, "llm_empty_output", False):
                fallback_reason = "LLM planner produced empty Responses output"
            else:
                fallback_reason = f"LLM planner output extraction failed: {str(exc)}"

        info: dict[str, Any] = {
            "provider": config.provider,
            "fallback_used": True,
            "fallback_reason": fallback_reason,
            "model": config.model,
            "llm_latency_sec": round(llm_diag["llm_request_ms"] / 1000, 3),
            "prompt_size_chars": prompt_size_chars,
            **llm_diag,
        }

        resp_json = getattr(exc, "response_json", None)
        if resp_json is not None:
            info["_raw_response_json"] = resp_json

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
