from datetime import UTC, datetime
from pathlib import Path


def emit_speech_text(text: str, out_path: str = "data/latest_speech.txt") -> None:
    path = Path(out_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(text, encoding="utf-8")

    log_path = path.parent / "speech_log.txt"
    timestamp = datetime.now(UTC).isoformat()
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp}\t{text}\n")
