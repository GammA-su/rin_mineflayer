"""
Summarize a stream run directory.

Usage:
    uv run python scripts/summarize_stream_run.py out/stream_runs/<run_id>
    uv run python scripts/summarize_stream_run.py out/stream_runs/<run_id> out/stream_runs/<run_id2> ...

Reads batch_*.json and tick_history_compact.jsonl (if present) from each run directory.
Prints a comparison-friendly summary: total ticks, action counts, failure counts,
material progress, timeouts, stuck states, fallback count, LLM latency, token estimates.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_batches(run_dir: Path) -> list[dict]:
    batches = sorted(run_dir.glob("batch_*.json"))
    result = []
    for p in batches:
        try:
            result.append(json.loads(p.read_text()))
        except Exception as e:
            print(f"  [warn] could not read {p.name}: {e}", file=sys.stderr)
    return result


def _load_compact_history(run_dir: Path) -> list[dict]:
    p = run_dir / "tick_history_compact.jsonl"
    if not p.exists():
        return []
    events = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return events


def _load_run_config(run_dir: Path) -> dict:
    p = run_dir / "run_config.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _flatten_ticks(batches: list[dict]) -> list[dict]:
    ticks = []
    for b in batches:
        for t in b.get("ticks", []):
            ticks.append(t)
    return ticks


def _item_count_from_inventory(inventory: list[dict] | None, item: str) -> int:
    if not inventory:
        return 0
    return sum(s.get("count", 0) for s in inventory if s.get("name") == item)


def _last_inventory(ticks: list[dict]) -> dict[str, int]:
    for t in reversed(ticks):
        inv = (t.get("after_status") or t.get("before_status") or {}).get("inventory")
        if inv:
            counts: dict[str, int] = defaultdict(int)
            for slot in inv:
                counts[slot["name"]] += slot.get("count", 0)
            return dict(counts)
    return {}


# ── per-run summary ───────────────────────────────────────────────────────────

def summarize_run(run_dir: Path) -> dict[str, Any]:
    batches = _load_batches(run_dir)
    compact = _load_compact_history(run_dir)
    config = _load_run_config(run_dir)
    ticks = _flatten_ticks(batches)

    total_ticks = len(ticks)
    if total_ticks == 0 and compact:
        total_ticks = len(compact)

    # ── action counts ──────────────────────────────────────────────────────
    action_counts: Counter = Counter()
    action_ok: Counter = Counter()
    action_fail: Counter = Counter()
    failure_types: Counter = Counter()
    stop_reasons: Counter = Counter()
    timeout_count = 0
    fallback_count = 0
    llm_latencies: list[float] = []
    estimated_tokens: list[int] = []
    prompt_chars: list[int] = []
    stuck_state_counts: Counter = Counter()
    context_modes: Counter = Counter()

    for t in ticks:
        raw_action = t.get("action", "unknown")
        action = raw_action if isinstance(raw_action, str) else raw_action.get("action", "unknown")
        ok = t.get("ok", False)
        action_counts[action] += 1
        if ok:
            action_ok[action] += 1
        else:
            action_fail[action] += 1

        result = t.get("result", {})
        result_data = result.get("result", {}) if isinstance(result, dict) else {}
        ft = result_data.get("failure_type") or result_data.get("verifier", {}).get("failure_type") if isinstance(result_data, dict) else None
        if ft:
            failure_types[ft] += 1
        sr = result_data.get("stop_reason") if isinstance(result_data, dict) else None
        if sr:
            stop_reasons[sr] += 1
        if ft in ("action_timeout", "timeout") or sr in ("timeout", "action_timeout"):
            timeout_count += 1

        if t.get("fallback_used"):
            fallback_count += 1

        planner = t.get("planner", {})
        lat = planner.get("llm_latency_sec") or t.get("llm_latency_sec")
        if lat:
            llm_latencies.append(lat)

        diag = t.get("diagnostics", {})
        et = diag.get("estimated_input_tokens")
        if et:
            estimated_tokens.append(et)
        pc = diag.get("state_packet_char_count") or planner.get("prompt_size_chars")
        if pc:
            prompt_chars.append(pc)
        cm = diag.get("context_mode")
        if cm:
            context_modes[cm] += 1

        # stuck states from planner
        p_stuck = planner.get("stuck_state") or {}
        if isinstance(p_stuck, dict) and p_stuck.get("active"):
            stuck_state_counts[p_stuck.get("kind", "unknown")] += 1

    # supplement with compact history if available
    if compact:
        for ev in compact:
            sk = ev.get("stuck_state_kind")
            if sk and sk not in ("none", None, ""):
                stuck_state_counts[sk] += 1

    # ── milestones ─────────────────────────────────────────────────────────
    first_milestones: dict[str, int] = {}
    last_milestones: dict[str, bool] = {}
    for i, t in enumerate(ticks):
        ms = t.get("milestones", {})
        completed = ms.get("completed", {})
        for key, val in completed.items():
            if val and key not in first_milestones:
                first_milestones[key] = i + 1
        last_milestones = completed

    newly_completed: list[str] = []
    for t in ticks:
        for m in t.get("newly_completed_milestones", []):
            if m not in newly_completed:
                newly_completed.append(m)

    # ── final inventory ────────────────────────────────────────────────────
    final_inv = _last_inventory(ticks)

    # ── LLM / token stats ─────────────────────────────────────────────────
    avg_latency = sum(llm_latencies) / len(llm_latencies) if llm_latencies else None
    avg_tokens = int(sum(estimated_tokens) / len(estimated_tokens)) if estimated_tokens else None
    total_estimated_tokens = sum(estimated_tokens)
    avg_prompt_chars = int(sum(prompt_chars) / len(prompt_chars)) if prompt_chars else None

    # ── model / config info ───────────────────────────────────────────────
    model = config.get("llm", {}).get("model") or config.get("model")
    context_mode = config.get("context_mode") or (context_modes.most_common(1)[0][0] if context_modes else None)
    mission = config.get("mission")

    return {
        "run_id": run_dir.name,
        "total_ticks": total_ticks,
        "total_batches": len(batches),
        "has_compact_history": bool(compact),
        "compact_event_count": len(compact),
        "model": model,
        "context_mode": context_mode,
        "mission": mission,
        # action stats
        "action_counts": dict(action_counts.most_common()),
        "action_ok": dict(action_ok),
        "action_fail": dict(action_fail),
        # failures
        "failure_types": dict(failure_types.most_common()),
        "stop_reasons": dict(stop_reasons.most_common()),
        "timeout_count": timeout_count,
        "fallback_count": fallback_count,
        # stuck states
        "stuck_state_counts": dict(stuck_state_counts.most_common()),
        # milestones
        "milestones_completed": [k for k, v in last_milestones.items() if v],
        "milestones_completed_count": sum(1 for v in last_milestones.values() if v),
        "milestones_total": len(last_milestones),
        "newly_completed_milestones": newly_completed,
        "first_milestone_ticks": first_milestones,
        # llm perf
        "avg_llm_latency_sec": round(avg_latency, 3) if avg_latency else None,
        "avg_estimated_input_tokens": avg_tokens,
        "total_estimated_input_tokens": total_estimated_tokens or None,
        "avg_prompt_chars": avg_prompt_chars,
        # inventory
        "final_inventory": final_inv,
    }


# ── pretty printing ───────────────────────────────────────────────────────────

def _bar(val: int, total: int, width: int = 20) -> str:
    if total == 0:
        return " " * width
    filled = int(round(val / total * width))
    return "#" * filled + "-" * (width - filled)


def _print_run(s: dict) -> None:
    w = 72
    print("=" * w)
    print(f"  Run: {s['run_id']}")
    if s.get("model"):
        print(f"  Model: {s['model']}")
    if s.get("context_mode"):
        print(f"  Context mode: {s['context_mode']}")
    if s.get("mission"):
        print(f"  Mission: {s['mission'][:80]}")
    print("=" * w)

    print(f"\n{'─'*30} OVERVIEW {'─'*31}")
    print(f"  Total ticks:    {s['total_ticks']}")
    print(f"  Batches:        {s['total_batches']}")
    print(f"  Fallbacks:      {s['fallback_count']}")
    print(f"  Timeouts:       {s['timeout_count']}")
    if s.get("has_compact_history"):
        print(f"  Compact events: {s['compact_event_count']}")

    print(f"\n{'─'*30} ACTIONS {'─'*32}")
    ac = s["action_counts"]
    ok_map = s["action_ok"]
    fail_map = s["action_fail"]
    total = s["total_ticks"]
    if ac:
        header = f"  {'Action':<35}  {'Count':>5}  {'OK':>5}  {'Fail':>5}  Ratio"
        print(header)
        for action, count in sorted(ac.items(), key=lambda x: -x[1]):
            ok_n = ok_map.get(action, 0)
            fail_n = fail_map.get(action, 0)
            ratio = f"{ok_n/count*100:.0f}%" if count else "  -"
            print(f"  {action:<35}  {count:>5}  {ok_n:>5}  {fail_n:>5}  {ratio}")
    else:
        print("  (no data)")

    print(f"\n{'─'*30} FAILURES {'─'*31}")
    ft = s["failure_types"]
    if ft:
        for k, v in sorted(ft.items(), key=lambda x: -x[1]):
            print(f"  {k:<45} {v:>4}")
    else:
        print("  (none)")

    print(f"\n{'─'*28} STOP REASONS {'─'*29}")
    sr = s["stop_reasons"]
    if sr:
        for k, v in sorted(sr.items(), key=lambda x: -x[1]):
            print(f"  {k:<45} {v:>4}")
    else:
        print("  (none)")

    print(f"\n{'─'*29} STUCK STATES {'─'*29}")
    sk = s["stuck_state_counts"]
    if sk:
        for k, v in sorted(sk.items(), key=lambda x: -x[1]):
            print(f"  {k:<45} {v:>4}")
    else:
        print("  (none)")

    print(f"\n{'─'*30} MILESTONES {'─'*30}")
    print(f"  Completed: {s['milestones_completed_count']} / {s['milestones_total']}")
    completed = s["milestones_completed"]
    if completed:
        print(f"  Items: {', '.join(completed)}")
    if s["newly_completed_milestones"]:
        print(f"  Newly completed this run: {', '.join(s['newly_completed_milestones'])}")

    first_ticks = s.get("first_milestone_ticks", {})
    if first_ticks:
        print("  First achieved at tick:")
        for milestone, tick in sorted(first_ticks.items(), key=lambda x: x[1]):
            print(f"    tick {tick:>4}  {milestone}")

    print(f"\n{'─'*28} FINAL INVENTORY {'─'*26}")
    inv = s.get("final_inventory", {})
    if inv:
        for item, count in sorted(inv.items(), key=lambda x: -x[1])[:30]:
            print(f"  {item:<40} {count:>5}")
    else:
        print("  (no inventory data)")

    print(f"\n{'─'*29} LLM PERFORMANCE {'─'*25}")
    if s.get("avg_llm_latency_sec") is not None:
        print(f"  Avg latency:          {s['avg_llm_latency_sec']:.3f}s")
    if s.get("avg_estimated_input_tokens"):
        print(f"  Avg input tokens:     {s['avg_estimated_input_tokens']:,}")
    if s.get("total_estimated_input_tokens"):
        print(f"  Total input tokens:   {s['total_estimated_input_tokens']:,}")
    if s.get("avg_prompt_chars"):
        print(f"  Avg prompt chars:     {s['avg_prompt_chars']:,}")

    # rough cost estimate (gpt-4o-mini pricing as fallback, ~$0.15/1M input tokens)
    total_tok = s.get("total_estimated_input_tokens")
    if total_tok:
        cost_est = total_tok / 1_000_000 * 0.15
        print(f"  Estimated cost (est): ${cost_est:.4f}  (at $0.15/1M input tokens)")

    print()


def _print_comparison(summaries: list[dict]) -> None:
    if len(summaries) < 2:
        return
    print("\n" + "=" * 72)
    print("  COMPARISON")
    print("=" * 72)

    runs = [s["run_id"] for s in summaries]
    col_w = max(len(r) for r in runs) + 2

    def row(label: str, vals: list) -> None:
        formatted = [str(v) if v is not None else "-" for v in vals]
        print(f"  {label:<35}" + "".join(f"{v:>{col_w}}" for v in formatted))

    print(f"  {'':35}" + "".join(f"{r:>{col_w}}" for r in runs))
    print(f"  {'─'*35}" + "─" * (col_w * len(runs)))
    row("Total ticks", [s["total_ticks"] for s in summaries])
    row("Fallback count", [s["fallback_count"] for s in summaries])
    row("Timeout count", [s["timeout_count"] for s in summaries])
    row("Milestones completed", [f"{s['milestones_completed_count']}/{s['milestones_total']}" for s in summaries])
    row("Avg LLM latency (s)", [s.get("avg_llm_latency_sec") for s in summaries])
    row("Avg input tokens", [s.get("avg_estimated_input_tokens") for s in summaries])
    row("Context mode", [s.get("context_mode") or "-" for s in summaries])
    row("Model", [s.get("model") or "-" for s in summaries])

    # top action per run
    for i, s in enumerate(summaries):
        ac = s["action_counts"]
        top = sorted(ac.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{a}({c})" for a, c in top)
        print(f"  Top actions [{s['run_id']}]: {top_str}")

    # top failure per run
    for i, s in enumerate(summaries):
        ft = s["failure_types"]
        top = sorted(ft.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{k}({v})" for k, v in top) if top else "none"
        print(f"  Top failures [{s['run_id']}]: {top_str}")

    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    run_dirs = [Path(a) for a in args]
    for rd in run_dirs:
        if not rd.is_dir():
            print(f"error: not a directory: {rd}", file=sys.stderr)
            sys.exit(1)

    summaries = []
    for rd in run_dirs:
        s = summarize_run(rd)
        _print_run(s)
        summaries.append(s)

    if len(summaries) >= 2:
        _print_comparison(summaries)


if __name__ == "__main__":
    main()
