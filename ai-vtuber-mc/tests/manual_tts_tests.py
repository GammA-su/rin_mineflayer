from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.tts import emit_speech_text


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "nested" / "latest_speech.txt"

        emit_speech_text("hello voice", str(out_path))
        emit_speech_text("second line", str(out_path))

        assert out_path.read_text(encoding="utf-8") == "second line"

        log_path = out_path.parent / "speech_log.txt"
        log_text = log_path.read_text(encoding="utf-8")
        assert "hello voice" in log_text
        assert "second line" in log_text

    print("manual tts tests passed")


if __name__ == "__main__":
    main()
