"""One-shot LLM provider smoke test for the Minecraft planner.

Examples:
  uv run python scripts/test_llm_provider.py --provider openai --model gpt-5.5
  uv run python scripts/test_llm_provider.py --provider openai --model gpt-5.5 --debug
  uv run python scripts/test_llm_provider.py --provider local_openai_compatible --model Qwen3.5-9B-Q4_K_M.gguf --base-url http://127.0.0.1:8087/v1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.llm_provider import chat_completion_json, resolve_llm_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the configured planner LLM provider")
    parser.add_argument("--provider", default=None, choices=["local_openai_compatible", "openai"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--debug", action="store_true", help="Print full diagnostics JSON")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    overrides = {
        "provider": args.provider,
        "model": args.model,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
    }
    config = resolve_llm_config(overrides, default_max_tokens=48)
    messages = [
        {
            "role": "system",
            "content": 'Return strict JSON only. Return exactly JSON {"a":"status","args":{}}',
        },
        {
            "role": "user",
            "content": 'Return exactly JSON {"a":"status","args":{}}',
        },
    ]

    try:
        parsed, raw_text, _response, diagnostics = chat_completion_json(config=config, messages=messages)
        print("=== LLM Provider Smoke Test ===")
        print(f"  provider    : {diagnostics.get('llm_provider')}")
        print(f"  model       : {diagnostics.get('llm_model')}")
        print(f"  endpoint    : {diagnostics.get('llm_request_endpoint')}")
        print(f"  api_mode    : {diagnostics.get('llm_request_api_mode')}")
        print(f"  latency_ms  : {diagnostics.get('llm_request_ms')}")
        print(f"  parsed      : {json.dumps(parsed)}")
        print(f"  raw_preview : {raw_text[:200]}")
        if args.debug:
            print("\n=== Full Diagnostics ===")
            print(json.dumps(diagnostics, indent=2))
    except Exception as exc:  # noqa: BLE001
        from vtuber_ai.llm_provider import chat_failure_diagnostics
        import time
        started = time.perf_counter()
        failure_diag = chat_failure_diagnostics(config, started, exc=exc)
        print("=== LLM Provider Smoke Test [FAILED] ===")
        print(f"  provider         : {failure_diag.get('llm_provider')}")
        print(f"  model            : {failure_diag.get('llm_model')}")
        print(f"  endpoint         : {failure_diag.get('llm_request_endpoint')}")
        print(f"  api_mode         : {failure_diag.get('llm_request_api_mode')}")
        print(f"  error            : {type(exc).__name__}: {exc}")
        if "llm_http_status_code" in failure_diag:
            print(f"  http_status      : {failure_diag['llm_http_status_code']}")
            print(f"  http_error_body  : {failure_diag.get('llm_http_error_body_preview', '')[:400]}")
            if failure_diag.get("llm_http_error_type"):
                print(f"  http_error_type  : {failure_diag['llm_http_error_type']}")
            if failure_diag.get("llm_http_error_code"):
                print(f"  http_error_code  : {failure_diag['llm_http_error_code']}")
        if args.debug:
            print("\n=== Full Failure Diagnostics ===")
            print(json.dumps(failure_diag, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
