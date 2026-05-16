"""
Persistent world memory: waypoints and death log.

Stored in the same SQLite file as the main memory so backup/copy is one file.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "data/memory.sqlite"

VALID_WAYPOINT_KINDS = frozenset(
    {
        "home",
        "workspace",
        "surface",
        "crafting_area",
        "furnace_area",
        "furnace",
        "mine_entrance",
        "last_surface",
        "nether_portal_overworld",
        "nether_portal_nether",
        "fortress",
        "blaze_spawner",
        "stronghold",
        "end_portal_room",
        "death_location",
        "lava_pool",
        "general",
    }
)


def init_world_memory(db_path: str = DEFAULT_DB_PATH) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(path)) as conn:
        with conn:
            conn.execute(
                """
                create table if not exists waypoints (
                    id        integer primary key autoincrement,
                    label     text    unique not null,
                    kind      text    not null default 'general',
                    x         real    not null,
                    y         real    not null,
                    z         real    not null,
                    dimension text    not null default 'overworld',
                    ts        text    not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists known_places (
                    id            integer primary key autoincrement,
                    name          text    unique not null,
                    kind          text    not null default 'general',
                    dimension     text    not null default 'overworld',
                    x             real    not null,
                    y             real    not null,
                    z             real    not null,
                    confidence    real    not null default 0.5,
                    last_seen_ts  text    not null,
                    notes         text,
                    metadata_json text
                )
                """
            )
            conn.execute(
                """
                create table if not exists death_log (
                    id        integer primary key autoincrement,
                    ts        text    not null,
                    dimension text    not null default 'overworld',
                    x         real    not null,
                    y         real    not null,
                    z         real    not null,
                    cause     text,
                    inventory_json text,
                    source_ts_ms integer,
                    recovery_failures integer not null default 0,
                    abandoned integer not null default 0
                )
                """
            )
            _ensure_column(conn, "death_log", "cause", "text")
            _ensure_column(conn, "death_log", "inventory_json", "text")
            _ensure_column(conn, "death_log", "source_ts_ms", "integer")
            _ensure_column(conn, "death_log", "recovery_failures", "integer not null default 0")
            _ensure_column(conn, "death_log", "abandoned", "integer not null default 0")
            _ensure_column(conn, "known_places", "metadata_json", "text")
            _ensure_column(conn, "known_places", "confidence", "real not null default 0.5")
            _ensure_column(conn, "known_places", "notes", "text")


def upsert_waypoint(
    label: str,
    kind: str,
    x: float,
    y: float,
    z: float,
    dimension: str,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    _ensure_str(label, "label")
    init_world_memory(db_path)
    safe_kind = kind if kind in VALID_WAYPOINT_KINDS else "general"
    ts = datetime.now(UTC).isoformat()

    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                insert into waypoints (label, kind, x, y, z, dimension, ts)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(label) do update set
                    kind      = excluded.kind,
                    x         = excluded.x,
                    y         = excluded.y,
                    z         = excluded.z,
                    dimension = excluded.dimension,
                    ts        = excluded.ts
                """,
                (label.strip(), safe_kind, float(x), float(y), float(z), str(dimension or "overworld"), ts),
            )


def get_waypoint(label: str, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    init_world_memory(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "select * from waypoints where label = ?", (label,)
        ).fetchone()
    return dict(row) if row else None


def list_waypoints(db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_world_memory(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "select label, kind, x, y, z, dimension, ts from waypoints order by ts desc"
        ).fetchall()
    return [dict(row) for row in rows]


def remember_known_place(
    *,
    name: str,
    kind: str,
    position: dict[str, Any],
    dimension: str,
    confidence: float = 0.7,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    _ensure_str(name, "name")
    init_world_memory(db_path)
    safe_kind = kind if kind in VALID_WAYPOINT_KINDS else "general"
    ts = datetime.now(UTC).isoformat()
    x, y, z = _position_xyz(position)
    metadata_json = json.dumps(metadata or {})
    safe_confidence = max(0.0, min(1.0, float(confidence)))

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute(
                """
                insert into known_places (
                    name, kind, dimension, x, y, z, confidence, last_seen_ts, notes, metadata_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(name) do update set
                    kind=excluded.kind,
                    dimension=excluded.dimension,
                    x=excluded.x,
                    y=excluded.y,
                    z=excluded.z,
                    confidence=max(known_places.confidence, excluded.confidence),
                    last_seen_ts=excluded.last_seen_ts,
                    notes=coalesce(excluded.notes, known_places.notes),
                    metadata_json=excluded.metadata_json
                """,
                (
                    name.strip(),
                    safe_kind,
                    str(dimension or "overworld"),
                    x,
                    y,
                    z,
                    safe_confidence,
                    ts,
                    notes,
                    metadata_json,
                ),
            )
            row = conn.execute("select * from known_places where name = ?", (name.strip(),)).fetchone()
    return _decode_known_place(dict(row)) if row else {}


def remember_place(
    *,
    name: str,
    kind: str,
    dimension: str,
    position: dict[str, Any],
    confidence: float = 0.7,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    return remember_known_place(
        name=name,
        kind=kind,
        position=position,
        dimension=dimension,
        confidence=confidence,
        notes=notes,
        metadata=metadata,
        db_path=db_path,
    )


def remember_workspace(
    position: dict[str, Any],
    dimension: str,
    has_crafting_table: bool = False,
    has_furnace: bool = False,
    has_chest: bool = False,
    safe: bool = True,
    notes: str | None = None,
    *,
    open_space_score: float | None = None,
    name: str | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    x, y, z = _position_xyz(position)
    label = name or f"workspace:{dimension}:{round(x)}:{round(y)}:{round(z)}"
    metadata = {
        "has_crafting_table": bool(has_crafting_table),
        "has_furnace": bool(has_furnace),
        "has_chest": bool(has_chest),
        "safe": bool(safe),
        "open_space_score": float(open_space_score if open_space_score is not None else (1.0 if safe else 0.0)),
        "last_verified": datetime.now(UTC).isoformat(),
    }
    place = remember_known_place(
        name=label,
        kind="workspace",
        position={"x": x, "y": y, "z": z},
        dimension=dimension,
        confidence=0.85 if safe else 0.55,
        notes=notes,
        metadata=metadata,
        db_path=db_path,
    )
    upsert_waypoint("workspace", "workspace", x, y, z, dimension, db_path=db_path)
    if has_crafting_table:
        upsert_waypoint("crafting_area", "crafting_area", x, y, z, dimension, db_path=db_path)
    if has_furnace:
        upsert_waypoint("furnace_area", "furnace_area", x, y, z, dimension, db_path=db_path)
    return place


def nearest_workspace(
    current_position: dict[str, Any] | None,
    dimension: str,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    init_world_memory(db_path)
    current = _position_tuple(current_position)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select * from known_places
            where kind in ('workspace', 'crafting_area', 'furnace_area', 'home')
              and dimension = ?
            order by confidence desc, last_seen_ts desc
            """,
            (str(dimension or "overworld"),),
        ).fetchall()
    places = [_decode_known_place(dict(row)) for row in rows]
    if not places:
        return None
    if current is None:
        return places[0]
    for place in places:
        place["distance"] = _distance(current, (place["x"], place["y"], place["z"]))
    return sorted(places, key=lambda item: (item.get("distance", 999999.0), -float(item.get("confidence", 0))))[0]


def nearest_known_place(
    kind: str,
    current_position: dict[str, Any] | None,
    dimension: str,
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    init_world_memory(db_path)
    current = _position_tuple(current_position)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select * from known_places
            where kind = ?
              and dimension = ?
            order by confidence desc, last_seen_ts desc
            """,
            (str(kind or "general"), str(dimension or "overworld")),
        ).fetchall()
    places = [_decode_known_place(dict(row)) for row in rows]
    if not places:
        return None
    if current is None:
        return places[0]
    for place in places:
        place["distance"] = _distance(current, (place["x"], place["y"], place["z"]))
    return sorted(places, key=lambda item: (item.get("distance", 999999.0), -float(item.get("confidence", 0))))[0]


def update_workspace_station(
    kind: str,
    *,
    position: dict[str, Any] | None = None,
    dimension: str = "overworld",
    db_path: str = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    station = _station_metadata_key(kind)
    if not station:
        return None
    workspace = nearest_workspace(position, dimension, db_path=db_path)
    if workspace is None:
        if position is None:
            return None
        kwargs = {"has_crafting_table": False, "has_furnace": False, "has_chest": False}
        kwargs[station] = True
        return remember_workspace(position, dimension, safe=True, notes=f"station placed: {kind}", db_path=db_path, **kwargs)

    metadata = workspace.get("metadata") if isinstance(workspace.get("metadata"), dict) else {}
    metadata[station] = True
    metadata.setdefault("safe", True)
    metadata["last_verified"] = datetime.now(UTC).isoformat()
    return remember_known_place(
        name=workspace["name"],
        kind=workspace.get("kind") or "workspace",
        position={"x": workspace["x"], "y": workspace["y"], "z": workspace["z"]},
        dimension=workspace.get("dimension") or dimension,
        confidence=max(0.8, float(workspace.get("confidence") or 0.0)),
        notes=workspace.get("notes") or f"station placed: {kind}",
        metadata=metadata,
        db_path=db_path,
    )


def get_relevant_known_places(status: dict[str, Any] | None, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    status = status if isinstance(status, dict) else {}
    position = status.get("position") if isinstance(status.get("position"), dict) else None
    dimension = str(status.get("dimension") or "overworld")
    workspace = nearest_workspace(position, dimension, db_path=db_path)
    return {
        "nearest_workspace": _compact_workspace(workspace) if workspace else {"exists": False},
    }


def list_known_places(
    kind: str | None = None,
    dimension: str | None = None,
    db_path: str = DEFAULT_DB_PATH,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_world_memory(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if kind is not None:
        clauses.append("kind = ?")
        params.append(str(kind))
    if dimension is not None:
        clauses.append("dimension = ?")
        params.append(str(dimension))
    where = ("where " + " and ".join(clauses)) if clauses else ""
    params.append(max(0, int(limit)))
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"select * from known_places {where} order by last_seen_ts desc limit ?",
            params,
        ).fetchall()
    return [_decode_known_place(dict(row)) for row in rows]


def record_death(
    x: float,
    y: float,
    z: float,
    dimension: str,
    *,
    ts_ms: int | None = None,
    cause: str | None = None,
    inventory: list[dict[str, Any]] | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    init_world_memory(db_path)
    ts = (
        datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()
        if isinstance(ts_ms, int) and ts_ms > 0
        else datetime.now(UTC).isoformat()
    )
    safe_dim = str(dimension or "overworld")
    inventory_json = json.dumps(inventory or [])

    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                insert into death_log (ts, dimension, x, y, z, cause, inventory_json, source_ts_ms)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, safe_dim, float(x), float(y), float(z), cause, inventory_json, ts_ms),
            )
            conn.execute(
                """
                insert into waypoints (label, kind, x, y, z, dimension, ts)
                values ('death_location', 'death_location', ?, ?, ?, ?, ?)
                on conflict(label) do update set
                    kind='death_location', x=excluded.x, y=excluded.y, z=excluded.z,
                    dimension=excluded.dimension, ts=excluded.ts
                """,
                (float(x), float(y), float(z), safe_dim, ts),
            )
            conn.execute(
                """
                insert into known_places (
                    name, kind, dimension, x, y, z, confidence, last_seen_ts, notes, metadata_json
                )
                values ('death_location', 'death_location', ?, ?, ?, ?, 1.0, ?, ?, ?)
                on conflict(name) do update set
                    kind='death_location',
                    dimension=excluded.dimension,
                    x=excluded.x,
                    y=excluded.y,
                    z=excluded.z,
                    confidence=excluded.confidence,
                    last_seen_ts=excluded.last_seen_ts,
                    notes=excluded.notes,
                    metadata_json=excluded.metadata_json
                """,
                (
                    safe_dim,
                    float(x),
                    float(y),
                    float(z),
                    ts,
                    cause,
                    json.dumps({"source_ts_ms": ts_ms, "inventory_count": len(inventory or [])}),
                ),
            )


def record_death_if_new(
    x: float,
    y: float,
    z: float,
    dimension: str,
    ts_ms: int,
    cause: str | None = None,
    inventory: list[dict[str, Any]] | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Record death only when ts_ms is newer than the most recent death. Returns True if recorded."""
    last = get_last_death(db_path)
    if last:
        last_source_ts = last.get("source_ts_ms")
        if isinstance(last_source_ts, int) and ts_ms <= last_source_ts:
            return False
        try:
            last_dt = datetime.fromisoformat(last["ts"])
            candidate_dt = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            if candidate_dt <= last_dt:
                return False
        except (ValueError, KeyError, TypeError):
            pass
    record_death(x, y, z, dimension, ts_ms=ts_ms, cause=cause, inventory=inventory, db_path=db_path)
    return True


def get_last_death(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    init_world_memory(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "select * from death_log order by id desc limit 1"
        ).fetchone()
    if not row:
        return None
    death = dict(row)
    death["inventory"] = _decode_json_list(death.get("inventory_json"))
    return death


def update_death_recovery_state(
    *,
    failures: int | None = None,
    abandoned: bool | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    init_world_memory(db_path)
    last = get_last_death(db_path)
    if not last:
        return
    assignments: list[str] = []
    values: list[Any] = []
    if failures is not None:
        assignments.append("recovery_failures = ?")
        values.append(max(0, int(failures)))
    if abandoned is not None:
        assignments.append("abandoned = ?")
        values.append(1 if abandoned else 0)
    if not assignments:
        return
    values.append(last["id"])
    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            conn.execute(f"update death_log set {', '.join(assignments)} where id = ?", values)


def get_death_state(db_path: str = DEFAULT_DB_PATH, recent_seconds: int = 300) -> dict[str, Any]:
    death = get_last_death(db_path)
    if not death:
        return {"known": False, "last_death": None, "recent": False}

    age_seconds: int | None = None
    recent = False
    try:
        death_dt = datetime.fromisoformat(str(death["ts"]))
        age_seconds = max(0, int((datetime.now(UTC) - death_dt).total_seconds()))
        recent = age_seconds <= recent_seconds
    except (ValueError, TypeError, KeyError):
        pass

    return {
        "known": True,
        "last_death": death,
        "recent": recent,
        "age_seconds": age_seconds,
        "despawn_warning": age_seconds is not None and age_seconds >= 240,
        "time_remaining_s": max(0, 300 - age_seconds) if age_seconds is not None else None,
        "recovery_failures": death.get("recovery_failures", 0),
        "abandoned": bool(death.get("abandoned")),
        "suggested_next_action": (
            "abandon_death_recovery"
            if death.get("recovery_failures", 0) >= 2 or death.get("abandoned")
            else "recover_death_items"
        ),
    }


def _ensure_str(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"world_memory: {field} must be a non-empty string")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"alter table {table} add column {column} {definition}")


def _position_xyz(position: dict[str, Any]) -> tuple[float, float, float]:
    if not isinstance(position, dict):
        raise ValueError("world_memory: position must be a dict with x, y, z")
    return float(position["x"]), float(position["y"]), float(position["z"])


def _position_tuple(position: dict[str, Any] | None) -> tuple[float, float, float] | None:
    if not isinstance(position, dict):
        return None
    try:
        return _position_xyz(position)
    except (KeyError, TypeError, ValueError):
        return None


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _decode_known_place(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {}
    raw = row.get("metadata_json")
    if isinstance(raw, str) and raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                metadata = decoded
        except json.JSONDecodeError:
            metadata = {}
    row["metadata"] = metadata
    return row


def _station_metadata_key(kind: str) -> str | None:
    normalized = str(kind or "").strip().lower()
    mapping = {
        "crafting_table": "has_crafting_table",
        "place_crafting_table": "has_crafting_table",
        "crafting_area": "has_crafting_table",
        "furnace": "has_furnace",
        "place_furnace": "has_furnace",
        "furnace_area": "has_furnace",
        "chest": "has_chest",
        "place_chest": "has_chest",
        "storage": "has_chest",
    }
    return mapping.get(normalized)


def _compact_workspace(workspace: dict[str, Any]) -> dict[str, Any]:
    metadata = workspace.get("metadata") if isinstance(workspace.get("metadata"), dict) else {}
    return {
        "exists": True,
        "name": workspace.get("name"),
        "kind": workspace.get("kind"),
        "distance": round(float(workspace.get("distance", 0.0)), 1) if workspace.get("distance") is not None else None,
        "dimension": workspace.get("dimension"),
        "position": {"x": workspace.get("x"), "y": workspace.get("y"), "z": workspace.get("z")},
        "has_crafting_table": bool(metadata.get("has_crafting_table")),
        "has_furnace": bool(metadata.get("has_furnace")),
        "has_chest": bool(metadata.get("has_chest")),
        "safe": bool(metadata.get("safe")),
        "open_space_score": metadata.get("open_space_score"),
        "last_verified": metadata.get("last_verified"),
    }


def _decode_json_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, str) or not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
