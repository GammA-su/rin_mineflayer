param(
  [string]$BridgeUrl = $(if ($env:MINEFLAYER_BRIDGE_URL) { $env:MINEFLAYER_BRIDGE_URL } else { "http://localhost:3001" }),
  [string]$LogDir = "out/smoke_logs",
  [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"
$Tier = "tier1_tools"
$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$OutDir = Join-Path $LogDir $RunId
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Invoke-BodyAction {
  param(
    [int]$Index,
    [string]$Action,
    [hashtable]$Args = @{},
    [bool]$Critical = $true
  )

  $request = @{ action = $Action; args = $Args }
  $json = $request | ConvertTo-Json -Depth 20 -Compress
  $response = $null
  $httpError = $null

  try {
    $raw = Invoke-WebRequest -Uri "$BridgeUrl/action" -Method Post -ContentType "application/json" -Body $json -TimeoutSec $TimeoutSec
    $response = $raw.Content | ConvertFrom-Json
  } catch {
    $httpError = $_.Exception.Message
    if ($_.Exception.Response) {
      try {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        $content = $reader.ReadToEnd()
        if ($content) { $response = $content | ConvertFrom-Json }
      } catch {}
    }
    if (-not $response) {
      $response = [pscustomobject]@{ ok = $false; action = $Action; result = @{ failure_type = "http_error" }; error = $httpError }
    }
  }

  $record = [pscustomobject]@{
    tier = $Tier
    index = $Index
    timestamp = (Get-Date).ToString("o")
    request = $request
    response = $response
  }
  $safeAction = $Action -replace "[^A-Za-z0-9_-]", "_"
  $record | ConvertTo-Json -Depth 40 | Set-Content -Path (Join-Path $OutDir ("{0:00}_{1}.json" -f $Index, $safeAction)) -Encoding UTF8

  $okText = if ($response.ok) { "OK" } else { "FAIL" }
  $errorText = if ($response.error) { $response.error } else { "" }
  $resultText = ($response.result | ConvertTo-Json -Depth 8 -Compress)
  if ($resultText.Length -gt 300) { $resultText = $resultText.Substring(0, 300) + "..." }
  Write-Host ("[{0}] {1} action={2} error={3} result={4}" -f $Tier, $okText, $response.action, $errorText, $resultText)

  if ($Critical -and -not $response.ok) {
    throw "Critical smoke failure in $Tier action '$Action': $errorText"
  }
  return $response
}

$steps = @(
  @{ action = "status"; args = @{} },
  @{ action = "collect_wood"; args = @{ count = 4 } },
  @{ action = "craft_planks"; args = @{} },
  @{ action = "craft_sticks"; args = @{} },
  @{ action = "craft_crafting_table"; args = @{} },
  @{ action = "find_safe_workspace"; args = @{ radius = 16 } },
  @{ action = "place_crafting_table"; args = @{} },
  @{ action = "craft_wooden_pickaxe"; args = @{} },
  @{ action = "mine_stone"; args = @{ count = 3 } },
  @{ action = "craft_stone_pickaxe"; args = @{} }
)

for ($i = 0; $i -lt $steps.Count; $i++) {
  Invoke-BodyAction -Index ($i + 1) -Action $steps[$i].action -Args $steps[$i].args -Critical $true | Out-Null
}

Write-Host "Tier 1 smoke complete. Logs: $OutDir"
