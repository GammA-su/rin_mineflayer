from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vtuber_ai.llm import FALLBACK_SPEECH, plan_action


def main() -> None:
    os.environ["VTUBER_LLM_PROVIDER"] = "fake"

    say = plan_action("say hello there", "rin")
    assert say.action == "say"
    assert say.args == {"message": "hello there"}
    assert say.speech == "hello there"
    assert say.reason

    assert plan_action("status please").action == "status"
    assert plan_action("follow me", "rin").args == {"username": "rin"}
    assert plan_action("come here", "rin").action == "come_here"
    assert plan_action("stop now").action == "stop"
    assert plan_action("jump").action == "jump"
    assert plan_action("be happy").args == {"mood": "happy"}
    assert plan_action("collect wood").action == "collect_wood"
    assert plan_action("craft planks").action == "craft_planks"
    assert plan_action("make sticks").action == "craft_sticks"
    assert plan_action("craft crafting table").action == "craft_crafting_table"
    assert plan_action("place crafting table").action == "place_crafting_table"
    assert plan_action("craft wooden pickaxe").action == "craft_wooden_pickaxe"
    assert plan_action("mine stone").action == "mine_stone"
    assert plan_action("craft stone pickaxe").action == "craft_stone_pickaxe"

    fallback = plan_action("what do you think?")
    assert fallback.action == "say"
    assert fallback.args == {"message": FALLBACK_SPEECH}
    assert fallback.speech == FALLBACK_SPEECH
    assert fallback.reason

    print("manual llm tests passed")


if __name__ == "__main__":
    main()
