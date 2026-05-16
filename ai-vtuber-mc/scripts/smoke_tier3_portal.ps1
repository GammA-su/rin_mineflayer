param(
  [string]$BridgeUrl = $(if ($env:MINEFLAYER_BRIDGE_URL) { $env:MINEFLAYER_BRIDGE_URL } else { "http://localhost:3001" }),
  [string]$LogDir = "out/smoke_logs",
  [int]$TimeoutSec = 240
)

$ErrorActionPreference = "Stop"
$Tier = "tier3_portal"
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

Invoke-BodyAction -Index 1 -Action "collect_water" -Args @{} -Critical $true | Out-Null
Invoke-BodyAction -Index 2 -Action "collect_lava" -Args @{} -Critical $true | Out-Null
Invoke-BodyAction -Index 3 -Action "craft_flint_and_steel" -Args @{} -Critical $true | Out-Null

$obsidian = Invoke-BodyAction -Index 4 -Action "collect_obsidian" -Args @{ count = 10 } -Critical $false
if (-not $obsidian.ok) {
  Write-Host "[tier3_portal] collect_obsidian failed, trying cast_nether_portal alternative."
  Invoke-BodyAction -Index 5 -Action "cast_nether_portal" -Args @{} -Critical $true | Out-Null
} else {
  Write-Host "[tier3_portal] collect_obsidian succeeded, skipping cast_nether_portal alternative."
}

Invoke-BodyAction -Index 6 -Action "build_nether_portal" -Args @{} -Critical $true | Out-Null
Invoke-BodyAction -Index 7 -Action "light_nether_portal" -Args @{} -Critical $true | Out-Null
Invoke-BodyAction -Index 8 -Action "enter_nether" -Args @{} -Critical $true | Out-Null
Invoke-BodyAction -Index 9 -Action "return_to_portal" -Args @{} -Critical $true | Out-Null

Write-Host "Tier 3 smoke complete. Logs: $OutDir"
