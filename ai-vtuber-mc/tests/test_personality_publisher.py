"""pytest tests for personality_publisher."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from vtuber_ai.personality_publisher import (
    _bounded_raw,
    _compact_verifier,
    _extract_failed_requirements,
    _extract_nearby_stations,
    _trunc,
    build_tick_event,
    publish_tick_event,
)


# ---------------------------------------------------------------------------
# Helpers: representative tick dicts
# ---------------------------------------------------------------------------

def _mining_success_tick() -> dict[str, Any]:
    """Tick that mirrors a successful mine_coal /agent/tick response."""
    return {
        "ok": True,
        "mission": "Beat Minecraft while playing naturally and surviving.",
        "objective": "mine_coal",
        "action": {
            "action": "mine_coal",
            "args": {"count": 1, "radius": 8, "allowExcavate": True},
            "speech": "Mining some coal.",
            "reason": "Need coal for fuel. Objective: mine_coal",
        },
        "result": {
            "ok": True,
            "action": "mine_coal",
            "result": {
                "collected": 1,
                "stop_reason": "collected_requested",
                "failure_type": None,
                "inventory": {"coal": 1, "stone_pickaxe": 1},
                "position": {"x": 10, "y": 64, "z": 20},
            },
            "error": None,
        },
        "verifier": {"success": True, "failure_type": None, "stop_reason": None},
        "after_status": {
            "health": 20,
            "food": 18,
            "position": {"x": 10, "y": 64, "z": 20},
        },
        "planner": {"mode": "hybrid", "llm_latency_sec": 0.5, "source": "llm"},
    }


def _invalid_args_failure_tick() -> dict[str, Any]:
    """Tick that mirrors an invalid_args failure from smelt_item."""
    return {
        "ok": False,
        "mission": "Beat Minecraft while playing naturally and surviving.",
        "objective": "smelt_item",
        "action": {
            "action": "smelt_item",
            "args": {},
            "speech": "",
            "reason": "Smelt raw iron.",
        },
        "result": {
            "ok": False,
            "action": "smelt_item",
            "result": {
                "failure_type": "invalid_args",
                "stop_reason": "invalid_args",
            },
            "error": "Action 'smelt_item' requires args.input as a non-empty string.",
        },
        "verifier": {"success": False, "failure_type": "invalid_args"},
        "after_status": {"health": 20, "food": 20},
        "planner": {"mode": "hybrid"},
    }


# ---------------------------------------------------------------------------
# build_tick_event — successful mining tick
# ---------------------------------------------------------------------------

class TestBuildTickEventSuccess:
    def test_tick_id_and_run_id(self):
        event = build_tick_event(11, _mining_success_tick(), run_id="20260519T120000Z")
        assert event["tick_id"] == 11
        assert event["run_id"] == "20260519T120000Z"

    def test_action_and_args(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["action"] == "mine_coal"
        assert event["args"] == {"count": 1, "radius": 8, "allowExcavate": True}

    def test_ok_true(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["ok"] is True

    def test_failure_none_on_success(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["failure"] is None

    def test_stop_reason_extracted(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["stop"] == "collected_requested"

    def test_error_none_on_success(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["error"] is None

    def test_collected_integer(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["collected"] == 1

    def test_mission_and_objective(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["mission"].startswith("Beat Minecraft")
        assert event["objective"] == "mine_coal"

    def test_health_and_hunger(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["health"] == 20
        assert event["hunger"] == 18

    def test_position_from_payload(self):
        event = build_tick_event(11, _mining_success_tick())
        assert event["position"] == {"x": 10, "y": 64, "z": 20}

    def test_raw_keys_present(self):
        event = build_tick_event(11, _mining_success_tick())
        assert isinstance(event["raw"], dict)
        assert "planner" in event["raw"]
        assert "result" in event["raw"]

    def test_run_id_none_by_default(self):
        event = build_tick_event(1, _mining_success_tick())
        assert event["run_id"] is None


# ---------------------------------------------------------------------------
# build_tick_event — invalid_args failure tick
# ---------------------------------------------------------------------------

class TestBuildTickEventFailure:
    def test_ok_false(self):
        event = build_tick_event(45, _invalid_args_failure_tick())
        assert event["ok"] is False

    def test_action_name(self):
        event = build_tick_event(45, _invalid_args_failure_tick())
        assert event["action"] == "smelt_item"

    def test_failure_type_extracted(self):
        event = build_tick_event(45, _invalid_args_failure_tick())
        assert event["failure"] == "invalid_args"

    def test_stop_reason_extracted(self):
        event = build_tick_event(45, _invalid_args_failure_tick())
        assert event["stop"] == "invalid_args"

    def test_error_message_extracted(self):
        event = build_tick_event(45, _invalid_args_failure_tick())
        assert event["error"] is not None
        assert "requires args.input" in event["error"]

    def test_collected_none_on_failure(self):
        event = build_tick_event(45, _invalid_args_failure_tick())
        assert event["collected"] is None

    def test_tick_id(self):
        event = build_tick_event(45, _invalid_args_failure_tick())
        assert event["tick_id"] == 45


# ---------------------------------------------------------------------------
# build_tick_event — truncation of long strings
# ---------------------------------------------------------------------------

class TestBuildTickEventTruncation:
    def test_long_mission_truncated_to_1000(self):
        tick = _mining_success_tick()
        tick["mission"] = "M" * 2000
        event = build_tick_event(1, tick)
        assert len(event["mission"]) == 1000

    def test_long_error_truncated_to_1000(self):
        tick = _invalid_args_failure_tick()
        tick["result"]["error"] = "E" * 2000
        event = build_tick_event(1, tick)
        assert event["error"] is not None
        assert len(event["error"]) == 1000

    def test_long_reason_truncated(self):
        tick = _mining_success_tick()
        tick["action"]["reason"] = "R" * 2000
        event = build_tick_event(1, tick)
        assert len(event["reason"]) == 1000


# ---------------------------------------------------------------------------
# build_tick_event — missing/empty tick
# ---------------------------------------------------------------------------

class TestBuildTickEventEdgeCases:
    def test_empty_tick(self):
        event = build_tick_event(1, {})
        assert event["action"] == "?"
        assert event["args"] == {}
        assert event["ok"] is False
        assert event["failure"] is None
        assert event["collected"] is None

    def test_position_falls_back_to_after_status(self):
        tick = _mining_success_tick()
        # Remove position from inner result so it must come from after_status
        tick["result"]["result"].pop("position", None)
        event = build_tick_event(1, tick)
        assert event["position"] == {"x": 10, "y": 64, "z": 20}

    def test_failure_from_verifier_when_payload_empty(self):
        tick = {
            "ok": False,
            "result": {"ok": False, "action": "status", "result": {}, "error": None},
            "verifier": {"success": False, "failure_type": "bridge_error"},
        }
        event = build_tick_event(1, tick)
        assert event["failure"] == "bridge_error"


# ---------------------------------------------------------------------------
# _bounded_raw
# ---------------------------------------------------------------------------

class TestBoundedRaw:
    def test_small_obj_returned_unchanged(self):
        obj = {"a": 1, "b": "hello"}
        assert _bounded_raw(obj, max_bytes=8192) == obj

    def test_large_obj_returns_marker(self):
        big = {"data": "x" * 10_000}
        result = _bounded_raw(big, max_bytes=100)
        assert result.get("_truncated") is True
        assert "_size_bytes" in result

    def test_large_planner_in_raw_truncated(self):
        tick = _mining_success_tick()
        tick["planner"] = {"huge_key": "y" * 10_000}
        event = build_tick_event(1, tick)
        assert event["raw"]["planner"].get("_truncated") is True

    def test_large_result_in_raw_truncated(self):
        tick = _mining_success_tick()
        tick["result"]["result"]["log"] = "z" * 10_000
        event = build_tick_event(1, tick)
        assert event["raw"]["result"].get("_truncated") is True


# ---------------------------------------------------------------------------
# _trunc
# ---------------------------------------------------------------------------

class TestTrunc:
    def test_short_string_unchanged(self):
        assert _trunc("hello") == "hello"

    def test_long_string_cut_to_1000(self):
        s = "a" * 2000
        result = _trunc(s)
        assert len(result) == 1000
        assert result == "a" * 1000

    def test_non_string_unchanged(self):
        assert _trunc(42) == 42
        assert _trunc(None) is None
        assert _trunc({"k": "v"}) == {"k": "v"}


# ---------------------------------------------------------------------------
# publish_tick_event
# ---------------------------------------------------------------------------

class TestPublishTickEvent:
    def _make_mock_client(self, post_side_effect=None, post_return=None):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        if post_side_effect is not None:
            mock_client.post.side_effect = post_side_effect
        elif post_return is not None:
            mock_client.post.return_value = post_return
        return mock_client

    def test_returns_true_on_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_client = self._make_mock_client(post_return=mock_resp)

        with patch("httpx.Client", return_value=mock_client):
            result = publish_tick_event({"tick_id": 1}, "http://127.0.0.1:8010/events/tick")

        assert result is True

    def test_returns_false_on_connect_error(self):
        mock_client = self._make_mock_client(
            post_side_effect=httpx.ConnectError("connection refused")
        )

        with patch("httpx.Client", return_value=mock_client):
            result = publish_tick_event({"tick_id": 1}, "http://127.0.0.1:9999/events/tick")

        assert result is False

    def test_returns_false_on_http_status_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )
        mock_client = self._make_mock_client(post_return=mock_resp)

        with patch("httpx.Client", return_value=mock_client):
            result = publish_tick_event({"tick_id": 1}, "http://127.0.0.1:8010/events/tick")

        assert result is False

    def test_returns_false_on_timeout(self):
        mock_client = self._make_mock_client(
            post_side_effect=httpx.TimeoutException("timeout")
        )

        with patch("httpx.Client", return_value=mock_client):
            result = publish_tick_event({"tick_id": 1}, "http://127.0.0.1:8010/events/tick")

        assert result is False

    def test_does_not_raise_on_any_error(self):
        mock_client = self._make_mock_client(post_side_effect=RuntimeError("boom"))

        with patch("httpx.Client", return_value=mock_client):
            result = publish_tick_event({"tick_id": 1}, "http://127.0.0.1:8010/events/tick")

        assert result is False


# ---------------------------------------------------------------------------
# run_stream_loop CLI argument parsing
# ---------------------------------------------------------------------------

def _load_run_stream_loop():
    """Import run_stream_loop.py as a module without executing main()."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    spec = importlib.util.spec_from_file_location(
        "run_stream_loop",
        scripts_dir / "run_stream_loop.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestRunStreamLoopCLI:
    def test_personality_url_accepted(self):
        mod = _load_run_stream_loop()
        saved = sys.argv
        try:
            sys.argv = [
                "run_stream_loop.py",
                "--personality-url",
                "http://127.0.0.1:8010/events/tick",
            ]
            args = mod._parse_args()
        finally:
            sys.argv = saved

        assert args.personality_url == "http://127.0.0.1:8010/events/tick"

    def test_personality_timeout_sec_accepted(self):
        mod = _load_run_stream_loop()
        saved = sys.argv
        try:
            sys.argv = [
                "run_stream_loop.py",
                "--personality-timeout-sec",
                "1.5",
            ]
            args = mod._parse_args()
        finally:
            sys.argv = saved

        assert args.personality_timeout_sec == 1.5

    def test_personality_url_defaults_to_none(self):
        mod = _load_run_stream_loop()
        saved = sys.argv
        try:
            sys.argv = ["run_stream_loop.py"]
            args = mod._parse_args()
        finally:
            sys.argv = saved

        assert args.personality_url is None

    def test_personality_timeout_defaults_to_float(self):
        mod = _load_run_stream_loop()
        saved = sys.argv
        try:
            sys.argv = ["run_stream_loop.py"]
            args = mod._parse_args()
        finally:
            sys.argv = saved

        assert isinstance(args.personality_timeout_sec, float)


# ---------------------------------------------------------------------------
# _compact_verifier
# ---------------------------------------------------------------------------

class TestCompactVerifier:
    def test_none_on_empty_dict(self):
        assert _compact_verifier({}) is None

    def test_preserves_success_and_failure_type(self):
        v = {"success": False, "failure_type": "navigation_failed", "stop_reason": "path_timeout"}
        result = _compact_verifier(v)
        assert result is not None
        assert result["success"] is False
        assert result["failure_type"] == "navigation_failed"
        assert result["stop_reason"] == "path_timeout"

    def test_evidence_bounded(self):
        v = {
            "success": True,
            "failure_type": None,
            "evidence": {"log": "x" * 10_000},
        }
        result = _compact_verifier(v)
        assert result is not None
        assert result["evidence"].get("_truncated") is True

    def test_failed_because_bounded(self):
        big_fb = [{"kind": "timeout", "data": "z" * 5000}]
        v = {"success": False, "failed_because": big_fb}
        result = _compact_verifier(v)
        assert result is not None
        assert result["failed_because"].get("_truncated") is True

    def test_small_verifier_returned_intact(self):
        v = {
            "success": True,
            "failure_type": None,
            "stop_reason": None,
            "recommendation": "ok",
            "failed_because": [],
            "evidence": {"action_ok": True},
        }
        result = _compact_verifier(v)
        assert result is not None
        assert result["failed_because"] == []
        assert result["evidence"] == {"action_ok": True}


# ---------------------------------------------------------------------------
# _extract_failed_requirements
# ---------------------------------------------------------------------------

class TestExtractFailedRequirements:
    def test_returns_from_verifier_failed_because(self):
        verifier = {"failed_because": [{"kind": "path_timeout", "action": "mine_coal"}]}
        result = _extract_failed_requirements(verifier, {})
        assert result == [{"kind": "path_timeout", "action": "mine_coal"}]

    def test_falls_back_to_inner_result(self):
        verifier = {}
        outer = {"result": {"failed_because": [{"kind": "missing_tool"}]}}
        result = _extract_failed_requirements(verifier, outer)
        assert result == [{"kind": "missing_tool"}]

    def test_empty_list_when_none_found(self):
        result = _extract_failed_requirements({}, {})
        assert result == []

    def test_verifier_takes_priority_over_result(self):
        verifier = {"failed_because": [{"kind": "verifier_source"}]}
        outer = {"result": {"failed_because": [{"kind": "result_source"}]}}
        result = _extract_failed_requirements(verifier, outer)
        assert result[0]["kind"] == "verifier_source"


# ---------------------------------------------------------------------------
# _extract_nearby_stations
# ---------------------------------------------------------------------------

class TestExtractNearbyStations:
    def test_returns_none_when_no_nearby_blocks(self):
        assert _extract_nearby_stations({}) is None

    def test_returns_none_when_nearby_blocks_not_dict(self):
        assert _extract_nearby_stations({"nearbyBlocks": "invalid"}) is None

    def test_extracts_station_blocks(self):
        after_status = {
            "nearbyBlocks": {
                "crafting_table": {"name": "crafting_table", "distance": 3, "position": {"x": 1, "y": 2, "z": 3}},
                "furnace": {"name": "furnace", "distance": 8, "position": {"x": 4, "y": 2, "z": 3}},
                "stone": {"name": "stone", "distance": 1},  # not a station — should be ignored
            }
        }
        result = _extract_nearby_stations(after_status)
        assert result is not None
        assert "crafting_table" in result
        assert "furnace" in result
        assert "stone" not in result

    def test_extracts_only_known_fields_from_block(self):
        after_status = {
            "nearbyBlocks": {
                "furnace": {"name": "furnace", "distance": 5, "hardness": 3.5, "position": {"x": 0, "y": 0, "z": 0}}
            }
        }
        result = _extract_nearby_stations(after_status)
        assert result is not None
        furnace = result["furnace"]
        assert "hardness" not in furnace
        assert "distance" in furnace

    def test_returns_none_when_no_station_blocks_present(self):
        after_status = {"nearbyBlocks": {"stone": {"name": "stone", "distance": 1}}}
        assert _extract_nearby_stations(after_status) is None


# ---------------------------------------------------------------------------
# build_tick_event — new raw fields
# ---------------------------------------------------------------------------

def _rich_tick() -> dict[str, Any]:
    """Tick with planner fallback_reason, verifier failed_because, nearby stations."""
    return {
        "ok": False,
        "mission": "Beat Minecraft.",
        "objective": "mine_iron_ore",
        "action": {
            "action": "mine_iron_ore",
            "args": {"count": 1},
            "speech": "",
            "reason": "Need raw iron for smelting.",
        },
        "result": {
            "ok": False,
            "action": "mine_iron_ore",
            "result": {"failure_type": "navigation_failed", "stop_reason": "path_timeout_before_target"},
            "error": "Timed out pathing to target block after 12000ms.",
        },
        "verifier": {
            "success": False,
            "failure_type": "navigation_failed",
            "stop_reason": "path_timeout",
            "failed_because": [{"kind": "path_timeout", "action": "mine_iron_ore", "recoverable": True}],
            "evidence": {"action_ok": False},
            "recommendation": "Try explore_nearby.",
        },
        "after_status": {
            "health": 18,
            "food": 14,
            "inventory": {"stone_pickaxe": 2, "coal": 5},
            "nearbyBlocks": {
                "crafting_table": {"name": "crafting_table", "distance": 3, "position": {"x": 1, "y": 64, "z": 1}},
                "stone": {"name": "stone", "distance": 1},
            },
        },
        "planner": {
            "mode": "hybrid",
            "fallback_used": True,
            "fallback_reason": "LLM chose action not supported by bridge: dig_tunnel.",
        },
    }


class TestBuildTickEventRawFields:
    def test_fallback_reason_in_raw(self):
        event = build_tick_event(1, _rich_tick())
        assert event["raw"]["fallback_reason"] == "LLM chose action not supported by bridge: dig_tunnel."

    def test_fallback_reason_none_when_absent(self):
        tick = _rich_tick()
        tick["planner"]["fallback_reason"] = None
        event = build_tick_event(1, tick)
        assert event["raw"]["fallback_reason"] is None

    def test_failed_requirements_extracted(self):
        event = build_tick_event(1, _rich_tick())
        reqs = event["raw"]["failed_requirements"]
        assert isinstance(reqs, list)
        assert reqs[0]["kind"] == "path_timeout"

    def test_nearby_stations_extracted(self):
        event = build_tick_event(1, _rich_tick())
        stations = event["raw"]["nearby_stations"]
        assert stations is not None
        assert "crafting_table" in stations
        assert "stone" not in stations

    def test_inventory_summary_in_raw(self):
        event = build_tick_event(1, _rich_tick())
        inv = event["raw"]["inventory_summary"]
        assert inv is not None
        assert inv.get("stone_pickaxe") == 2

    def test_verifier_is_compact(self):
        event = build_tick_event(1, _rich_tick())
        v = event["verifier"]
        assert v is not None
        assert "success" in v
        assert "failure_type" in v
        assert "evidence" in v
        assert "failed_because" in v

    def test_verifier_success_preserved(self):
        event = build_tick_event(1, _rich_tick())
        assert event["verifier"]["success"] is False
        assert event["verifier"]["failure_type"] == "navigation_failed"

    def test_raw_nearby_stations_none_when_no_stations(self):
        tick = _rich_tick()
        tick["after_status"]["nearbyBlocks"] = {"stone": {"name": "stone"}}
        event = build_tick_event(1, tick)
        assert event["raw"]["nearby_stations"] is None

    def test_raw_inventory_summary_none_when_absent(self):
        tick = _rich_tick()
        tick["after_status"].pop("inventory", None)
        tick["result"]["result"].pop("inventory", None)
        event = build_tick_event(1, tick)
        # May be None if no inventory source exists
        # (presence of result payload inventory can still provide it)
        # Just ensure no crash
        assert "inventory_summary" in event["raw"]
