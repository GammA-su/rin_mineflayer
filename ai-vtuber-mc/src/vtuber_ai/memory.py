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

    return [dict(row) for row in rows]


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

    return [dict(row) for row in rows]
