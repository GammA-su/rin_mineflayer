from typing import Any

from vtuber_ai.schemas import ActionRequest

ALLOWED_ACTIONS = frozenset(
    {
        "status",
        "say",
        "look_around",
        "explore_nearby",
        "look_at_player",
        "follow_player",
        "stop",
        "come_here",
        "jump",
        "set_vtuber_mood",
        "acquire_blocks",
        "navigate_to_block_type",
        "collect_wood",
        "craft_planks",
        "craft_sticks",
        "craft_crafting_table",
        "place_crafting_table",
        "craft_wooden_pickaxe",
        "mine_stone",
        "craft_stone_pickaxe",
        "flee",
        "eat_food",
    }
)

ALLOWED_MOODS = frozenset(
    {
        "neutral",
        "happy",
        "surprised",
        "scared",
        "focused",
        "confused",
    }
)

ALLOWED_ACQUIRE_TARGETS = frozenset(
    {
        "oak_log",
        "birch_log",
        "spruce_log",
        "jungle_log",
        "acacia_log",
        "dark_oak_log",
        "mangrove_log",
        "cherry_log",
        "crimson_stem",
        "warped_stem",
        "stone",
        "cobblestone",
        "deepslate",
        "coal_ore",
        "deepslate_coal_ore",
        "iron_ore",
        "deepslate_iron_ore",
        "copper_ore",
        "deepslate_copper_ore",
        "dirt",
        "grass_block",
        "sand",
        "gravel",
    }
)

ALLOWED_ACQUIRE_ACCESS_MODES = frozenset({"surface_first", "safe_staircase"})

_ACTION_ARGS = {
    "status": frozenset(),
    "say": frozenset({"message"}),
    "look_around": frozenset({"radius"}),
    "explore_nearby": frozenset({"radius"}),
    "look_at_player": frozenset({"username"}),
    "follow_player": frozenset({"username"}),
    "stop": frozenset(),
    "come_here": frozenset({"username"}),
    "jump": frozenset(),
    "set_vtuber_mood": frozenset({"mood"}),
    "acquire_blocks": frozenset({"targets", "count", "radius", "allowExcavate", "accessMode"}),
    "navigate_to_block_type": frozenset({"targets", "radius"}),
    "collect_wood": frozenset({"count"}),
    "craft_planks": frozenset({"count"}),
    "craft_sticks": frozenset({"count"}),
    "craft_crafting_table": frozenset({"count"}),
    "place_crafting_table": frozenset(),
    "craft_wooden_pickaxe": frozenset(),
    "mine_stone": frozenset({"count"}),
    "craft_stone_pickaxe": frozenset(),
    "flee": frozenset(),
    "eat_food": frozenset(),
}


class PolicyError(ValueError):
    """Raised when an action is outside the safe Minecraft action policy."""


def validate_action(action_request: ActionRequest) -> ActionRequest:
    request = ActionRequest.model_validate(action_request)

    if request.action not in ALLOWED_ACTIONS:
        allowed = ", ".join(sorted(ALLOWED_ACTIONS))
        raise PolicyError(f"Action '{request.action}' is not allowed. Allowed actions: {allowed}.")

    _reject_unknown_args(request.action, request.args)

    if request.action == "say":
        _validate_say(request.args)
    elif request.action in {"look_at_player", "follow_player", "come_here"}:
        _validate_optional_username(request.action, request.args)
    elif request.action == "set_vtuber_mood":
        _validate_mood(request.args)
    elif request.action == "acquire_blocks":
        _validate_acquire_blocks(request.args)
    elif request.action == "navigate_to_block_type":
        _validate_navigate_to_block_type(request.args)
    elif request.action == "collect_wood":
        _validate_optional_count(request.action, request.args, max_count=16)
    elif request.action in {"craft_planks", "craft_sticks", "craft_crafting_table"}:
        _validate_optional_count(request.action, request.args, max_count=64)
    elif request.action == "mine_stone":
        _validate_optional_count(request.action, request.args, max_count=16)
    elif request.action == "explore_nearby":
        _validate_optional_int_range(request.action, request.args, "radius", min_value=8, max_value=64)
    elif request.action == "look_around":
        _validate_optional_int_range(request.action, request.args, "radius", min_value=8, max_value=32)

    return request


def _reject_unknown_args(action: str, args: dict[str, Any]) -> None:
    allowed_args = _ACTION_ARGS[action]
    unknown_args = sorted(set(args) - allowed_args)

    if not unknown_args:
        return

    unknown = ", ".join(unknown_args)
    if not allowed_args:
        raise PolicyError(f"Action '{action}' does not accept args: {unknown}.")

    allowed = ", ".join(sorted(allowed_args))
    raise PolicyError(f"Action '{action}' received unknown args: {unknown}. Allowed args: {allowed}.")


def _validate_say(args: dict[str, Any]) -> None:
    message = args.get("message")

    if not isinstance(message, str) or not message.strip():
        raise PolicyError("Action 'say' requires args.message as a non-empty string.")

    if len(message) > 240:
        raise PolicyError("Action 'say' args.message must be at most 240 characters.")

    if message.lstrip().startswith("/"):
        raise PolicyError("Action 'say' cannot send slash commands.")


def _validate_optional_username(action: str, args: dict[str, Any]) -> None:
    if "username" not in args:
        return

    username = args["username"]
    if not isinstance(username, str) or not username.strip():
        raise PolicyError(f"Action '{action}' args.username must be a non-empty string when provided.")

    if len(username) > 32:
        raise PolicyError(f"Action '{action}' args.username must be at most 32 characters.")


def _validate_mood(args: dict[str, Any]) -> None:
    mood = args.get("mood")

    if not isinstance(mood, str) or mood not in ALLOWED_MOODS:
        allowed = ", ".join(sorted(ALLOWED_MOODS))
        raise PolicyError(f"Action 'set_vtuber_mood' requires args.mood to be one of: {allowed}.")


def _validate_optional_count(action: str, args: dict[str, Any], max_count: int) -> None:
    if "count" not in args:
        return

    count = args["count"]
    if not isinstance(count, int) or isinstance(count, bool):
        raise PolicyError(f"Action '{action}' args.count must be an integer when provided.")

    if count < 1 or count > max_count:
        raise PolicyError(f"Action '{action}' args.count must be between 1 and {max_count}.")


def _validate_acquire_blocks(args: dict[str, Any]) -> None:
    _validate_acquire_targets("acquire_blocks", args)
    _validate_optional_count("acquire_blocks", args, max_count=32)
    _validate_optional_int_range("acquire_blocks", args, "radius", min_value=8, max_value=96)

    if "allowExcavate" in args and not isinstance(args["allowExcavate"], bool):
        raise PolicyError("Action 'acquire_blocks' args.allowExcavate must be a boolean when provided.")

    access_mode = args.get("accessMode")
    if access_mode is not None and access_mode not in ALLOWED_ACQUIRE_ACCESS_MODES:
        allowed = ", ".join(sorted(ALLOWED_ACQUIRE_ACCESS_MODES))
        raise PolicyError(f"Action 'acquire_blocks' args.accessMode must be one of: {allowed}.")


def _validate_navigate_to_block_type(args: dict[str, Any]) -> None:
    _validate_acquire_targets("navigate_to_block_type", args)
    _validate_optional_int_range("navigate_to_block_type", args, "radius", min_value=8, max_value=96)


def _validate_acquire_targets(action: str, args: dict[str, Any]) -> None:
    targets = args.get("targets")
    if not isinstance(targets, list) or len(targets) == 0:
        raise PolicyError(f"Action '{action}' requires args.targets as a non-empty list.")

    for target in targets:
        if not isinstance(target, str) or target not in ALLOWED_ACQUIRE_TARGETS:
            allowed = ", ".join(sorted(ALLOWED_ACQUIRE_TARGETS))
            raise PolicyError(f"Action '{action}' target is not allowed: {target}. Allowed targets: {allowed}.")


def _validate_optional_int_range(
    action: str,
    args: dict[str, Any],
    arg_name: str,
    min_value: int,
    max_value: int,
) -> None:
    if arg_name not in args:
        return

    value = args[arg_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise PolicyError(f"Action '{action}' args.{arg_name} must be an integer when provided.")

    if value < min_value or value > max_value:
        raise PolicyError(f"Action '{action}' args.{arg_name} must be between {min_value} and {max_value}.")
