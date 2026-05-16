param(
  [string]$BridgeUrl = $(if ($env:MINEFLAYER_BRIDGE_URL) { $env:MINEFLAYER_BRIDGE_URL } else { "http://localhost:3001" }),
  [string]$LogDir = "out/smoke_logs",
  [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"
$Tier = "tier2_iron"
$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$OutDir = Join-Path $LogDir $RunId
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Invoke-BodyAction {
  param([int]$Index, [string]$Action, [hashtable]$Args = @{}, [bool]$Critical = $true)
  $request = @{ action = $Action; args = $Args }
  $json = $request | ConvertTo-Json -Depth 20 -Compress
  $response = $null
  try {
    $raw = Invoke-WebRequest -Uri "$BridgeUrl/action" -Method Post -ContentType "application/json" -Body $json -TimeoutSec $TimeoutSec
    $response = $raw.Content | ConvertFrom-Json
  } catch {
    if ($_.Exception.Response) {
      try {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        $content = $reader.ReadToEnd()
        if ($content) { $response = $content | ConvertFrom-Json }
      } catch {}
    }
    if (-not $response) {
      $response = [pscustomobject]@{ ok = $false; action = $Action; result = @{ failure_type = "http_error" }; error = $_.Exception.Message }
    }
  }
  $record = [pscustomobject]@{ tier = $Tier; index = $Index; timestamp = (Get-Date).ToString("o"); request = $request; response = $response }
  $safeAction = $Action -replace "[^A-Za-z0-9_-]", "_"
  $record | ConvertTo-Json -Depth 40 | Set-Content -Path (Join-Path $OutDir ("{0:00}_{1}.json" -f $Index, $safeAction)) -Encoding UTF8
  $okText = if ($response.ok) { "OK" } else { "FAIL" }
  $resultText = ($response.result | ConvertTo-Json -Depth 8 -Compress)
  if ($resultText.Length -gt 300) { $resultText = $resultText.Substring(0, 300) + "..." }
  Write-Host ("[{0}] {1} action={2} error={3} result={4}" -f $Tier, $okText, $response.action, $response.error, $resultText)
  if ($Critical -and -not $response.ok) { throw "Critical smoke failure in $Tier action '$Action': $($response.error)" }
  return $response
}

$steps = @(
  @{ action = "status"; args = @{} },
  @{ action = "craft_furnace"; args = @{} },
  @{ action = "place_furnace"; args = @{} },
  @{ action = "mine_coal"; args = @{ count = 4 } },
  @{ action = "mine_iron_ore"; args = @{ count = 3 } },
  @{ action = "smelt_iron"; args = @{ count = 3 } },
  @{ action = "craft_shield"; args = @{} },
  @{ action = "craft_bucket"; args = @{} },
  @{ action = "craft_iron_pickaxe"; args = @{} },
  @{ action = "equip_best_armor"; args = @{} },
  @{ action = "equip_best_tool"; args = @{ block = "stone" } },
  @{ action = "equip_best_weapon"; args = @{} }
)

for ($i = 0; $i -lt $steps.Count; $i++) {
  Invoke-BodyAction -Index ($i + 1) -Action $steps[$i].action -Args $steps[$i].args -Critical $true | Out-Null
}

Write-Host "Tier 2 smoke complete. Logs: $OutDir"
