from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.action_catalog import (  # noqa: E402
    action_catalog_summary,
    action_metadata_rows,
    actions_by_status,
    get_llm_exposed_specs,
    validate_action_catalog,
)


def main() -> None:
    validation = validate_action_catalog()
    assert validation["ok"], validation["errors"]
    assert validation["duplicates"] == [], validation["duplicates"]

    rows = action_metadata_rows()
    names = [row["name"] for row in rows]
    assert len(names) == len(set(names)), "catalog contains duplicate action names"

    summary = action_catalog_summary()
    assert summary["total"] == len(rows)
    assert summary["implemented"] == len(actions_by_status("implemented"))
    assert summary["planned"] == len(actions_by_status("planned"))

    for row in rows:
        assert row["status"], f"{row['name']} missing status"
        assert isinstance(row["args_schema"], dict), f"{row['name']} missing args_schema"
        assert row["retry_policy"], f"{row['name']} missing retry_policy"
        assert row["verifier_signature"], f"{row['name']} missing verifier_signature"
        if row["status"] in {"planned", "stub"}:
            assert not row["exposes_to_llm"], f"{row['name']} must not expose planned/stub action"

    for name, spec in get_llm_exposed_specs().items():
        assert spec.status in {"implemented", "partial"}, f"{name} exposes invalid status {spec.status}"

    from vtuber_ai.action_catalog import CATALOG
    unstuck = CATALOG.get("unstuck_escape")
    assert unstuck is not None, "unstuck_escape missing from catalog"
    assert unstuck.status == "implemented", f"unstuck_escape status={unstuck.status}"
    assert unstuck.moves_bot, "unstuck_escape must have moves_bot=True"
    assert unstuck.can_dig, "unstuck_escape must have can_dig=True"
    assert "radius" in (unstuck.args_schema or {}), "unstuck_escape missing radius arg"
    assert "mode" in (unstuck.args_schema or {}), "unstuck_escape missing mode arg"

    print(
        "manual_action_catalog_tests passed:",
        f"total={summary['total']}",
        f"implemented={summary['implemented']}",
        f"partial={summary['partial']}",
        f"planned={summary['planned']}",
    )


if __name__ == "__main__":
    main()
