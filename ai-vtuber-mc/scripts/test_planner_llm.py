"""Real planner invocation test for the OpenAI Responses API path.

Uses an actual game-state packet (overworld start, empty inventory) rather than the
smoke-test prompt that forces status.  This exercises the full planner path so that
HTTP errors from the Responses API surface with full diagnostics.

Examples:
  uv run python scripts/test_planner_llm.py --provider openai --model gpt-5.5 --debug
  uv run python scripts/test_planner_llm.py --provider local_openai_compatible --base-url http://127.0.0.1:8087/v1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.game_brain import AUTONOMOUS_ALLOWED_ACTIONS, choose_next_action


def _build_starter_state() -> dict:
    """Build a realistic minimal overworld start state."""
    summary = {
        "ok": True,
        "health": 20,
        "food": 20,
        "hostile_nearby": False,
        "has_food": False,
        "dimension": "overworld",
        "time": {"timeOfDay": 1000, "isDay": True},
        "position": {"x": 0, "y": 64, "z": 0},
        "inventory_counts": {},
        "nearby_blocks": {
            "oak_log": {"name": "oak_log", "position": {"x": 3, "y": 64, "z": 0}},
            "grass_block": {"name": "grass_block", "position": {"x": 1, "y": 63, "z": 0}},
        },
        "nearby_block_counts": {"oak_log": 5, "grass_block": 12, "dirt": 8, "stone": 3},
        "nearby_entities": [],
    }
    return {
        "summary": summary,
        "recent_ticks": [],
        "last_action": None,
        "last_result": None,
        "last_verifier": None,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real planner LLM test using full game-state packet")
    parser.add_argument("--provider", default=None, choices=["local_openai_compatible", "openai"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--debug", action="store_true", help="Print full diagnostics JSON")
    parser.add_argument("--dump-raw-response", action="store_true", help="Dump the full raw JSON response to a file")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    import os
    if args.debug:
        os.environ["VTUBER_DEBUG_LLM"] = "1"

    llm_config: dict = {k: v for k, v in {
        "provider": args.provider,
        "model": args.model,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
    }.items() if v is not None}

    state = _build_starter_state()
    mission = "Beat Minecraft by playing naturally and surviving."

    print("=== Planner LLM Test ===")
    print(f"  provider : {args.provider or '(from env)'}")
    print(f"  model    : {args.model or '(from env)'}")
    print()

    decision, info = choose_next_action(
        state,
        [],
        mission,
        AUTONOMOUS_ALLOWED_ACTIONS,
        "llm",
        llm_config=llm_config or None,
    )

    print(f"  endpoint      : {info.get('llm_request_endpoint')}")
    print(f"  api_mode      : {info.get('llm_request_api_mode')}")
    print(f"  attempt_count : {info.get('llm_attempt_count', 1)}")
    print(f"  retry_format  : {info.get('llm_retry_format', 'none (first attempt succeeded)')}")
    print(f"  input_has_json: {info.get('llm_request_contains_json_word')}")
    print(f"  fallback_used : {info.get('fallback_used')}")

    if info.get("fallback_used"):
        print(f"  fallback_reason      : {info.get('fallback_reason')}")
        if info.get("llm_http_status_code") is not None:
            print(f"  llm_http_status_code : {info['llm_http_status_code']}")
            print(f"  llm_http_error_body  : {str(info.get('llm_http_error_body_preview', ''))[:400]}")
            if info.get("llm_http_error_type"):
                print(f"  llm_http_error_type  : {info['llm_http_error_type']}")
            if info.get("llm_http_error_code"):
                print(f"  llm_http_error_code  : {info['llm_http_error_code']}")
        attempt_errors = info.get("llm_attempt_error_previews")
        if attempt_errors:
            print(f"  all attempt errors ({len(attempt_errors)}):")
            for i, err in enumerate(attempt_errors, 1):
                print(f"    [{i}] {err[:200]}")
        raw_preview = info.get("raw_llm_text_preview")
        print(f"  raw_llm_text_preview : {raw_preview}")
        print(f"  parsed_action        : None (fallback)")
    else:
        raw_len = info.get("raw_llm_output_chars", 0)
        print(f"  raw_llm_output_chars : {raw_len}")
        print(f"  parsed_action        : {decision.action}  args={json.dumps(decision.args)}")
        if decision.speech:
            print(f"  speech               : {decision.speech}")
        if decision.reason:
            print(f"  reason               : {decision.reason}")

    print(f"  latency_ms    : {info.get('llm_request_ms')}")

    if args.dump_raw_response:
        raw_resp = info.get("_raw_response_json")
        if raw_resp:
            import time
            from pathlib import Path
            out_dir = Path("out/debug")
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time())
            filepath = out_dir / f"openai_response_{timestamp}.json"
            with filepath.open("w", encoding="utf-8") as f:
                json.dump(raw_resp, f, indent=2)
            print(f"  Raw response dumped to: {filepath}")
        else:
            print("  No raw response available to dump.")

    if args.debug:
        print("\n=== Full Diagnostics ===")
        # Remove raw response from diagnostics dump so it doesn't clutter the terminal
        diag_to_print = {k: v for k, v in info.items() if k != "_raw_response_json"}
        safe_info = {k: v for k, v in diag_to_print.items() if "key" not in k.lower() and "secret" not in k.lower()}
        print(json.dumps(safe_info, indent=2, default=str))

    if info.get("fallback_used"):
        sys.exit(1)


if __name__ == "__main__":
    main()
