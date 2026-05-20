"""Continuous stream runner for the AI VTuber Minecraft agent.

Calls /agent/tick in a loop so each tick is printed the moment it completes.
Batch JSON files are saved every --max-ticks-per-batch ticks.
Stops only on Ctrl+C.

Usage:
    uv run python scripts/run_stream_loop.py --mission "Beat Minecraft while playing naturally and surviving."

With personality engine:
    uv run python scripts/run_stream_loop.py \\
      --mission "Beat Minecraft while playing naturally and surviving." \\
      --personality-url http://127.0.0.1:8010/events/tick
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
from typing import IO

import httpx

_DEFAULT_API_URL = "http://127.0.0.1:8000"
_DEFAULT_OUT_DIR = "out/stream_runs"
_DEFAULT_MISSION = "Beat Minecraft while playing naturally and surviving."
_DEFAULT_USER = "AI_VTuber"
_DEFAULT_MAX_TICKS = 25
_DEFAULT_TICK_DELAY = 1.0
_RETRY_WAIT_SEC = 5

_DEFAULT_PERSONALITY_TIMEOUT = float(
    os.getenv("PERSONALITY_ENGINE_TIMEOUT_SEC", "0.75")
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Continuous AI VTuber stream loop")
    p.add_argument("--mission", default=_DEFAULT_MISSION)
    p.add_argument("--user", default=_DEFAULT_USER)
    p.add_argument("--max-ticks-per-batch", type=int, default=_DEFAULT_MAX_TICKS, dest="max_ticks")
    p.add_argument("--tick-delay-sec", type=float, default=_DEFAULT_TICK_DELAY, dest="tick_delay_sec")
    p.add_argument("--api-url", default=_DEFAULT_API_URL, dest="api_url")
    p.add_argument("--out-dir", default=_DEFAULT_OUT_DIR, dest="out_dir")
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


def _result_payload(tick: dict) -> dict:
    """Unwrap ActionResult nesting: result.result is the actual payload dict."""
    outer = tick.get("result") or {}
    if not isinstance(outer, dict):
        return {}
    inner = outer.get("result")
    return inner if isinstance(inner, dict) else outer


def _tick_line(global_tick: int, tick: dict) -> str:
    """Format one tick as a compact log line.

    [42] mine_coal {"count":1} -> ok=true failure=none stop=collected_requested collected=4
    """
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


def main() -> None:
    args = _parse_args()

    # Resolve personality config: CLI flag takes precedence over env vars.
    cli_url: str | None = args.personality_url
    env_url: str = os.getenv("PERSONALITY_ENGINE_URL", "").strip()
    env_enabled: bool = os.getenv("PERSONALITY_ENGINE_ENABLED", "false").strip().lower() in (
        "1", "true", "yes"
    )
    personality_url: str = cli_url or env_url
    # CLI URL always enables publishing; env URL requires PERSONALITY_ENGINE_ENABLED=true.
    personality_enabled: bool = bool(cli_url) or (bool(env_url) and env_enabled)
    personality_timeout_sec: float = args.personality_timeout_sec

    # _stop is set by the SIGINT handler. All sleeps use _stop.wait(timeout=N)
    # so they return immediately on Ctrl+C regardless of what httpx does with the signal.
    _stop = threading.Event()
    signal.signal(signal.SIGINT, lambda _sig, _frame: _stop.set())

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) / run_ts
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "mission": args.mission,
        "user": args.user,
        "planner": "hybrid",
        "allow_autonomy": True,
    }
    url = args.api_url.rstrip("/") + "/agent/tick"

    log_path = out_dir / "actions.log"
    with log_path.open("w", encoding="utf-8") as log_fh:
        _emit(f"Stream loop starting — output: {out_dir}", log_fh)
        _emit(f"  mission    : {args.mission}", log_fh)
        _emit(f"  api_url    : {url}", log_fh)
        _emit(f"  ticks/batch: {args.max_ticks}  tick_delay: {args.tick_delay_sec}s", log_fh)
        if personality_enabled and personality_url:
            _emit(
                f"  personality: {personality_url}  timeout={personality_timeout_sec}s",
                log_fh,
            )
        else:
            _emit("  personality: disabled", log_fh)
        _emit("Press Ctrl+C to stop.", log_fh)
        _emit("", log_fh)

        global_tick = 0
        batch_num = 0
        batch_ticks: list[dict] = []
        batch_global_start = 1

        with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)) as client:
            while not _stop.is_set():
                try:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    tick = resp.json()
                except Exception as exc:
                    # Check flag first: httpx sometimes wraps a SIGINT as a
                    # RemoteProtocolError or ReadError instead of re-raising
                    # KeyboardInterrupt, which would cause infinite retries.
                    if _stop.is_set():
                        break
                    _emit(f"  [API error] {exc} — retrying in {_RETRY_WAIT_SEC}s …", log_fh)
                    _stop.wait(timeout=_RETRY_WAIT_SEC)
                    continue

                if _stop.is_set():
                    break

                global_tick += 1
                tick["tick"] = global_tick
                batch_ticks.append(tick)

                _emit(_tick_line(global_tick, tick), log_fh)

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

                if args.tick_delay_sec > 0:
                    _stop.wait(timeout=args.tick_delay_sec)

        # save any partial batch on exit
        if batch_ticks:
            batch_num += 1
            _save_batch(out_dir, batch_num, batch_ticks, batch_global_start)
            _emit(f"  [batch {batch_num} saved  ticks {batch_global_start}-{global_tick} (partial)]", log_fh)

        _emit(f"\nStopped. {global_tick} ticks total. Output: {out_dir}", log_fh)


if __name__ == "__main__":
    main()
