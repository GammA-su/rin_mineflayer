"""Continuous stream runner for the AI VTuber Minecraft agent.

Calls /agent/tick in a loop so each tick is printed the moment it completes.
Batch JSON files are saved every --max-ticks-per-batch ticks.
Stops only on Ctrl+C.

Usage:
    uv run python scripts/run_stream_loop.py --mission "Beat Minecraft while playing naturally and surviving."

With full context mode:
    uv run python scripts/run_stream_loop.py \\
      --mission "Beat Minecraft while playing naturally and surviving." \\
      --context-mode full \\
      --full-context-max-ticks 1000

With sliding window:
    uv run python scripts/run_stream_loop.py \\
      --context-mode full-window \\
      --full-context-window-ticks 200
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

import httpx

_DEFAULT_API_URL = "http://127.0.0.1:8000"
_DEFAULT_OUT_DIR = "out/stream_runs"
_DEFAULT_MISSION = "Beat Minecraft while playing naturally and surviving."
_DEFAULT_USER = "AI_VTuber"
_DEFAULT_MAX_TICKS = 25
_DEFAULT_TICK_DELAY = 1.0
_DEFAULT_EPISODE_TICKS = 50
_RETRY_WAIT_SEC = 5

_DEFAULT_PERSONALITY_TIMEOUT = float(
    os.getenv("PERSONALITY_ENGINE_TIMEOUT_SEC", "0.75")
)

_CONTEXT_MODES = ("compressed", "full", "full-window", "episodic")
# "episodic" uses compressed context for the planner but enables episode
# summaries every --episode-ticks ticks and injects episode_memory into each tick.


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Continuous AI VTuber stream loop")
    p.add_argument("--mission", default=_DEFAULT_MISSION)
    p.add_argument("--user", default=_DEFAULT_USER)
    p.add_argument("--max-ticks-per-batch", type=int, default=_DEFAULT_MAX_TICKS, dest="max_ticks")
    p.add_argument("--tick-delay-sec", type=float, default=_DEFAULT_TICK_DELAY, dest="tick_delay_sec")
    p.add_argument("--api-url", default=_DEFAULT_API_URL, dest="api_url")
    p.add_argument("--out-dir", default=_DEFAULT_OUT_DIR, dest="out_dir")
    p.add_argument("--llm-provider", default=None, dest="llm_provider")
    p.add_argument("--llm-model", default=None, dest="llm_model")
    p.add_argument("--llm-base-url", default=None, dest="llm_base_url")
    p.add_argument(
        "--llm-api-key-env",
        default=None,
        dest="llm_api_key_env",
        help="Name of the environment variable containing the LLM API key; never the key value itself.",
    )
    p.add_argument(
        "--personality-url",
        default=None,
        dest="personality_url",
        help="Personality engine event endpoint, e.g. http://127.0.0.1:8010/events/tick",
    )
    p.add_argument(
        "--personality-timeout-sec",
        type=float,
        default=_DEFAULT_PERSONALITY_TIMEOUT,
        dest="personality_timeout_sec",
        help="Max seconds to wait for the personality service (default 0.75)",
    )
    # Context mode options
    p.add_argument(
        "--context-mode",
        choices=_CONTEXT_MODES,
        default="compressed",
        dest="context_mode",
        help="Planner context mode: compressed (default), full, full-window, or episodic (compressed + episode summaries)",
    )
    p.add_argument(
        "--full-context-max-ticks",
        type=int,
        default=1000,
        dest="full_context_max_ticks",
        help="Max ticks to include in 'full' mode (default 1000)",
    )
    p.add_argument(
        "--full-context-window-ticks",
        type=int,
        default=200,
        dest="full_context_window_ticks",
        help="Sliding window size for 'full-window' mode (default 200)",
    )
    p.add_argument(
        "--full-context-include-raw-results",
        action="store_true",
        default=False,
        dest="full_context_include_raw_results",
        help="Include full raw result objects in compact history (default false)",
    )
    p.add_argument(
        "--full-context-include-planner-debug",
        action="store_true",
        default=False,
        dest="full_context_include_planner_debug",
        help="Include planner debug fields in compact history (default false)",
    )
    p.add_argument(
        "--episode-ticks",
        type=int,
        default=_DEFAULT_EPISODE_TICKS,
        dest="episode_ticks",
        help=f"Generate a strategic episode summary every N ticks (default {_DEFAULT_EPISODE_TICKS}; 0 to disable)",
    )
    p.add_argument(
        "--episode-summary-provider",
        default="same",
        dest="episode_summary_provider",
        help="LLM provider for episode summaries: 'same' uses the same provider as the planner (default)",
    )
    p.add_argument(
        "--episode-memory-max-episodes",
        type=int,
        default=20,
        dest="episode_memory_max_episodes",
        help="Max number of past episode summaries to keep in memory (default 20)",
    )
    return p.parse_args()


def _action_name(tick: dict) -> str:
    action = tick.get("action")
    if isinstance(action, dict):
        return action.get("action") or "?"
    if isinstance(action, str):
        return action
    return "?"


def _action_args(tick: dict) -> dict:
    action = tick.get("action")
    if isinstance(action, dict):
        return action.get("args") or {}
    return tick.get("args") or {}


def _action_objective(tick: dict) -> str:
    action = tick.get("action")
    if isinstance(action, dict):
        return action.get("objective") or ""
    return ""


def _result_payload(tick: dict) -> dict:
    """Unwrap ActionResult nesting: result.result is the actual payload dict."""
    outer = tick.get("result") or {}
    if not isinstance(outer, dict):
        return {}
    inner = outer.get("result")
    return inner if isinstance(inner, dict) else outer


def _tick_line(global_tick: int, tick: dict) -> str:
    """Format one tick as a compact log line."""
    action = _action_name(tick)
    args = _action_args(tick)
    ok = bool(tick.get("ok"))

    payload = _result_payload(tick)
    verifier = tick.get("verifier") or {}
    if not isinstance(verifier, dict):
        verifier = {}

    outer_result = tick.get("result") or {}
    if not isinstance(outer_result, dict):
        outer_result = {}

    failure_type = (
        verifier.get("failure_type")
        or payload.get("failure_type")
        or outer_result.get("failure_type")
        or "none"
    )

    stop_reason = (
        payload.get("stop_reason")
        or verifier.get("stop_reason")
        or outer_result.get("stop_reason")
        or ""
    )

    collected = (
        payload.get("collected")
        if payload.get("collected") is not None
        else payload.get("count")
    )

    error = (
        outer_result.get("error")
        or tick.get("error")
        or payload.get("error")
        or ""
    )

    args_str = json.dumps(args, separators=(",", ":")) if args else "{}"
    parts = [
        f"[{global_tick}]",
        action,
        args_str,
        "->",
        f"ok={'true' if ok else 'false'}",
        f"failure={failure_type}",
    ]
    if stop_reason:
        parts.append(f"stop={stop_reason}")
    if collected is not None:
        parts.append(f"collected={collected}")
    if error:
        parts.append(f"error={error!r}")

    return " ".join(parts)


def _build_compact_event(
    global_tick: int,
    batch_num: int,
    local_tick: int,
    tick: dict,
    include_raw_results: bool = False,
    include_planner_debug: bool = False,
) -> dict[str, Any]:
    """Build a compact tick history event from a full tick response."""
    action = _action_name(tick)
    args = _action_args(tick)
    objective = _action_objective(tick)
    ok = bool(tick.get("ok"))

    payload = _result_payload(tick)
    verifier = tick.get("verifier") or {}
    if not isinstance(verifier, dict):
        verifier = {}
    outer_result = tick.get("result") or {}
    if not isinstance(outer_result, dict):
        outer_result = {}

    failure_type = (
        verifier.get("failure_type")
        or payload.get("failure_type")
        or outer_result.get("failure_type")
        or ("none" if ok else "unknown")
    )

    stop_reason = (
        payload.get("stop_reason")
        or verifier.get("stop_reason")
        or outer_result.get("stop_reason")
    )

    error = (
        outer_result.get("error")
        or tick.get("error")
        or payload.get("error")
    )

    # Position from after_status
    after_status = tick.get("after_status") or tick.get("before_status") or {}
    if isinstance(after_status, dict):
        position = after_status.get("position")
    else:
        position = None

    # Important result: inventory delta, collected count, partial success
    important_result: dict[str, Any] = {}
    for key in ("collected", "inventory_delta", "partial_success", "distance_moved",
                "targetCandidatesFound", "blocks_dug"):
        val = payload.get(key)
        if val is not None:
            important_result[key] = val
    if not important_result and include_raw_results:
        important_result = payload

    # Stuck state kind from planner info
    planner = tick.get("planner") or {}
    if not isinstance(planner, dict):
        planner = {}
    stuck_state = planner.get("stuck_state") or {}
    if isinstance(stuck_state, dict):
        stuck_state_kind = stuck_state.get("kind")
    else:
        stuck_state_kind = None

    event: dict[str, Any] = {
        "global_tick": global_tick,
        "batch": batch_num,
        "local_tick": local_tick,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "objective": objective,
        "action": action,
        "args": args,
        "ok": ok,
        "failure_type": failure_type,
        "stop_reason": stop_reason,
        "error": error,
        "position": position,
        "important_result": important_result or None,
        "stuck_state_kind": stuck_state_kind,
    }

    if include_planner_debug:
        event["planner_debug"] = {
            k: planner.get(k)
            for k in ("context_mode", "full_context_tick_count", "prompt_size_chars",
                      "llm_latency_sec", "prompt_budget_exceeded", "fallback_used")
        }

    return event


def _emit(line: str, log_fh: IO[str]) -> None:
    print(line)
    sys.stdout.flush()
    log_fh.write(line + "\n")
    log_fh.flush()


def _save_batch(out_dir: Path, batch_num: int, ticks: list[dict], global_start: int) -> None:
    path = out_dir / f"batch_{batch_num:06d}.json"
    data = {
        "batch": batch_num,
        "ticks_run": len(ticks),
        "global_tick_start": global_start,
        "global_tick_end": global_start + len(ticks) - 1,
        "ticks": ticks,
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


def _save_run_config(out_dir: Path, args: argparse.Namespace, llm_payload: dict) -> None:
    config = {
        "run_id": out_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mission": args.mission,
        "user": args.user,
        "api_url": args.api_url,
        "llm_provider": llm_payload.get("provider"),
        "llm_model": llm_payload.get("model"),
        "llm_base_url": llm_payload.get("base_url"),
        "context_mode": args.context_mode,
        "full_context_max_ticks": args.full_context_max_ticks,
        "full_context_window_ticks": args.full_context_window_ticks,
        "full_context_include_raw_results": args.full_context_include_raw_results,
        "full_context_include_planner_debug": args.full_context_include_planner_debug,
        "episode_ticks": args.episode_ticks,
        "episode_summary_provider": args.episode_summary_provider,
        "episode_memory_max_episodes": args.episode_memory_max_episodes,
        "max_ticks_per_batch": args.max_ticks,
        "tick_delay_sec": args.tick_delay_sec,
    }
    (out_dir / "run_config.json").write_text(json.dumps(config, indent=2, default=str), encoding="utf-8")


def _publish_in_background(
    tick_id: int,
    tick: dict,
    run_id: str,
    url: str,
    timeout_sec: float,
) -> None:
    """Build and POST the BrainTickEvent on a daemon thread — fire-and-forget."""
    try:
        from vtuber_ai.personality_publisher import build_tick_event, publish_tick_event
    except ImportError:
        return

    event = build_tick_event(tick_id=tick_id, tick=tick, run_id=run_id)
    t = threading.Thread(
        target=publish_tick_event,
        args=(event, url, timeout_sec),
        daemon=True,
        name=f"personality-{tick_id}",
    )
    t.start()


def _call_episode_summary(
    client: httpx.Client,
    api_url: str,
    episode_index: int,
    tick_range: list[int],
    episode_compact_ticks: list[dict],
    last_tick: dict | None,
    llm_payload: dict,
) -> dict | None:
    """POST /agent/episode_summary and return the parsed result, or None on failure."""
    last_status = None
    milestones = None
    if isinstance(last_tick, dict):
        last_status = last_tick.get("after_status") or last_tick.get("before_status")
        milestones = last_tick.get("milestones")

    payload: dict = {
        "episode_index": episode_index,
        "tick_range": tick_range,
        "episode_ticks": episode_compact_ticks,
    }
    if last_status:
        payload["last_status"] = last_status
    if milestones:
        payload["milestones"] = milestones
    if llm_payload:
        payload["llm"] = llm_payload

    try:
        resp = client.post(api_url.rstrip("/") + "/agent/episode_summary", json=payload, timeout=60.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"  [episode_summary error] {exc}", flush=True)
        return None


def _print_episode_banner(summary: dict, log_fh: "IO[str]") -> None:
    """Print and log the strategic episode summary banner."""
    ep = summary.get("episode_index", "?")
    phase = summary.get("current_game_phase", "unknown")
    conf = summary.get("phase_confidence", "?")
    strategy = summary.get("next_50_tick_strategy") or {}
    intent = strategy.get("strategic_intent", "")
    why = strategy.get("why_this_advances_the_game", "")
    priorities = strategy.get("priority_order") or []
    avoid = strategy.get("avoid") or []
    progress = summary.get("win_condition_progress") or {}
    what_advanced = progress.get("what_advanced") or []
    self_summary = summary.get("self_summary", "")
    source = summary.get("summary_source", "llm")

    lines = [
        f"=== Episode {ep} strategic memory ===",
        f"Phase: {phase} (confidence: {conf})  source={source}",
        f"Summary: {self_summary}",
    ]
    if what_advanced:
        lines.append("Progress toward beating game:")
        for item in what_advanced[:5]:
            lines.append(f"  - {item}")
    if intent:
        lines.append(f"Next {_DEFAULT_EPISODE_TICKS}-tick intent:")
        lines.append(f"  {intent}")
    if why:
        lines.append(f"  Why: {why}")
    if priorities:
        lines.append("Priorities:")
        for p in priorities[:4]:
            lines.append(f"  {priorities.index(p)+1}. {p}")
    if avoid:
        lines.append("Avoid:")
        for a in avoid[:3]:
            lines.append(f"  - {a}")
    lines.append("=" * 36)

    for line in lines:
        _emit(line, log_fh)


def main() -> None:
    args = _parse_args()

    # Resolve personality config: CLI flag takes precedence over env vars.
    cli_url: str | None = args.personality_url
    env_url: str = os.getenv("PERSONALITY_ENGINE_URL", "").strip()
    env_enabled: bool = os.getenv("PERSONALITY_ENGINE_ENABLED", "false").strip().lower() in (
        "1", "true", "yes"
    )
    personality_url: str = cli_url or env_url
    personality_enabled: bool = bool(cli_url) or (bool(env_url) and env_enabled)
    personality_timeout_sec: float = args.personality_timeout_sec

    _stop = threading.Event()
    signal.signal(signal.SIGINT, lambda _sig, _frame: _stop.set())

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) / run_ts
    out_dir.mkdir(parents=True, exist_ok=True)

    llm_payload = {
        "provider": args.llm_provider,
        "model": args.llm_model,
        "base_url": args.llm_base_url,
        "api_key_env": args.llm_api_key_env,
    }
    llm_payload = {key: value for key, value in llm_payload.items() if value}

    # "episodic" mode: use compressed context for the backend, enable episode summaries.
    # The episode memory is injected per-tick instead of sending the full history.
    is_episodic = args.context_mode == "episodic"
    backend_context_mode = "compressed" if is_episodic else args.context_mode
    # Auto-enable episode summaries in episodic mode if not explicitly set to 0.
    effective_episode_ticks = args.episode_ticks if not is_episodic else (
        args.episode_ticks if args.episode_ticks > 0 else _DEFAULT_EPISODE_TICKS
    )

    _save_run_config(out_dir, args, llm_payload)

    base_payload: dict[str, Any] = {
        "mission": args.mission,
        "user": args.user,
        "planner": "hybrid",
        "allow_autonomy": True,
        "context_mode": backend_context_mode,
    }
    if llm_payload:
        base_payload["llm"] = llm_payload

    url = args.api_url.rstrip("/") + "/agent/tick"

    # In-memory compact tick history for full/full-window modes
    compact_history: list[dict[str, Any]] = []
    history_jsonl_path = out_dir / "tick_history_compact.jsonl"
    history_fh = history_jsonl_path.open("w", encoding="utf-8")

    log_path = out_dir / "actions.log"
    try:
        with log_path.open("w", encoding="utf-8") as log_fh:
            _emit(f"Stream loop starting — output: {out_dir}", log_fh)
            _emit(f"  mission      : {args.mission}", log_fh)
            _emit(f"  api_url      : {url}", log_fh)
            _emit(f"  context_mode : {args.context_mode}", log_fh)
            if args.context_mode == "full":
                _emit(f"  max_ticks    : {args.full_context_max_ticks}", log_fh)
            elif args.context_mode == "full-window":
                _emit(f"  window_ticks : {args.full_context_window_ticks}", log_fh)
            elif is_episodic:
                _emit(f"  backend mode : compressed + episode memory injection", log_fh)
            if effective_episode_ticks > 0:
                _emit(f"  episode_ticks: {effective_episode_ticks}  max_episodes={args.episode_memory_max_episodes}", log_fh)
            if llm_payload:
                _emit(
                    "  llm          : "
                    f"provider={llm_payload.get('provider', '(env)')} "
                    f"model={llm_payload.get('model', '(env)')} "
                    f"base_url={llm_payload.get('base_url', '(env)')} "
                    f"api_key_env={llm_payload.get('api_key_env', '(provider default)')}",
                    log_fh,
                )
            _emit(f"  ticks/batch  : {args.max_ticks}  tick_delay: {args.tick_delay_sec}s", log_fh)
            if personality_enabled and personality_url:
                _emit(
                    f"  personality  : {personality_url}  timeout={personality_timeout_sec}s",
                    log_fh,
                )
            else:
                _emit("  personality  : disabled", log_fh)
            _emit("Press Ctrl+C to stop.", log_fh)
            _emit("", log_fh)

            global_tick = 0
            batch_num = 0
            batch_ticks: list[dict] = []
            batch_global_start = 1

            # Episode tracking
            episode_index = 0
            episode_start_tick = 1
            episode_compact_ticks: list[dict] = []
            episode_history: list[dict] = []  # last N episode summaries
            last_episode_memory: dict | None = None
            last_full_tick: dict | None = None

            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)) as client:
                while not _stop.is_set():
                    # Build payload with full context and episode memory if available
                    payload = dict(base_payload)
                    if args.context_mode != "compressed" and compact_history:
                        payload["full_context"] = {
                            "ticks": compact_history,
                            "max_ticks": args.full_context_max_ticks,
                            "window_ticks": args.full_context_window_ticks,
                            "include_raw_results": args.full_context_include_raw_results,
                            "include_planner_debug": args.full_context_include_planner_debug,
                        }
                    if last_episode_memory is not None:
                        payload["episode_memory"] = last_episode_memory

                    try:
                        resp = client.post(url, json=payload)
                        resp.raise_for_status()
                        tick = resp.json()
                    except Exception as exc:
                        if _stop.is_set():
                            break
                        _emit(f"  [API error] {exc} — retrying in {_RETRY_WAIT_SEC}s …", log_fh)
                        _stop.wait(timeout=_RETRY_WAIT_SEC)
                        continue

                    if _stop.is_set():
                        break

                    global_tick += 1
                    local_tick = len(batch_ticks) + 1
                    tick["tick"] = global_tick
                    batch_ticks.append(tick)
                    last_full_tick = tick

                    _emit(_tick_line(global_tick, tick), log_fh)

                    # Build and store compact event
                    compact_event = _build_compact_event(
                        global_tick=global_tick,
                        batch_num=batch_num + 1,
                        local_tick=local_tick,
                        tick=tick,
                        include_raw_results=args.full_context_include_raw_results,
                        include_planner_debug=args.full_context_include_planner_debug,
                    )
                    compact_history.append(compact_event)
                    episode_compact_ticks.append(compact_event)
                    history_fh.write(json.dumps(compact_event, default=str) + "\n")
                    history_fh.flush()

                    if personality_enabled and personality_url:
                        _publish_in_background(
                            tick_id=global_tick,
                            tick=tick,
                            run_id=run_ts,
                            url=personality_url,
                            timeout_sec=personality_timeout_sec,
                        )

                    if len(batch_ticks) >= args.max_ticks:
                        batch_num += 1
                        _save_batch(out_dir, batch_num, batch_ticks, batch_global_start)
                        _emit(f"  [batch {batch_num} saved  ticks {batch_global_start}-{global_tick}]", log_fh)
                        batch_ticks = []
                        batch_global_start = global_tick + 1

                    # Episode summary every --episode-ticks ticks
                    if effective_episode_ticks > 0 and global_tick > 0 and global_tick % effective_episode_ticks == 0:
                        episode_index += 1
                        _emit(f"  [generating episode {episode_index} summary ticks {episode_start_tick}-{global_tick}]", log_fh)
                        ep_summary = _call_episode_summary(
                            client=client,
                            api_url=args.api_url,
                            episode_index=episode_index,
                            tick_range=[episode_start_tick, global_tick],
                            episode_compact_ticks=episode_compact_ticks,
                            last_tick=last_full_tick,
                            llm_payload=llm_payload,
                        )
                        if ep_summary is not None:
                            last_episode_memory = {k: v for k, v in ep_summary.items() if k != "ok"}
                            episode_history.append(last_episode_memory)
                            # Trim to max_episodes
                            if len(episode_history) > args.episode_memory_max_episodes:
                                episode_history = episode_history[-args.episode_memory_max_episodes:]
                            _print_episode_banner(last_episode_memory, log_fh)
                            # Save episode summary to file
                            ep_path = out_dir / f"episode_{episode_index:04d}.json"
                            ep_path.write_text(json.dumps(last_episode_memory, indent=2, default=str), encoding="utf-8")
                        else:
                            _emit(f"  [episode {episode_index} summary failed]", log_fh)
                        episode_compact_ticks = []
                        episode_start_tick = global_tick + 1

                    if args.tick_delay_sec > 0:
                        _stop.wait(timeout=args.tick_delay_sec)

            # save any partial batch on exit
            if batch_ticks:
                batch_num += 1
                _save_batch(out_dir, batch_num, batch_ticks, batch_global_start)
                _emit(f"  [batch {batch_num} saved  ticks {batch_global_start}-{global_tick} (partial)]", log_fh)

            _emit(f"\nStopped. {global_tick} ticks total. Output: {out_dir}", log_fh)
    finally:
        history_fh.close()


if __name__ == "__main__":
    main()
