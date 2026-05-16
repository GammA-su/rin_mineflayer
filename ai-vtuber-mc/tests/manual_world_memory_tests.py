import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.world_memory import (
    init_world_memory,
    list_known_places,
    nearest_known_place,
    nearest_workspace,
    remember_place,
    remember_workspace,
    update_workspace_station,
    get_relevant_known_places,
    _compact_workspace,
)


def main() -> None:
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db = f.name

    try:
        init_world_memory(db)

        # --- remember_workspace ---
        ws = remember_workspace(
            {"x": 10.0, "y": 64.0, "z": 20.0},
            "overworld",
            has_crafting_table=True,
            notes="test workspace",
            db_path=db,
        )
        assert ws["kind"] == "workspace", f"kind={ws['kind']}"
        assert ws["metadata"]["has_crafting_table"] is True
        assert ws["metadata"]["has_furnace"] is False
        assert ws["metadata"]["has_chest"] is False
        assert ws["metadata"]["safe"] is True

        # --- list_known_places no filter ---
        places = list_known_places(db_path=db)
        assert len(places) >= 1, "expected at least one place"

        # --- list_known_places kind filter ---
        workspaces = list_known_places(kind="workspace", db_path=db)
        assert len(workspaces) >= 1
        assert all(p["kind"] == "workspace" for p in workspaces)

        # --- list_known_places dimension filter ---
        ow = list_known_places(dimension="overworld", db_path=db)
        assert len(ow) >= 1
        nether = list_known_places(dimension="nether", db_path=db)
        assert len(nether) == 0, f"expected 0 nether places, got {len(nether)}"

        # --- list_known_places combined filter ---
        ow_ws = list_known_places(kind="workspace", dimension="overworld", db_path=db)
        assert len(ow_ws) >= 1

        # --- nearest_workspace ---
        near = nearest_workspace({"x": 12.0, "y": 64.0, "z": 22.0}, "overworld", db_path=db)
        assert near is not None
        assert near["metadata"]["has_crafting_table"] is True
        dist = near.get("distance")
        assert dist is not None and dist < 20, f"expected distance < 20, got {dist}"

        # nearest_workspace in wrong dimension returns None
        nether_ws = nearest_workspace({"x": 12.0, "y": 64.0, "z": 22.0}, "nether", db_path=db)
        assert nether_ws is None

        # --- _compact_workspace has exists=True ---
        compact = _compact_workspace(near)
        assert compact["exists"] is True
        assert "has_crafting_table" in compact
        assert "position" in compact

        # --- remember_place ---
        lava = remember_place(
            name="test_lava_pool",
            kind="lava_pool",
            dimension="overworld",
            position={"x": 50.0, "y": 30.0, "z": 50.0},
            confidence=0.9,
            notes="lava for portal",
            db_path=db,
        )
        assert lava["name"] == "test_lava_pool"
        assert lava["kind"] == "lava_pool"
        assert lava["metadata"] == {}

        # remember_place with metadata
        portal = remember_place(
            name="test_portal",
            kind="nether_portal_overworld",
            dimension="overworld",
            position={"x": 100.0, "y": 64.0, "z": 100.0},
            metadata={"lit": True},
            db_path=db,
        )
        assert portal["metadata"]["lit"] is True

        # --- nearest_known_place ---
        nearest = nearest_known_place(
            "workspace",
            {"x": 12.0, "y": 64.0, "z": 22.0},
            "overworld",
            db_path=db,
        )
        assert nearest is not None
        assert nearest["kind"] == "workspace"
        assert nearest.get("distance") is not None

        nearest_lava = nearest_known_place(
            "lava_pool",
            {"x": 52.0, "y": 30.0, "z": 52.0},
            "overworld",
            db_path=db,
        )
        assert nearest_lava is not None
        assert nearest_lava["name"] == "test_lava_pool"

        # nearest_known_place for non-existent kind
        missing = nearest_known_place("stronghold", {"x": 0, "y": 64, "z": 0}, "overworld", db_path=db)
        assert missing is None

        # --- update_workspace_station: add furnace to existing workspace ---
        updated = update_workspace_station(
            "furnace",
            position={"x": 10.0, "y": 64.0, "z": 20.0},
            dimension="overworld",
            db_path=db,
        )
        assert updated is not None
        assert updated["metadata"]["has_furnace"] is True
        assert updated["metadata"]["has_crafting_table"] is True  # preserved

        # --- update_workspace_station: add chest ---
        updated2 = update_workspace_station(
            "chest",
            position={"x": 10.0, "y": 64.0, "z": 20.0},
            dimension="overworld",
            db_path=db,
        )
        assert updated2 is not None
        assert updated2["metadata"]["has_chest"] is True
        assert updated2["metadata"]["has_furnace"] is True
        assert updated2["metadata"]["has_crafting_table"] is True

        # Verify via list_known_places
        final_ws = list_known_places(kind="workspace", db_path=db)
        meta = final_ws[0]["metadata"]
        assert meta["has_furnace"] is True
        assert meta["has_crafting_table"] is True
        assert meta["has_chest"] is True

        # --- get_relevant_known_places returns exists=True when workspace known ---
        status = {"position": {"x": 12.0, "y": 64.0, "z": 22.0}, "dimension": "overworld"}
        relevant = get_relevant_known_places(status, db_path=db)
        assert isinstance(relevant, dict)
        nw = relevant.get("nearest_workspace")
        assert isinstance(nw, dict)
        assert nw["exists"] is True
        assert nw["has_crafting_table"] is True
        assert nw["has_furnace"] is True

        # --- get_relevant_known_places returns exists=False when none known ---
        nether_status = {"position": {"x": 0, "y": 64, "z": 0}, "dimension": "nether"}
        nether_relevant = get_relevant_known_places(nether_status, db_path=db)
        nw_nether = nether_relevant.get("nearest_workspace")
        assert isinstance(nw_nether, dict)
        assert nw_nether["exists"] is False

        print("manual world memory tests passed")
    finally:
        os.unlink(db)


if __name__ == "__main__":
    main()
