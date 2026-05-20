# ai-vtuber-mc

Beginner-friendly runbook for running a local Minecraft AI VTuber prototype.

## 1. What This Project Is

`ai-vtuber-mc` is a small Minecraft AI VTuber control stack.

It lets a Python service receive chat-like goals, plan a safe action, validate that action, and send it to a Mineflayer bot running in Minecraft Java Edition.

This project is intentionally conservative:

- no arbitrary JavaScript execution
- no raw code from the LLM
- no combat
- no broad destructive Minecraft actions
- `collect_wood` can break only whitelisted log/stem blocks near the bot
- `place_crafting_table` places at most one crafting table on a safe adjacent block

Use a private local Minecraft server first.

Do not run this bot on public servers unless the server rules explicitly allow bots.

## 2. Architecture

There are two running services:

```text
curl / viewer / future chat input
        |
        v
Python FastAPI orchestrator
http://localhost:8000
        |
        | validates safe ActionRequest
        v
Node.js Mineflayer bridge
http://localhost:3001
        |
        v
Local Minecraft Java server
localhost:25565
```

Python:

- receives `POST /chat_goal`
- plans an action with `vtuber_ai.llm`
- validates the action with `vtuber_ai.policy`
- logs memory to SQLite at `data/memory.sqlite`
- writes speech text to `data/latest_speech.txt`
- forwards safe actions to Mineflayer

Node.js:

- connects to Minecraft using Mineflayer
- exposes `GET /status`
- exposes `POST /action`
- executes only whitelisted actions

## 3. Requirements

Windows 11 PowerShell:

- Minecraft Java Edition
- Java 21 or a Java version supported by your chosen Minecraft server jar
- Python 3.11+
- `uv`
- Node.js 20+
- npm
- a local Minecraft server jar, usually from the official Minecraft server download page

Check versions:

```powershell
java -version
python --version
uv --version
node --version
npm --version
```

Arch Linux:

```bash
sudo pacman -Syu jre-openjdk python nodejs npm
```

Install `uv` on Windows PowerShell if needed:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install `uv` on Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 4. Create A Local Minecraft Java Server

Make a separate folder for the server. Do not put the server jar inside this repo.

Windows PowerShell:

```powershell
mkdir C:\minecraft-local
cd C:\minecraft-local
```

Download the Minecraft Java server jar from the official Minecraft website and place it in this folder as:

```text
C:\minecraft-local\server.jar
```

Start it once so it creates the config files:

```powershell
java -Xmx2G -Xms1G -jar server.jar nogui
```

It will stop and ask you to accept the EULA. Read `eula.txt`, then if you accept:

```powershell
(Get-Content .\eula.txt) -replace 'eula=false', 'eula=true' | Set-Content .\eula.txt
```

Linux/Arch:

```bash
mkdir -p ~/minecraft-local
cd ~/minecraft-local
java -Xmx2G -Xms1G -jar server.jar nogui
sed -i 's/eula=false/eula=true/' eula.txt
```

## 5. Configure server.properties For Local Bot Testing

Open `server.properties` in a text editor.

Windows PowerShell:

```powershell
notepad .\server.properties
```

Recommended first local test settings:

```properties
online-mode=false
white-list=false
difficulty=peaceful
allow-flight=true
enable-command-block=false
spawn-protection=0
server-port=25565
```

Important notes:

- `online-mode=false` is only for private local offline testing.
- Do not use `online-mode=false` on a public server.
- `white-list=false` is convenient for the first local test.
- `difficulty=peaceful` avoids mobs while you test movement and chat.
- `allow-flight=true` is optional, but it can help avoid false kicks with bots.
- `enable-command-block=false` keeps command blocks disabled.
- `spawn-protection=0` makes local test worlds less confusing.

After editing, save the file.

## 6. Start Minecraft Server

In one PowerShell window:

```powershell
cd C:\minecraft-local
java -Xmx2G -Xms1G -jar server.jar nogui
```

Leave this window running.

Then open Minecraft Java Edition and connect to:

```text
localhost:25565
```

Linux/Arch:

```bash
cd ~/minecraft-local
java -Xmx2G -Xms1G -jar server.jar nogui
```

## 7. Start Mineflayer Bot Bridge

Open a second PowerShell window.

From this repo:

```powershell
cd C:\Projecyt\rin_mineflayer\ai-vtuber-mc\bot
Copy-Item .env.example .env
npm install
node mineflayer_bot.js
```

Default bot environment:

```env
MC_HOST=localhost
MC_PORT=25565
MC_USERNAME=AI_VTuber
MC_VERSION=
BRIDGE_PORT=3001
```

If `MC_VERSION` is empty, Mineflayer auto-detects the Minecraft version.

Expected logs:

```text
Mineflayer bridge listening on port 3001
Mineflayer logged in as AI_VTuber
Mineflayer bot spawned
```

The bot should also say:

```text
AI VTuber online!
```

Linux/Arch:

```bash
cd /path/to/ai-vtuber-mc/bot
cp .env.example .env
npm install
node mineflayer_bot.js
```

## 8. Start Python Orchestrator

Open a third PowerShell window.

From this repo:

```powershell
cd C:\Projecyt\rin_mineflayer\ai-vtuber-mc
uv sync
uv run uvicorn vtuber_ai.main:app --reload --port 8000
```

Leave this window running.

Linux/Arch:

```bash
cd /path/to/ai-vtuber-mc
uv sync
uv run uvicorn vtuber_ai.main:app --reload --port 8000
```

The Python service is now available at:

```text
http://localhost:8000
```

The Mineflayer bridge is available at:

```text
http://localhost:3001
```

## 9. Test Commands With curl

Use `curl.exe` in PowerShell. PowerShell aliases `curl` to another command on some systems, so `curl.exe` is clearer.

Root check:

```powershell
curl.exe http://localhost:8000/
```

Status through Python:

```powershell
curl.exe http://localhost:8000/status
```

Status direct to Mineflayer bridge:

```powershell
curl.exe http://localhost:3001/status
```

Say:

```powershell
curl.exe -X POST http://localhost:8000/chat_goal `
  -H "Content-Type: application/json" `
  -d "{\"user\":\"local_user\",\"message\":\"say hello stream\"}"
```

Follow me:

```powershell
curl.exe -X POST http://localhost:8000/chat_goal `
  -H "Content-Type: application/json" `
  -d "{\"user\":\"YourMinecraftName\",\"message\":\"follow me\"}"
```

Stop:

```powershell
curl.exe -X POST http://localhost:8000/chat_goal `
  -H "Content-Type: application/json" `
  -d "{\"user\":\"YourMinecraftName\",\"message\":\"stop\"}"
```

Jump:

```powershell
curl.exe -X POST http://localhost:8000/chat_goal `
  -H "Content-Type: application/json" `
  -d "{\"user\":\"YourMinecraftName\",\"message\":\"jump\"}"
```

Collect wood:

```powershell
curl.exe -X POST http://localhost:8000/chat_goal `
  -H "Content-Type: application/json" `
  -d "{\"user\":\"YourMinecraftName\",\"message\":\"collect wood\"}"
```

Direct bridge test with `Invoke-RestMethod` and an explicit count:

```powershell
$body = @{
  action = "collect_wood"
  args = @{
    count = 4
  }
  speech = ""
  reason = "manual local collect_wood test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

`collect_wood` searches within radius `32`, accepts `count` from `1` to `16`, and only targets whitelisted log/stem block names.

Craft planks from collected logs or stems:

```powershell
$body = @{
  action = "craft_planks"
  args = @{
    count = 4
  }
  speech = ""
  reason = "manual local craft_planks test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Craft sticks from planks:

```powershell
$body = @{
  action = "craft_sticks"
  args = @{
    count = 1
  }
  speech = ""
  reason = "manual local craft_sticks test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Craft a crafting table from planks:

```powershell
$body = @{
  action = "craft_crafting_table"
  args = @{
    count = 1
  }
  speech = ""
  reason = "manual local craft_crafting_table test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Place one crafting table near the bot:

```powershell
$body = @{
  action = "place_crafting_table"
  args = @{}
  speech = ""
  reason = "manual local place_crafting_table test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Craft a wooden pickaxe at a nearby crafting table:

```powershell
$body = @{
  action = "craft_wooden_pickaxe"
  args = @{}
  speech = ""
  reason = "manual local craft_wooden_pickaxe test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Mine nearby exposed stone with a wooden pickaxe or better:

```powershell
$body = @{
  action = "mine_stone"
  args = @{
    count = 3
  }
  speech = ""
  reason = "manual local mine_stone test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Craft a stone pickaxe at a nearby crafting table:

```powershell
$body = @{
  action = "craft_stone_pickaxe"
  args = @{}
  speech = ""
  reason = "manual local craft_stone_pickaxe test"
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:3001/action" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

If Python reports that a Mineflayer action timed out while the bot is still chopping, increase the Python bridge action timeout and restart the Python orchestrator:

```powershell
$env:MINEFLAYER_ACTION_TIMEOUT_SECONDS = "300"
uv run uvicorn vtuber_ai.main:app --reload --port 8000
```

Read recent memory:

```powershell
curl.exe "http://localhost:8000/memory/recent?limit=10"
```

Read latest speech:

```powershell
curl.exe http://localhost:8000/speech/latest
```

Recommended agent objective:

```powershell
curl.exe http://localhost:8000/agent/objective
```

Inspect the current autonomous gameplay state:

```powershell
curl.exe http://localhost:8000/agent/state
```

Run one autonomous observe-plan-act-verify step:

```powershell
curl.exe -X POST http://localhost:8000/agent/run_once `
  -H "Content-Type: application/json" `
  -d "{\"mission\":\"survive and progress toward beating Minecraft\",\"user\":\"agent\"}"
```

Run a short autonomous loop:

```powershell
curl.exe -X POST http://localhost:8000/agent/run_loop `
  -H "Content-Type: application/json" `
  -d "{\"mission\":\"survive and progress toward beating Minecraft\",\"max_steps\":3,\"user\":\"agent\",\"allow_autonomy\":true}"
```

`/agent/run_loop` rejects requests unless `allow_autonomy=true`. `max_steps` must be between `1` and `20`.

Run one gameplay brain tick with the hybrid planner:

```powershell
$body = @{
  mission = "Beat Minecraft while playing naturally and surviving."
  user = "AI_VTuber"
  planner = "hybrid"
  allow_autonomy = $true
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:8000/agent/tick" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Run 10 gameplay brain ticks:

```powershell
$body = @{
  mission = "Beat Minecraft while playing naturally and surviving."
  user = "AI_VTuber"
  planner = "hybrid"
  max_ticks = 10
  tick_delay_sec = 1.0
  allow_autonomy = $true
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Uri "http://localhost:8000/agent/live" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Use the LLM planner for autonomous agent steps:

```powershell
$env:VTUBER_LLM_BASE_URL = "http://localhost:1234/v1"
$env:VTUBER_LLM_API_KEY = "dummy"
$env:VTUBER_LLM_MODEL = "local-model"
$env:VTUBER_LLM_MAX_TOKENS = "96"
$env:VTUBER_LLM_TIMEOUT_SEC = "120"
uv run uvicorn vtuber_ai.main:app --reload --port 8000
```

Then set the request body `planner` to `llm` or `hybrid`. `hybrid` uses only emergency survival reflexes first, then the LLM. If the LLM is unavailable or unusable, the fallback is the neutral `status` action, not a hardcoded Minecraft progression plan. `/agent/tick` returns `llm_latency_sec`, `prompt_size_chars`, `llm_state_packet_preview`, `available_actions_count`, and arg-sanitization diagnostics so you can see what the planner received.

The older curriculum endpoints can still use the environment planner mode:

```powershell
$env:VTUBER_AGENT_PLANNER = "curriculum"
uv run uvicorn vtuber_ai.main:app --reload --port 8000
```

Linux/Arch curl example:

```bash
curl -X POST http://localhost:8000/chat_goal \
  -H "Content-Type: application/json" \
  -d '{"user":"YourMinecraftName","message":"follow me"}'
```

## 10. Troubleshooting

Python cannot import dependencies:

```powershell
uv sync
```

Then restart:

```powershell
uv run uvicorn vtuber_ai.main:app --reload --port 8000
```

Mineflayer cannot connect:

- confirm the Minecraft server is running
- confirm `server-port=25565`
- confirm `MC_HOST=localhost`
- confirm `MC_PORT=25565`
- check that Windows Firewall is not blocking local Java or Node connections

Bot is kicked with flying or movement errors:

- set `allow-flight=true` in `server.properties`
- restart the Minecraft server

Bot joins but actions fail with player not found:

- join the Minecraft server with your own player first
- use your exact Minecraft username in the `user` field
- stay near the bot for `follow_player`, `come_here`, and `look_at_player`

PowerShell JSON quoting is failing:

- use `curl.exe`, not `curl`
- keep the backtick continuation character at the end of each continued line
- use escaped double quotes inside the JSON: `\"`

Port already in use:

- Python uses port `8000`
- Node bridge uses port `3001`
- Minecraft uses port `25565`

Check Windows processes:

```powershell
netstat -ano | findstr ":8000"
netstat -ano | findstr ":3001"
netstat -ano | findstr ":25565"
```

Manual checks:

```powershell
uv run python tests/manual_policy_tests.py
uv run python tests/manual_llm_tests.py
uv run python tests/manual_llm_provider_tests.py
uv run python tests/manual_memory_tests.py
uv run python tests/manual_tts_tests.py
uv run python tests/manual_agent_tests.py
uv run python tests/manual_game_brain_tests.py
uv run python tests/manual_action_catalog_tests.py
powershell -ExecutionPolicy Bypass -File tests/manual_node_arg_normalizer_tests.ps1
```

Node syntax check:

```powershell
node --check bot/mineflayer_bot.js
```

Action not supported by bridge:

If a tick result shows `error: "Unsupported action: <name>"`, the Node bridge does not implement that action yet. Steps to fix:

1. Check what the bridge currently supports:
   ```powershell
   curl.exe http://localhost:3001/actions
   ```
2. Implement the missing action in `bot/mineflayer_bot.js` and add its name to the `ACTIONS` set.
3. Restart the Node bridge.

Python automatically fetches `GET /actions` at each tick and only asks the LLM to choose from actions the bridge actually supports. If the bridge endpoint is unreachable, Python falls back to its own action list.

## 11. Safety Model

The LLM or fake planner does not directly control Minecraft.

The flow is:

```text
message -> planner -> ActionRequest -> policy.validate_action -> Mineflayer bridge whitelist -> Minecraft
```

Safety rules:

- Python validates every action before sending it to Mineflayer.
- Mineflayer validates every action again before executing it.
- Minecraft strategy for `/agent/tick` and `/agent/live` is LLM-driven from compact game state, inventory, nearby observations, available action schemas, and previous action feedback.
- Deterministic Python code enforces safety, sanitizes action args, handles emergency survival reflexes, executes whitelisted skills, verifies results, and logs feedback.
- Python does not encode a full Minecraft prerequisite tree for autonomous gameplay.
- Unknown actions are rejected.
- Unknown args are rejected.
- Chat messages beginning with `/` are rejected.
- No raw JavaScript is accepted.
- No `eval` is used.
- No combat is implemented.
- Destructive resource actions are limited to whitelisted intent names.
- `collect_wood` is implemented with a radius limit, count limit, max attempts, timeout protection, and a strict log/stem block whitelist.
- `craft_planks`, `craft_sticks`, and `craft_crafting_table` are implemented through Mineflayer recipes.
- `place_crafting_table` places one crafting table only, does not dig for placement, and refuses unsafe liquid placement.
- `craft_wooden_pickaxe` requires a nearby crafting table plus enough planks and sticks.
- `mine_stone` requires a wooden pickaxe or better, refuses low health, mines only literal `stone`, and uses radius, attempt, and timeout limits.
- `craft_stone_pickaxe` requires a nearby crafting table plus enough cobblestone and sticks.
- `look_around`, `explore_nearby`, `flee`, and `eat_food` are high-level whitelisted skills, not raw keyboard or code control.
- `/status` includes health, food, position, dimension, time, inventory, nearby players, nearby entities, nearby block counts, and liquid/on-ground flags for planning.

Autonomous gameplay tick flow:

```text
observe -> think -> validate -> act -> verify -> remember -> speak
```

`POST /agent/run_once` executes exactly one planned action. `POST /agent/run_loop` requires `allow_autonomy=true`, runs at most `max_steps`, and stops early when the verifier sees completion or repeated failure.

`POST /agent/tick` executes at most one gameplay-brain action and requires `allow_autonomy=true`. `POST /agent/live` runs up to `max_ticks` sequentially, requires `allow_autonomy=true`, and stops early on repeated failures, bridge errors, or dangerous low-health states without recovery.

Gameplay brain planner modes:

```powershell
$body = @{
  mission = "Beat Minecraft while playing naturally and surviving."
  user = "AI_VTuber"
  planner = "hybrid"
  allow_autonomy = $true
} | ConvertTo-Json -Depth 4
```

`hybrid` is the default for the gameplay brain. It uses deterministic emergency reflexes only for immediate survival, then asks an OpenAI-compatible LLM to choose a short-term objective and one high-level skill. If the LLM is unavailable or returns invalid JSON, it falls back to the neutral `status` action. `llm` skips emergency reflexes and asks the model directly. `fallback` uses only the neutral fallback.

```powershell
$env:VTUBER_LLM_BASE_URL = "http://localhost:1234/v1"
$env:VTUBER_LLM_API_KEY = "dummy"
$env:VTUBER_LLM_MODEL = "local-model"
$env:VTUBER_LLM_MAX_TOKENS = "96"
$env:VTUBER_LLM_TIMEOUT_SEC = "120"
uv run uvicorn vtuber_ai.main:app --reload --port 8000
```

The gameplay brain sends a compact state packet only: mission, health, food, dimension, time/day flag, position, inventory counts, top 20 nearby block counts, special nearby blocks such as `crafting_table`, top 10 nearby entities, last 3 memory events, previous action result, and available action schemas. It does not send full status snapshots, full before/after verifier objects, long memory logs, or verbose schemas.

The LLM is expected to reason from that packet. For example, if a previous action failed because materials were missing, the next tick should choose an action that obtains or prepares the missing materials. The safety layer still decides whether the chosen action and args are allowed before Mineflayer sees them.

Older curriculum agent planner modes:

```powershell
$env:VTUBER_AGENT_PLANNER = "curriculum"
```

`curriculum` is the default for `/agent/run_once` and `/agent/run_loop`. `llm` sends the mission, current curriculum objective, bot status, inventory summary, recent memory, allowed actions, and last failure to an OpenAI-compatible model. If the LLM returns invalid JSON or a policy-rejected action, the agent falls back to the curriculum action.

Chat goal planner providers:

```powershell
$env:VTUBER_LLM_PROVIDER = "fake"
```

OpenAI-compatible provider example:

```powershell
$env:VTUBER_LLM_PROVIDER = "openai_compatible"
$env:VTUBER_LLM_BASE_URL = "http://localhost:1234/v1"
$env:VTUBER_LLM_API_KEY = ""
$env:VTUBER_LLM_MODEL = "local-model"
$env:VTUBER_LLM_MAX_TOKENS = "96"
$env:VTUBER_LLM_TIMEOUT_SEC = "120"
```

Even with an LLM provider, model output is treated as untrusted. Agent LLM actions still pass through `policy.validate_action` and the Mineflayer bridge whitelist. For the gameplay brain, invalid actions become structured failure feedback for the next tick instead of a hardcoded strategic override.

Provider-neutral TTS hook:

- Python writes latest speech to `data/latest_speech.txt`
- Python appends all speech to `data/speech_log.txt`
- OBS, VTube Studio, Piper, ElevenLabs, Azure, or a local voice model can watch this file
- this project does not require a paid TTS provider

## 12. Action Capability Map v2

The LLM only sees **implemented** or **partial** actions that the Node bridge supports and that have `exposes_to_llm=True` in `src/vtuber_ai/action_catalog.py`.

**Planned** actions are roadmap only. They appear in `action_catalog.py` and `GET /actions_metadata` but are never sent to the LLM and are rejected by `policy.validate_action`.

To promote a planned action to implemented:
1. Implement it in `bot/mineflayer_bot.js` and add its name to the `ACTIONS` set.
2. Set `status="implemented"` in `action_catalog.py`.
3. Add its name to `ALLOWED_ACTIONS` in `policy.py`.
4. Add it to `AUTONOMOUS_ALLOWED_ACTIONS` in `game_brain.py` if it should be brain-accessible.
5. Restart both services.

PowerShell diagnostics:

```powershell
# Python catalog validation and status counts
Invoke-RestMethod "http://localhost:8000/actions/summary" | ConvertTo-Json -Depth 8

# All planned Python catalog actions
(Invoke-RestMethod "http://localhost:8000/actions/planned").actions |
  Select-Object name,category,status,exposes_to_llm

# Implemented Python catalog actions exposed to the LLM
(Invoke-RestMethod "http://localhost:8000/actions/implemented").actions |
  Where-Object { $_.exposes_to_llm } |
  Select-Object name,category,status

# Node bridge metadata duplicates removed during merge
(Invoke-RestMethod "http://localhost:3001/actions_metadata").duplicates_removed |
  Format-Table -AutoSize

# Node bridge executable actions only
(Invoke-RestMethod "http://localhost:3001/actions").actions

# Manual Tier 2 iron-age body skill smoke
powershell -ExecutionPolicy Bypass -File scripts/smoke_tier2_iron.ps1
```

### Core / Control

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| status | implemented | low | Return current bot status and observations | — |
| say | implemented | low | Send a safe chat message | — |
| look_around | implemented | low | Refresh nearby observations | — |
| explore_nearby | implemented | low | Scout nearby terrain | — |
| stop | implemented | low | Stop all movement | — |
| jump | implemented | low | Perform one jump | — |
| look_at_player | implemented | low | Look toward a player | — |
| follow_player | implemented | low | Follow a player | — |
| come_here | implemented | low | Navigate to a player | — |
| navigate_to_block_type | implemented | low | Move near a target block type | target_block_in_radius |
| acquire_blocks | implemented | medium | Collect allowlisted blocks | target_block_in_radius |
| recover_position | planned | medium | Escape stuck/clipped position | — |
| return_to_surface | planned | medium | Navigate upward to surface | bot_is_underground |
| return_to_known_position | planned | medium | Navigate to saved position | waypoint_exists |
| set_home_position | planned | low | Record current pos as home | — |
| mark_waypoint | planned | low | Save named waypoint | — |
| list_waypoints | planned | low | Return saved waypoints | — |
| return_to_waypoint | planned | medium | Navigate to named waypoint | waypoint_exists |

### Sensing

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| check_inventory | planned | low | Structured inventory summary | — |
| check_time_of_day | planned | low | Current time and day/night flag | — |
| check_light_level | planned | low | Light level at bot position | — |
| check_biome | planned | low | Biome at bot position | — |
| scan_for_hostiles | planned | low | List nearby hostile entities | — |
| scan_for_passive_mobs | planned | low | List nearby passive mobs | — |
| scan_for_chests | planned | low | Locate nearby chests | — |
| scan_for_specific_block | planned | low | Locate a specific block type | — |
| scan_for_liquids | planned | low | Detect water or lava nearby | — |
| scan_for_structures | planned | low | Detect nearby structures | — |

### Movement / Positioning

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| find_safe_workspace | planned | low | Find flat safe work area | — |
| dig_staircase | planned | medium | Dig 1x2 staircase down | has_pickaxe |
| pillar_up | planned | medium | Place blocks to rise | has_pillar_material |
| bridge_gap | planned | high | Bridge a horizontal gap | has_bridge_material |
| place_block_in_direction | planned | medium | Place block in a direction | has_block_in_inventory |
| mlg_water_bucket | planned | high | Place water mid-fall | has_water_bucket, bot_is_falling |
| enter_boat | planned | medium | Board nearby boat | boat_nearby |
| exit_boat | planned | low | Dismount boat | bot_in_boat |
| set_sneak | planned | low | Toggle sneak | — |
| set_sprint | planned | low | Toggle sprint | — |

### Generic Placement

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| place_crafting_table | implemented | low | Place crafting table from inventory | has_crafting_table_in_inventory |
| place_block | planned | medium | Place any held block | has_block_in_inventory |
| place_furnace | implemented | low | Place furnace | has_furnace_in_inventory |
| place_torch | planned | low | Place torch on surface | has_torch_in_inventory |
| place_chest | planned | low | Place chest | has_chest_in_inventory |
| place_bed | planned | medium | Place bed | has_bed_in_inventory |
| place_boat | planned | low | Place boat on water | has_boat_in_inventory, water_nearby |
| place_water | planned | high | Pour water from bucket | has_water_bucket |
| place_lava | planned | critical | Pour lava from bucket | has_lava_bucket |

### Crafting

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| craft_planks | implemented | low | Craft planks from logs | has_logs_or_stems |
| craft_sticks | implemented | low | Craft sticks from planks | has_planks |
| craft_crafting_table | implemented | low | Craft crafting table | has_4_planks |
| craft_wooden_pickaxe | implemented | low | Craft wooden pickaxe | has_nearby_crafting_table, has_3_planks, has_2_sticks |
| craft_stone_pickaxe | implemented | low | Craft stone pickaxe | has_nearby_crafting_table, has_3_cobblestone, has_2_sticks |
| craft_item | implemented | low | Allowlisted generic craft | crafting_table_nearby_if_needed |
| craft_furnace | implemented | low | Craft furnace | has_nearby_crafting_table, has_8_cobblestone |
| craft_torches | implemented | low | Craft torches | has_coal, has_sticks |
| craft_chest | implemented | low | Craft chest | has_nearby_crafting_table, has_8_planks |
| craft_shield | implemented | low | Craft shield | has_nearby_crafting_table, has_planks, has_iron_ingot |
| craft_bucket | implemented | low | Craft iron bucket | has_nearby_crafting_table, has_3_iron_ingots |
| craft_iron_pickaxe | implemented | low | Craft iron pickaxe | has_nearby_crafting_table, has_3_iron_ingots, has_2_sticks |
| craft_iron_sword | implemented | low | Craft iron sword | has_nearby_crafting_table, has_2_iron_ingots, has_1_stick |
| craft_iron_armor | implemented | low | Craft and equip iron armor pieces by priority | has_nearby_crafting_table, has_iron_ingots_for_at_least_one_piece |
| craft_bow | planned | low | Craft bow | has_nearby_crafting_table, has_3_sticks, has_3_string |
| craft_arrows | planned | low | Craft arrows | has_flint, has_sticks, has_feather |
| craft_flint_and_steel | planned | medium | Craft flint and steel | has_nearby_crafting_table, has_iron_ingot, has_flint |
| craft_boat | planned | low | Craft boat | has_nearby_crafting_table, has_5_planks |
| craft_bed | planned | low | Craft bed | has_nearby_crafting_table, has_3_planks, has_3_wool |
| craft_blaze_powder | planned | low | Craft blaze powder | has_blaze_rod |
| craft_eyes_of_ender | planned | medium | Craft Eyes of Ender | has_ender_pearls, has_blaze_powder |
| craft_diamond_pickaxe | planned | low | Craft diamond pickaxe | has_nearby_crafting_table, has_3_diamonds, has_2_sticks |
| craft_diamond_sword | planned | low | Craft diamond sword | has_nearby_crafting_table, has_2_diamonds, has_1_stick |
| craft_diamond_armor | planned | low | Craft full diamond armor | has_nearby_crafting_table, has_24_diamonds |

### Resource Acquisition

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| collect_wood | implemented | low | Collect logs or stems | — |
| mine_stone | implemented | medium | Mine stone for cobblestone | has_pickaxe, health_gte_10 |
| mine_coal | implemented | medium | Mine coal ore | has_pickaxe |
| mine_iron_ore | implemented | medium | Mine iron ore | has_stone_pickaxe_or_better |
| mine_diamond_ore | planned | high | Mine diamond ore | has_iron_pickaxe_or_better |
| mine_redstone | planned | medium | Mine redstone ore | has_iron_pickaxe_or_better |
| mine_gold_ore | planned | medium | Mine gold ore | has_iron_pickaxe_or_better |
| mine_gravel | planned | low | Mine gravel for flint | — |
| collect_flint | planned | low | Collect flint from gravel | — |
| collect_sand | planned | low | Collect sand | — |
| collect_water | planned | medium | Fill bucket from water source | has_empty_bucket, water_source_nearby |
| collect_lava | planned | critical | Fill bucket from lava source | has_empty_bucket, lava_source_nearby |
| collect_obsidian | planned | high | Mine obsidian | has_diamond_pickaxe |
| collect_food | planned | medium | Hunt or harvest food | — |

### Furnace / Smelting

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| smelt_item | partial | low | Smelt allowlisted item in furnace | has_furnace_nearby, has_fuel |
| smelt_iron | partial | low | Smelt raw iron to ingots | has_furnace_nearby, has_raw_iron, has_fuel |
| smelt_food | planned | low | Cook raw food | has_furnace_nearby, has_raw_food, has_fuel |
| smelt_gold | planned | low | Smelt raw gold to ingots | has_furnace_nearby, has_raw_gold, has_fuel |

### Inventory / Equipment / Containers

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| eat_food | implemented | low | Eat food to recover hunger | has_food_in_inventory |
| drop_item | planned | medium | Drop item from inventory | — |
| equip_armor | planned | low | Equip best available armor | — |
| equip_gold_armor | planned | medium | Equip gold armor (Nether) | has_gold_armor_in_inventory |
| equip_tool | planned | low | Equip specific tool | — |
| equip_best_tool | planned | low | Equip best tool for task | — |
| equip_best_weapon | planned | low | Equip best weapon | — |
| equip_best_armor | planned | low | Equip best armor | — |
| select_hotbar_slot | planned | low | Move item to hotbar slot | — |
| open_chest | planned | low | Open nearby chest | chest_nearby |
| loot_chest | planned | medium | Take items from chest | chest_nearby |
| deposit_items | planned | medium | Place items in chest | chest_nearby_open |
| withdraw_items | planned | medium | Take items from chest | chest_nearby_open |

### Survival

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| flee | implemented | medium | Move away from danger | — |
| retreat_from_combat | planned | medium | Disengage and move to safety | — |
| sleep_if_possible | planned | low | Sleep in bed at night | bed_nearby, is_night, no_hostiles |
| set_spawn_with_bed | planned | low | Set spawn with bed | bed_nearby |
| build_emergency_shelter | planned | high | Place emergency walls and roof | has_shelter_material |
| avoid_hazard | planned | medium | Step away from nearby hazard | — |
| escape_liquid | planned | high | Swim out of water or lava | — |
| handle_stuck | planned | medium | Break block or strafe to unstick | — |

### Death / Recovery

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| recover_death_items | planned | high | Navigate to death location to retrieve items | death_location_known |
| abandon_death_recovery | planned | low | Give up on death recovery | — |
| return_to_spawn_or_home | planned | medium | Navigate to home or world spawn | — |

### Combat

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| attack_mob | planned | high | Attack specific mob | has_weapon_or_fists |
| attack_nearest_hostile | planned | high | Attack nearest hostile | hostile_nearby |
| kill_passive_mob | planned | medium | Kill passive mob for drops | passive_mob_nearby |
| kill_blaze | planned | critical | Kill Blaze in Nether Fortress | in_nether_fortress, has_weapon |
| kill_enderman | planned | high | Kill Enderman for pearl | has_sword |
| block_with_shield | planned | high | Raise shield to block hit | has_shield |
| shoot_bow | planned | high | Shoot bow at target | has_bow, has_arrows |
| charge_bow | planned | medium | Fully draw bow | has_bow |
| deflect_ghast_fireball | planned | critical | Hit fireball back to Ghast | in_nether, fireball_incoming |
| kite_mob | planned | high | Move-and-hit a mob | has_weapon, hostile_nearby |
| throw_ender_pearl | planned | high | Teleport with Ender Pearl | has_ender_pearl |

### Nether Portal

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| find_lava_pool | planned | high | Locate lava pool for portal | — |
| build_nether_portal | planned | high | Place obsidian portal frame | has_10_obsidian |
| cast_nether_portal | planned | high | Cast portal with buckets | has_lava_bucket, has_water_bucket |
| light_nether_portal | planned | high | Light portal with flint and steel | portal_frame_complete, has_flint_and_steel |
| enter_nether | planned | critical | Step into lit portal | portal_lit_nearby |
| leave_nether | planned | critical | Return through Nether-side portal | in_nether, portal_nearby |
| return_to_portal | planned | high | Navigate to nearest portal | portal_location_known |

### Nether Progression

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| navigate_nether_safely | planned | critical | Move through Nether avoiding hazards | in_nether |
| avoid_opening_chests_near_piglins | planned | high | Override chest opens near Piglins | in_nether |
| find_nether_fortress | planned | critical | Search for Nether Fortress | in_nether |
| find_bastion_or_piglins | planned | high | Locate Bastion or Piglins | in_nether |
| barter_with_piglins | planned | high | Trade gold with Piglins | has_gold_armor, has_gold_ingot, piglin_nearby |
| collect_blaze_rods | planned | critical | Kill Blazes and collect rods | in_nether_fortress, has_weapon |
| collect_ender_pearls | planned | high | Obtain ender pearls | has_weapon_or_gold_ingots |
| retreat_from_nether_danger | planned | critical | Flee Nether threats | in_nether |
| equip_gold_armor | planned | medium | Equip gold armor before Piglin areas | has_gold_armor_in_inventory |

### Stronghold / End Portal

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| throw_eye_of_ender | planned | medium | Throw Eye to trace stronghold | has_ender_eye |
| locate_stronghold_step | planned | high | Move toward stronghold | stronghold_direction_known |
| dig_staircase_to_stronghold | planned | high | Mine down to stronghold | above_stronghold, has_pickaxe |
| scan_for_end_portal_room | planned | high | Search stronghold for portal room | in_stronghold |
| activate_end_portal | planned | critical | Fill portal frame with Eyes | has_ender_eyes_sufficient, portal_room_found |
| enter_end | planned | critical | Jump into End Portal | end_portal_active |

### End Fight

| Action | Status | Risk | Description | Preconditions |
|---|---|---|---|---|
| end_safe_landing | planned | critical | Land without fall damage | in_the_end |
| equip_pumpkin_head | planned | high | Equip pumpkin to prevent Enderman aggro | has_carved_pumpkin |
| look_down_around_endermen | planned | medium | Avoid Enderman aggro via gaze | in_the_end |
| scan_end_crystals | planned | high | Locate all active End Crystals | in_the_end |
| destroy_end_crystal | planned | high | Break one End Crystal | has_ranged_or_melee_weapon |
| destroy_caged_end_crystal | planned | high | Break caged End Crystal | has_pickaxe, has_ranged_weapon |
| destroy_nearby_end_crystals | planned | high | Destroy all reachable crystals | has_ranged_or_melee_weapon |
| attack_perched_dragon | planned | critical | Melee dragon while perched | has_sword, dragon_is_perched |
| attack_dragon_with_bow | planned | critical | Shoot dragon while circling | has_bow, has_arrows |
| use_bed_bomb | planned | critical | Detonate bed under dragon | has_bed, dragon_is_perched |
| avoid_bed_explosion | planned | critical | Move away before bed explodes | in_the_end |
| dragon_phase_crystals | planned | critical | Phase: destroy all crystals | in_the_end, crystals_remaining |
| dragon_phase_circle | planned | critical | Phase: shoot circling dragon | has_bow, has_arrows |
| dragon_phase_perch | planned | critical | Phase: attack perched dragon | has_sword_or_bed, dragon_is_perched |
| fight_dragon_phase | planned | critical | Composite dragon fight driver | in_the_end |
| return_to_overworld_via_end_portal | planned | critical | Exit through End Portal | dragon_dead, exit_portal_open |
| finish_dragon_fight | planned | critical | Full dragon fight sequence | in_the_end |

## 13. Next Features

Good next steps:

- add safer navigation back to a placed crafting table after mining
- add pathfinding goals with timeouts
- add a web dashboard for status, memory, and speech
- add player proximity checks before movement actions
- add a local TTS watcher using Piper
- add VTube Studio expression or hotkey integration
- add richer memory search over SQLite
- add pytest tests once the API stabilizes
- add Docker or scripts for repeatable startup

Start with private local testing before adding any autonomous behavior.

## 14. Connecting the personality engine

The stream loop can forward each tick result to a separate FastAPI personality
service as a compact `BrainTickEvent` JSON.  Publishing is best-effort — if the
personality service is offline or slow the gameplay loop continues unaffected.

Start the personality service in one terminal:

```bash
cd ai-vtuber-personality-engine
uv run vtuber-personality serve --host 127.0.0.1 --port 8010
```

Start the stream loop with the `--personality-url` flag in another terminal:

```bash
cd ai-vtuber-mc
uv run python scripts/run_stream_loop.py \
  --api-url http://127.0.0.1:8000 \
  --mission "Beat Minecraft while playing naturally and surviving." \
  --user AI_VTuber \
  --max-ticks-per-batch 25 \
  --tick-delay-sec 1 \
  --personality-url http://127.0.0.1:8010/events/tick
```

The startup banner confirms the personality endpoint:

```text
  personality: http://127.0.0.1:8010/events/tick  timeout=0.75s
```

When disabled (no URL provided):

```text
  personality: disabled
```

**Environment variable equivalents** (useful for running without CLI flags):

| Variable | Default | Purpose |
|---|---|---|
| `PERSONALITY_ENGINE_URL` | `""` | Personality event endpoint URL |
| `PERSONALITY_ENGINE_TIMEOUT_SEC` | `0.75` | Max seconds to wait for the service |
| `PERSONALITY_ENGINE_ENABLED` | `false` | Set to `true` to enable when URL comes from env |

When the URL comes from `--personality-url` on the CLI, `PERSONALITY_ENGINE_ENABLED`
is ignored — the CLI flag always enables publishing.  When the URL comes only from
`PERSONALITY_ENGINE_URL`, you must also set `PERSONALITY_ENGINE_ENABLED=true`.

**Event shape** — each tick sends:

```json
{
  "tick_id": 11,
  "run_id": "20260519T120000Z",
  "mission": "Beat Minecraft…",
  "objective": "mine_coal",
  "action": "mine_coal",
  "args": {"count": 1, "radius": 8},
  "ok": true,
  "failure": null,
  "stop": "collected_requested",
  "error": null,
  "collected": 1,
  "reason": "Need coal for fuel. Objective: mine_coal",
  "verifier": {"success": true},
  "inventory": {"coal": 1},
  "position": {"x": 10, "y": 64, "z": 20},
  "health": 20,
  "hunger": 18,
  "raw": {
    "planner": {"mode": "hybrid", "llm_latency_sec": 0.5},
    "result": {"ok": true, "action": "mine_coal", "result": {…}}
  }
}
```

Long strings are truncated to 1 000 characters.  `raw.planner` and `raw.result`
are capped at 4 096 bytes each and replaced with `{"_truncated": true, "_size_bytes": N}`
when they exceed the limit.

**Running the publisher tests:**

```bash
cd ai-vtuber-mc
uv sync
uv run pytest -q
```
