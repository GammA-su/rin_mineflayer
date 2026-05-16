import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vtuber_ai.schemas import ActionRequest, ActionResult

DEFAULT_DB_PATH = "data/memory.sqlite"


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    path = Path(db_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(path)) as conn:
        with conn:
            conn.execute(
                """
                create table if not exists events (
                    id integer primary key autoincrement,
                    ts text,
                    user text,
                    message text,
                    action text,
                    args_json text,
                    speech text,
                    reason text,
                    ok integer,
                    result_json text,
                    error text
                )
                """
            )
            conn.execute(
                """
                create table if not exists agent_ticks (
                    id integer primary key autoincrement,
                    ts text,
                    user text,
                    mission text,
                    objective text,
                    action text,
                    args_json text,
                    speech text,
                    reason text,
                    ok integer,
                    before_state_json text,
                    after_state_json text,
                    verifier_json text,
                    result_json text,
                    error text
                )
                """
            )
            conn.execute(
                """
                create table if not exists death_events (
                    id integer primary key autoincrement,
                    ts text not null,
                    source_ts_ms integer,
                    dimension text,
                    x real,
                    y real,
                    z real,
                    cause text,
                    inventory_json text
                )
                """
            )


def log_event(
    user: str | None,
    message: str,
    action_request: ActionRequest,
    action_result: ActionResult,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    init_db(db_path)

    ts = datetime.now(UTC).isoformat()
    args_json = json.dumps(action_request.args)
    result_json = json.dumps(action_result.result)

    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                insert into events (
                    ts,
                    user,
                    message,
                    action,
                    args_json,
                    speech,
                    reason,
                    ok,
                    result_json,
                    error
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    user,
                    message,
                    action_request.action,
                    args_json,
                    action_request.speech,
                    action_request.reason,
                    1 if action_result.ok else 0,
                    result_json,
                    action_result.error,
                ),
            )


def get_recent_events(limit: int = 20, db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    safe_limit = max(0, int(limit))

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select
                id,
                ts,
                user,
                message,
                action,
                args_json,
                speech,
                reason,
                ok,
                result_json,
                error
            from events
            order by id desc
            limit ?
            """,
            (safe_limit,),
        ).fetchall()

    return [_enrich_json_fields(dict(row), ("args_json", "result_json")) for row in rows]


def log_death_event(
    *,
    x: float,
    y: float,
    z: float,
    dimension: str,
    source_ts_ms: int | None = None,
    cause: str | None = None,
    inventory: list[dict[str, Any]] | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    init_db(db_path)
    ts = datetime.now(UTC).isoformat()
    inventory_json = json.dumps(inventory or [])

    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            if source_ts_ms is not None:
                existing = conn.execute(
                    "select id from death_events where source_ts_ms = ? limit 1",
                    (int(source_ts_ms),),
                ).fetchone()
                if existing:
                    return
            conn.execute(
                """
                insert into death_events (
                    ts, source_ts_ms, dimension, x, y, z, cause, inventory_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    source_ts_ms,
                    str(dimension or "overworld"),
                    float(x),
                    float(y),
                    float(z),
                    cause,
                    inventory_json,
                ),
            )
            conn.execute(
                """
                insert into events (
                    ts, user, message, action, args_json, speech, reason, ok, result_json, error
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    "system",
                    f"death_event dimension={dimension} x={x} y={y} z={z}",
                    "death_event",
                    "{}",
                    "",
                    "Recorded bot death state.",
                    1,
                    json.dumps(
                        {
                            "x": x,
                            "y": y,
                            "z": z,
                            "dimension": dimension,
                            "source_ts_ms": source_ts_ms,
                            "cause": cause,
                            "inventory_count": len(inventory or []),
                        }
                    ),
                    None,
                ),
            )


def log_agent_tick(
    *,
    user: str,
    mission: str,
    objective: str,
    action_request: ActionRequest,
    action_result: ActionResult,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    verifier_result: dict[str, Any],
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    init_db(db_path)

    ts = datetime.now(UTC).isoformat()

    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                insert into agent_ticks (
                    ts,
                    user,
                    mission,
                    objective,
                    action,
                    args_json,
                    speech,
                    reason,
                    ok,
                    before_state_json,
                    after_state_json,
                    verifier_json,
                    result_json,
                    error
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    user,
                    mission,
                    objective,
                    action_request.action,
                    json.dumps(action_request.args),
                    action_request.speech,
                    action_request.reason,
                    1 if action_result.ok else 0,
                    json.dumps(before_state),
                    json.dumps(after_state),
                    json.dumps(verifier_result),
                    json.dumps(action_result.result),
                    action_result.error,
                ),
            )


def get_recent_agent_ticks(limit: int = 20, db_path: str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    safe_limit = max(0, int(limit))

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select
                id,
                ts,
                user,
                mission,
                objective,
                action,
                args_json,
                speech,
                reason,
                ok,
                before_state_json,
                after_state_json,
                verifier_json,
                result_json,
                error
            from agent_ticks
            order by id desc
            limit ?
            """,
            (safe_limit,),
        ).fetchall()

    return [
        _enrich_json_fields(
            dict(row),
            ("args_json", "before_state_json", "after_state_json", "verifier_json", "result_json"),
        )
        for row in rows
    ]


def _decode_json_field(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _enrich_json_fields(row: dict[str, Any], field_names: tuple[str, ...]) -> dict[str, Any]:
    aliases = {
        "args_json": "args",
        "before_state_json": "before_state",
        "after_state_json": "after_state",
        "verifier_json": "verifier",
        "result_json": "result",
    }
    for field_name in field_names:
        decoded = _decode_json_field(row.get(field_name))
        if decoded is not None:
            row[aliases.get(field_name, field_name.removesuffix("_json"))] = decoded
    return row
