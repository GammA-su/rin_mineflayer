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

## 12. Next Features

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
