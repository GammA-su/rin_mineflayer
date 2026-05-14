from pathlib import Path
import json
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.memory import get_recent_events, init_db, log_event
from vtuber_ai.schemas import ActionRequest, ActionResult


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "nested" / "memory.sqlite")
        init_db(db_path)

        action = ActionRequest(
            action="say",
            args={"message": "hello"},
            speech="hello",
            reason="manual test",
        )
        result = ActionResult(
            ok=True,
            action="say",
            result={"spoken": "hello"},
        )

        log_event("rin", "say hello", action, result, db_path=db_path)
        rows = get_recent_events(db_path=db_path)

        assert len(rows) == 1
        row = rows[0]
        assert row["user"] == "rin"
        assert row["message"] == "say hello"
        assert row["action"] == "say"
        assert json.loads(row["args_json"]) == {"message": "hello"}
        assert row["speech"] == "hello"
        assert row["reason"] == "manual test"
        assert row["ok"] == 1
        assert json.loads(row["result_json"]) == {"spoken": "hello"}
        assert row["error"] is None

    print("manual memory tests passed")


if __name__ == "__main__":
    main()
